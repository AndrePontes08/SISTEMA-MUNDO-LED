from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db import transaction

from compras.models import Compra, ItemCompra, Produto, Fornecedor


@dataclass(frozen=True)
class ItemPayload:
    produto: Produto
    quantidade: Decimal
    preco_unitario: Decimal


def recalcular_total(compra: Compra) -> Compra:
    total = Decimal("0.00")
    itens = compra.itens.all()
    for it in itens:
        total += (it.quantidade or Decimal("0")) * (it.preco_unitario or Decimal("0"))
    compra.valor_total = total.quantize(Decimal("0.01"))
    compra.save(update_fields=["valor_total"])
    return compra


@transaction.atomic
def criar_compra_com_itens(
    *,
    fornecedor: Fornecedor,
    centro_custo: str,
    data_compra,
    itens: Iterable[ItemPayload],
    observacoes: str = "",
    nota_fiscal=None,
) -> Compra:
    compra = Compra.objects.create(
        fornecedor=fornecedor,
        centro_custo=centro_custo,
        data_compra=data_compra,
        observacoes=observacoes or "",
        nota_fiscal=nota_fiscal,
    )

    bulk = []
    for p in itens:
        bulk.append(
            ItemCompra(
                compra=compra,
                produto=p.produto,
                quantidade=p.quantidade,
                preco_unitario=p.preco_unitario,
            )
        )
    ItemCompra.objects.bulk_create(bulk)

    # Atualiza o total
    compra = Compra.objects.select_for_update().get(pk=compra.pk)
    compra = recalcular_total(compra)
    return compra
