from __future__ import annotations

from django.contrib import messages
from django.db.models import Prefetch
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from compras.forms import (
    CompraForm,
    FornecedorForm,
    GarantiaForm,
    ItemCompraFormSet,
    ProdutoForm,
)
from compras.models import (
    CentroCustoChoices,
    Compra,
    CompraEvento,
    Fornecedor,
    Garantia,
    ItemCompra,
    Produto,
)
from compras.services.compras_service import recalcular_total
from compras.services.statistics_service import ComprasStatisticsService
from core.services.paginacao import get_pagination_params
from core.services.permissoes import GroupRequiredMixin
from estoque.services.integracao_compras import dar_entrada_por_compra


class ComprasAccessMixin(GroupRequiredMixin):
    required_groups = ("admin/gestor", "compras/estoque", "comprador", "estoquista")


def _is_admin_ou_gestor(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or user.groups.filter(name="admin/gestor").exists()))


def _is_estoquista(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or user.groups.filter(name__in=["admin/gestor", "estoquista", "compras/estoque"]).exists()
        )
    )


def _is_comprador(user) -> bool:
    return bool(user and user.is_authenticated and user.groups.filter(name="comprador").exists())


class CompraListView(ComprasAccessMixin, ListView):
    model = Compra
    template_name = "compras/compra_list.html"
    context_object_name = "compras"

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = (
            Compra.objects.select_related("fornecedor", "aprovado_por", "recebido_por")
            .prefetch_related("itens")
            .order_by("-data_compra", "-id")
        )
        centro = (self.request.GET.get("centro_custo") or "").strip()
        if centro:
            qs = qs.filter(centro_custo=centro)

        fornecedor = (self.request.GET.get("fornecedor") or "").strip()
        if fornecedor:
            qs = qs.filter(fornecedor__nome__icontains=fornecedor)

        data_inicio = (self.request.GET.get("data_inicio") or "").strip()
        data_fim = (self.request.GET.get("data_fim") or "").strip()
        if data_inicio:
            qs = qs.filter(data_compra__gte=data_inicio)
        if data_fim:
            qs = qs.filter(data_compra__lte=data_fim)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["centros_custo"] = CentroCustoChoices.choices
        context["stats"] = ComprasStatisticsService.obter_estatisticas_gerais()
        context["top_fornecedores"] = ComprasStatisticsService.obter_top_fornecedores(5)
        context["tendencias"] = ComprasStatisticsService.obter_tendencias()
        context["compras_por_centro"] = ComprasStatisticsService.obter_compras_por_centro_custo()
        return context


class CompraAprovacaoListView(ComprasAccessMixin, ListView):
    model = Compra
    template_name = "compras/aprovacao_list.html"
    context_object_name = "compras"

    def dispatch(self, request, *args, **kwargs):
        if not _is_admin_ou_gestor(request.user):
            messages.error(request, "Acesso restrito a diretor/admin.")
            return redirect("compras:compra_list")
        return super().dispatch(request, *args, **kwargs)

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = (
            Compra.objects.select_related("fornecedor")
            .prefetch_related("itens")
            .filter(status=Compra.StatusChoices.SOLICITADA)
            .order_by("-data_compra", "-id")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(fornecedor__nome__icontains=q)
        return qs


class CompraDetailView(ComprasAccessMixin, DetailView):
    model = Compra
    template_name = "compras/compra_detail.html"
    context_object_name = "compra"

    def get_queryset(self):
        return (
            Compra.objects.select_related("fornecedor", "aprovado_por", "recebido_por")
            .prefetch_related(
                Prefetch("itens", queryset=ItemCompra.objects.select_related("produto").prefetch_related("garantias")),
                "eventos",
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_receive"] = _is_estoquista(self.request.user)
        ctx["can_approve"] = _is_admin_ou_gestor(self.request.user)
        return ctx


class CompraCreateView(ComprasAccessMixin, CreateView):
    model = Compra
    form_class = CompraForm
    template_name = "compras/compra_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["itens_formset"] = ItemCompraFormSet(self.request.POST, instance=self.object)
        else:
            ctx["itens_formset"] = ItemCompraFormSet(instance=self.object)
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx["itens_formset"]
        if not formset.is_valid():
            return self.form_invalid(form)

        self.object = form.save()
        formset.instance = self.object
        formset.save()
        recalcular_total(self.object)
        messages.success(self.request, "Compra criada com sucesso.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("compras:compra_detail", kwargs={"pk": self.object.pk})


class CompraUpdateView(ComprasAccessMixin, UpdateView):
    model = Compra
    form_class = CompraForm
    template_name = "compras/compra_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["itens_formset"] = ItemCompraFormSet(self.request.POST, instance=self.object)
        else:
            ctx["itens_formset"] = ItemCompraFormSet(instance=self.object)
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx["itens_formset"]
        if not formset.is_valid():
            return self.form_invalid(form)

        self.object = form.save()
        formset.save()
        recalcular_total(self.object)
        messages.success(self.request, "Compra atualizada com sucesso.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("compras:compra_detail", kwargs={"pk": self.object.pk})


class GarantiaCreateView(ComprasAccessMixin, CreateView):
    model = Garantia
    form_class = GarantiaForm
    template_name = "compras/garantia_form.html"

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.full_clean()
        obj.save()
        messages.success(self.request, "Garantia cadastrada com sucesso.")
        return redirect(reverse("compras:compra_detail", kwargs={"pk": obj.item.compra_id}))


class DownloadCompraFileView(ComprasAccessMixin, View):
    """
    Baixa arquivos anexados a compra.
    """

    def get(self, request, *args, **kwargs):
        compra = Compra.objects.filter(pk=kwargs["pk"]).first()
        if not compra:
            raise Http404("Compra nao encontrada.")

        field = kwargs.get("field")
        arquivo = None
        if field == "nota":
            arquivo = getattr(compra, "nota_fiscal", None)
        elif field == "boleto":
            arquivo = getattr(compra, "boleto", None)
        elif field == "pedido":
            arquivo = getattr(compra, "pedido", None)
        elif field == "comprovante":
            arquivo = getattr(compra, "comprovante_pagamento", None)
        elif field == "orc1":
            arquivo = getattr(compra, "orcamento_1", None)
        elif field == "orc2":
            arquivo = getattr(compra, "orcamento_2", None)
        elif field == "orc3":
            arquivo = getattr(compra, "orcamento_3", None)

        if not arquivo:
            raise Http404("Arquivo nao encontrado.")

        try:
            return FileResponse(arquivo.open("rb"), as_attachment=True, filename=arquivo.name.split("/")[-1])
        except Exception:
            raise Http404("Arquivo nao encontrado.")


class AprovarCompraView(ComprasAccessMixin, View):
    """Aprovacao por diretor/admin."""

    def post(self, request, *args, **kwargs):
        if not _is_admin_ou_gestor(request.user):
            messages.error(request, "Somente diretor/admin pode aprovar compra.")
            return redirect(reverse("compras:compra_detail", kwargs={"pk": kwargs["pk"]}))

        compra = Compra.objects.filter(pk=kwargs["pk"]).first()
        if not compra:
            raise Http404("Compra nao encontrada.")

        if compra.status == Compra.StatusChoices.APROVADA:
            messages.info(request, "Compra ja aprovada.")
            return redirect(reverse("compras:compra_detail", kwargs={"pk": compra.pk}))

        if not (compra.orcamento_1 and compra.orcamento_2 and compra.orcamento_3):
            messages.error(request, "Aprovacao bloqueada: anexe os 3 orcamentos.")
            return redirect(reverse("compras:compra_detail", kwargs={"pk": compra.pk}))
        if compra.orcamento_escolhido not in {"ORC_1", "ORC_2", "ORC_3"}:
            messages.error(request, "Aprovacao bloqueada: selecione o orcamento escolhido.")
            return redirect(reverse("compras:compra_detail", kwargs={"pk": compra.pk}))
        if not (compra.justificativa_escolha or "").strip():
            messages.error(request, "Aprovacao bloqueada: preencha justificativa da escolha.")
            return redirect(reverse("compras:compra_detail", kwargs={"pk": compra.pk}))
        if not (compra.observacoes or "").strip():
            messages.error(request, "Aprovacao bloqueada: preencha observacoes.")
            return redirect(reverse("compras:compra_detail", kwargs={"pk": compra.pk}))

        compra.status = Compra.StatusChoices.APROVADA
        compra.aprovado_em = timezone.now()
        compra.aprovado_por = request.user if request.user.is_authenticated else None
        compra.save(update_fields=["status", "aprovado_em", "aprovado_por"])
        CompraEvento.objects.create(
            compra=compra,
            tipo=CompraEvento.TipoEvento.APROVACAO,
            usuario=(request.user if request.user.is_authenticated else None),
            detalhe=f"Compra aprovada. Orcamento escolhido: {compra.orcamento_escolhido}.",
        )
        messages.success(request, "Compra aprovada com sucesso.")
        return redirect(reverse("compras:compra_detail", kwargs={"pk": compra.pk}))


class MarcarRecebidaView(ComprasAccessMixin, View):
    """Marca compra como recebida e cria entrada no estoque."""

    def post(self, request, *args, **kwargs):
        if not _is_estoquista(request.user):
            messages.error(request, "Somente o estoquista (ou admin/gestor) pode registrar recebimento.")
            return redirect(reverse("compras:compra_detail", kwargs={"pk": kwargs["pk"]}))
        if _is_comprador(request.user) and not _is_admin_ou_gestor(request.user):
            messages.error(request, "Comprador nao pode registrar recebimento. Acao restrita ao estoque.")
            return redirect(reverse("compras:compra_detail", kwargs={"pk": kwargs["pk"]}))

        compra = Compra.objects.filter(pk=kwargs["pk"]).first()
        if not compra:
            raise Http404("Compra nao encontrada.")
        if compra.status != Compra.StatusChoices.APROVADA:
            messages.error(request, "A compra precisa estar APROVADA antes do recebimento.")
            return redirect(reverse("compras:compra_detail", kwargs={"pk": compra.pk}))

        already_received = compra.status == Compra.StatusChoices.RECEBIDA
        if not already_received:
            compra.status = Compra.StatusChoices.RECEBIDA
            compra.recebido_em = timezone.now()
            if request.user and request.user.is_authenticated:
                compra.recebido_por = request.user
            compra.save(update_fields=["status", "recebido_em", "recebido_por"])
            CompraEvento.objects.create(
                compra=compra,
                tipo=CompraEvento.TipoEvento.RECEBIMENTO,
                usuario=(request.user if request.user.is_authenticated else None),
                detalhe="Recebimento registrado por estoquista/admin via interface.",
            )

        criados = dar_entrada_por_compra(compra)
        if criados > 0:
            messages.success(request, f"Entrada no estoque criada para {criados} item(ns).")
        else:
            if already_received:
                messages.info(request, "Compra ja estava marcada como recebida; nenhuma entrada criada.")
            else:
                messages.info(request, "Nenhuma entrada criada (itens ja possuiam movimentos).")

        return redirect(reverse("compras:compra_detail", kwargs={"pk": compra.pk}))


class FornecedorQuickCreateView(ComprasAccessMixin, CreateView):
    model = Fornecedor
    form_class = FornecedorForm
    template_name = "compras/fornecedor_quick_form.html"

    def form_valid(self, form):
        obj = form.save()
        messages.success(self.request, f"Fornecedor '{obj.nome}' cadastrado.")
        next_url = self.request.GET.get("next")
        if next_url:
            return redirect(next_url)
        return redirect("compras:compra_create")


class ProdutoQuickCreateView(ComprasAccessMixin, CreateView):
    model = Produto
    form_class = ProdutoForm
    template_name = "compras/produto_quick_form.html"

    def form_valid(self, form):
        obj = form.save()
        messages.success(self.request, f"Produto '{obj.nome}' cadastrado.")
        next_url = self.request.GET.get("next")
        if next_url:
            return redirect(next_url)
        return redirect("compras:compra_create")
