from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()


@register.filter(name='br_currency')
def br_currency(value, decimals=2):
    """Formata valor para moeda brasileira"""
    try:
        if value is None or value == "":
            return "R$ 0,00"
        
        value = Decimal(str(value))
        
        if decimals == 0:
            value = int(round(value))
            formatted = f"{value:,}".replace(",", ".")
            return f"R$ {formatted}"
        
        formatted = f"{value:,.{decimals}f}"
        # Converter do padrão americano (1,234.56) para brasileiro (1.234,56)
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"
    except (ValueError, TypeError, InvalidOperation):
        return "R$ 0,00"


@register.filter(name='br_number')
def br_number(value, decimals=2):
    """Formata número para padrão brasileiro (sem R$)"""
    try:
        if value is None or value == "":
            return "0,00"
        
        value = Decimal(str(value))
        
        if decimals == 0:
            value = int(round(value))
            return f"{value:,}".replace(",", ".")
        
        formatted = f"{value:,.{decimals}f}"
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted
    except (ValueError, TypeError, InvalidOperation):
        return "0,00"


@register.filter(name='get_item')
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

