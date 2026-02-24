from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DateTimeField, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce, ExtractHour
from django.utils import timezone

from vendas.models import StatusVendaChoices, Venda


class VendasStatisticsService:
    @staticmethod
    def _periodo_metrics(base_qs) -> dict:
        total_vendas = base_qs.count()
        total_faturado = base_qs.aggregate(
            total=Coalesce(Sum("total_final"), Value(Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2)))
        )["total"]
        ticket_medio = (total_faturado / total_vendas).quantize(Decimal("0.01")) if total_vendas else Decimal("0.00")
        return {
            "total_vendas": total_vendas,
            "total_faturado": total_faturado,
            "ticket_medio": ticket_medio,
        }

    @staticmethod
    def resumo(periodo_dias: int = 30) -> dict:
        hoje = timezone.localdate()
        inicio = hoje - timedelta(days=max(1, periodo_dias))
        base = Venda.objects.filter(
            data_venda__range=(inicio, hoje),
            status__in=[StatusVendaChoices.FATURADA, StatusVendaChoices.FINALIZADA],
        )

        periodo_metrics = VendasStatisticsService._periodo_metrics(base)

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

        base_hoje = Venda.objects.filter(
            data_venda=hoje,
            status__in=[StatusVendaChoices.FATURADA, StatusVendaChoices.FINALIZADA],
        )
        base_mes = Venda.objects.filter(
            data_venda__year=hoje.year,
            data_venda__month=hoje.month,
            status__in=[StatusVendaChoices.FATURADA, StatusVendaChoices.FINALIZADA],
        )
        base_ano = Venda.objects.filter(
            data_venda__year=hoje.year,
            status__in=[StatusVendaChoices.FATURADA, StatusVendaChoices.FINALIZADA],
        )

        horario_base = (
            Venda.objects.filter(status__in=[StatusVendaChoices.FATURADA, StatusVendaChoices.FINALIZADA])
            .annotate(evento_em=Coalesce("faturada_em", "criado_em", output_field=DateTimeField()))
            .annotate(hora=ExtractHour("evento_em"))
            .values("hora")
            .annotate(total=Count("id"))
            .order_by("hora")
        )
        mapa_horas = {int(row["hora"]): int(row["total"]) for row in horario_base if row["hora"] is not None}
        vendas_por_hora = [{"hora": h, "total": mapa_horas.get(h, 0)} for h in range(24)]
        pico_horario = max(vendas_por_hora, key=lambda row: row["total"]) if vendas_por_hora else {"hora": 0, "total": 0}

        return {
            "periodo_dias": periodo_dias,
            "data_inicio": inicio,
            "data_fim": hoje,
            "total_vendas_faturadas": periodo_metrics["total_vendas"],
            "total_faturado": periodo_metrics["total_faturado"],
            "ticket_medio": periodo_metrics["ticket_medio"],
            "top_produtos": list(top_produtos),
            "top_clientes": list(top_clientes),
            "vendas_por_status": list(vendas_por_status),
            "resumo_dia": VendasStatisticsService._periodo_metrics(base_hoje),
            "resumo_mes": VendasStatisticsService._periodo_metrics(base_mes),
            "resumo_ano": VendasStatisticsService._periodo_metrics(base_ano),
            "vendas_por_hora": vendas_por_hora,
            "pico_horario": pico_horario,
        }
