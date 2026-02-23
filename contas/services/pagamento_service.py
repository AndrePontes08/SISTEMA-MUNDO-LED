from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from contas.models import ContaAPagar, StatusContaChoices


@transaction.atomic
def confirmar_pagamento(conta: ContaAPagar) -> ContaAPagar:
    """
    REGRA CRÍTICA:
    - Só pode confirmar PAGA se existir comprovante
    - EXCETO se exige_comprovante=False (normalmente importados)
    """
    conta = ContaAPagar.objects.select_for_update().get(pk=conta.pk)

    if conta.status == StatusContaChoices.PAGA:
        return conta

    if conta.exige_comprovante and not conta.comprovante:
        raise ValueError("Não é possível confirmar pagamento sem comprovante.")

    conta.status = StatusContaChoices.PAGA
    conta.pago_em = timezone.localdate()
    conta.save(update_fields=["status", "pago_em"])
    return conta
