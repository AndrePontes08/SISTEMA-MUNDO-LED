from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from difflib import SequenceMatcher

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from financeiro.models import (
    Conciliacao,
    ConciliacaoItem,
    Recebivel,
    StatusConciliacaoChoices,
    StatusRecebivelChoices,
    TipoConciliacaoChoices,
    TipoMovimentoChoices,
    TransacaoBancaria,
)


@dataclass
class RegraConciliacao:
    tolerancia_valor: Decimal = Decimal("0.05")
    janela_dias: int = 7


class ConciliacaoService:
    REGRA_PADRAO = RegraConciliacao()

    @classmethod
    def gerar_sugestoes(cls, transacao: TransacaoBancaria, limite: int = 5) -> list[dict]:
        if transacao.tipo_movimento != TipoMovimentoChoices.ENTRADA:
            return []
        regra = cls.REGRA_PADRAO
        inicio = transacao.data_lancamento - timedelta(days=regra.janela_dias)
        fim = transacao.data_lancamento + timedelta(days=regra.janela_dias)

        candidatos = (
            Recebivel.objects.filter(
                status=StatusRecebivelChoices.ABERTO,
                data_prevista__range=(inicio, fim),
            )
            .order_by("data_prevista", "id")
        )

        sugestoes: list[dict] = []
        for recebivel in candidatos:
            diferenca = abs((recebivel.valor or Decimal("0.00")) - (transacao.valor or Decimal("0.00")))
            if diferenca > regra.tolerancia_valor:
                continue
            similaridade = cls._similaridade_texto(transacao.descricao, recebivel.descricao)
            score = max(0.0, 1.0 - float(diferenca)) + (similaridade * 0.2)
            sugestoes.append(
                {
                    "recebivel_id": recebivel.id,
                    "descricao": recebivel.descricao,
                    "valor": recebivel.valor,
                    "data_prevista": recebivel.data_prevista,
                    "diferenca": diferenca,
                    "similaridade": round(similaridade, 4),
                    "score": round(score, 4),
                }
            )

        sugestoes.sort(key=lambda item: item["score"], reverse=True)
        return sugestoes[:limite]

    @classmethod
    def marcar_sugestoes_para_transacoes(cls, transacao_ids: list[int]) -> None:
        for transacao in TransacaoBancaria.objects.filter(id__in=transacao_ids):
            if transacao.status_conciliacao in (
                StatusConciliacaoChoices.CONCILIADA,
                StatusConciliacaoChoices.DIVERGENTE,
                StatusConciliacaoChoices.IGNORADA,
            ):
                continue
            sugestoes = cls.gerar_sugestoes(transacao, limite=1)
            novo_status = (
                StatusConciliacaoChoices.SUGERIDA if sugestoes else StatusConciliacaoChoices.PENDENTE
            )
            if transacao.status_conciliacao != novo_status:
                transacao.status_conciliacao = novo_status
                transacao.save(update_fields=["status_conciliacao"])

    @classmethod
    def conciliar(
        cls,
        transacao: TransacaoBancaria,
        recebiveis: list[Recebivel],
        usuario,
        observacao: str = "",
        tipo: str = TipoConciliacaoChoices.MANUAL,
    ) -> Conciliacao:
        if not recebiveis:
            raise ValidationError("Selecione ao menos um recebivel para conciliar.")
        if hasattr(transacao, "conciliacao"):
            raise ValidationError("Transacao ja conciliada anteriormente.")
        if transacao.status_conciliacao == StatusConciliacaoChoices.CONCILIADA:
            raise ValidationError("Transacao ja marcada como conciliada.")

        soma = sum((r.valor for r in recebiveis), Decimal("0.00"))
        if abs(soma - transacao.valor) > cls.REGRA_PADRAO.tolerancia_valor:
            raise ValidationError("Soma dos recebiveis difere do valor da transacao acima da tolerancia.")

        with transaction.atomic():
            conciliacao = Conciliacao.objects.create(
                transacao=transacao,
                tipo=tipo,
                status_final=StatusConciliacaoChoices.CONCILIADA,
                observacao=observacao,
                conciliado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
                conciliado_em=timezone.now(),
            )
            for recebivel in recebiveis:
                ConciliacaoItem.objects.create(
                    conciliacao=conciliacao,
                    recebivel=recebivel,
                    valor_alocado=recebivel.valor,
                )
                recebivel.status = StatusRecebivelChoices.RECEBIDO
                recebivel.save(update_fields=["status", "atualizado_em"])

            transacao.status_conciliacao = StatusConciliacaoChoices.CONCILIADA
            transacao.save(update_fields=["status_conciliacao"])
        return conciliacao

    @classmethod
    def marcar_divergente(cls, transacao: TransacaoBancaria, usuario, observacao: str = "") -> Conciliacao:
        return cls._marcar_status_final(
            transacao=transacao,
            status=StatusConciliacaoChoices.DIVERGENTE,
            usuario=usuario,
            observacao=observacao,
        )

    @classmethod
    def ignorar(cls, transacao: TransacaoBancaria, usuario, observacao: str = "") -> Conciliacao:
        return cls._marcar_status_final(
            transacao=transacao,
            status=StatusConciliacaoChoices.IGNORADA,
            usuario=usuario,
            observacao=observacao,
        )

    @classmethod
    def _marcar_status_final(
        cls,
        transacao: TransacaoBancaria,
        status: str,
        usuario,
        observacao: str,
    ) -> Conciliacao:
        if hasattr(transacao, "conciliacao"):
            raise ValidationError("Transacao ja possui registro final de conciliacao.")
        with transaction.atomic():
            conciliacao = Conciliacao.objects.create(
                transacao=transacao,
                tipo=TipoConciliacaoChoices.MANUAL,
                status_final=status,
                observacao=observacao,
                conciliado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
                conciliado_em=timezone.now(),
            )
            transacao.status_conciliacao = status
            transacao.save(update_fields=["status_conciliacao"])
        return conciliacao

    @staticmethod
    def _similaridade_texto(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

