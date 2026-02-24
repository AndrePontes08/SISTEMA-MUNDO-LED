from __future__ import annotations

import io
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib import messages
from django.db.models import Count, DecimalField, Prefetch, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from core.services.paginacao import get_pagination_params
from core.services.permissoes import GroupRequiredMixin
from core.services.formato_brl import format_brl, payment_label, unit_label
from vendas.forms import CancelarVendaForm, FechamentoCaixaForm, ItemVendaFormSet, VendaForm
from vendas.models import (
    FechamentoCaixaDiario,
    ItemVenda,
    StatusVendaChoices,
    TipoDocumentoVendaChoices,
    TipoPagamentoChoices,
    Venda,
)
from vendas.services.statistics_service import VendasStatisticsService
from vendas.services.fechamento_caixa_service import gerar_fechamento_caixa
from vendas.services.vendas_service import (
    cancelar_venda,
    confirmar_venda,
    converter_orcamento_em_venda,
    faturar_venda,
    finalizar_venda,
    recalcular_totais,
    registrar_evento,
)


class VendasAccessMixin(GroupRequiredMixin):
    required_groups = ("admin/gestor", "vendedor")

    def _is_manager(self) -> bool:
        user = self.request.user
        return bool(user.is_superuser or user.groups.filter(name="admin/gestor").exists())


def _escape_pdf_text(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 11 Tf", "50 805 Td"]
    for idx, line in enumerate(lines):
        if idx > 0:
            commands.append("0 -16 Td")
        commands.append(f"({_escape_pdf_text(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="ignore")

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n")
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(
        f"5 0 obj << /Length {len(stream)} >> stream\n".encode("latin-1")
        + stream
        + b"\nendstream endobj\n"
    )

    header = b"%PDF-1.4\n"
    body = b""
    offsets = [0]
    for obj in objects:
        offsets.append(len(header) + len(body))
        body += obj

    xref_start = len(header) + len(body)
    xref = [f"xref\n0 {len(objects)+1}\n".encode("latin-1"), b"0000000000 65535 f \n"]
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n \n".encode("latin-1"))
    trailer = f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("latin-1")
    return header + body + b"".join(xref) + trailer


def _pdf_business_lines(venda: Venda) -> list[str]:
    validade = (venda.data_venda + timedelta(days=7)).strftime("%d/%m/%Y")
    if venda.numero_parcelas and venda.numero_parcelas > 1:
        parcelamento = (
            f"{venda.numero_parcelas}x a cada {venda.intervalo_parcelas_dias or 30} dias"
        )
    else:
        parcelamento = "A vista"
    lines = [
        "MUNDO LED",
        f"{venda.get_tipo_documento_display()} {venda.codigo_identificacao}",
        f"Cliente: {venda.cliente.nome}",
        f"Data emissao: {venda.data_venda:%d/%m/%Y}",
        f"Validade da proposta: {validade}",
        f"Vendedor responsavel: {venda.vendedor or '-'}",
        f"Pagamento: {payment_label(venda.tipo_pagamento)} | Status: {venda.get_status_display()}",
        f"Parcelamento: {parcelamento}",
        "",
        "ITENS",
    ]
    for item in venda.itens.all():
        lines.append(
            f"- {item.produto.nome} | qtd {item.quantidade} | unit {format_brl(item.preco_unitario)} | "
            f"desc {format_brl(item.desconto)} | subtotal {format_brl(item.subtotal)}"
        )
    lines.extend(
        [
            "",
            f"Subtotal: {format_brl(venda.subtotal)}",
            f"Desconto total: {format_brl(venda.desconto_total)}",
            f"Acrescimo: {format_brl(venda.acrescimo)}",
            f"Total: {format_brl(venda.total_final)}",
            "",
            "CONDICOES COMERCIAIS",
            "1) Valores sujeitos a confirmacao de estoque no faturamento.",
            "2) Prazo de entrega a confirmar com o vendedor.",
            "3) Garantia conforme politica interna e fabricante.",
            "",
            "OBSERVACOES",
            (venda.observacoes or "-"),
            "",
            "Assinatura cliente: __________________________",
            "Assinatura vendedor: _________________________",
            "",
            "MUNDO LED - Documento gerado pelo ERP",
        ]
    )
    return lines


def _split_text_plain(text: str, limit: int = 95) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return ["-"]
    words = raw.split()
    lines: list[str] = []
    current = ""
    for word in words:
        tentative = word if not current else f"{current} {word}"
        if len(tentative) <= limit:
            current = tentative
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


class VendaListView(VendasAccessMixin, ListView):
    model = Venda
    template_name = "vendas/venda_list.html"
    context_object_name = "vendas"

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = (
            Venda.objects.select_related("cliente", "vendedor")
            .prefetch_related("itens")
            .order_by("-data_venda", "-id")
        )
        status = (self.request.GET.get("status") or "").strip()
        tipo_documento = (self.request.GET.get("tipo_documento") or "").strip()
        cliente = (self.request.GET.get("cliente") or "").strip()
        vendedor = (self.request.GET.get("vendedor") or "").strip()
        tipo_pagamento = (self.request.GET.get("tipo_pagamento") or "").strip()
        data_inicio = (self.request.GET.get("data_inicio") or "").strip()
        data_fim = (self.request.GET.get("data_fim") or "").strip()

        if status:
            qs = qs.filter(status=status)
        if tipo_documento:
            qs = qs.filter(tipo_documento=tipo_documento)
        if cliente:
            qs = qs.filter(cliente__nome__icontains=cliente)
        if vendedor:
            qs = qs.filter(vendedor__username__istartswith=vendedor)
        if tipo_pagamento:
            qs = qs.filter(tipo_pagamento=tipo_pagamento)
        if data_inicio:
            qs = qs.filter(data_venda__gte=data_inicio)
        if data_fim:
            qs = qs.filter(data_venda__lte=data_fim)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        periodo = self.request.GET.get("periodo", "30")
        periodo_dias = int(periodo) if periodo.isdigit() else 30
        base_filtrada = self.get_queryset()
        resumo_filtrado = base_filtrada.aggregate(
            total_vendas=Count("id"),
            total_final=Coalesce(
                Sum("total_final"),
                Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)),
            ),
            total_descontos=Coalesce(
                Sum("desconto_total"),
                Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)),
            ),
        )
        querydict = self.request.GET.copy()
        querydict.pop("page", None)
        ctx["status_choices"] = StatusVendaChoices.choices
        ctx["tipo_documento_choices"] = TipoDocumentoVendaChoices.choices
        ctx["tipo_pagamento_choices"] = [(value, payment_label(value)) for value, _ in TipoPagamentoChoices.choices]
        ctx["resumo_filtrado"] = resumo_filtrado
        ctx["querystring"] = querydict.urlencode()
        ctx["dashboard"] = VendasStatisticsService.resumo(periodo_dias=periodo_dias)
        return ctx


class VendaDetailView(VendasAccessMixin, DetailView):
    model = Venda
    template_name = "vendas/venda_detail.html"
    context_object_name = "venda"

    def get_queryset(self):
        return (
            Venda.objects.select_related("cliente", "vendedor")
            .prefetch_related(
                Prefetch("itens", queryset=ItemVenda.objects.select_related("produto")),
                "eventos__usuario",
                "movimentos_estoque__movimento",
                "recebiveis__recebivel",
                "boletos__boleto",
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cancelar_form"] = CancelarVendaForm()
        return ctx


class VendaCreateView(VendasAccessMixin, CreateView):
    model = Venda
    form_class = VendaForm
    template_name = "vendas/venda_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["itens_formset"] = ItemVendaFormSet(self.request.POST, instance=self.object)
        else:
            ctx["itens_formset"] = ItemVendaFormSet(instance=self.object)
        ctx["empty_item_form"] = ItemVendaFormSet(instance=self.object).empty_form
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial["data_venda"] = timezone.localdate()
        return initial

    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx["itens_formset"]
        if not formset.is_valid():
            return self.form_invalid(form)
        itens_validos = [f for f in formset.forms if f.cleaned_data and not f.cleaned_data.get("DELETE") and f.cleaned_data.get("produto")]
        if not itens_validos:
            messages.error(self.request, "Adicione ao menos um produto para salvar.")
            return self.form_invalid(form)
        if not self._validar_autorizacao_desconto(itens_validos):
            return self.form_invalid(form)

        self.object = form.save(commit=False)
        if not self._is_manager():
            self.object.vendedor = self.request.user
        self.object.data_venda = timezone.localdate()
        self.object.save()
        formset.instance = self.object
        formset.save()
        recalcular_totais(self.object)
        registrar_evento(self.object, "CRIACAO", self.request.user, "Venda criada pela interface")
        if getattr(self, "_desconto_percentual", Decimal("0.00")) > Decimal("10.00"):
            registrar_evento(
                self.object,
                "OUTRO",
                self.request.user,
                (
                    f"Desconto acima do limite aprovado ({self._desconto_percentual:.2f}%). "
                    f"Autorizado por: {self._desconto_autorizador.username}."
                ),
            )
        messages.success(self.request, "Venda criada com sucesso.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("vendas:venda_detail", kwargs={"pk": self.object.pk})

    def _usuario_pode_autorizar_desconto(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.groups.filter(name="admin/gestor").exists():
            return True
        return user.username.lower() in {"lucas", "tabatha"}

    def _maior_percentual_desconto(self, itens_forms) -> Decimal:
        maior = Decimal("0.00")
        for item_form in itens_forms:
            data = item_form.cleaned_data or {}
            preco = data.get("preco_unitario") or Decimal("0.00")
            quantidade = data.get("quantidade") or Decimal("0.000")
            desconto = data.get("desconto") or Decimal("0.00")
            bruto = preco * quantidade
            if bruto <= 0 or desconto <= 0:
                continue
            percentual = ((desconto / bruto) * Decimal("100.00")).quantize(Decimal("0.01"))
            if percentual > maior:
                maior = percentual
        return maior

    def _validar_autorizacao_desconto(self, itens_forms) -> bool:
        self._desconto_percentual = self._maior_percentual_desconto(itens_forms)
        self._desconto_autorizador = None
        if self._desconto_percentual <= Decimal("10.00"):
            return True

        if self._usuario_pode_autorizar_desconto(self.request.user):
            self._desconto_autorizador = self.request.user
            return True

        usuario_aut = (self.request.POST.get("desconto_autorizador") or "").strip()
        senha_aut = (self.request.POST.get("desconto_senha") or "").strip()
        if not usuario_aut or not senha_aut:
            messages.error(
                self.request,
                (
                    f"Desconto de {self._desconto_percentual:.2f}% excede o limite de 10%. "
                    "Informe usuário e senha de administrador/gerente para autorizar."
                ),
            )
            return False

        autorizado = authenticate(self.request, username=usuario_aut, password=senha_aut)
        if not self._usuario_pode_autorizar_desconto(autorizado):
            messages.error(self.request, "Credencial de autorização inválida para desconto acima de 10%.")
            return False
        self._desconto_autorizador = autorizado
        return True


class VendaUpdateView(VendasAccessMixin, UpdateView):
    model = Venda
    form_class = VendaForm
    template_name = "vendas/venda_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["itens_formset"] = ItemVendaFormSet(self.request.POST, instance=self.object)
        else:
            ctx["itens_formset"] = ItemVendaFormSet(instance=self.object)
        ctx["empty_item_form"] = ItemVendaFormSet(instance=self.object).empty_form
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        if self.object.status in (StatusVendaChoices.FATURADA, StatusVendaChoices.FINALIZADA, StatusVendaChoices.CANCELADA):
            messages.error(self.request, "Não é permitido editar venda nesse status.")
            return redirect(reverse("vendas:venda_detail", kwargs={"pk": self.object.pk}))

        ctx = self.get_context_data()
        formset = ctx["itens_formset"]
        if not formset.is_valid():
            return self.form_invalid(form)
        itens_validos = [f for f in formset.forms if f.cleaned_data and not f.cleaned_data.get("DELETE") and f.cleaned_data.get("produto")]
        if not itens_validos:
            messages.error(self.request, "Adicione ao menos um produto para salvar.")
            return self.form_invalid(form)
        if not self._validar_autorizacao_desconto(itens_validos):
            return self.form_invalid(form)

        before = self.get_object()
        change_log = self._build_change_log(before, form, formset)

        self.object = form.save(commit=False)
        if not self._is_manager():
            self.object.vendedor = before.vendedor
        self.object.save()
        formset.save()
        recalcular_totais(self.object)
        if change_log:
            registrar_evento(
                self.object,
                "OUTRO",
                self.request.user,
                "Alteracoes registradas: " + "; ".join(change_log),
            )
        if getattr(self, "_desconto_percentual", Decimal("0.00")) > Decimal("10.00"):
            registrar_evento(
                self.object,
                "OUTRO",
                self.request.user,
                (
                    f"Desconto acima do limite aprovado em edicao ({self._desconto_percentual:.2f}%). "
                    f"Autorizado por: {self._desconto_autorizador.username}."
                ),
            )
        messages.success(self.request, "Venda atualizada com sucesso.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("vendas:venda_detail", kwargs={"pk": self.object.pk})

    def _build_change_log(self, before: Venda, form: VendaForm, formset: ItemVendaFormSet) -> list[str]:
        logs: list[str] = []
        labels = {
            "tipo_documento": "Tipo",
            "cliente": "Cliente",
            "vendedor": "Vendedor",
            "unidade_saida": "Unidade de saida",
            "data_venda": "Data da venda",
            "tipo_pagamento": "Pagamento",
            "numero_parcelas": "Parcelas",
            "intervalo_parcelas_dias": "Intervalo parcelas",
            "primeiro_vencimento": "Primeiro vencimento",
            "acrescimo": "Acrescimo",
            "observacoes": "Observacoes",
        }

        for field_name, label in labels.items():
            old_value = getattr(before, field_name)
            new_value = form.cleaned_data.get(field_name)
            old_repr = str(old_value) if old_value is not None else "-"
            new_repr = str(new_value) if new_value is not None else "-"
            if field_name in ("cliente", "vendedor"):
                old_repr = str(old_value) if old_value else "-"
                new_repr = str(new_value) if new_value else "-"
            if old_repr != new_repr:
                logs.append(f"{label}: {old_repr} -> {new_repr}")

        for item_form in formset.forms:
            cleaned = getattr(item_form, "cleaned_data", None) or {}
            if not cleaned:
                continue
            instance = item_form.instance
            if cleaned.get("DELETE"):
                if instance and instance.pk:
                    logs.append(
                        f"Item removido: {instance.produto.nome} qtd {instance.quantidade}"
                    )
                continue
            produto = cleaned.get("produto")
            quantidade = cleaned.get("quantidade")
            if not instance.pk and produto:
                logs.append(f"Item adicionado: {produto.nome} qtd {quantidade}")
                continue
            if instance.pk and item_form.has_changed():
                item_changes = ", ".join(item_form.changed_data)
                logs.append(f"Item {instance.id} alterado: {item_changes}")

        return logs

    def _usuario_pode_autorizar_desconto(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.groups.filter(name="admin/gestor").exists():
            return True
        return user.username.lower() in {"lucas", "tabatha"}

    def _maior_percentual_desconto(self, itens_forms) -> Decimal:
        maior = Decimal("0.00")
        for item_form in itens_forms:
            data = item_form.cleaned_data or {}
            preco = data.get("preco_unitario") or Decimal("0.00")
            quantidade = data.get("quantidade") or Decimal("0.000")
            desconto = data.get("desconto") or Decimal("0.00")
            bruto = preco * quantidade
            if bruto <= 0 or desconto <= 0:
                continue
            percentual = ((desconto / bruto) * Decimal("100.00")).quantize(Decimal("0.01"))
            if percentual > maior:
                maior = percentual
        return maior

    def _validar_autorizacao_desconto(self, itens_forms) -> bool:
        self._desconto_percentual = self._maior_percentual_desconto(itens_forms)
        self._desconto_autorizador = None
        if self._desconto_percentual <= Decimal("10.00"):
            return True

        if self._usuario_pode_autorizar_desconto(self.request.user):
            self._desconto_autorizador = self.request.user
            return True

        usuario_aut = (self.request.POST.get("desconto_autorizador") or "").strip()
        senha_aut = (self.request.POST.get("desconto_senha") or "").strip()
        if not usuario_aut or not senha_aut:
            messages.error(
                self.request,
                (
                    f"Desconto de {self._desconto_percentual:.2f}% excede o limite de 10%. "
                    "Informe usuário e senha de administrador/gerente para autorizar."
                ),
            )
            return False

        autorizado = authenticate(self.request, username=usuario_aut, password=senha_aut)
        if not self._usuario_pode_autorizar_desconto(autorizado):
            messages.error(self.request, "Credencial de autorização inválida para desconto acima de 10%.")
            return False
        self._desconto_autorizador = autorizado
        return True


class VendaConfirmarView(VendasAccessMixin, View):
    def post(self, request, *args, **kwargs):
        venda = Venda.objects.get(pk=kwargs["pk"])
        confirmar_venda(venda, request.user)
        messages.success(request, "Venda confirmada.")
        return redirect("vendas:venda_detail", pk=venda.pk)


class VendaFaturarView(VendasAccessMixin, View):
    def post(self, request, *args, **kwargs):
        venda = Venda.objects.get(pk=kwargs["pk"])
        try:
            result = faturar_venda(venda, request.user)
        except Exception as exc:
            messages.error(request, f"Falha ao faturar: {exc}")
            return redirect("vendas:venda_detail", pk=venda.pk)

        if result.already_processed:
            messages.info(request, "Venda ja estava faturada/finalizada; nenhum efeito novo foi aplicado.")
        else:
            messages.success(
                request,
                (
                    "Venda faturada. "
                    f"Estoque: {result.movimentos_criados} | "
                    f"Recebiveis: {result.recebiveis_criados} | "
                    f"Boletos: {result.boletos_criados}"
                ),
            )
        return redirect("vendas:venda_detail", pk=venda.pk)


class OrcamentoConverterView(VendasAccessMixin, View):
    def post(self, request, *args, **kwargs):
        venda = Venda.objects.get(pk=kwargs["pk"])
        try:
            converter_orcamento_em_venda(venda, request.user)
            messages.success(request, "Orçamento convertido em venda.")
        except Exception as exc:
            messages.error(request, f"Falha ao converter orçamento: {exc}")
        return redirect("vendas:venda_detail", pk=venda.pk)


class VendaPDFView(VendasAccessMixin, View):
    def get(self, request, *args, **kwargs):
        venda = (
            Venda.objects.select_related("cliente", "vendedor")
            .prefetch_related("itens__produto")
            .get(pk=kwargs["pk"])
        )
        filename = f"{venda.codigo_identificacao}.pdf"
        try:
            # PDF premium com identidade visual quando reportlab estiver disponivel.
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm
            from reportlab.lib import colors
            from reportlab.pdfgen import canvas

            def wrap_text(pdf, text: str, max_width: float, font_name: str = "Helvetica", font_size: int = 9) -> list[str]:
                text = (text or "").strip()
                if not text:
                    return ["-"]
                pdf.setFont(font_name, font_size)
                words = text.split()
                lines_local: list[str] = []
                current = ""
                for word in words:
                    candidate = word if not current else f"{current} {word}"
                    if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
                        current = candidate
                    else:
                        if current:
                            lines_local.append(current)
                        current = word
                if current:
                    lines_local.append(current)
                return lines_local or ["-"]

            buffer = io.BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=A4)
            width, height = A4

            logo_candidates = [
                settings.BASE_DIR / "core" / "static" / "core" / "img" / "logo_mundo_led.png",
                settings.BASE_DIR / "core" / "static" / "core" / "img" / "logo.jpg",
            ]
            logo_path = None
            for candidate in logo_candidates:
                if candidate.exists():
                    logo_path = str(candidate)
                    break
            left = 12 * mm
            right = width - 12 * mm
            header_bottom = height - 41 * mm
            if logo_path:
                try:
                    pdf.drawImage(
                        logo_path,
                        left,
                        height - 35 * mm,
                        width=22 * mm,
                        height=22 * mm,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                except Exception:
                    pass
            pdf.setFillColor(colors.HexColor("#111827"))
            pdf.setFont("Helvetica-Bold", 18)
            pdf.drawString(left + 26 * mm, height - 19 * mm, "MUNDO LED")
            pdf.setFont("Helvetica", 10)
            pdf.setFillColor(colors.HexColor("#374151"))
            pdf.drawString(left + 26 * mm, height - 25 * mm, "Documento comercial de venda/orçamento")
            pdf.setFillColor(colors.HexColor("#111827"))
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawRightString(right, height - 18 * mm, venda.codigo_identificacao)
            pdf.setFont("Helvetica", 9)
            pdf.drawRightString(right, height - 25 * mm, f"Gerado em {timezone.localtime():%d/%m/%Y %H:%M}")
            pdf.setStrokeColor(colors.HexColor("#d1d5db"))
            pdf.line(left, header_bottom, right, header_bottom)

            y = header_bottom - 8 * mm
            validade = (venda.data_venda + timedelta(days=7)).strftime("%d/%m/%Y")
            if venda.numero_parcelas and venda.numero_parcelas > 1:
                parcelamento = f"{venda.numero_parcelas}x / {venda.intervalo_parcelas_dias or 30} dias"
            else:
                parcelamento = "A vista"

            info_top = y
            info_bottom = y - 37 * mm
            pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
            pdf.roundRect(left, info_bottom, right - left, info_top - info_bottom, 3, fill=0, stroke=1)
            pdf.setFont("Helvetica-Bold", 10)
            pdf.setFillColor(colors.HexColor("#111827"))
            pdf.drawString(left + 3 * mm, info_top - 6 * mm, "Dados da venda")
            pdf.setFont("Helvetica", 10)
            pdf.drawString(left + 3 * mm, info_top - 12 * mm, f"Tipo: {venda.get_tipo_documento_display()}")
            pdf.drawString(left + 3 * mm, info_top - 18 * mm, f"Cliente: {venda.cliente.nome}")
            pdf.drawString(left + 3 * mm, info_top - 24 * mm, f"Vendedor: {venda.vendedor or '-'}")
            pdf.drawString(left + 3 * mm, info_top - 30 * mm, f"Unidade: {unit_label(venda.unidade_saida)}")
            pdf.drawString(left + 3 * mm, info_top - 36 * mm, f"Data: {venda.data_venda:%d/%m/%Y}  |  Validade: {validade}")

            col2 = left + 105 * mm
            pdf.drawString(col2, info_top - 12 * mm, f"Forma de pagamento: {payment_label(venda.tipo_pagamento)}")
            pdf.drawString(col2, info_top - 18 * mm, f"Parcelamento: {parcelamento}")
            if venda.primeiro_vencimento:
                pdf.drawString(col2, info_top - 24 * mm, f"1 vencimento: {venda.primeiro_vencimento:%d/%m/%Y}")
            else:
                pdf.drawString(col2, info_top - 24 * mm, "1 vencimento: -")
            pdf.drawString(col2, info_top - 30 * mm, f"Status: {venda.get_status_display()}")
            y = info_bottom - 9 * mm

            # Header da tabela de itens
            x0 = left
            x_prod = x0
            x_qtd = 114 * mm
            x_unit = 130 * mm
            x_desc = 148 * mm
            x_sub = 170 * mm
            x_end = right
            row_h = 8 * mm

            pdf.setFillColor(colors.HexColor("#f3f4f6"))
            pdf.rect(x0, y - row_h + 2, x_end - x0, row_h, fill=1, stroke=0)
            pdf.setFillColor(colors.HexColor("#111827"))
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(x_prod + 1.5, y - 3.4, "Produto")
            pdf.drawString(x_qtd + 1, y - 3.4, "Qtd")
            pdf.drawString(x_unit + 1, y - 3.4, "Unit. R$")
            pdf.drawString(x_desc + 1, y - 3.4, "Desc. R$")
            pdf.drawString(x_sub + 1, y - 3.4, "Subtotal")
            y -= row_h + 2

            pdf.setFont("Helvetica", 10)
            for item in venda.itens.all():
                if y < 45 * mm:
                    pdf.showPage()
                    y = height - 26 * mm
                    pdf.setFont("Helvetica-Bold", 11)
                    pdf.setFillColor(colors.HexColor("#111827"))
                    pdf.drawString(left, y, f"MUNDO LED | {venda.codigo_identificacao}")
                    y -= 7 * mm
                    pdf.setFillColor(colors.HexColor("#f3f4f6"))
                    pdf.rect(x0, y - row_h + 2, x_end - x0, row_h, fill=1, stroke=0)
                    pdf.setFillColor(colors.HexColor("#111827"))
                    pdf.setFont("Helvetica-Bold", 10)
                    pdf.drawString(x_prod + 1.5, y - 3.4, "Produto")
                    pdf.drawString(x_qtd + 1, y - 3.4, "Qtd")
                    pdf.drawString(x_unit + 1, y - 3.4, "Unit. R$")
                    pdf.drawString(x_desc + 1, y - 3.4, "Desc. R$")
                    pdf.drawString(x_sub + 1, y - 3.4, "Subtotal")
                    y -= row_h + 2
                    pdf.setFont("Helvetica", 10)

                produto_lines = wrap_text(pdf, item.produto.nome, max_width=(x_qtd - x_prod - 6), font_size=10)
                item_lines = max(1, len(produto_lines))
                current_row_h = max(row_h, item_lines * 5 * mm)

                pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
                pdf.rect(x0, y - current_row_h + 1.2, x_end - x0, current_row_h, fill=0, stroke=1)
                pdf.line(x_qtd, y + 1.2, x_qtd, y - current_row_h + 1.2)
                pdf.line(x_unit, y + 1.2, x_unit, y - current_row_h + 1.2)
                pdf.line(x_desc, y + 1.2, x_desc, y - current_row_h + 1.2)
                pdf.line(x_sub, y + 1.2, x_sub, y - current_row_h + 1.2)

                text_y = y - 4.2
                for idx, pline in enumerate(produto_lines):
                    pdf.drawString(x_prod + 1.5, text_y - (idx * 4.7 * mm), pline)
                pdf.drawRightString(x_unit - 1.2, text_y, str(item.quantidade))
                pdf.drawRightString(x_desc - 1.2, text_y, format_brl(item.preco_unitario, decimals=2).replace("R$ ", ""))
                pdf.drawRightString(x_sub - 1.2, text_y, format_brl(item.desconto, decimals=2).replace("R$ ", ""))
                pdf.drawRightString(x_end - 1.5, text_y, format_brl(item.subtotal, decimals=2).replace("R$ ", ""))
                y -= current_row_h + 2

            y -= 5 * mm
            resumo_top = y
            resumo_bottom = y - 27 * mm
            if resumo_bottom < 32 * mm:
                pdf.showPage()
                y = height - 26 * mm
                resumo_top = y
                resumo_bottom = y - 27 * mm
            pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
            pdf.roundRect(left, resumo_bottom, right - left, resumo_top - resumo_bottom, 3, fill=0, stroke=1)
            pdf.setFont("Helvetica-Bold", 11)
            pdf.setFillColor(colors.HexColor("#111827"))
            pdf.drawString(left + 3 * mm, resumo_top - 6 * mm, "Resumo financeiro")
            pdf.setFont("Helvetica", 10)
            pdf.drawString(left + 3 * mm, resumo_top - 13 * mm, f"Subtotal: {format_brl(venda.subtotal)}")
            pdf.drawString(left + 3 * mm, resumo_top - 19 * mm, f"Desconto total: {format_brl(venda.desconto_total)}")
            pdf.drawString(left + 3 * mm, resumo_top - 25 * mm, f"Acrescimo: {format_brl(venda.acrescimo)}")
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawRightString(right - 3 * mm, resumo_top - 19 * mm, f"TOTAL: {format_brl(venda.total_final)}")
            y = resumo_bottom - 8 * mm

            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(left, y, "Condicoes comerciais")
            y -= 6 * mm
            pdf.setFont("Helvetica", 10)
            pdf.drawString(left, y, "1) Valores sujeitos a confirmacao de estoque no faturamento.")
            y -= 5 * mm
            pdf.drawString(left, y, "2) Prazo de entrega a confirmar com o vendedor.")
            y -= 5 * mm
            pdf.drawString(left, y, "3) Garantia conforme politica interna e fabricante.")
            y -= 8 * mm
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(left, y, "Observações")
            y -= 6 * mm
            pdf.setFont("Helvetica", 10)
            obs_lines = wrap_text(pdf, venda.observacoes or "-", max_width=right - left, font_size=10)
            for obs_line in obs_lines[:8]:
                if y < 45 * mm:
                    pdf.showPage()
                    y = height - 28 * mm
                    pdf.setFont("Helvetica", 10)
                pdf.drawString(left, y, obs_line)
                y -= 5 * mm
            y -= 5 * mm

            pdf.setFont("Helvetica", 10)
            pdf.line(left, y, 90 * mm, y)
            pdf.line(110 * mm, y, 185 * mm, y)
            y -= 5 * mm
            pdf.drawString(left, y, "Assinatura cliente")
            pdf.drawString(110 * mm, y, "Assinatura vendedor")
            y -= 9 * mm
            pdf.drawString(left, y, "MUNDO LED - Documento gerado pelo ERP")
            pdf.showPage()
            pdf.save()
            buffer.seek(0)
            return FileResponse(buffer, as_attachment=True, filename=filename, content_type="application/pdf")
        except Exception:
            lines = _pdf_business_lines(venda)
            if venda.observacoes:
                obs_expanded: list[str] = []
                for line in lines:
                    if line == (venda.observacoes or "-"):
                        obs_expanded.extend(_split_text_plain(venda.observacoes, limit=95))
                    else:
                        obs_expanded.append(line)
                lines = obs_expanded
            return HttpResponse(
                _build_simple_pdf(lines),
                content_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )


class VendaFinalizarView(VendasAccessMixin, View):
    def post(self, request, *args, **kwargs):
        venda = Venda.objects.get(pk=kwargs["pk"])
        try:
            finalizar_venda(venda, request.user)
            messages.success(request, "Venda finalizada.")
        except Exception as exc:
            messages.error(request, f"Falha ao finalizar: {exc}")
        return redirect("vendas:venda_detail", pk=venda.pk)


class VendaCancelarView(VendasAccessMixin, View):
    def post(self, request, *args, **kwargs):
        venda = Venda.objects.get(pk=kwargs["pk"])
        form = CancelarVendaForm(request.POST)
        motivo = ""
        if form.is_valid():
            motivo = form.cleaned_data.get("motivo") or ""
        try:
            result = cancelar_venda(venda, request.user, motivo=motivo)
        except Exception as exc:
            messages.error(request, f"Falha ao cancelar: {exc}")
            return redirect("vendas:venda_detail", pk=venda.pk)

        if result.already_canceled:
            messages.info(request, "Venda ja estava cancelada.")
        else:
            messages.warning(
                request,
                (
                    "Venda cancelada. "
                    f"Reversoes estoque: {result.reversoes_estoque} | "
                    f"Recebiveis cancelados: {result.recebiveis_cancelados} | "
                    f"Boletos cancelados: {result.boletos_cancelados}"
                ),
            )
        return redirect("vendas:venda_detail", pk=venda.pk)


class VendasDashboardView(VendasAccessMixin, TemplateView):
    template_name = "vendas/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        periodo = self.request.GET.get("periodo", "30")
        periodo_dias = int(periodo) if periodo.isdigit() else 30
        dashboard = VendasStatisticsService.resumo(periodo_dias=periodo_dias)
        ctx["dashboard"] = dashboard
        max_hora = max((row["total"] for row in dashboard.get("vendas_por_hora", [])), default=0)
        ctx["max_hora"] = max_hora if max_hora > 0 else 1
        max_periodo = max(
            dashboard.get("resumo_dia", {}).get("total_faturado", 0),
            dashboard.get("resumo_mes", {}).get("total_faturado", 0),
            dashboard.get("resumo_ano", {}).get("total_faturado", 0),
        )
        ctx["max_periodo"] = max_periodo if max_periodo > 0 else 1
        return ctx


class FechamentoCaixaListView(VendasAccessMixin, ListView):
    model = FechamentoCaixaDiario
    template_name = "vendas/fechamento_caixa_list.html"
    context_object_name = "fechamentos"

    def get_paginate_by(self, queryset):
        return get_pagination_params(self.request).page_size

    def get_queryset(self):
        qs = FechamentoCaixaDiario.objects.select_related("criado_por").order_by("-data_referencia", "-id")
        data_ref = (self.request.GET.get("data_referencia") or "").strip()
        if data_ref:
            qs = qs.filter(data_referencia=data_ref)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        data_ref = (self.request.GET.get("data_referencia") or "").strip()
        ctx["form"] = FechamentoCaixaForm(
            initial={"data_referencia": data_ref or timezone.localdate()},
        )
        querydict = self.request.GET.copy()
        querydict.pop("page", None)
        ctx["querystring"] = querydict.urlencode()
        return ctx


class FechamentoCaixaGerarView(VendasAccessMixin, View):
    def post(self, request, *args, **kwargs):
        form = FechamentoCaixaForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe uma data válida para gerar o fechamento de caixa.")
            return redirect("vendas:fechamento_caixa_list")

        data_referencia = form.cleaned_data["data_referencia"]
        observacoes = form.cleaned_data.get("observacoes") or ""
        fechamento = gerar_fechamento_caixa(
            data_referencia=data_referencia,
            usuario=request.user,
            observacoes=observacoes,
        )
        messages.success(
            request,
            f"Fechamento de caixa de {data_referencia:%d/%m/%Y} gerado com sucesso (ID {fechamento.id}).",
        )
        return redirect(f"{reverse('vendas:fechamento_caixa_list')}?data_referencia={data_referencia:%Y-%m-%d}")


class FechamentoCaixaPDFView(VendasAccessMixin, View):
    def get(self, request, *args, **kwargs):
        fechamento = FechamentoCaixaDiario.objects.get(pk=kwargs["pk"])
        if not fechamento.arquivo_pdf:
            messages.error(request, "PDF do fechamento não encontrado.")
            return redirect("vendas:fechamento_caixa_list")
        filename = f"fechamento_caixa_{fechamento.data_referencia:%Y%m%d}_{fechamento.id}.pdf"
        return HttpResponse(
            bytes(fechamento.arquivo_pdf),
            content_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
