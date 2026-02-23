from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from financeiro.models import StatusConciliacaoChoices, TipoMovimentoChoices, TransacaoBancaria

from importadores.models import UnidadeContaFinanceiraConfig


class FinanceiroResumoService:
    """
    Consulta resumida do financeiro existente sem alterar regras atuais.
    """

    STATUS_FINAIS = (
        StatusConciliacaoChoices.CONCILIADA,
        StatusConciliacaoChoices.DIVERGENTE,
        StatusConciliacaoChoices.IGNORADA,
    )

    @classmethod
    def total_saidas_confirmadas_por_unidade(cls, *, data_referencia, unidade: str) -> Decimal:
        config = UnidadeContaFinanceiraConfig.objects.filter(unidade=unidade, ativa=True).first()
        if not config:
            return Decimal("0.00")

        total = (
            TransacaoBancaria.objects.filter(
                conta=config.conta_bancaria,
                data_lancamento=data_referencia,
                tipo_movimento=TipoMovimentoChoices.SAIDA,
                status_conciliacao__in=cls.STATUS_FINAIS,
            ).aggregate(total=Sum("valor"))["total"]
            or Decimal("0.00")
        )
        return total.quantize(Decimal("0.01"))

