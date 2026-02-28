from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
import unicodedata

from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import redirect
from django.http import Http404
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView, UpdateView

from compras.models import Compra, CompraEvento, Produto
from core.services.permissoes import GroupRequiredMixin
from core.services.paginacao import get_pagination_params

from estoque.forms import (
    ContagemRapidaForm,
    ContagemRapidaItemFormSet,
    ImportCustoEstoqueForm,
    MovimentoForm,
    MovimentoItemFormSet,
    ProdutoEstoqueForm,
    SaidaOperacionalForm,
    SaidaOperacionalItemFormSet,
    TransferenciaForm,
    TransferenciaItemFormSet,
)
from estoque.models import (
    ProdutoEstoque,
    AlertaEstoque,
    StatusAlerta,
    EstoqueMovimento,
    ProdutoEstoqueUnidade,
    SaidaOperacionalEstoque,
    TransferenciaEstoque,
    UnidadeLoja,
)
from estoque.services.contagem_service import (
    aplicar_contagem_rapida,
    garantir_estoque_unidades_produto,
)
from estoque.services.estoque_service import registrar_entrada, registrar_saida, registrar_ajuste
from estoque.services.saida_operacional_service import registrar_saida_operacional_lote
from estoque.services.integracao_compras import dar_entrada_por_compra
from estoque.services.statistics_service import EstoqueStatisticsService
from estoque.services.transferencias_service import transferir_lote_entre_unidades


class EstoqueReadOnlyAccessMixin(GroupRequiredMixin):
    required_groups = ("admin/gestor", "compras/estoque", "estoquista", "vendedor")


def _is_admin_autorizado(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(
        name__in=("admin/gestor", "compras/estoque", "estoquista")
    ).exists()


class EstoqueManageAccessMixin(GroupRequiredMixin):
    required_groups = ("admin/gestor", "compras/estoque", "estoquista")


def _garantir_configs_estoque_produtos_ativos() -> None:
    existentes = set(ProdutoEstoque.objects.values_list("produto_id", flat=True))
    faltantes = list(
        Produto.objects.filter(ativo=True).exclude(id__in=existentes).only("id")
    )
    if faltantes:
        ProdutoEstoque.objects.bulk_create(
            [ProdutoEstoque(produto=produto) for produto in faltantes],
            ignore_conflicts=True,
        )


class EstoqueDashboardView(EstoqueReadOnlyAccessMixin, TemplateView):
    template_name = "estoque/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["alertas_abertos"] = (
            AlertaEstoque.objects.select_related("produto")
            .filter(status=StatusAlerta.ABERTO)
            .order_by("-criado_em")
        )
        ctx["produtos_baixos"] = (
            ProdutoEstoque.objects.select_related("produto")
            .filter(saldo_atual__lte=F("estoque_minimo"))
            .order_by("produto__nome")
        )[:50]
        ctx["compras_pendentes_recebimento"] = (
            Compra.objects.select_related("fornecedor")
            .prefetch_related("itens")
            .filter(status=Compra.StatusChoices.APROVADA)
            .order_by("data_compra", "id")
        )[:10]
        return ctx


class ProdutoEstoqueListView(EstoqueReadOnlyAccessMixin, ListView):
    model = ProdutoEstoque
    template_name = "estoque/produtoestoque_list.html"
    context_object_name = "configs"

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = (
            ProdutoEstoque.objects.select_related("produto")
            .prefetch_related("produto__estoque_unidades")
            .order_by("produto__nome")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(produto__nome__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        for cfg in ctx["configs"]:
            garantir_estoque_unidades_produto(cfg.produto)
            saldo_fm = "0.000"
            saldo_ml = "0.000"
            rows = ProdutoEstoqueUnidade.objects.filter(produto=cfg.produto)
            for row in rows:
                if row.unidade == UnidadeLoja.LOJA_1:
                    saldo_fm = str(row.saldo_atual)
                elif row.unidade == UnidadeLoja.LOJA_2:
                    saldo_ml = str(row.saldo_atual)
            cfg.saldo_fm = saldo_fm
            cfg.saldo_ml = saldo_ml
        return ctx


class EstoqueCompletoView(EstoqueReadOnlyAccessMixin, ListView):
    model = ProdutoEstoque
    template_name = "estoque/estoque_completo.html"
    context_object_name = "configs"

    def post(self, request, *args, **kwargs):
        if not _is_admin_autorizado(request.user):
            messages.error(
                request,
                "Somente os setores autorizados de estoque/gestao podem alterar custos de produtos.",
            )
            return redirect("estoque:estoque_completo")

        form = ImportCustoEstoqueForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Arquivo CSV inválido.")
            return redirect("estoque:estoque_completo")

        arquivo = form.cleaned_data["arquivo"]
        raw = arquivo.read()
        try:
            text = raw.decode("utf-8")
        except Exception:
            text = raw.decode("latin-1")

        sample = text[:4096]
        lines = text.splitlines()
        header_line = lines[0] if lines else ""
        delimiter = ";" if header_line.count(";") >= header_line.count(",") else ","

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        # Fallback: alguns CSVs chegam com header inteiro em uma coluna só.
        if reader.fieldnames and len(reader.fieldnames) == 1 and ";" in str(reader.fieldnames[0]):
            reader = csv.DictReader(io.StringIO(text), delimiter=";")
        atualizados = 0
        ignorados = 0
        for row in reader:
            normalized: dict[str, str] = {}
            for key, value in (row or {}).items():
                raw_key = str(key or "").strip().lower()
                ascii_key = (
                    unicodedata.normalize("NFKD", raw_key)
                    .encode("ascii", "ignore")
                    .decode("ascii")
                )
                ascii_key = ascii_key.replace(" ", "_")
                normalized[ascii_key] = value

            sku = (normalized.get("sku") or "").strip()
            if not sku:
                ignorados += 1
                continue

            # Compatível com layouts diferentes de planilha (incluindo gestao-estoque.csv).
            custo_medio_raw = (
                normalized.get("valor_utilizado")
                or normalized.get("custo_medio")
                or normalized.get("custo")
                or normalized.get("preco")
                or normalized.get("valor_de_venda")
                or normalized.get("valor_venda")
                or ""
            )
            custo_total_raw = (
                normalized.get("custo_total")
                or ""
            )
            reservado_raw = normalized.get("reservado") or ""
            disponivel_raw = (
                normalized.get("disponivel")
                or ""
            )

            def _to_dec(raw_val: str) -> Decimal:
                txt = str(raw_val or "").strip()
                if txt == "":
                    return Decimal("0")
                if "." in txt and "," in txt:
                    txt = txt.replace(".", "").replace(",", ".")
                elif "," in txt:
                    txt = txt.replace(",", ".")
                try:
                    return Decimal(txt)
                except (InvalidOperation, ValueError):
                    return Decimal("0")

            custo = _to_dec(custo_medio_raw)
            if custo <= 0:
                custo_total = _to_dec(custo_total_raw)
                quantidade = _to_dec(reservado_raw) + _to_dec(disponivel_raw)
                if custo_total > 0 and quantidade > 0:
                    custo = (custo_total / quantidade).quantize(Decimal("0.0001"))
            if custo < 0:
                ignorados += 1
                continue

            cfg = ProdutoEstoque.objects.select_related("produto").filter(produto__sku__iexact=sku).first()
            if not cfg:
                produto = Produto.objects.filter(sku__iexact=sku).first()
                if not produto:
                    ignorados += 1
                    continue
                cfg = ProdutoEstoque.objects.create(produto=produto)
            cfg.custo_medio = custo.quantize(Decimal("0.0001"))
            cfg.save(update_fields=["custo_medio", "atualizado_em"])
            atualizados += 1

        messages.success(
            request,
            f"Importação concluída. Custos atualizados: {atualizados}. Linhas ignoradas: {ignorados}.",
        )
        return redirect("estoque:estoque_completo")

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        _garantir_configs_estoque_produtos_ativos()
        qs = ProdutoEstoque.objects.select_related("produto").order_by("produto__nome")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(produto__nome__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        total_valor_fm = Decimal("0.00")
        total_valor_ml = Decimal("0.00")
        total_valor_geral = Decimal("0.00")
        for cfg in ctx["configs"]:
            garantir_estoque_unidades_produto(cfg.produto)
            rows = ProdutoEstoqueUnidade.objects.filter(produto=cfg.produto)
            cfg.saldo_fm = "0.000"
            cfg.saldo_ml = "0.000"
            saldo_fm_dec = Decimal("0.000")
            saldo_ml_dec = Decimal("0.000")
            for row in rows:
                if row.unidade == UnidadeLoja.LOJA_1:
                    cfg.saldo_fm = str(row.saldo_atual)
                    saldo_fm_dec = row.saldo_atual or Decimal("0.000")
                elif row.unidade == UnidadeLoja.LOJA_2:
                    cfg.saldo_ml = str(row.saldo_atual)
                    saldo_ml_dec = row.saldo_atual or Decimal("0.000")
            saldo_total_unidades = (saldo_fm_dec + saldo_ml_dec).quantize(Decimal("0.001"))
            if (cfg.saldo_atual or Decimal("0.000")) != saldo_total_unidades:
                cfg.saldo_atual = saldo_total_unidades
                cfg.save(update_fields=["saldo_atual", "atualizado_em"])
            custo = cfg.custo_medio or Decimal("0.0000")
            cfg.valor_fm = (saldo_fm_dec * custo).quantize(Decimal("0.01"))
            cfg.valor_ml = (saldo_ml_dec * custo).quantize(Decimal("0.01"))
            cfg.valor_total = ((cfg.saldo_atual or Decimal("0.000")) * custo).quantize(Decimal("0.01"))
            total_valor_fm += cfg.valor_fm
            total_valor_ml += cfg.valor_ml
            total_valor_geral += cfg.valor_total
        ctx["import_form"] = ImportCustoEstoqueForm()
        ctx["total_valor_fm"] = total_valor_fm.quantize(Decimal("0.01"))
        ctx["total_valor_ml"] = total_valor_ml.quantize(Decimal("0.01"))
        ctx["total_valor_geral"] = total_valor_geral.quantize(Decimal("0.01"))
        return ctx


class EstoqueAjusteRapidoView(EstoqueManageAccessMixin, View):
    @staticmethod
    def _to_dec(raw: str, scale: str) -> Decimal:
        txt = str(raw or "").strip()
        if txt == "":
            return Decimal("0").quantize(Decimal(scale))
        if "." in txt and "," in txt:
            txt = txt.replace(".", "").replace(",", ".")
        elif "," in txt:
            txt = txt.replace(",", ".")
        try:
            val = Decimal(txt)
        except (InvalidOperation, ValueError):
            val = Decimal("0")
        if val < 0:
            val = Decimal("0")
        return val.quantize(Decimal(scale))

    def post(self, request, *args, **kwargs):
        cfg = ProdutoEstoque.objects.select_related("produto").filter(pk=kwargs["pk"]).first()
        if not cfg:
            messages.error(request, "Item de estoque não encontrado.")
            return redirect("estoque:estoque_completo")

        custo_medio = self._to_dec(request.POST.get("custo_medio"), "0.0001")
        saldo_fm = self._to_dec(request.POST.get("saldo_fm"), "0.001")
        saldo_ml = self._to_dec(request.POST.get("saldo_ml"), "0.001")
        saldo_total = (saldo_fm + saldo_ml).quantize(Decimal("0.001"))

        unidade_fm, _ = ProdutoEstoqueUnidade.objects.get_or_create(produto=cfg.produto, unidade=UnidadeLoja.LOJA_1)
        unidade_ml, _ = ProdutoEstoqueUnidade.objects.get_or_create(produto=cfg.produto, unidade=UnidadeLoja.LOJA_2)
        unidade_fm.saldo_atual = saldo_fm
        unidade_ml.saldo_atual = saldo_ml
        unidade_fm.save(update_fields=["saldo_atual", "atualizado_em"])
        unidade_ml.save(update_fields=["saldo_atual", "atualizado_em"])

        cfg.custo_medio = custo_medio
        cfg.saldo_atual = saldo_total
        cfg.save(update_fields=["custo_medio", "saldo_atual", "atualizado_em"])

        messages.success(request, f"Ajuste rápido salvo para {cfg.produto.nome}.")
        return redirect("estoque:estoque_completo")


class ProdutoEstoqueUpdateView(EstoqueManageAccessMixin, UpdateView):
    model = ProdutoEstoque
    form_class = ProdutoEstoqueForm
    template_name = "estoque/produtoestoque_form.html"

    def get_success_url(self):
        messages.success(self.request, "Configuração de estoque atualizada.")
        return reverse("estoque:produtoestoque_list")


class MovimentoCreateView(EstoqueManageAccessMixin, TemplateView):
    template_name = "estoque/movimento_form.html"
    item_formset_prefix = "itens"

    def _build_forms(self):
        if self.request.method == "POST":
            form = MovimentoForm(self.request.POST)
            formset = MovimentoItemFormSet(self.request.POST, prefix=self.item_formset_prefix)
            return form, formset
        form = MovimentoForm(initial={"data_movimento": timezone.localdate()})
        formset = MovimentoItemFormSet(prefix=self.item_formset_prefix)
        return form, formset

    @staticmethod
    def _extract_items(formset):
        itens = []
        for f in formset:
            data = f.cleaned_data if hasattr(f, "cleaned_data") else {}
            if not data or data.get("DELETE"):
                continue
            produto = data.get("produto")
            quantidade = data.get("quantidade")
            if produto and quantidade:
                itens.append({"produto": produto, "quantidade": quantidade})
        return itens

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form, formset = kwargs.get("form"), kwargs.get("formset")
        if form is None or formset is None:
            form, formset = self._build_forms()
        ctx["form"] = form
        ctx["formset"] = formset
        return ctx

    def post(self, request, *args, **kwargs):
        form, formset = self._build_forms()
        if not form.is_valid() or not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        tipo = form.cleaned_data["tipo"]
        data_movimento = form.cleaned_data["data_movimento"]
        observacao = form.cleaned_data.get("observacao") or ""
        itens = self._extract_items(formset)

        if not itens:
            messages.error(request, "Informe pelo menos um produto com quantidade.")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        try:
            with transaction.atomic():
                for item in itens:
                    produto = item["produto"]
                    quantidade = item["quantidade"]
                    if tipo == "ENTRADA":
                        registrar_entrada(
                            produto=produto,
                            quantidade=quantidade,
                            data_movimento=data_movimento,
                            observacao=observacao,
                        )
                    elif tipo == "SAIDA":
                        registrar_saida(
                            produto=produto,
                            quantidade=quantidade,
                            data_movimento=data_movimento,
                            observacao=observacao,
                        )
                    else:
                        registrar_ajuste(
                            produto=produto,
                            quantidade=quantidade,
                            data_movimento=data_movimento,
                            observacao=observacao,
                        )
        except Exception as exc:
            messages.error(request, f"Erro ao registrar movimentos: {exc}")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        messages.success(request, f"{len(itens)} movimento(s) registrado(s) com sucesso.")
        return redirect("estoque:dashboard")


class MovimentoListView(EstoqueManageAccessMixin, ListView):
    model = EstoqueMovimento
    template_name = "estoque/movimento_list.html"
    context_object_name = "movimentos"

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = EstoqueMovimento.objects.select_related("produto").order_by("-data_movimento", "-id")
        produto_id = (self.request.GET.get("produto") or "").strip()
        if produto_id.isdigit():
            qs = qs.filter(produto_id=int(produto_id))
        return qs


class EntradaPorCompraView(EstoqueManageAccessMixin, TemplateView):
    """
    Ação simples: cria entradas para os itens da compra.
    """
    template_name = "estoque/entrada_por_compra.html"

    def post(self, request, *args, **kwargs):
        compra_id = kwargs["compra_id"]
        compra = Compra.objects.get(pk=compra_id)
        criados = dar_entrada_por_compra(compra)
        messages.success(request, f"Entradas criadas no estoque: {criados}")
        return redirect("compras:compra_detail", pk=compra_id)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        compra_id = kwargs["compra_id"]
        ctx["compra"] = Compra.objects.select_related("fornecedor").prefetch_related("itens__produto").get(pk=compra_id)
        return ctx


class RecebimentoCompraListView(EstoqueManageAccessMixin, ListView):
    model = Compra
    template_name = "estoque/recebimento_list.html"
    context_object_name = "compras"

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = (
            Compra.objects.select_related("fornecedor", "aprovado_por")
            .prefetch_related("itens")
            .filter(status=Compra.StatusChoices.APROVADA)
            .order_by("data_compra", "id")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(fornecedor__nome__icontains=q)
        return qs


class RecebimentoCompraDetailView(EstoqueManageAccessMixin, DetailView):
    model = Compra
    template_name = "estoque/recebimento_detail.html"
    context_object_name = "compra"

    def get_queryset(self):
        return (
            Compra.objects.select_related("fornecedor", "aprovado_por")
            .prefetch_related("itens__produto")
            .filter(status=Compra.StatusChoices.APROVADA)
        )


class ConfirmarRecebimentoCompraView(EstoqueManageAccessMixin, View):
    def post(self, request, *args, **kwargs):
        compra = Compra.objects.filter(pk=kwargs["pk"]).select_related("fornecedor").prefetch_related("itens__produto").first()
        if not compra:
            raise Http404("Compra nao encontrada.")

        if compra.status != Compra.StatusChoices.APROVADA:
            messages.error(request, "Somente compras APROVADAS podem ser recebidas no estoque.")
            return redirect("estoque:recebimento_list")

        observacao = (request.POST.get("observacao_conferencia") or "").strip()
        with transaction.atomic():
            compra.status = Compra.StatusChoices.RECEBIDA
            compra.recebido_em = timezone.now()
            compra.recebido_por = request.user if request.user.is_authenticated else None
            compra.save(update_fields=["status", "recebido_em", "recebido_por"])

            criados = dar_entrada_por_compra(compra)
            detalhe = "Recebimento registrado via modulo de estoque apos conferencia."
            if observacao:
                detalhe = f"{detalhe} Observacao: {observacao}"
            CompraEvento.objects.create(
                compra=compra,
                tipo=CompraEvento.TipoEvento.RECEBIMENTO,
                usuario=(request.user if request.user.is_authenticated else None),
                detalhe=detalhe,
            )

        messages.success(
            request,
            f"Recebimento da compra #{compra.id} confirmado no estoque. Entradas geradas: {criados}.",
        )
        return redirect("estoque:recebimento_list")


class IndicadoresEstoqueView(EstoqueManageAccessMixin, TemplateView):
    template_name = "estoque/indicadores.html"

    @staticmethod
    def _parse_positive_int(raw: str, default: int) -> int:
        value = (raw or "").strip()
        if not value.isdigit():
            return default
        parsed = int(value)
        return parsed if parsed > 0 else default

    def get(self, request, *args, **kwargs):
        dias_estoque = self._parse_positive_int(request.GET.get("dias_estoque"), 365)
        meses_giro = self._parse_positive_int(request.GET.get("meses_giro"), 12)
        indicadores = EstoqueStatisticsService.relatorio_geral(
            dias_estoque=dias_estoque,
            meses_giro=meses_giro,
        )
        if request.GET.get("format") == "json":
            return JsonResponse(
                {
                    "dias_estoque": dias_estoque,
                    "meses_giro": meses_giro,
                    "total_produtos": len(indicadores),
                    "itens": indicadores,
                }
            )
        self._cached_payload = {
            "dias_estoque": dias_estoque,
            "meses_giro": meses_giro,
            "indicadores": indicadores,
        }
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(getattr(self, "_cached_payload", {}))
        return ctx


class TransferenciaCreateView(EstoqueManageAccessMixin, TemplateView):
    template_name = "estoque/transferencia_form.html"
    item_formset_prefix = "itens"

    def _build_forms(self):
        if self.request.method == "POST":
            form = TransferenciaForm(self.request.POST)
            formset = TransferenciaItemFormSet(self.request.POST, prefix=self.item_formset_prefix)
            return form, formset
        form = TransferenciaForm(initial={"data_transferencia": timezone.localdate()})
        formset = TransferenciaItemFormSet(prefix=self.item_formset_prefix)
        return form, formset

    @staticmethod
    def _extract_items(formset):
        itens = []
        for f in formset:
            data = f.cleaned_data if hasattr(f, "cleaned_data") else {}
            if not data or data.get("DELETE"):
                continue
            produto = data.get("produto")
            quantidade = data.get("quantidade")
            if produto and quantidade:
                itens.append({"produto": produto, "quantidade": quantidade})
        return itens

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = kwargs.get("form")
        formset = kwargs.get("formset")
        if form is None or formset is None:
            form, formset = self._build_forms()
        ctx["form"] = form
        ctx["formset"] = formset
        historico = (
            TransferenciaEstoque.objects.select_related("produto", "usuario")
            .order_by("-data_transferencia", "-id")[:120]
        )
        grupos = {}
        for t in historico:
            chave = t.lote_referencia or f"IND-{t.id}"
            if chave not in grupos:
                grupos[chave] = {
                    "lote_referencia": chave,
                    "data_transferencia": t.data_transferencia,
                    "unidade_origem": t.get_unidade_origem_display(),
                    "unidade_destino": t.get_unidade_destino_display(),
                    "usuario": (t.usuario.username if t.usuario else "-"),
                    "observacao": t.observacao,
                    "itens": [],
                }
            grupos[chave]["itens"].append(t)
        ctx["historico_grupos"] = list(grupos.values())
        return ctx

    def post(self, request, *args, **kwargs):
        form, formset = self._build_forms()
        if not form.is_valid() or not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, formset=formset))
        itens = self._extract_items(formset)
        if not itens:
            messages.error(request, "Informe pelo menos um produto com quantidade para transferir.")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        try:
            result = transferir_lote_entre_unidades(
                itens=itens,
                unidade_origem=form.cleaned_data["unidade_origem"],
                unidade_destino=form.cleaned_data["unidade_destino"],
                usuario=request.user,
                data_transferencia=form.cleaned_data["data_transferencia"],
                observacao=form.cleaned_data.get("observacao") or "",
            )
        except Exception as exc:
            messages.error(request, f"Erro ao transferir lote: {exc}")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        messages.success(
            request,
            (
                "Transferencia em lote registrada com sucesso. "
                f"Lote: {result.lote_referencia} | itens: {result.total_itens}"
            ),
        )
        return redirect("estoque:transferencia_create")


class ContagemRapidaView(EstoqueManageAccessMixin, TemplateView):
    template_name = "estoque/contagem_rapida.html"
    item_formset_prefix = "itens"

    def _build_forms(self):
        if self.request.method == "POST":
            form = ContagemRapidaForm(self.request.POST)
            formset = ContagemRapidaItemFormSet(self.request.POST, prefix=self.item_formset_prefix)
            return form, formset
        form = ContagemRapidaForm(initial={"data_contagem": timezone.localdate(), "unidade": UnidadeLoja.LOJA_1})
        formset = ContagemRapidaItemFormSet(prefix=self.item_formset_prefix)
        return form, formset

    @staticmethod
    def _extract_items(formset):
        itens = []
        for f in formset:
            data = f.cleaned_data if hasattr(f, "cleaned_data") else {}
            if not data or data.get("DELETE"):
                continue
            produto = data.get("produto")
            quantidade_contada = data.get("quantidade_contada")
            if produto is not None and quantidade_contada is not None:
                itens.append(
                    {
                        "produto": produto,
                        "quantidade_contada": quantidade_contada,
                        "valor_unitario": data.get("valor_unitario"),
                    }
                )
        return itens

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = kwargs.get("form")
        formset = kwargs.get("formset")
        if form is None or formset is None:
            form, formset = self._build_forms()
        ctx["form"] = form
        ctx["formset"] = formset

        unidade_raw = (
            form.cleaned_data.get("unidade")
            if form.is_bound and form.is_valid()
            else (form["unidade"].value() or UnidadeLoja.LOJA_1)
        )
        try:
            unidade = UnidadeLoja(unidade_raw)
        except ValueError:
            unidade = UnidadeLoja.LOJA_1
        itens_unidade = (
            ProdutoEstoqueUnidade.objects.select_related("produto")
            .filter(unidade=unidade)
            .order_by("produto__nome")[:120]
        )
        ctx["saldos_unidade"] = itens_unidade
        ctx["unidade_label"] = unidade.label
        return ctx

    def post(self, request, *args, **kwargs):
        form, formset = self._build_forms()
        if not form.is_valid() or not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        unidade = form.cleaned_data["unidade"]
        itens = self._extract_items(formset)
        if not itens:
            messages.error(request, "Informe ao menos um produto com quantidade contada.")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        try:
            for item in itens:
                garantir_estoque_unidades_produto(item["produto"])
            result = aplicar_contagem_rapida(
                unidade=unidade,
                itens=itens,
                usuario=request.user,
                data_contagem=form.cleaned_data["data_contagem"],
                observacao=form.cleaned_data.get("observacao") or "",
            )
        except Exception as exc:
            messages.error(request, f"Erro ao aplicar contagem: {exc}")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        messages.success(
            request,
            (
                f"Contagem aplicada para {UnidadeLoja(unidade).label}. "
                f"Itens processados: {result.total_itens}. Ajustados: {result.itens_ajustados}."
            ),
        )
        return redirect("estoque:contagem_rapida")


class SaidaOperacionalView(EstoqueManageAccessMixin, TemplateView):
    template_name = "estoque/saida_operacional.html"
    item_formset_prefix = "itens"

    def _build_forms(self):
        if self.request.method == "POST":
            form = SaidaOperacionalForm(self.request.POST)
            formset = SaidaOperacionalItemFormSet(self.request.POST, prefix=self.item_formset_prefix)
            return form, formset
        form = SaidaOperacionalForm(initial={"data_saida": timezone.localdate(), "unidade": UnidadeLoja.LOJA_1})
        formset = SaidaOperacionalItemFormSet(prefix=self.item_formset_prefix)
        return form, formset

    @staticmethod
    def _extract_items(formset):
        itens = []
        for f in formset:
            data = f.cleaned_data if hasattr(f, "cleaned_data") else {}
            if not data or data.get("DELETE"):
                continue
            produto = data.get("produto")
            quantidade = data.get("quantidade")
            if produto is not None and quantidade is not None:
                itens.append({"produto": produto, "quantidade": quantidade})
        return itens

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = kwargs.get("form")
        formset = kwargs.get("formset")
        if form is None or formset is None:
            form, formset = self._build_forms()
        ctx["form"] = form
        ctx["formset"] = formset
        ctx["ultimas_saidas"] = (
            SaidaOperacionalEstoque.objects.select_related("produto", "usuario")
            .order_by("-data_saida", "-id")[:60]
        )
        return ctx

    def post(self, request, *args, **kwargs):
        form, formset = self._build_forms()
        if not form.is_valid() or not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, formset=formset))
        itens = self._extract_items(formset)
        if not itens:
            messages.error(request, "Informe ao menos um item para a saída.")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))
        try:
            result = registrar_saida_operacional_lote(
                unidade=form.cleaned_data["unidade"],
                tipo=form.cleaned_data["tipo"],
                itens=itens,
                usuario=request.user,
                data_saida=form.cleaned_data["data_saida"],
                observacao=form.cleaned_data.get("observacao") or "",
            )
        except Exception as exc:
            messages.error(request, f"Falha ao registrar saída: {exc}")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        messages.success(
            request,
            (
                "Saída registrada com sucesso. "
                f"Itens processados: {result.total_itens}."
            ),
        )
        return redirect("estoque:saida_operacional")
