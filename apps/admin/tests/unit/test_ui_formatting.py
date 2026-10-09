from decimal import Decimal

from ui.style import format_currency, format_quantity


def test_format_currency_rounds_to_two_decimal_places() -> None:
    assert format_currency(Decimal("21.12121221")) == "21.12 ֏"
    assert format_currency(Decimal("21.129")) == "21.13 ֏"
    assert format_currency(Decimal("21.1")) == "21.1 ֏"
    assert format_currency(Decimal("21000")) == "21'000 ֏"


def test_format_quantity_rounds_to_two_decimal_places() -> None:
    assert format_quantity(Decimal("21.12121221")) == "21.12"
    assert format_quantity(Decimal("21.129")) == "21.13"
    assert format_quantity(Decimal("21.1")) == "21.1"
    assert format_quantity(Decimal("-0.001")) == "0"
    assert format_quantity(None) == ""
