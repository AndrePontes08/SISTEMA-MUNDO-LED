from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from compras.models import Produto
from estoque.models import EstoqueMovimento, ProdutoEstoqueUnidade, TipoMovimento

from importadores.models import (
    CaixaImportacaoInconsistencia,
    CaixaRelatorioImportacao,
    CaixaRelatorioItem,
    MovimentoVendaEstoque,
)


class EstoqueBaixaService:
    @classmethod
    @transaction.atomic
    def baixar_itens_por_importacao(cls, importacao: CaixaRelatorioImportacao) -> dict[str, int]:
        baixados = 0
        inconsistentes = 0
        detectados = 0

        for item in importacao.itens.select_for_update().all():
            detectados += 1
            result = cls._baixar_item(importacao, item)
            if result:
                baixados += 1
            else:
                inconsistentes += 1

        importacao.itens_detectados = detectados
        importacao.itens_baixados = baixados
        importacao.itens_inconsistentes = inconsistentes
        importacao.save(update_fields=["itens_detectados", "itens_baixados", "itens_inconsistentes", "atualizado_em"])
        return {
            "detectados": detectados,
            "baixados": baixados,
            "inconsistentes": inconsistentes,
        }

    @classmethod
    def _baixar_item(cls, importacao: CaixaRelatorioImportacao, item: CaixaRelatorioItem) -> bool:
        codigo = (item.codigo_mercadoria or "").strip()
        produto = Produto.objects.filter(sku=codigo).first()
        if not produto:
            cls._registrar_inconsistencia(importacao, item, "Produto nao encontrado para codigo de mercadoria.")
            return False

        estoque, _ = ProdutoEstoqueUnidade.objects.select_for_update().get_or_create(
            produto=produto,
            unidade=importacao.unidade,
            defaults={"saldo_atual": Decimal("0.000")},
        )

        qtd = item.quantidade or Decimal("0.000")
        if qtd <= 0:
            cls._registrar_inconsistencia(importacao, item, "Quantidade invalida para baixa.")
            return False

        if estoque.saldo_atual < qtd:
            cls._registrar_inconsistencia(
                importacao,
                item,
                f"Saldo insuficiente na unidade ({estoque.saldo_atual}) para baixar {qtd}.",
            )
            return False

        estoque.saldo_atual = (estoque.saldo_atual - qtd).quantize(Decimal("0.001"))
        estoque.save(update_fields=["saldo_atual", "atualizado_em"])

        mov = EstoqueMovimento.objects.create(
            produto=produto,
            tipo=TipoMovimento.SAIDA,
            quantidade=qtd,
            data_movimento=importacao.data_referencia,
            observacao=f"VENDA PDF Caixa (importacao #{importacao.id}, unidade {importacao.unidade})",
        )
        MovimentoVendaEstoque.objects.create(
            importacao=importacao,
            item=item,
            movimento_estoque=mov,
            unidade=importacao.unidade,
            tipo="VENDA",
        )

        item.produto = produto
        item.estoque_baixado = True
        item.mensagem = ""
        item.save(update_fields=["produto", "estoque_baixado", "mensagem"])
        return True

    @staticmethod
    def _registrar_inconsistencia(importacao: CaixaRelatorioImportacao, item: CaixaRelatorioItem, descricao: str) -> None:
        CaixaImportacaoInconsistencia.objects.create(
            importacao=importacao,
            codigo=item.codigo_mercadoria,
            descricao=descricao,
            detalhes=item.descricao,
        )
        item.estoque_baixado = False
        item.mensagem = descricao[:255]
        item.save(update_fields=["estoque_baixado", "mensagem"])

