"""Context processors para templates"""

from core.services.formato_brl import format_brl


def currency_formatter(request):
    """Fornece função de formatação de moeda para templates"""
    def br_currency(value, decimals=2):
        """Formata valor para moeda brasileira."""
        return format_brl(value, decimals=decimals)

    return {'br_currency': br_currency}
