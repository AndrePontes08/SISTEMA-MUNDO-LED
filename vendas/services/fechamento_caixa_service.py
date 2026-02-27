from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.services.formato_brl import format_brl, payment_label, unit_label
from vendas.models import FechamentoCaixaDiario, StatusVendaChoices, TipoDocumentoVendaChoices, Venda


def _build_simple_pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "40 800 Td"]
    for idx, line in enumerate(lines):
        if idx > 0:
            commands.append("0 -14 Td")
        esc = (line or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({esc}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="ignore")

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
    )
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(f"5 0 obj << /Length {len(stream)} >> stream\n".encode("latin-1") + stream + b"\nendstream endobj\n")

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


def _seller_label(venda: Venda) -> str:
    if not venda.vendedor:
        return "-"
    full = (venda.vendedor.get_full_name() or "").strip()
    username = (venda.vendedor.username or "").strip()
    if full and full.lower() != username.lower():
        return f"{full} ({username})"
    return username or full or "-"


def _payload_dia(data_referencia) -> dict[str, Any]:
    vendas_qs = (
        Venda.objects.select_related("cliente", "vendedor")
        .prefetch_related("itens__produto", "pagamentos")
        .filter(
            data_venda=data_referencia,
            tipo_documento=TipoDocumentoVendaChoices.VENDA,
        )
        .exclude(status=StatusVendaChoices.CANCELADA)
        .order_by("id")
    )
    vendas = list(vendas_qs)

    totais_pagamento: dict[str, Decimal] = {}
    lista_vendas = []
    total_receita = Decimal("0.00")
    total_descontos = Decimal("0.00")

    for venda in vendas:
        total_receita += venda.total_final or Decimal("0.00")
        total_descontos += venda.desconto_total or Decimal("0.00")
        pagamentos_venda = list(venda.pagamentos.all())
        if pagamentos_venda:
            for pagamento in pagamentos_venda:
                label_pagto = payment_label(pagamento.tipo_pagamento)
                totais_pagamento[label_pagto] = totais_pagamento.get(label_pagto, Decimal("0.00")) + (pagamento.valor or Decimal("0.00"))
        else:
            label_pagto = payment_label(venda.tipo_pagamento)
            totais_pagamento[label_pagto] = totais_pagamento.get(label_pagto, Decimal("0.00")) + (venda.total_final or Decimal("0.00"))

        qtd_itens = Decimal("0")
        itens = []
        for item in venda.itens.all():
            qtd_itens += Decimal(str(item.quantidade or "0"))
            itens.append(
                {
                    "produto": item.produto.nome,
                    "quantidade": str(item.quantidade),
                    "preco_unitario": str(item.preco_unitario),
                    "desconto": str(item.desconto),
                    "subtotal": str(item.subtotal),
                }
            )

        lista_vendas.append(
            {
                "id": venda.id,
                "codigo": venda.codigo_identificacao,
                "cliente": venda.cliente.nome,
                "vendedor": _seller_label(venda),
                "unidade": unit_label(venda.unidade_saida),
                "qtd_itens": str(qtd_itens.quantize(Decimal("0.001"))),
                "pagamentos": [
                    {
                        "tipo_pagamento": payment_label(p.tipo_pagamento),
                        "valor": str(p.valor or Decimal("0.00")),
                    }
                    for p in pagamentos_venda
                ],
                "status": venda.get_status_display(),
                "desconto_total": str(venda.desconto_total or Decimal("0.00")),
                "total_final": str(venda.total_final or Decimal("0.00")),
                "observacoes": venda.observacoes or "",
                "itens": itens,
            }
        )

    totais_pagamento_str = {k: str(v.quantize(Decimal("0.01"))) for k, v in totais_pagamento.items()}
    return {
        "data_referencia": data_referencia.isoformat(),
        "total_vendas": len(lista_vendas),
        "total_receita": str(total_receita.quantize(Decimal("0.01"))),
        "total_descontos": str(total_descontos.quantize(Decimal("0.01"))),
        "totais_por_pagamento": totais_pagamento_str,
        "vendas": lista_vendas,
    }


def _pdf_fechamento(payload: dict[str, Any], observacoes: str = "") -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        left = 12 * mm
        right = width - 12 * mm
        line_h = 4.6 * mm
        y = height - 15 * mm

        def wrap_text(text: str, max_width: float, font_name: str = "Helvetica", font_size: int = 8.6) -> list[str]:
            text = (text or "").strip()
            if not text:
                return ["-"]
            pdf.setFont(font_name, font_size)
            words = text.split()
            lines: list[str] = []
            current = ""
            for word in words:
                candidate = word if not current else f"{current} {word}"
                if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
            return lines or ["-"]

        def page_header() -> None:
            nonlocal y
            logo_candidates = [
                settings.BASE_DIR / "core" / "static" / "core" / "img" / "logo_mundo_led.png",
                settings.BASE_DIR / "core" / "static" / "core" / "img" / "logo.jpg",
            ]
            logo_path = None
            for candidate in logo_candidates:
                if candidate.exists():
                    logo_path = str(candidate)
                    break
            if logo_path:
                try:
                    pdf.drawImage(
                        logo_path,
                        left,
                        height - 31 * mm,
                        width=18 * mm,
                        height=18 * mm,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                except Exception:
                    pass

            pdf.setFillColor(colors.HexColor("#111827"))
            pdf.setFont("Helvetica-Bold", 15)
            pdf.drawString(left + 21 * mm, height - 17 * mm, "MUNDO LED")
            pdf.setFont("Helvetica", 9)
            pdf.setFillColor(colors.HexColor("#374151"))
            pdf.drawString(left + 21 * mm, height - 22 * mm, "Relatorio de fechamento diario de caixa")
            pdf.setFillColor(colors.HexColor("#111827"))
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawRightString(right, height - 16 * mm, f"Data de referencia: {payload['data_referencia']}")
            pdf.setFont("Helvetica", 8.4)
            pdf.drawRightString(right, height - 21 * mm, f"Gerado em {timezone.localtime():%d/%m/%Y %H:%M}")
            pdf.setStrokeColor(colors.HexColor("#d1d5db"))
            pdf.line(left, height - 33 * mm, right, height - 33 * mm)
            y = height - 39 * mm

        def ensure_space(required_height: float) -> None:
            nonlocal y
            if y - required_height < 16 * mm:
                pdf.showPage()
                page_header()

        page_header()

        # resumo
        pay_rows = list(payload["totais_por_pagamento"].items())
        resumo_h = max(38 * mm, (24 + max(1, len(pay_rows)) * 5.2) * mm)
        ensure_space(resumo_h + 4 * mm)
        resumo_top = y
        resumo_bottom = y - resumo_h
        pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
        pdf.roundRect(left, resumo_bottom, right - left, resumo_h, 3, fill=0, stroke=1)

        inner_y = resumo_top - 5 * mm
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(left + 3 * mm, inner_y, "Resumo do dia")
        inner_y -= 7 * mm
        pdf.setFont("Helvetica", 11)
        pdf.drawString(left + 3 * mm, inner_y, f"Total de vendas: {payload['total_vendas']}")
        inner_y -= line_h
        pdf.drawString(left + 3 * mm, inner_y, f"Descontos totais: {format_brl(payload['total_descontos'])}")
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawRightString(right - 3 * mm, resumo_top - 10.5 * mm, f"Receita total: {format_brl(payload['total_receita'])}")

        inner_y -= 5 * mm
        pdf.setFont("Helvetica-Bold", 10.2)
        pdf.drawString(left + 3 * mm, inner_y, "Totais por forma de pagamento")
        inner_y -= line_h
        pdf.setFont("Helvetica", 10)
        if pay_rows:
            for pagamento, total in pay_rows:
                pdf.drawString(left + 7 * mm, inner_y, f"- {pagamento}: {format_brl(total)}")
                inner_y -= line_h
        else:
            pdf.drawString(left + 7 * mm, inner_y, "-")

        y = resumo_bottom - 7 * mm

        # secao vendas
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(left, y, "Secao 1 - Vendas do dia")
        y -= 6 * mm

        col = {
            "codigo": left,
            "cliente": left + 24 * mm,
            "vendedor": left + 90 * mm,
            "pagto": left + 126 * mm,
            "itens": left + 163 * mm,
            "total": left + 174 * mm,
        }

        def draw_header_table() -> None:
            nonlocal y
            ensure_space(10 * mm)
            pdf.setFillColor(colors.HexColor("#f3f4f6"))
            pdf.rect(left, y - 6 * mm, right - left, 7 * mm, fill=1, stroke=0)
            pdf.setFillColor(colors.HexColor("#111827"))
            pdf.setFont("Helvetica-Bold", 8.2)
            pdf.drawString(col["codigo"] + 1.2, y - 3.8 * mm, "Codigo")
            pdf.drawString(col["cliente"] + 1.2, y - 3.8 * mm, "Cliente")
            pdf.drawString(col["vendedor"] + 1.2, y - 3.8 * mm, "Vendedor")
            pdf.drawString(col["pagto"] + 1.2, y - 3.8 * mm, "Pagamento")
            pdf.drawString(col["itens"] + 1.2, y - 3.8 * mm, "Itens")
            pdf.drawString(col["total"] + 1.2, y - 3.8 * mm, "Total")
            y -= 8 * mm

        draw_header_table()

        for venda in payload["vendas"]:
            pagamentos_texto = " | ".join([f"{row['tipo_pagamento']}: {format_brl(row['valor'])}" for row in venda.get("pagamentos", [])]) or "-"
            cliente_lines = wrap_text(venda["cliente"], max_width=(col["vendedor"] - col["cliente"] - 2 * mm), font_size=8.1)[:2]
            pagto_lines = wrap_text(pagamentos_texto, max_width=(col["itens"] - col["pagto"] - 2 * mm), font_size=7.9)[:2]
            row_lines = max(len(cliente_lines), len(pagto_lines), 1)
            row_h = max(7.2 * mm, (row_lines * 4.2 * mm) + 2.0 * mm)
            ensure_space(row_h + 2 * mm)
            if y < 24 * mm:
                draw_header_table()

            pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
            pdf.rect(left, y - row_h + 1, right - left, row_h, fill=0, stroke=1)
            for x in (col["cliente"], col["vendedor"], col["pagto"], col["itens"], col["total"]):
                pdf.line(x, y + 1, x, y - row_h + 1)

            base_y = y - 3.6 * mm
            pdf.setFont("Helvetica", 8.1)
            pdf.drawString(col["codigo"] + 1.2, base_y, venda["codigo"])
            for i, line in enumerate(cliente_lines):
                pdf.drawString(col["cliente"] + 1.2, base_y - (i * 4.1 * mm), line)
            pdf.drawString(col["vendedor"] + 1.2, base_y, venda["vendedor"])
            for i, line in enumerate(pagto_lines):
                pdf.drawString(col["pagto"] + 1.2, base_y - (i * 4.1 * mm), line)

            qtd_txt = str(venda.get("qtd_itens", "0")).split(".")[0]
            pdf.drawRightString(col["total"] - 1.0, base_y, qtd_txt)
            pdf.setFont("Helvetica-Bold", 8.2)
            pdf.drawRightString(right - 1.0, base_y, format_brl(venda["total_final"]).replace("R$ ", ""))
            y -= row_h + 1.5 * mm

        y -= 2 * mm
        ensure_space(18 * mm)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left, y, "Observacoes do fechamento")
        y -= 5.5 * mm
        pdf.setFont("Helvetica", 9.5)
        obs_lines = wrap_text(f"Observacoes do fechamento: {observacoes or '-'}", max_width=(right - left), font_size=9.2)
        for line in obs_lines[:6]:
            ensure_space(6 * mm)
            pdf.drawString(left, y, line)
            y -= 5 * mm

        pdf.save()
        buffer.seek(0)
        return buffer.getvalue()
    except Exception:
        lines = [
            "MUNDO LED - FECHAMENTO DIARIO DE CAIXA",
            f"Data de referencia: {payload['data_referencia']}",
            "",
            "SECAO 1 - VENDAS DO DIA",
        ]
        for venda in payload["vendas"]:
            pagamentos_txt = " | ".join([f"{p['tipo_pagamento']}: {format_brl(p['valor'])}" for p in venda.get("pagamentos", [])]) or "-"
            lines.append(
                f"Venda {venda['codigo']} | Cliente {venda['cliente']} | Vendedor {venda['vendedor']} | Pgto {pagamentos_txt} | Total {format_brl(venda['total_final'])}"
            )
        lines.extend(
            [
                "",
                "SECAO 2 - OBSERVACOES",
                f"Total de vendas: {payload['total_vendas']}",
                f"Receita total: {format_brl(payload['total_receita'])}",
                f"Descontos totais: {format_brl(payload['total_descontos'])}",
                f"Observacoes: {observacoes or '-'}",
            ]
        )
        return _build_simple_pdf(lines)


@transaction.atomic
def gerar_fechamento_caixa(*, data_referencia, usuario=None, observacoes: str = "") -> FechamentoCaixaDiario:
    payload = _payload_dia(data_referencia)
    pdf_bytes = _pdf_fechamento(payload, observacoes=observacoes)

    fechamento = FechamentoCaixaDiario.objects.create(
        data_referencia=data_referencia,
        total_vendas=int(payload["total_vendas"]),
        total_receita=Decimal(payload["total_receita"]),
        total_descontos=Decimal(payload["total_descontos"]),
        totais_por_pagamento=payload["totais_por_pagamento"],
        observacoes=observacoes or "",
        detalhes_json=payload,
        arquivo_pdf=pdf_bytes,
        criado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
    )
    return fechamento
