from __future__ import annotations

from decimal import Decimal


def format_brl(value) -> str:
    """
    Formata valor numérico em BRL com padrão brasileiro.
    Ex: 1234.5 -> 'R$ 1.234,50'
    """
    if value is None:
        return "R$ 0,00"
    if not isinstance(value, Decimal):
        try:
            value = Decimal(str(value))
        except Exception:
            return "R$ 0,00"

    quant = value.quantize(Decimal("0.01"))
    s = f"{quant:,.2f}"  # 1,234.56 (US)
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"
