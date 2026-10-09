from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def format_thousands(value: object) -> str:
    """Format a visible number with apostrophe thousands separators."""
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return str(value)

    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{Decimal(text or '0'):,}".replace(",", "'")