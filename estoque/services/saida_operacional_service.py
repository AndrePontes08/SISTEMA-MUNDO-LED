from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from estoque.models import (
    EstoqueMovimento,
    ProdutoEstoque,
    ProdutoEstoqueUnidade,
    SaidaOperacionalEstoque,
    TipoMovimento,
    UnidadeLoja,
)
from estoque.services.estoque_service import registrar_saida
from estoque.services.unidade_estoque_service import garantir_unidades_produto


@dataclass(frozen=True)
class SaidaOperacionalResult:
    total_itens: int
    itens_processados: int


@transaction.atomic
def registrar_saida_operacional_lote(
    *,
    unidade: str,
    tipo: str,
    itens: list[dict],
    usuario=None,
    data_saida=None,
    observacao: str = "",
) -> SaidaOperacionalResult:
    if not itens:
        raise ValueError("Informe ao menos um item para a saída.")
    if data_saida is None:
        data_saida = timezone.localdate()

    unidade_label = UnidadeLoja(unidade).label
    itens_processados = 0

    for item in itens:
        produto = item["produto"]
        quantidade = Decimal(item["quantidade"]).quantize(Decimal("0.001"))
        if quantidade <= 0:
            raise ValueError("Quantidade deve ser maior que zero.")

        garantir_unidades_produto(produto)
        saldo_unidade = ProdutoEstoqueUnidade.objects.select_for_update().get(
            produto=produto,
            unidade=unidade,
        )
        if saldo_unidade.saldo_atual < quantidade:
            raise ValueError(
                f"Saldo insuficiente para {produto.nome} em {unidade_label}. "
                f"Atual: {saldo_unidade.saldo_atual}."
            )

        # Compatibilidade: bases antigas podem ter saldo consolidado sem lotes.
        # Nesse caso, mantém a baixa consistente no saldo e registra movimento.
        try:
            movimento = registrar_saida(
                produto=produto,
                quantidade=quantidade,
                data_movimento=data_saida,
                observacao=f"Saida operacional [{tipo}] [{unidade_label}] {observacao}".strip(),
            ).movimento
        except ValueError as exc:
            mensagem = str(exc).lower()
            if "lotes" not in mensagem:
                raise
            cfg, _ = ProdutoEstoque.objects.select_for_update().get_or_create(produto=produto)
            if cfg.saldo_atual < quantidade:
                raise
            cfg.saldo_atual = (cfg.saldo_atual - quantidade).quantize(Decimal("0.001"))
            cfg.save(update_fields=["saldo_atual", "atualizado_em"])
            movimento = EstoqueMovimento.objects.create(
                produto=produto,
                tipo=TipoMovimento.SAIDA,
                quantidade=quantidade,
                data_movimento=data_saida,
                observacao=(
                    f"Saida operacional sem lote [{tipo}] [{unidade_label}] {observacao}".strip()
                ),
            )

        saldo_unidade.saldo_atual = (saldo_unidade.saldo_atual - quantidade).quantize(Decimal("0.001"))
        saldo_unidade.save(update_fields=["saldo_atual", "atualizado_em"])

        SaidaOperacionalEstoque.objects.create(
            produto=produto,
            unidade=unidade,
            tipo=tipo,
            quantidade=quantidade,
            data_saida=data_saida,
            observacao=observacao or "",
            usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
            movimento=movimento,
        )
        itens_processados += 1

    return SaidaOperacionalResult(total_itens=len(itens), itens_processados=itens_processados)
