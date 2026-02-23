from __future__ import annotations

from decimal import Decimal
from django.db.models import Sum

from contas.models import ContaAPagar, RegraImposto


def calcular_imposto_mes(ano: int, mes: int) -> dict:
    regra = RegraImposto.objects.filter(ativo=True).order_by("-id").first()
    percentual = regra.aliquota_percentual if regra else Decimal("0.000")

    total = (
        ContaAPagar.objects.filter(vencimento__year=ano, vencimento__month=mes)
        .aggregate(t=Sum("valor"))
        .get("t")
        or Decimal("0.00")
    )

    imposto = (total * (percentual / Decimal("100"))).quantize(Decimal("0.01"))
    return {
        "percentual": percentual,
        "total_mes": total.quantize(Decimal("0.01")),
        "imposto_estimado": imposto,
        "regra_nome": regra.nome if regra else "Sem regra ativa",
    }
