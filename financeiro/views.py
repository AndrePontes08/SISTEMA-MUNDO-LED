from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.db.models import Max, Min, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, TemplateView, View

from core.services.paginacao import get_pagination_params
from core.services.permissoes import GroupRequiredMixin
from financeiro.forms import (
    ConciliacaoActionForm,
    ContaBancariaForm,
    HistoricoImportacaoFiltroForm,
    OFXUploadForm,
)
from financeiro.models import (
    ContaBancaria,
    ExtratoImportacao,
    Recebivel,
    StatusConciliacaoChoices,
    StatusImportacaoChoices,
    TransacaoBancaria,
)
from financeiro.services.conciliacao_service import ConciliacaoService
from financeiro.services.importacao_service import ImportacaoOFXService


class FinanceiroAccessMixin(GroupRequiredMixin):
    required_groups = ("admin/gestor", "financeiro")


class FinanceiroDashboardView(FinanceiroAccessMixin, TemplateView):
    template_name = "financeiro/dashboard.html"


class ContaBancariaCreateView(FinanceiroAccessMixin, CreateView):
    form_class = ContaBancariaForm
    template_name = "financeiro/conta_bancaria_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Conta bancaria cadastrada com sucesso.")
        return response

    def get_success_url(self):
        next_url = (self.request.GET.get("next") or "").strip()
        if next_url:
            return next_url
        return reverse("financeiro:importar_ofx")


class ImportarOFXView(FinanceiroAccessMixin, TemplateView):
    template_name = "financeiro/importar_ofx.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = kwargs.get("form") or OFXUploadForm()
        importacao_id = self.request.GET.get("preview")
        if importacao_id:
            importacao = ExtratoImportacao.objects.filter(pk=importacao_id).first()
            if importacao:
                ctx["importacao_preview"] = importacao
                ctx["preview_rows"] = (importacao.resumo or {}).get("preview_transacoes", [])
        return ctx

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "preview").strip().lower()
        if action == "confirmar":
            return self._confirmar(request)
        return self._preview(request)

    def _preview(self, request):
        form = OFXUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        arquivo = form.cleaned_data["arquivo"]
        conta = form.cleaned_data.get("conta_bancaria")
        try:
            importacao, _ = ImportacaoOFXService.criar_preview(
                uploaded_file=arquivo,
                usuario=request.user,
                conta_forcada=conta,
            )
        except Exception as exc:
            messages.error(request, f"Falha ao analisar OFX: {exc}")
            return self.render_to_response(self.get_context_data(form=form))
        return redirect(f"{reverse('financeiro:importar_ofx')}?preview={importacao.id}")

    def _confirmar(self, request):
        importacao_id = request.POST.get("importacao_id")
        conta_id = request.POST.get("conta_bancaria")
        importacao = get_object_or_404(ExtratoImportacao, pk=importacao_id)
        conta = importacao.conta
        if conta_id:
            conta = ContaBancaria.objects.filter(pk=conta_id).first()
        try:
            result = ImportacaoOFXService.confirmar_importacao(importacao, conta, request.user)
            messages.success(
                request,
                (
                    f"Importacao concluida. Novas: {result['novas']} | Duplicadas: {result['duplicadas']} "
                    f"| Status: {result['status']}"
                ),
            )
            if result["erros"]:
                for erro in result["erros"][:8]:
                    messages.warning(request, erro)
            return redirect("financeiro:historico_importacoes")
        except Exception as exc:
            messages.error(request, f"Falha ao importar: {exc}")
            return redirect(f"{reverse('financeiro:importar_ofx')}?preview={importacao.id}")


class HistoricoImportacoesView(FinanceiroAccessMixin, ListView):
    template_name = "financeiro/historico_importacoes.html"
    context_object_name = "importacoes"
    model = ExtratoImportacao

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = (
            ExtratoImportacao.objects.select_related("conta", "criado_por")
            .order_by("-criado_em")
        )
        self.form = HistoricoImportacaoFiltroForm(self.request.GET or None)
        if self.form.is_valid():
            conta = self.form.cleaned_data.get("conta")
            banco = (self.form.cleaned_data.get("banco") or "").strip()
            status = self.form.cleaned_data.get("status")
            data_inicio = self.form.cleaned_data.get("data_inicio")
            data_fim = self.form.cleaned_data.get("data_fim")
            if conta:
                qs = qs.filter(conta=conta)
            if banco:
                qs = qs.filter(Q(banco_nome__icontains=banco) | Q(banco_codigo__icontains=banco))
            if status:
                qs = qs.filter(status=status)
            if data_inicio:
                qs = qs.filter(criado_em__date__gte=data_inicio)
            if data_fim:
                qs = qs.filter(criado_em__date__lte=data_fim)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filtro_form"] = getattr(self, "form", HistoricoImportacaoFiltroForm())
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        ctx["alertas_conta"] = self._build_alertas_por_conta()
        return ctx

    def _build_alertas_por_conta(self):
        from django.utils import timezone

        hoje = timezone.localdate()
        alertas = []
        for conta in ContaBancaria.objects.filter(ativa=True).order_by("nome"):
            ultima = conta.importacoes.exclude(status=StatusImportacaoChoices.PREVIEW).first()
            if not ultima:
                alertas.append(f"{conta.nome}: sem importacao registrada.")
                continue
            dias = (hoje - ultima.criado_em.date()).days
            if dias > 3:
                alertas.append(f"{conta.nome}: sem importacao ha {dias} dias.")
            cobertura = conta.transacoes.aggregate(inicio=Min("data_lancamento"), fim=Max("data_lancamento"))
            if cobertura["inicio"] and cobertura["fim"]:
                gap = (hoje - cobertura["fim"]).days
                if gap > 2:
                    alertas.append(f"{conta.nome}: periodo importado termina ha {gap} dias.")
        return alertas


class ImportacaoDetailView(FinanceiroAccessMixin, DetailView):
    template_name = "financeiro/importacao_detail.html"
    model = ExtratoImportacao
    context_object_name = "importacao"


class ConciliacaoListView(FinanceiroAccessMixin, ListView):
    template_name = "financeiro/conciliacao_list.html"
    context_object_name = "transacoes"
    model = TransacaoBancaria

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        status = (self.request.GET.get("status") or "").strip()
        qs = (
            TransacaoBancaria.objects.select_related("conta", "importacao")
            .filter(
                status_conciliacao__in=[
                    StatusConciliacaoChoices.PENDENTE,
                    StatusConciliacaoChoices.SUGERIDA,
                ]
            )
            .order_by("-data_lancamento", "-id")
        )
        if status in (StatusConciliacaoChoices.PENDENTE, StatusConciliacaoChoices.SUGERIDA):
            qs = qs.filter(status_conciliacao=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        suggestions = {}
        for tx in ctx["transacoes"]:
            suggestions[tx.id] = ConciliacaoService.gerar_sugestoes(tx, limite=5)
        ctx["suggestions"] = suggestions
        ctx["action_form"] = ConciliacaoActionForm()
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


class ConciliacaoActionView(FinanceiroAccessMixin, View):
    def post(self, request, *args, **kwargs):
        transacao = get_object_or_404(TransacaoBancaria, pk=kwargs["pk"])
        action = (request.POST.get("action") or "").strip().lower()
        form = ConciliacaoActionForm(request.POST)
        observacao = request.POST.get("observacao", "")

        try:
            if action == "conciliar":
                if not form.is_valid():
                    raise ValueError("Selecione os recebiveis para conciliar.")
                ids = list(form.cleaned_data["recebiveis"].values_list("id", flat=True))
                recebiveis = list(Recebivel.objects.filter(id__in=ids))
                ConciliacaoService.conciliar(
                    transacao=transacao,
                    recebiveis=recebiveis,
                    usuario=request.user,
                    observacao=observacao,
                )
                messages.success(request, f"Transacao {transacao.id} conciliada.")
            elif action == "divergente":
                ConciliacaoService.marcar_divergente(transacao, request.user, observacao=observacao)
                messages.warning(request, f"Transacao {transacao.id} marcada como divergente.")
            elif action == "ignorar":
                ConciliacaoService.ignorar(transacao, request.user, observacao=observacao)
                messages.info(request, f"Transacao {transacao.id} ignorada.")
            else:
                messages.error(request, "Acao invalida.")
        except Exception as exc:
            messages.error(request, f"Falha na conciliacao: {exc}")

        querystring = (request.POST.get("querystring") or "").strip()
        base = reverse("financeiro:conciliacao")
        return redirect(f"{base}?{querystring}" if querystring else base)
