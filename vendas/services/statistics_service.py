from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from vendas.models import StatusVendaChoices, Venda


class VendasStatisticsService:
    @staticmethod
    def resumo(periodo_dias: int = 30) -> dict:
        hoje = timezone.localdate()
        inicio = hoje - timedelta(days=max(1, periodo_dias))
        base = Venda.objects.filter(
            data_venda__range=(inicio, hoje),
            status__in=[StatusVendaChoices.FATURADA, StatusVendaChoices.FINALIZADA],
        )

        total_vendas = base.count()
        total_faturado = base.aggregate(
            total=Coalesce(Sum("total_final"), Value(Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2)))
        )["total"]
        ticket_medio = (total_faturado / total_vendas).quantize(Decimal("0.01")) if total_vendas else Decimal("0.00")

        top_produtos = (
            base.values("itens__produto_id", "itens__produto__nome")
            .annotate(
                quantidade=Coalesce(Sum("itens__quantidade"), Value(Decimal("0.000"))),
                total=Coalesce(Sum("itens__subtotal"), Value(Decimal("0.00"))),
            )
            .order_by("-quantidade", "-total")[:10]
        )
        top_clientes = (
            base.values("cliente_id", "cliente__nome")
            .annotate(
                total=Coalesce(Sum("total_final"), Value(Decimal("0.00"))),
                vendas=Count("id"),
            )
            .order_by("-total", "-vendas")[:10]
        )
        vendas_por_status = (
            Venda.objects.filter(data_venda__range=(inicio, hoje))
            .values("status")
            .annotate(total=Count("id"))
            .order_by("status")
        )

        return {
            "periodo_dias": periodo_dias,
            "data_inicio": inicio,
            "data_fim": hoje,
            "total_vendas_faturadas": total_vendas,
            "total_faturado": total_faturado,
            "ticket_medio": ticket_medio,
            "top_produtos": list(top_produtos),
            "top_clientes": list(top_clientes),
            "vendas_por_status": list(vendas_por_status),
        }

