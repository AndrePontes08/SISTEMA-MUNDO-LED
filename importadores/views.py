from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.views.generic import DetailView, ListView, TemplateView

from core.services.paginacao import get_pagination_params
from core.services.permissoes import GroupRequiredMixin
from importadores.forms import CaixaPDFUploadForm
from importadores.models import CaixaRelatorioImportacao
from importadores.services.importacao_caixa_service import ImportacaoCaixaService


class ImportadoresAccessMixin(GroupRequiredMixin):
    required_groups = ("admin/gestor", "financeiro", "compras/estoque")


class CaixaImportarView(ImportadoresAccessMixin, TemplateView):
    template_name = "importadores/caixa_importar.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = kwargs.get("form") or CaixaPDFUploadForm()
        return ctx

    def post(self, request, *args, **kwargs):
        form = CaixaPDFUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            importacao = ImportacaoCaixaService.importar_pdf(
                uploaded_file=form.cleaned_data["arquivo_pdf"],
                usuario=request.user,
                unidade_override=form.cleaned_data.get("unidade_override") or "",
                data_referencia_override=form.cleaned_data.get("data_referencia_override"),
            )
            messages.success(
                request,
                (
                    f"PDF importado. Unidade: {importacao.unidade} | Data: {importacao.data_referencia} | "
                    f"Vendas: {importacao.total_vendas} | Itens baixados: {importacao.itens_baixados}."
                ),
            )
            if importacao.itens_inconsistentes:
                messages.warning(request, f"Itens com inconsistencia: {importacao.itens_inconsistentes}.")
        except ValidationError as exc:
            msg = "; ".join(exc.messages) if getattr(exc, "messages", None) else str(exc)
            messages.error(request, f"Falha na importacao: {msg}")
            return self.render_to_response(self.get_context_data(form=form))
        except Exception as exc:
            messages.error(request, f"Falha na importacao: {exc}")
            return self.render_to_response(self.get_context_data(form=form))
        return self.render_to_response(self.get_context_data(form=CaixaPDFUploadForm()))


class CaixaImportacaoListView(ImportadoresAccessMixin, ListView):
    template_name = "importadores/caixa_importacao_list.html"
    context_object_name = "importacoes"
    model = CaixaRelatorioImportacao

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = CaixaRelatorioImportacao.objects.select_related("criado_por").order_by("-data_referencia", "-id")
        unidade = (self.request.GET.get("unidade") or "").strip()
        if unidade:
            qs = qs.filter(unidade=unidade)
        return qs


class CaixaImportacaoDetailView(ImportadoresAccessMixin, DetailView):
    template_name = "importadores/caixa_importacao_detail.html"
    context_object_name = "importacao"
    model = CaixaRelatorioImportacao
