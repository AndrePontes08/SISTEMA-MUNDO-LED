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
    nome_unidade = UnidadeLoja(unidade).label

    for item in itens:
        produto = item["produto"]
        quantidade_contada = Decimal(item["quantidade_contada"]).quantize(Decimal("0.001"))
        if quantidade_contada < 0:
            raise ValueError("Quantidade contada não pode ser negativa.")

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

    return ContagemRapidaResult(total_itens=len(itens), itens_ajustados=itens_ajustados)
