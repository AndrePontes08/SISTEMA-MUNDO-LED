from __future__ import annotations

from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from compras.models import Produto
from estoque.models import ProdutoEstoque, AlertaEstoque, StatusAlerta


@transaction.atomic
def verificar_e_criar_alerta(produto: Produto) -> None:
    """
    Regra:
      - Se saldo_atual <= estoque_minimo => cria alerta ABERTO (se não existir)
      - Se saldo_atual > estoque_minimo => resolve alertas ABERTOS (se existirem)
    """
    cfg, _ = ProdutoEstoque.objects.get_or_create(produto=produto)
    saldo = cfg.saldo_atual or Decimal("0.000")
    minimo = cfg.estoque_minimo or Decimal("0.000")

    aberto = AlertaEstoque.objects.filter(produto=produto, status=StatusAlerta.ABERTO).first()

    if saldo <= minimo:
        if not aberto:
            AlertaEstoque.objects.create(
                produto=produto,
                status=StatusAlerta.ABERTO,
                saldo_no_momento=saldo,
                minimo_configurado=minimo,
            )
        else:
            # atualiza snapshot do alerta
            aberto.saldo_no_momento = saldo
            aberto.minimo_configurado = minimo
            aberto.save(update_fields=["saldo_no_momento", "minimo_configurado"])
    else:
        # resolve se necessário
        if aberto:
            aberto.status = StatusAlerta.RESOLVIDO
            aberto.resolvido_em = timezone.now()
            aberto.save(update_fields=["status", "resolvido_em"])
