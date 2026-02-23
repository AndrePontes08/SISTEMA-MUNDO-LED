from __future__ import annotations

from decimal import Decimal

from vendas.models import Venda


def recalcular_totais(venda: Venda) -> Venda:
    subtotal = Decimal("0.00")
    desconto_total = Decimal("0.00")
    for item in venda.itens.all():
        subtotal += item.subtotal
        desconto_total += item.desconto or Decimal("0.00")

    total_final = subtotal + (venda.acrescimo or Decimal("0.00"))
    venda.subtotal = subtotal.quantize(Decimal("0.01"))
    venda.desconto_total = desconto_total.quantize(Decimal("0.01"))
    venda.total_final = total_final.quantize(Decimal("0.01"))
    venda.save(update_fields=["subtotal", "desconto_total", "total_final", "atualizado_em"])
    return venda

