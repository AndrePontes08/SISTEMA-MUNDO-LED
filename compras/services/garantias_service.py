from __future__ import annotations

from django.db import transaction

from compras.models import Garantia, ItemCompra


@transaction.atomic
def criar_garantia(
    *,
    item: ItemCompra,
    data_inicio,
    data_fim,
    arquivo=None,
    observacao: str = "",
) -> Garantia:
    g = Garantia(
        item=item,
        data_inicio=data_inicio,
        data_fim=data_fim,
        observacao=observacao or "",
    )
    if arquivo:
        g.arquivo = arquivo
    g.full_clean()
    g.save()
    return g
