from __future__ import annotations

from decimal import Decimal
from django.db import transaction

from compras.models import Compra
from estoque.services.estoque_service import registrar_entrada


@transaction.atomic
def dar_entrada_por_compra(compra: Compra) -> int:
    """
    Cria movimentos de ENTRADA no estoque para cada item da compra.
    - Não duplica: se já existirem movimentos vinculados a item_compra, ignora.
    Retorna quantidade de movimentos criados.
    """
    criados = 0

    compra = (
        Compra.objects.select_related("fornecedor")
        .prefetch_related("itens__produto")
        .get(pk=compra.pk)
    )

    for item in compra.itens.all():
        # já tem movimento para este item?
        if item.movimentos_estoque.filter(tipo="ENTRADA").exists():
            continue

        registrar_entrada(
            produto=item.produto,
            quantidade=(item.quantidade or Decimal("0")).quantize(Decimal("0.001")),
            data_movimento=compra.data_compra,
            compra=compra,
            item_compra=item,
            preco_unitario=(item.preco_unitario or Decimal('0.00')),
            observacao=f"Entrada por compra #{compra.id}",
        )
        criados += 1

    return criados
