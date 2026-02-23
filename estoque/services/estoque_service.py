from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from compras.models import Produto, Compra, ItemCompra
from estoque.models import ProdutoEstoque, EstoqueMovimento, TipoMovimento, Lote
from estoque.services.alertas_service import verificar_e_criar_alerta


@dataclass(frozen=True)
class MovimentoResult:
    movimento: EstoqueMovimento
    saldo_atual: Decimal


def _get_cfg(produto: Produto) -> ProdutoEstoque:
    cfg, _ = ProdutoEstoque.objects.get_or_create(produto=produto)
    return cfg


@transaction.atomic
def registrar_entrada(
    *,
    produto: Produto,
    quantidade: Decimal,
    data_movimento=None,
    compra: Compra | None = None,
    item_compra: ItemCompra | None = None,
    preco_unitario: Decimal | None = None,
    observacao: str = "",
) -> MovimentoResult:
    if data_movimento is None:
        data_movimento = timezone.localdate()

    cfg = _get_cfg(produto)

    lote = Lote.objects.create(
        produto=produto,
        compra=compra,
        item_compra=item_compra,
        data_entrada=data_movimento,
        quantidade_inicial=quantidade,
        quantidade_restante=quantidade,
    )

    mov = EstoqueMovimento.objects.create(
        produto=produto,
        tipo=TipoMovimento.ENTRADA,
        quantidade=quantidade,
        data_movimento=data_movimento,
        compra=compra,
        item_compra=item_compra,
        lote=lote,
        observacao=observacao or "",
    )

    # Atualiza custo médio se preço for informado (padrão ponderado)
    saldo_previo = (cfg.saldo_atual or Decimal("0"))
    if preco_unitario is not None:
        total_valor_previo = (saldo_previo * (cfg.custo_medio or Decimal("0")))
        total_valor_nova_entrada = (quantidade * preco_unitario)
        novo_saldo = (saldo_previo + quantidade)
        if novo_saldo > 0:
            novo_custo = (total_valor_previo + total_valor_nova_entrada) / novo_saldo
        else:
            novo_custo = cfg.custo_medio or Decimal("0")
        cfg.custo_medio = novo_custo
    cfg.saldo_atual = saldo_previo + quantidade
    cfg.save(update_fields=["saldo_atual", "atualizado_em", "custo_medio"])

    # Entrada pode resolver alerta
    verificar_e_criar_alerta(produto)

    return MovimentoResult(movimento=mov, saldo_atual=cfg.saldo_atual)


@transaction.atomic
def registrar_saida(
    *,
    produto: Produto,
    quantidade: Decimal,
    data_movimento=None,
    observacao: str = "",
) -> MovimentoResult:
    if data_movimento is None:
        data_movimento = timezone.localdate()

    cfg = _get_cfg(produto)

    # Consumir lotes por FIFO
    restante = quantidade
    lotes = Lote.objects.select_for_update().filter(produto=produto, quantidade_restante__gt=Decimal("0.000")).order_by("data_entrada", "id")

    for lote in lotes:
        if restante <= 0:
            break
        consumir = min(lote.quantidade_restante, restante)
        lote.quantidade_restante = (lote.quantidade_restante - consumir).quantize(Decimal("0.001"))
        lote.save(update_fields=["quantidade_restante"])
        restante -= consumir

    if restante > 0:
        # não tem saldo suficiente nos lotes (inconsistência), mas bloqueia para evitar negativo
        raise ValueError("Saldo insuficiente em lotes para registrar saída.")

    mov = EstoqueMovimento.objects.create(
        produto=produto,
        tipo=TipoMovimento.SAIDA,
        quantidade=quantidade,
        data_movimento=data_movimento,
        observacao=observacao or "",
    )

    novo_saldo = (cfg.saldo_atual or Decimal("0")) - quantidade
    if novo_saldo < 0:
        raise ValueError("Saldo insuficiente para registrar saída.")
    cfg.saldo_atual = novo_saldo.quantize(Decimal("0.001"))
    cfg.save(update_fields=["saldo_atual", "atualizado_em"])

    verificar_e_criar_alerta(produto)

    return MovimentoResult(movimento=mov, saldo_atual=cfg.saldo_atual)


@transaction.atomic
def registrar_ajuste(
    *,
    produto: Produto,
    quantidade: Decimal,
    data_movimento=None,
    observacao: str = "",
) -> MovimentoResult:
    """
    Ajuste representa correção manual:
      - quantidade positiva: entra
      - quantidade negativa: sai
    """
    if data_movimento is None:
        data_movimento = timezone.localdate()

    if quantidade == 0:
        raise ValueError("Ajuste não pode ser zero.")

    cfg = _get_cfg(produto)

    tipo = TipoMovimento.AJUSTE

    # Se positivo, cria lote para rastrear idade
    lote = None
    if quantidade > 0:
        lote = Lote.objects.create(
            produto=produto,
            data_entrada=data_movimento,
            quantidade_inicial=quantidade,
            quantidade_restante=quantidade,
        )
    else:
        # se negativo, consome FIFO
        registrar_saida(produto=produto, quantidade=abs(quantidade), data_movimento=data_movimento, observacao=f"AJUSTE: {observacao}")
        # já cria movimento SAIDA; para manter “um único movimento”, preferimos registrar ajuste como evento próprio
        # então voltamos e criamos o evento de ajuste também.
        pass

    mov = EstoqueMovimento.objects.create(
        produto=produto,
        tipo=tipo,
        quantidade=abs(quantidade),
        data_movimento=data_movimento,
        lote=lote,
        observacao=observacao or "",
    )

    if quantidade > 0:
        cfg.saldo_atual = (cfg.saldo_atual or Decimal("0")) + quantidade
    else:
        cfg.saldo_atual = (cfg.saldo_atual or Decimal("0")) - abs(quantidade)

    if cfg.saldo_atual < 0:
        raise ValueError("Ajuste resultaria em saldo negativo.")
    cfg.saldo_atual = cfg.saldo_atual.quantize(Decimal("0.001"))
    cfg.save(update_fields=["saldo_atual", "atualizado_em"])

    verificar_e_criar_alerta(produto)

    return MovimentoResult(movimento=mov, saldo_atual=cfg.saldo_atual)
