"""
Service para estatísticas e análises de compras
Fornece dados agregados, tendências e insights
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone

from compras.models import Compra, ItemCompra, Fornecedor, CentroCustoChoices


class ComprasStatisticsService:
    """Serviço de estatísticas avançadas de compras"""

    @staticmethod
    def obter_estatisticas_gerais() -> dict:
        """Obtém estatísticas gerais de compras"""
        total_compras = Compra.objects.count()
        total_itens = ItemCompra.objects.count()
        total_valor = Compra.objects.aggregate(Sum('valor_total'))['valor_total__sum'] or Decimal('0')
        total_fornecedores = Fornecedor.objects.count()

        return {
            'total_compras': total_compras,
            'total_itens': total_itens,
            'total_valor': total_valor,
            'total_fornecedores': total_fornecedores,
            'ticket_medio': total_valor / total_compras if total_compras > 0 else Decimal('0'),
        }

    @staticmethod
    def obter_top_fornecedores(limit: int = 10) -> list:
        """Retorna os fornecedores com maior volume de compras"""
        return (
            Fornecedor.objects.annotate(
                total_valor=Sum('compras__valor_total'),
                quantidade_compras=Count('compras'),
            )
            .filter(total_valor__isnull=False)
            .order_by('-total_valor')[:limit]
            .values('id', 'nome', 'total_valor', 'quantidade_compras')
        )

    @staticmethod
    def obter_produtos_mais_comprados(limit: int = 10) -> list:
        """Retorna os produtos mais frequentemente adquiridos"""
        return (
            ItemCompra.objects.values('produto__nome', 'produto__id')
            .annotate(
                quantidade_total=Sum('quantidade'),
                valor_total=Sum(Sum('preco_unitario')),
                vezes_comprado=Count('id'),
            )
            .order_by('-vezes_comprado')[:limit]
        )

    @staticmethod
    def obter_compras_por_centro_custo() -> dict:
        """Retorna estatísticas por centro de custo"""
        result = {}
        for choice_val, choice_label in CentroCustoChoices.choices:
            stats = Compra.objects.filter(centro_custo=choice_val).aggregate(
                total_valor=Sum('valor_total'),
                quantidade=Count('id'),
            )
            result[choice_label] = {
                'valor': stats['total_valor'] or Decimal('0'),
                'quantidade': stats['quantidade'] or 0,
            }
        return result

    @staticmethod
    def obter_compras_por_periodo(dias: int = 30) -> list:
        """Retorna compras agrupadas por período (últimos N dias)"""
        data_inicio = timezone.now() - timedelta(days=dias)
        compras = (
            Compra.objects
            .filter(data_compra__gte=data_inicio.date())
            .extra(select={'data': 'DATE(data_compra)'})
            .values('data')
            .annotate(
                total=Sum('valor_total'),
                quantidade=Count('id'),
            )
            .order_by('data')
        )
        return list(compras)

    @staticmethod
    def obter_tendencias() -> dict:
        """Analisa tendências de compra"""
        hoje = timezone.now().date()
        mes_atual = hoje.month
        ano_atual = hoje.year

        # Gastos do mês atual
        gasto_mes = Compra.objects.filter(
            data_compra__month=mes_atual,
            data_compra__year=ano_atual,
        ).aggregate(Sum('valor_total'))['valor_total__sum'] or Decimal('0')

        # Gastos do mês anterior
        mes_anterior = mes_atual - 1 if mes_atual > 1 else 12
        ano_anterior = ano_atual if mes_atual > 1 else ano_atual - 1
        gasto_mes_anterior = Compra.objects.filter(
            data_compra__month=mes_anterior,
            data_compra__year=ano_anterior,
        ).aggregate(Sum('valor_total'))['valor_total__sum'] or Decimal('0')

        # Calcular variação
        variacao = Decimal('0')
        if gasto_mes_anterior > 0:
            variacao = ((gasto_mes - gasto_mes_anterior) / gasto_mes_anterior) * 100

        return {
            'gasto_mes_atual': gasto_mes,
            'gasto_mes_anterior': gasto_mes_anterior,
            'variacao_percentual': variacao,
            'tendencia': 'ALTA' if variacao > 0 else 'BAIXA' if variacao < 0 else 'ESTÁVEL',
        }

    @staticmethod
    def obter_fornecedores_por_categoria() -> dict:
        """Agrupa fornecedores por volume de compras"""
        fornecedores = Fornecedor.objects.annotate(
            total_valor=Sum('compras__valor_total'),
        ).filter(total_valor__isnull=False).values('nome', 'total_valor')

        categorias = {
            'premium': [],  # > R$ 100k
            'principal': [],  # R$ 50k - 100k
            'secundario': [],  # R$ 10k - 50k
            'ocasional': [],  # < R$ 10k
        }

        for f in fornecedores:
            valor = f['total_valor'] or Decimal('0')
            if valor > Decimal('100000'):
                categorias['premium'].append(f)
            elif valor > Decimal('50000'):
                categorias['principal'].append(f)
            elif valor > Decimal('10000'):
                categorias['secundario'].append(f)
            else:
                categorias['ocasional'].append(f)

        return categorias

    @staticmethod
    def obter_precos_por_produto(produto_id: int, dias: int = 180) -> list:
        """Retorna histórico de preços por fornecedor para um produto no período (últimos N dias).

        Resultado: lista de dicts {fornecedor_id, fornecedor_nome, ultimo_preco, preco_medio, quantidade_total}
        """
        desde = timezone.now().date() - timedelta(days=dias)
        itens = (
            ItemCompra.objects.filter(produto_id=produto_id, compra__data_compra__gte=desde)
            .select_related("compra__fornecedor")
        )

        agreg: dict[int, dict] = {}
        for it in itens:
            f = it.compra.fornecedor
            fid = f.id
            if fid not in agreg:
                agreg[fid] = {"fornecedor_id": fid, "fornecedor_nome": f.nome, "ultimo_preco": it.preco_unitario, "total_valor": it.preco_unitario * it.quantidade, "quantidade_total": it.quantidade, "ultima_data": it.compra.data_compra}
            else:
                # atualiza ultimo_preco se data mais recente
                if it.compra.data_compra >= agreg[fid]["ultima_data"]:
                    agreg[fid]["ultimo_preco"] = it.preco_unitario
                    agreg[fid]["ultima_data"] = it.compra.data_compra
                agreg[fid]["total_valor"] += it.preco_unitario * it.quantidade
                agreg[fid]["quantidade_total"] += it.quantidade

        resultados = []
        for v in agreg.values():
            preco_medio = (v["total_valor"] / v["quantidade_total"]) if v["quantidade_total"] > 0 else Decimal("0")
            resultados.append({
                "fornecedor_id": v["fornecedor_id"],
                "fornecedor_nome": v["fornecedor_nome"],
                "ultimo_preco": v["ultimo_preco"],
                "preco_medio": preco_medio,
                "quantidade_total": v["quantidade_total"],
            })

        # ordenar por preco_medio asc
        resultados.sort(key=lambda x: x["preco_medio"])
        return resultados
