from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from compras.models import Produto
from estoque.models import ProdutoEstoqueUnidade, TransferenciaEstoque

User = get_user_model()


@dataclass(frozen=True)
class TransferenciaResult:
    transferencia: TransferenciaEstoque
    saldo_origem: Decimal
    saldo_destino: Decimal


@dataclass(frozen=True)
class TransferenciaLoteResult:
    lote_referencia: str
    total_itens: int


@transaction.atomic
def transferir_entre_unidades(
    *,
    produto: Produto,
    unidade_origem: str,
    unidade_destino: str,
    quantidade: Decimal,
    usuario: User | None = None,
    data_transferencia=None,
    observacao: str = "",
    lote_referencia: str = "",
) -> TransferenciaResult:
    if unidade_origem == unidade_destino:
        raise ValueError("Unidade de origem e destino devem ser diferentes.")
    if quantidade <= 0:
        raise ValueError("Quantidade deve ser maior que zero.")
    if data_transferencia is None:
        data_transferencia = timezone.localdate()

    origem, _ = ProdutoEstoqueUnidade.objects.select_for_update().get_or_create(
        produto=produto,
        unidade=unidade_origem,
        defaults={"saldo_atual": Decimal("0.000")},
    )
    destino, _ = ProdutoEstoqueUnidade.objects.select_for_update().get_or_create(
        produto=produto,
        unidade=unidade_destino,
        defaults={"saldo_atual": Decimal("0.000")},
    )

    if origem.saldo_atual < quantidade:
        raise ValueError(
            f"Saldo insuficiente na unidade de origem ({origem.saldo_atual})."
        )

    origem.saldo_atual = (origem.saldo_atual - quantidade).quantize(Decimal("0.001"))
    destino.saldo_atual = (destino.saldo_atual + quantidade).quantize(Decimal("0.001"))
    origem.save(update_fields=["saldo_atual", "atualizado_em"])
    destino.save(update_fields=["saldo_atual", "atualizado_em"])

    transferencia = TransferenciaEstoque.objects.create(
        lote_referencia=lote_referencia,
        produto=produto,
        unidade_origem=unidade_origem,
        unidade_destino=unidade_destino,
        quantidade=quantidade,
        data_transferencia=data_transferencia,
        observacao=observacao,
        usuario=usuario if (usuario and usuario.is_authenticated) else None,
    )

    return TransferenciaResult(
        transferencia=transferencia,
        saldo_origem=origem.saldo_atual,
        saldo_destino=destino.saldo_atual,
    )


@transaction.atomic
def transferir_lote_entre_unidades(
    *,
    itens: list[dict],
    unidade_origem: str,
    unidade_destino: str,
    usuario: User | None = None,
    data_transferencia=None,
    observacao: str = "",
) -> TransferenciaLoteResult:
    if not itens:
        raise ValueError("Informe ao menos um item para transferencia.")
    lote_referencia = f"L{uuid4().hex[:10].upper()}"
    for item in itens:
        produto = item["produto"]
        quantidade = item["quantidade"]
        transferir_entre_unidades(
            produto=produto,
            unidade_origem=unidade_origem,
            unidade_destino=unidade_destino,
            quantidade=quantidade,
            usuario=usuario,
            data_transferencia=data_transferencia,
            observacao=observacao,
            lote_referencia=lote_referencia,
        )
    return TransferenciaLoteResult(lote_referencia=lote_referencia, total_itens=len(itens))
