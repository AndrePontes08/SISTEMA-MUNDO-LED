from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from compras.models import Produto
from estoque.models import ProdutoEstoque, ProdutoEstoqueUnidade, UnidadeLoja
from estoque.services.estoque_service import registrar_ajuste
from estoque.services.unidade_estoque_service import garantir_unidades_produto


@dataclass(frozen=True)
class ContagemRapidaResult:
    total_itens: int
    itens_ajustados: int


def garantir_estoque_unidades_produto(produto: Produto) -> None:
    garantir_unidades_produto(produto)


def _sincronizar_saldo_consolidado(produto: Produto) -> None:
    total_unidades = (
        ProdutoEstoqueUnidade.objects.filter(produto=produto)
        .aggregate(total=Sum("saldo_atual"))
        .get("total")
        or Decimal("0.000")
    )
    cfg, _ = ProdutoEstoque.objects.get_or_create(produto=produto)
    cfg.saldo_atual = total_unidades.quantize(Decimal("0.001"))
    cfg.save(update_fields=["saldo_atual", "atualizado_em"])


@transaction.atomic
def aplicar_contagem_rapida(
    *,
    unidade: str,
    itens: list[dict],
    usuario=None,
    data_contagem=None,
    observacao: str = "",
) -> ContagemRapidaResult:
    if not itens:
        raise ValueError("Informe ao menos um item para contagem.")
    if data_contagem is None:
        data_contagem = timezone.localdate()

    itens_ajustados = 0
    produtos_tocados: set[int] = set()
    custos_tocados: dict[int, Decimal] = {}
    nome_unidade = UnidadeLoja(unidade).label

    for item in itens:
        produto = item["produto"]
        quantidade_contada = Decimal(item["quantidade_contada"]).quantize(Decimal("0.001"))
        valor_unitario_raw = item.get("valor_unitario")
        if quantidade_contada < 0:
            raise ValueError("Quantidade contada não pode ser negativa.")
        if valor_unitario_raw is not None and str(valor_unitario_raw) != "":
            valor_unitario = Decimal(valor_unitario_raw).quantize(Decimal("0.0001"))
            if valor_unitario < 0:
                raise ValueError("Valor unitário não pode ser negativo.")
            custos_tocados[produto.id] = valor_unitario

        garantir_estoque_unidades_produto(produto)
        saldo_unidade, _ = ProdutoEstoqueUnidade.objects.select_for_update().get_or_create(
            produto=produto,
            unidade=unidade,
            defaults={"saldo_atual": Decimal("0.000")},
        )

        saldo_anterior = (saldo_unidade.saldo_atual or Decimal("0.000")).quantize(Decimal("0.001"))
        diferenca = (quantidade_contada - saldo_anterior).quantize(Decimal("0.001"))
        produtos_tocados.add(produto.id)

        if diferenca != 0:
            detalhe = (
                f"Contagem rapida [{nome_unidade}] | anterior={saldo_anterior} "
                f"| contado={quantidade_contada} | diff={diferenca}"
            )
            if observacao:
                detalhe = f"{detalhe} | obs={observacao}"
            registrar_ajuste(
                produto=produto,
                quantidade=diferenca,
                data_movimento=data_contagem,
                observacao=detalhe,
            )
            itens_ajustados += 1

        saldo_unidade.saldo_atual = quantidade_contada
        saldo_unidade.save(update_fields=["saldo_atual", "atualizado_em"])

    for produto_id in produtos_tocados:
        produto = Produto.objects.get(pk=produto_id)
        _sincronizar_saldo_consolidado(produto)
        if produto_id in custos_tocados:
            cfg, _ = ProdutoEstoque.objects.get_or_create(produto=produto)
            cfg.custo_medio = custos_tocados[produto_id]
            cfg.save(update_fields=["custo_medio", "atualizado_em"])

    return ContagemRapidaResult(total_itens=len(itens), itens_ajustados=itens_ajustados)
