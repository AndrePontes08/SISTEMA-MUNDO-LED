from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.views.generic import TemplateView

from boletos.models import Boleto
from compras.models import Compra
from contas.models import ContaAPagar
from estoque.models import EstoqueMovimento, TransferenciaEstoque


class RelatoriosDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "relatorios/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        inicio_12m = hoje - timedelta(days=365)

        compras_mes = (
            Compra.objects.filter(data_compra__gte=inicio_12m)
            .annotate(mes=TruncMonth("data_compra"))
            .values("mes")
            .annotate(total=Sum("valor_total"), qtd=Count("id"))
            .order_by("mes")
        )
        labels_compras = [row["mes"].strftime("%m/%Y") for row in compras_mes if row["mes"]]
        valores_compras = [float(row["total"] or 0) for row in compras_mes]
        qtd_compras = [int(row["qtd"] or 0) for row in compras_mes]

        contas_status = ContaAPagar.objects.values("status").annotate(qtd=Count("id"), total=Sum("valor"))
        mapa_contas = {row["status"]: float(row["total"] or 0) for row in contas_status}

        boletos_status = Boleto.objects.values("status").annotate(qtd=Count("id"))
        labels_boletos = [row["status"] for row in boletos_status]
        valores_boletos = [int(row["qtd"] or 0) for row in boletos_status]

        movimentos_tipo = EstoqueMovimento.objects.filter(data_movimento__gte=inicio_12m).values("tipo").annotate(total=Sum("quantidade"))
        mapa_mov = {row["tipo"]: float(row["total"] or 0) for row in movimentos_tipo}

        transferencias_destino = (
            TransferenciaEstoque.objects.filter(data_transferencia__gte=inicio_12m)
            .values("unidade_destino")
            .annotate(total=Sum("quantidade"))
        )
        labels_transfer = [row["unidade_destino"] for row in transferencias_destino]
        valores_transfer = [float(row["total"] or 0) for row in transferencias_destino]

        ctx.update(
            {
                "kpi_total_compras": float(Compra.objects.aggregate(total=Sum("valor_total"))["total"] or 0),
                "kpi_contas_abertas": float(mapa_contas.get("ABERTA", 0)),
                "kpi_boletos_abertos": int(Boleto.objects.filter(status="ABERTO").count()),
                "kpi_transferencias_30d": int(
                    TransferenciaEstoque.objects.filter(data_transferencia__gte=hoje - timedelta(days=30)).count()
                ),
                "labels_compras_json": json.dumps(labels_compras),
                "valores_compras_json": json.dumps(valores_compras),
                "qtd_compras_json": json.dumps(qtd_compras),
                "labels_contas_json": json.dumps(["ABERTA", "PAGA", "CANCELADA"]),
                "valores_contas_json": json.dumps([
                    mapa_contas.get("ABERTA", 0),
                    mapa_contas.get("PAGA", 0),
                    mapa_contas.get("CANCELADA", 0),
                ]),
                "labels_boletos_json": json.dumps(labels_boletos),
                "valores_boletos_json": json.dumps(valores_boletos),
                "labels_mov_json": json.dumps(["ENTRADA", "SAIDA", "AJUSTE"]),
                "valores_mov_json": json.dumps([
                    mapa_mov.get("ENTRADA", 0),
                    mapa_mov.get("SAIDA", 0),
                    mapa_mov.get("AJUSTE", 0),
                ]),
                "labels_transfer_json": json.dumps(labels_transfer),
                "valores_transfer_json": json.dumps(valores_transfer),
            }
        )
        return ctx
