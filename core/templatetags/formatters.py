from django import template

from core.services.formato_brl import format_brl, format_number_brl, unit_label

register = template.Library()


@register.filter(name='br_currency')
def br_currency(value, decimals=2):
    """Formata valor para moeda brasileira."""
    return format_brl(value, decimals=decimals)


@register.filter(name='br_number')
def br_number(value, decimals=2):
    """Formata número para padrão brasileiro (sem R$)."""
    return format_number_brl(value, decimals=decimals)


@register.filter(name='get_item')
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter(name="unit_label")
def unit_label_filter(value):
    """Converte identificador interno de unidade para rótulo comercial."""
    return unit_label(value)
