from __future__ import annotations

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

from compras.models import Compra, CompraEvento
from core.services.permissoes import GroupRequiredMixin
from core.services.paginacao import get_pagination_params

from estoque.forms import (
    MovimentoForm,
    MovimentoItemFormSet,
    ProdutoEstoqueForm,
    TransferenciaForm,
    TransferenciaItemFormSet,
)
from estoque.models import ProdutoEstoque, AlertaEstoque, StatusAlerta, EstoqueMovimento, TransferenciaEstoque
from estoque.services.estoque_service import registrar_entrada, registrar_saida, registrar_ajuste
from estoque.services.integracao_compras import dar_entrada_por_compra
from estoque.services.statistics_service import EstoqueStatisticsService
from estoque.services.transferencias_service import transferir_lote_entre_unidades


class EstoqueAccessMixin(GroupRequiredMixin):
    required_groups = ("admin/gestor", "compras/estoque", "estoquista")


class EstoqueDashboardView(EstoqueAccessMixin, TemplateView):
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


class ProdutoEstoqueListView(EstoqueAccessMixin, ListView):
    model = ProdutoEstoque
    template_name = "estoque/produtoestoque_list.html"
    context_object_name = "configs"

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = ProdutoEstoque.objects.select_related("produto").order_by("produto__nome")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(produto__nome__icontains=q)
        return qs


class ProdutoEstoqueUpdateView(EstoqueAccessMixin, UpdateView):
    model = ProdutoEstoque
    form_class = ProdutoEstoqueForm
    template_name = "estoque/produtoestoque_form.html"

    def get_success_url(self):
        messages.success(self.request, "Configuração de estoque atualizada.")
        return reverse("estoque:produtoestoque_list")


class MovimentoCreateView(EstoqueAccessMixin, TemplateView):
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


class MovimentoListView(EstoqueAccessMixin, ListView):
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


class EntradaPorCompraView(EstoqueAccessMixin, TemplateView):
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


class RecebimentoCompraListView(EstoqueAccessMixin, ListView):
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


class RecebimentoCompraDetailView(EstoqueAccessMixin, DetailView):
    model = Compra
    template_name = "estoque/recebimento_detail.html"
    context_object_name = "compra"

    def get_queryset(self):
        return (
            Compra.objects.select_related("fornecedor", "aprovado_por")
            .prefetch_related("itens__produto")
            .filter(status=Compra.StatusChoices.APROVADA)
        )


class ConfirmarRecebimentoCompraView(EstoqueAccessMixin, View):
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


class IndicadoresEstoqueView(EstoqueAccessMixin, TemplateView):
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


class TransferenciaCreateView(EstoqueAccessMixin, TemplateView):
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
