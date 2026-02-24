from __future__ import annotations

from decimal import Decimal


def _to_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def format_brl(value, decimals: int = 2) -> str:
    """
    Formata valor numérico em BRL com padrão brasileiro.
    Ex: 1234.5 -> 'R$ 1.234,50'
    """
    value_dec = _to_decimal(value)
    if decimals == 0:
        formatted = f"{int(round(value_dec)):,}".replace(",", ".")
        return f"R$ {formatted}"
    quant = value_dec.quantize(Decimal("0.01"))
    s = f"{quant:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def format_number_brl(value, decimals: int = 2) -> str:
    """
    Formata valor numérico em padrão brasileiro sem prefixo monetário.
    Ex: 1234.5 -> '1.234,50'
    """
    value_dec = _to_decimal(value)
    if decimals == 0:
        return f"{int(round(value_dec)):,}".replace(",", ".")
    quant = value_dec.quantize(Decimal("0.01"))
    s = f"{quant:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


UNIT_LABELS = {
    "LOJA_1": "FM Comércio",
    "LOJA1": "FM Comércio",
    "LOJA_2": "ML Comércio",
    "LOJA2": "ML Comércio",
}


def unit_label(value) -> str:
    raw = (str(value or "")).strip()
    if not raw:
        return "-"
    return UNIT_LABELS.get(raw, raw)


PAYMENT_LABELS = {
    "PIX": "PIX",
    "CREDITO": "Crédito",
    "DEBITO": "Débito",
    "AVISTA": "Espécie",
    "PARCELADO_BOLETO": "Boleto",
    "PARCELADO": "Crédito na loja",
}


def payment_label(value) -> str:
    raw = (str(value or "")).strip()
    if not raw:
        return "-"
    return PAYMENT_LABELS.get(raw, raw)
