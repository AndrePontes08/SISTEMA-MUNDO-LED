"""Context processors para templates"""
from decimal import Decimal


def currency_formatter(request):
    """Fornece função de formatação de moeda para templates"""
    def br_currency(value, decimals=2):
        """Formata valor para moeda brasileira"""
        try:
            if value is None:
                return "R$ 0,00"
            value = Decimal(str(value))
            if decimals == 0:
                value = int(round(value))
                formatted = f"{value:,}".replace(",", ".")
                return f"R$ {formatted}"
            formatted = f"{value:,.{decimals}f}"
            formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
            return f"R$ {formatted}"
        except (ValueError, TypeError):
            return "R$ 0,00"
    
    return {'br_currency': br_currency}
