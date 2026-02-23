from __future__ import annotations

import io
from datetime import timedelta
from pathlib import Path

from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.http import JsonResponse, Http404, FileResponse, HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from core.services.permissoes import GroupRequiredMixin
from core.services.paginacao import get_pagination_params

from contas.forms import ContaAPagarForm, ConfirmarPagamentoForm, ImportCSVForm
from contas.models import ContaAPagar, StatusContaChoices
from contas.services.pagamento_service import confirmar_pagamento
from contas.services.importacao_csv import import_contas_csv
from contas.services.imposto_service import calcular_imposto_mes


class FinanceiroAccessMixin(GroupRequiredMixin):
    required_groups = ("admin/gestor", "financeiro")


class ContasDashboardView(FinanceiroAccessMixin, TemplateView):
    template_name = "contas/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from django.utils import timezone

        hoje = timezone.localdate()
        ano, mes = hoje.year, hoje.month
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        fim_semana = inicio_semana + timedelta(days=6)

        # OBS: seu campo no DB hoje está "vencimento"
        qs_mes = ContaAPagar.objects.filter(vencimento__year=ano, vencimento__month=mes)
        resumo = qs_mes.aggregate(
            total=Sum("valor"),
            abertas=Count("id", filter=Q(status=StatusContaChoices.ABERTA)),
            pagas=Count("id", filter=Q(status=StatusContaChoices.PAGA)),
        )
        ctx["total_mes"] = resumo["total"] or 0
        ctx["abertas_mes"] = resumo["abertas"] or 0
        ctx["pagas_mes"] = resumo["pagas"] or 0

        # imposto (se sua tabela/regra existir)
        try:
            ctx["imposto"] = calcular_imposto_mes(ano, mes)
        except Exception:
            ctx["imposto"] = {
                "regra_nome": "Sem regra ativa",
                "percentual": 0,
                "imposto_estimado": 0,
            }

        ctx["ultimas"] = (
            ContaAPagar.objects.select_related("categoria")
            .order_by("-id")[:10]
        )
        contas_abertas = ContaAPagar.objects.filter(status=StatusContaChoices.ABERTA)
        ctx["contas_dia"] = (
            contas_abertas.filter(vencimento=hoje)
            .select_related("categoria")
            .order_by("vencimento", "id")
        )
        ctx["contas_semana"] = (
            contas_abertas.filter(vencimento__range=(inicio_semana, fim_semana))
            .select_related("categoria")
            .order_by("vencimento", "id")
        )
        ctx["contas_mes"] = (
            contas_abertas.filter(vencimento__year=ano, vencimento__month=mes)
            .select_related("categoria")
            .order_by("vencimento", "id")
        )
        ctx["total_dia"] = ctx["contas_dia"].aggregate(total=Sum("valor"))["total"] or 0
        ctx["total_semana"] = ctx["contas_semana"].aggregate(total=Sum("valor"))["total"] or 0
        ctx["total_mes_abertas"] = ctx["contas_mes"].aggregate(total=Sum("valor"))["total"] or 0
        return ctx


class ContasPeriodoPDFView(FinanceiroAccessMixin, View):
    periodos_validos = ("dia", "semana", "mes")

    @staticmethod
    def _build_simple_pdf(lines: list[str]) -> bytes:
        # PDF simples sem dependencias externas (texto em uma pagina).
        def esc(text: str) -> str:
            return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

        content_lines = ["BT", "/F1 11 Tf", "50 800 Td", "14 TL"]
        for idx, line in enumerate(lines):
            if idx == 0:
                content_lines.append(f"({esc(line)}) Tj")
            else:
                content_lines.append(f"T* ({esc(line)}) Tj")
        content_lines.append("ET")
        content = "\n".join(content_lines).encode("latin-1", errors="replace")

        objects = []
        objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
        objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
        objects.append(
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        )
        objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
        objects.append(f"5 0 obj << /Length {len(content)} >> stream\n".encode("ascii") + content + b"\nendstream endobj\n")

        pdf = io.BytesIO()
        pdf.write(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(pdf.tell())
            pdf.write(obj)

        xref_start = pdf.tell()
        pdf.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        pdf.write(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            pdf.write(f"{off:010d} 00000 n \n".encode("ascii"))
        pdf.write(
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("ascii")
        )
        return pdf.getvalue()

    def get(self, request, *args, **kwargs):
        from django.utils import timezone

        periodo = (kwargs.get("periodo") or "").strip().lower()
        if periodo not in self.periodos_validos:
            raise Http404("Periodo invalido.")

        hoje = timezone.localdate()
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        fim_semana = inicio_semana + timedelta(days=6)
        qs = ContaAPagar.objects.filter(status=StatusContaChoices.ABERTA)

        if periodo == "dia":
            contas = qs.filter(vencimento=hoje).order_by("vencimento", "id")
            titulo = f"Contas do dia {hoje:%d/%m/%Y}"
        elif periodo == "semana":
            contas = qs.filter(vencimento__range=(inicio_semana, fim_semana)).order_by("vencimento", "id")
            titulo = f"Contas da semana {inicio_semana:%d/%m/%Y} a {fim_semana:%d/%m/%Y}"
        else:
            contas = qs.filter(vencimento__year=hoje.year, vencimento__month=hoje.month).order_by("vencimento", "id")
            titulo = f"Contas do mes {hoje:%m/%Y}"

        total = contas.aggregate(total=Sum("valor"))["total"] or 0
        lines = [titulo, "", f"Total: R$ {total}", ""]
        for conta in contas[:70]:
            lines.append(
                f"{conta.vencimento:%d/%m/%Y} | {conta.descricao[:45]} | "
                f"{conta.centro_custo} | R$ {conta.valor}"
            )
        if contas.count() > 70:
            lines.append("... lista truncada no PDF (70 linhas).")

        response = HttpResponse(self._build_simple_pdf(lines), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="contas_{periodo}.pdf"'
        return response


class ContaListView(FinanceiroAccessMixin, ListView):
    model = ContaAPagar
    template_name = "contas/conta_list.html"
    context_object_name = "contas"

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = (
            ContaAPagar.objects.select_related("categoria")
            .order_by("-vencimento", "-id")
        )

        status = (self.request.GET.get("status") or "").strip()
        if status in StatusContaChoices.values:
            qs = qs.filter(status=status)

        centro = (self.request.GET.get("centro_custo") or "").strip()
        if centro:
            qs = qs.filter(centro_custo=centro)

        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(descricao__icontains=q)

        # filtro por mês (YYYY-MM)
        ym = (self.request.GET.get("mes") or "").strip()
        if len(ym) == 7 and ym[4] == "-":
            y, m = ym.split("-")
            if y.isdigit() and m.isdigit():
                qs = qs.filter(vencimento__year=int(y), vencimento__month=int(m))

        # importado = 1/0
        imp = (self.request.GET.get("importado") or "").strip()
        if imp in ("1", "0"):
            qs = qs.filter(importado=(imp == "1"))

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()
        return ctx


class ContaDetailView(FinanceiroAccessMixin, DetailView):
    model = ContaAPagar
    template_name = "contas/conta_detail.html"
    context_object_name = "conta"


class ContaCreateView(FinanceiroAccessMixin, CreateView):
    model = ContaAPagar
    form_class = ContaAPagarForm
    template_name = "contas/conta_form.html"

    def get_success_url(self):
        return reverse("contas:conta_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.importado = False
        self.object.save()
        messages.success(self.request, "Conta criada.")
        return redirect(self.get_success_url())


class ContaUpdateView(FinanceiroAccessMixin, UpdateView):
    model = ContaAPagar
    form_class = ContaAPagarForm
    template_name = "contas/conta_form.html"

    def get_success_url(self):
        messages.success(self.request, "Conta atualizada.")
        return reverse("contas:conta_detail", kwargs={"pk": self.object.pk})


class ContaDeleteView(FinanceiroAccessMixin, DeleteView):
    model = ContaAPagar
    template_name = "contas/conta_confirm_delete.html"
    success_url = reverse_lazy("contas:conta_list")

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Conta removida.")
        return super().delete(request, *args, **kwargs)


class ConfirmarPagamentoView(FinanceiroAccessMixin, FormView):
    form_class = ConfirmarPagamentoForm
    template_name = "contas/confirmar_pagamento.html"

    def dispatch(self, request, *args, **kwargs):
        self.conta = get_object_or_404(ContaAPagar, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["conta"] = self.conta
        return ctx

    def form_valid(self, form):
        # permite anexar comprovante aqui também
        arquivo = form.cleaned_data.get("comprovante")
        if arquivo:
            self.conta.comprovante = arquivo
            self.conta.save(update_fields=["comprovante"])

        try:
            confirmar_pagamento(self.conta)
            messages.success(self.request, "Pagamento confirmado.")
            return redirect("contas:conta_detail", pk=self.conta.pk)
        except Exception as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)


class ReabrirContaView(FinanceiroAccessMixin, View):
    """
    Reabre uma conta marcada como paga (volta para ABERTA).
    """
    def post(self, request, *args, **kwargs):
        conta = get_object_or_404(ContaAPagar, pk=kwargs["pk"])
        conta.status = StatusContaChoices.ABERTA
        conta.pago_em = None
        conta.save(update_fields=["status", "pago_em"])
        messages.success(request, "Conta reaberta.")
        return redirect("contas:conta_detail", pk=conta.pk)


class ImportCSVView(FinanceiroAccessMixin, FormView):
    """
    UI para importar CSV (base inicial).
    """
    form_class = ImportCSVForm
    template_name = "contas/import_csv.html"
    success_url = reverse_lazy("contas:conta_list")

    def form_valid(self, form):
        arquivo = form.cleaned_data["arquivo"]
        exige = bool(form.cleaned_data.get("exige_comprovante_padrao", False))

        # csv.reader precisa de texto; garantimos decoding
        raw = arquivo.read()

        # tenta utf-8 primeiro, depois latin-1
        try:
            text = raw.decode("utf-8")
        except Exception:
            text = raw.decode("latin-1", errors="ignore")

        f = io.StringIO(text)

        result = import_contas_csv(
            f,
            fonte=f"UI:{arquivo.name}",
            exige_comprovante_padrao=exige,
        )

        messages.success(
            self.request,
            f"Importação concluída. Criados: {result['criados']}. Erros: {len(result['erros'])}.",
        )
        if result["erros"]:
            for err in result["erros"][:10]:
                messages.warning(self.request, err)

        return super().form_valid(form)


class ContaToggleExigeComprovanteView(FinanceiroAccessMixin, View):
    """
    Endpoint JSON pra alternar exige_comprovante via AJAX.
    """
    def post(self, request, *args, **kwargs):
        conta = get_object_or_404(ContaAPagar, pk=kwargs["pk"])
        conta.exige_comprovante = not bool(conta.exige_comprovante)
        conta.save(update_fields=["exige_comprovante"])
        return JsonResponse({"ok": True, "exige_comprovante": bool(conta.exige_comprovante)})


class ContaArquivoDownloadBaseView(FinanceiroAccessMixin, View):
    field_name = ""
    missing_message = "Arquivo não encontrado."

    def get(self, request, *args, **kwargs):
        conta = get_object_or_404(ContaAPagar, pk=kwargs["pk"])
        arquivo = getattr(conta, self.field_name, None)
        if not arquivo:
            raise Http404(self.missing_message)
        try:
            return FileResponse(
                arquivo.open("rb"),
                as_attachment=True,
                filename=Path(arquivo.name).name,
            )
        except Exception:
            raise Http404("Arquivo não encontrado.")


class DownloadComprovanteView(ContaArquivoDownloadBaseView):
    """
    Baixa o comprovante anexado (se existir).
    """
    field_name = "comprovante"
    missing_message = "Sem comprovante."


class DownloadBoletoView(ContaArquivoDownloadBaseView):
    """
    Baixa o boleto anexado (se existir).
    """
    field_name = "boleto"
    missing_message = "Sem boleto."


class DownloadNotaFiscalView(ContaArquivoDownloadBaseView):
    """
    Baixa a nota fiscal anexada (se existir).
    """
    field_name = "nota_fiscal"
    missing_message = "Sem nota fiscal."


class DownloadPedidoView(ContaArquivoDownloadBaseView):
    """
    Baixa o pedido/orçamento anexado (se existir).
    """
    field_name = "pedido"
    missing_message = "Sem pedido anexado."
