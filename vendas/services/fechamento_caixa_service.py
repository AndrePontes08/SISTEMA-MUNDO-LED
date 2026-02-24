from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.services.formato_brl import format_brl, unit_label
from vendas.models import FechamentoCaixaDiario, StatusVendaChoices, Venda


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
            status__in=[StatusVendaChoices.FATURADA, StatusVendaChoices.FINALIZADA],
        )
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
        label_pagto = venda.get_tipo_pagamento_display()
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
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 15 * mm

        def draw_line(text: str, font="Helvetica", size=9, step=5):
            nonlocal y
            if y < 18 * mm:
                pdf.showPage()
                y = height - 15 * mm
            pdf.setFont(font, size)
            pdf.drawString(12 * mm, y, text)
            y -= step * mm

        draw_line("MUNDO LED - FECHAMENTO DIARIO DE CAIXA", font="Helvetica-Bold", size=12, step=6)
        draw_line(f"Data de referencia: {payload['data_referencia']}", size=10)
        draw_line("", step=2)
        draw_line("SECAO 1 - DETALHAMENTO DAS VENDAS", font="Helvetica-Bold", size=10)

        for venda in payload["vendas"]:
            draw_line(
                f"Venda {venda['codigo']} | Cliente: {venda['cliente']} | Unidade: {venda['unidade']} | "
                f"Pagamento: {venda['pagamento']}",
                size=9,
            )
            draw_line(
                f"Vendedor: {venda['vendedor']} | Desconto: {format_brl(venda['desconto_total'])} | "
                f"Total: {format_brl(venda['total_final'])}",
                size=9,
            )
            for item in venda["itens"]:
                draw_line(
                    (
                        f"  - {item['produto']} | Qtd {item['quantidade']} | Unit {format_brl(item['preco_unitario'])} | "
                        f"Desc {format_brl(item['desconto'])} | Subtotal {format_brl(item['subtotal'])}"
                    ),
                    size=8,
                    step=4.5,
                )
            if venda["observacoes"]:
                draw_line(f"  Observacoes: {venda['observacoes']}", size=8, step=4.5)
            draw_line("", step=1.6)

        draw_line("", step=2)
        draw_line("SECAO 2 - RESUMO DO DIA", font="Helvetica-Bold", size=10)
        draw_line(f"Total de vendas: {payload['total_vendas']}")
        draw_line(f"Receita total: {format_brl(payload['total_receita'])}")
        draw_line(f"Descontos totais: {format_brl(payload['total_descontos'])}")
        draw_line("Totais por forma de pagamento:", font="Helvetica-Bold", size=9)
        for pagamento, total in payload["totais_por_pagamento"].items():
            draw_line(f"  - {pagamento}: {format_brl(total)}", size=9)
        draw_line(f"Observacoes do fechamento: {observacoes or '-'}", size=9)

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
