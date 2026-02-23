from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from estoque.models import UnidadeLoja

from importadores.models import CaixaRelatorioImportacao, StatusImportacaoPDFChoices
from importadores.services.financeiro_resumo_service import FinanceiroResumoService


class ResultadoDiarioService:
    @classmethod
    def obter_data_referencia_dashboard(cls):
        ontem = timezone.localdate() - timedelta(days=1)
        existe_ontem = CaixaRelatorioImportacao.objects.filter(
            data_referencia=ontem,
            status__in=[StatusImportacaoPDFChoices.SUCESSO, StatusImportacaoPDFChoices.PARCIAL],
        ).exists()
        if existe_ontem:
            return ontem
        ultima = (
            CaixaRelatorioImportacao.objects.filter(
                status__in=[StatusImportacaoPDFChoices.SUCESSO, StatusImportacaoPDFChoices.PARCIAL]
            )
            .order_by("-data_referencia")
            .first()
        )
        return ultima.data_referencia if ultima else None

    @classmethod
    def resumo_por_unidade(cls, data_referencia):
        rows = []
        total_vendas_geral = Decimal("0.00")
        total_saidas_geral = Decimal("0.00")

        for unidade in UnidadeLoja.values:
            total_vendas = (
                CaixaRelatorioImportacao.objects.filter(
                    data_referencia=data_referencia,
                    unidade=unidade,
                    status__in=[StatusImportacaoPDFChoices.SUCESSO, StatusImportacaoPDFChoices.PARCIAL],
                ).aggregate(total=Sum("total_vendas"))["total"]
                or Decimal("0.00")
            )
            total_saidas = FinanceiroResumoService.total_saidas_confirmadas_por_unidade(
                data_referencia=data_referencia,
                unidade=unidade,
            )
            resultado = (total_vendas - total_saidas).quantize(Decimal("0.01"))
            rows.append(
                {
                    "unidade": unidade,
                    "vendas": total_vendas.quantize(Decimal("0.01")),
                    "saidas": total_saidas.quantize(Decimal("0.01")),
                    "resultado": resultado,
                }
            )
            total_vendas_geral += total_vendas
            total_saidas_geral += total_saidas

        return {
            "linhas": rows,
            "total_vendas_geral": total_vendas_geral.quantize(Decimal("0.01")),
            "total_saidas_geral": total_saidas_geral.quantize(Decimal("0.01")),
            "resultado_geral": (total_vendas_geral - total_saidas_geral).quantize(Decimal("0.01")),
        }

    @classmethod
    def payload_dashboard(cls):
        data_ref = cls.obter_data_referencia_dashboard()
        if not data_ref:
            return {
                "data_referencia": None,
                "linhas": [],
                "total_vendas_geral": Decimal("0.00"),
                "total_saidas_geral": Decimal("0.00"),
                "resultado_geral": Decimal("0.00"),
            }
        resumo = cls.resumo_por_unidade(data_ref)
        resumo["data_referencia"] = data_ref
        return resumo

