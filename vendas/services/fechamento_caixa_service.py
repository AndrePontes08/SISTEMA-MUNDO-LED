from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.conf import settings
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


def _payload_dia(data_referencia) -> dict[str, Any]:
    vendas_qs = (
        Venda.objects.select_related("cliente", "vendedor")
        .prefetch_related("itens__produto")
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
        label_pagto = payment_label(venda.tipo_pagamento)
        totais_pagamento[label_pagto] = totais_pagamento.get(label_pagto, Decimal("0.00")) + (venda.total_final or Decimal("0.00"))

        itens = []
        for item in venda.itens.all():
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
                "vendedor": venda.vendedor.username if venda.vendedor else "-",
                "unidade": unit_label(venda.unidade_saida),
                "pagamento": label_pagto,
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
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        left = 12 * mm
        right = width - 12 * mm
        logo_candidates = [
            settings.BASE_DIR / "core" / "static" / "core" / "img" / "logo_mundo_led.png",
            settings.BASE_DIR / "core" / "static" / "core" / "img" / "logo.jpg",
        ]
        logo_path = None
        for candidate in logo_candidates:
            if candidate.exists():
                logo_path = str(candidate)
                break

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
        pdf.drawString(left + 26 * mm, height - 25 * mm, "Fechamento diário de caixa")
        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawRightString(right, height - 18 * mm, f"Data: {payload['data_referencia']}")
        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(right, height - 25 * mm, f"Gerado em {timezone.localtime():%d/%m/%Y %H:%M}")
        pdf.setStrokeColor(colors.HexColor("#d1d5db"))
        pdf.line(left, header_bottom, right, header_bottom)

        y = header_bottom - 8 * mm

        # Bloco de resumo do dia
        resumo_top = y
        resumo_bottom = y - 28 * mm
        pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
        pdf.roundRect(left, resumo_bottom, right - left, resumo_top - resumo_bottom, 3, fill=0, stroke=1)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(left + 3 * mm, resumo_top - 6 * mm, "Resumo do dia")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left + 3 * mm, resumo_top - 13 * mm, f"Total de vendas: {payload['total_vendas']}")
        pdf.drawString(left + 3 * mm, resumo_top - 19 * mm, f"Descontos totais: {format_brl(payload['total_descontos'])}")
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawRightString(right - 3 * mm, resumo_top - 13 * mm, f"Receita total: {format_brl(payload['total_receita'])}")
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left + 3 * mm, resumo_top - 25 * mm, "Total por forma de pagamento:")
        pay_line = " | ".join([f"{k}: {format_brl(v)}" for k, v in payload["totais_por_pagamento"].items()]) or "-"
        pdf.setFont("Helvetica", 9)
        pdf.drawString(left + 52 * mm, resumo_top - 25 * mm, pay_line[:120])

        y = resumo_bottom - 8 * mm

        # Seção 1 - detalhamento das vendas
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(left, y, "Seção 1 - Vendas do dia")
        y -= 6 * mm

        for venda in payload["vendas"]:
            if y < 40 * mm:
                pdf.showPage()
                y = height - 20 * mm
                pdf.setFont("Helvetica-Bold", 10)
                pdf.drawString(left, y, f"MUNDO LED | Fechamento diário {payload['data_referencia']}")
                y -= 7 * mm

            pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
            bloco_h = 18 * mm
            if venda["observacoes"]:
                bloco_h += 5 * mm
            pdf.roundRect(left, y - bloco_h, right - left, bloco_h, 2, fill=0, stroke=1)

            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(left + 3 * mm, y - 5 * mm, f"Venda {venda['codigo']} | Cliente: {venda['cliente']}")
            pdf.setFont("Helvetica", 9)
            pdf.drawString(
                left + 3 * mm,
                y - 10 * mm,
                f"Unidade: {venda['unidade']} | Vendedor: {venda['vendedor']} | Status: {venda['status']}",
            )
            pdf.drawString(
                left + 3 * mm,
                y - 14.5 * mm,
                f"Pagamento: {venda['pagamento']} | Desconto: {format_brl(venda['desconto_total'])} | Total: {format_brl(venda['total_final'])}",
            )
            if venda["observacoes"]:
                pdf.drawString(left + 3 * mm, y - 19 * mm, f"Observações: {venda['observacoes'][:90]}")
            y -= bloco_h + 2.5 * mm

            # Itens da venda
            for item in venda["itens"]:
                if y < 28 * mm:
                    pdf.showPage()
                    y = height - 20 * mm
                    pdf.setFont("Helvetica-Bold", 10)
                    pdf.drawString(left, y, f"MUNDO LED | Itens da venda {venda['codigo']}")
                    y -= 7 * mm
                pdf.setFont("Helvetica", 8.6)
                pdf.drawString(
                    left + 4 * mm,
                    y,
                    (
                        f"- {item['produto']} | Qtd {item['quantidade']} | Unit {format_brl(item['preco_unitario'])} | "
                        f"Desc {format_brl(item['desconto'])} | Subtotal {format_brl(item['subtotal'])}"
                    )[:140],
                )
                y -= 4.5 * mm
            y -= 1.5 * mm

        # Seção 2 - resumo final
        if y < 45 * mm:
            pdf.showPage()
            y = height - 20 * mm
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(left, y, "Seção 2 - Resumo consolidado")
        y -= 6 * mm
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left, y, f"Total de vendas: {payload['total_vendas']}")
        y -= 5 * mm
        pdf.drawString(left, y, f"Receita total: {format_brl(payload['total_receita'])}")
        y -= 5 * mm
        pdf.drawString(left, y, f"Descontos totais: {format_brl(payload['total_descontos'])}")
        y -= 5 * mm
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left, y, "Totais por forma de pagamento:")
        y -= 5 * mm
        pdf.setFont("Helvetica", 10)
        for pagamento, total in payload["totais_por_pagamento"].items():
            pdf.drawString(left + 4 * mm, y, f"- {pagamento}: {format_brl(total)}")
            y -= 5 * mm
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left, y, f"Observações do fechamento: {observacoes or '-'}")

        pdf.save()
        buffer.seek(0)
        return buffer.getvalue()
    except Exception:
        lines = [
            "MUNDO LED - FECHAMENTO DIARIO DE CAIXA",
            f"Data de referencia: {payload['data_referencia']}",
            "",
            "SECAO 1 - DETALHAMENTO DAS VENDAS",
        ]
        for venda in payload["vendas"]:
            lines.append(
                f"Venda {venda['codigo']} | Cliente {venda['cliente']} | Pgto {venda['pagamento']} | Total {format_brl(venda['total_final'])}"
            )
        lines.extend(
            [
                "",
                "SECAO 2 - RESUMO",
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
