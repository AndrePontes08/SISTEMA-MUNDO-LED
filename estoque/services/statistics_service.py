from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from django.db.models import Sum, F
from django.utils import timezone

from compras.models import Produto
from estoque.models import Lote, EstoqueMovimento, ProdutoEstoque


class EstoqueStatisticsService:
    """Serviços para indicadores de estoque: tempo médio em estoque e giro."""

    @staticmethod
    def tempo_medio_estoque(produto: Produto, dias: int = 365) -> Decimal:
        """Calcula tempo médio (dias) ponderado pelo volume dos lotes do produto no período.

        Usa lotes com `data_entrada` nos últimos `dias` dias. Retorna `Decimal` com dias médios.
        """
        desde = timezone.now().date() - timedelta(days=dias)
        lotes = Lote.objects.filter(produto=produto, data_entrada__gte=desde)
        total_qtd = Decimal("0")
        soma_pesos = Decimal("0")
        for lote in lotes:
            dias_em = lote.dias_em_estoque
            qtd = lote.quantidade_inicial or Decimal("0")
            soma_pesos += qtd * Decimal(dias_em)
            total_qtd += qtd
        if total_qtd == 0:
            return Decimal("0")
        return (soma_pesos / total_qtd).quantize(Decimal("1.00"))

    @staticmethod
    def giro_estoque(produto: Produto, meses: int = 12) -> Decimal:
        """Calcula giro = consumo_periodo / estoque_medio.

        Consumo é soma de movimentos do tipo SAIDA nos últimos `meses` meses.
        Estoque médio aproximado: saldo atual (melhoria futura: média histórica de saldo).
        """
        since = timezone.now().date() - timedelta(days=30 * meses)
        consumo = (
            EstoqueMovimento.objects.filter(produto=produto, tipo="SAIDA", data_movimento__gte=since)
            .aggregate(total=Sum("quantidade"))
            .get("total")
            or Decimal("0")
        )
        cfg = ProdutoEstoque.objects.filter(produto=produto).first()
        estoque_medio = (cfg.saldo_atual if cfg else Decimal("0")) or Decimal("0")
        if estoque_medio == 0:
            return Decimal("0")
        # giro anualizado proporcional ao período
        return (consumo / estoque_medio).quantize(Decimal("0.01"))

    @staticmethod
    def relatorio_geral(dias_estoque: int = 365, meses_giro: int = 12) -> list:
        """Retorna lista de indicadores por produto.

        Cada item: {produto_id, produto_nome, estoque_atual, tempo_medio, giro}
        """
        resultados = []
        produtos = Produto.objects.filter(ativo=True)
        for p in produtos:
            cfg = ProdutoEstoque.objects.filter(produto=p).first()
            estoque = (cfg.saldo_atual if cfg else Decimal("0")) or Decimal("0")
            tempo = EstoqueStatisticsService.tempo_medio_estoque(p, dias=dias_estoque)
            giro = EstoqueStatisticsService.giro_estoque(p, meses=meses_giro)
            resultados.append({
                "produto_id": p.id,
                "produto_nome": p.nome,
                "estoque_atual": estoque,
                "tempo_medio": tempo,
                "giro": giro,
            })
        return resultados
