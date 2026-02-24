from __future__ import annotations

from decimal import Decimal

from compras.models import Produto
from estoque.models import ProdutoEstoque, ProdutoEstoqueUnidade, UnidadeLoja


def garantir_unidades_produto(produto: Produto) -> None:
    cfg, _ = ProdutoEstoque.objects.get_or_create(produto=produto)
    unidades = list(ProdutoEstoqueUnidade.objects.filter(produto=produto))

    if not unidades:
        ProdutoEstoqueUnidade.objects.create(
            produto=produto,
            unidade=UnidadeLoja.LOJA_1,
            saldo_atual=(cfg.saldo_atual or Decimal("0.000")).quantize(Decimal("0.001")),
        )
        ProdutoEstoqueUnidade.objects.create(
            produto=produto,
            unidade=UnidadeLoja.LOJA_2,
            saldo_atual=Decimal("0.000"),
        )
        return

    presentes = {u.unidade for u in unidades}
    if UnidadeLoja.LOJA_1 not in presentes:
        ProdutoEstoqueUnidade.objects.create(
            produto=produto,
            unidade=UnidadeLoja.LOJA_1,
            saldo_atual=Decimal("0.000"),
        )
    if UnidadeLoja.LOJA_2 not in presentes:
        ProdutoEstoqueUnidade.objects.create(
            produto=produto,
            unidade=UnidadeLoja.LOJA_2,
            saldo_atual=Decimal("0.000"),
        )
