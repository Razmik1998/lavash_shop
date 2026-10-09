from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt

from networking.protocol import ProductPayload
from ui.checkout_window import CheckoutWindow
from ui.components import ChildProductSelectionDialog


class _FakeProductService:
    def list_products(self) -> list[ProductPayload]:
        return []


class _FakeSaleService:
    def __init__(self) -> None:
        self.called = False
        self.items: object | None = None

    def create_sale(self, *args: object, **kwargs: object) -> object:
        self.called = True
        self.items = args[3]
        return object()


def _run_synchronously(
    owner: object,
    fn: object,
    on_success: object,
    on_failure: object,
) -> None:
    try:
        result = fn()  # type: ignore[operator]
    except Exception as error:  # noqa: BLE001
        on_failure(error)  # type: ignore[operator]
        return
    on_success(result)  # type: ignore[operator]


@pytest.fixture(autouse=True)
def _synchronous_background(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ui.checkout_window.run_in_background", _run_synchronously)


def _product() -> ProductPayload:
    return ProductPayload(
        id="product-1",
        sku="SKU-1",
        barcode="123456789",
        name="fresh apples",
        unit="piece",
        selling_price="400",
        available_stock="10",
        minimum_price="300",
    )


def _window() -> CheckoutWindow:
    window = CheckoutWindow(
        _FakeProductService(), _FakeSaleService(), "session-1", "terminal-1"
    )
    window._on_products_loaded([_product()])
    return window


def test_product_row_shows_title_name_code_and_price_only(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _window()
    qtbot.addWidget(window)

    assert window._product_list.item(0, 0).text() == "Fresh Apples"
    assert window._product_list.item(0, 1).text() == "SKU-1"
    assert window._product_list.item(0, 2).text() == "400 ֏"


def test_clicking_product_adds_it_to_cart(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _window()
    qtbot.addWidget(window)

    window._product_list.cellClicked.emit(0, 1)

    assert window._cart == {"product-1": Decimal("1")}


def test_adding_product_allows_quantity_above_available_stock(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _window()
    qtbot.addWidget(window)

    window._add_product(_product(), Decimal("11"))

    assert window._cart == {"product-1": Decimal("11")}


@pytest.mark.parametrize("available_stock", ["0", "-2"])
def test_adding_product_ignores_zero_or_negative_stock(
    qtbot, available_stock: str
) -> None:  # type: ignore[no-untyped-def]
    product = replace(_product(), available_stock=available_stock)
    window = CheckoutWindow(
        _FakeProductService(), _FakeSaleService(), "session-1", "terminal-1"
    )
    window._on_products_loaded([product])
    qtbot.addWidget(window)

    window._add_product(product, Decimal("1"))

    assert window._cart == {"product-1": Decimal("1")}


def test_double_clicking_cart_line_applies_minimum_price(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("ui.checkout_window.confirm", lambda *_args: True)
    window = _window()
    qtbot.addWidget(window)
    window._add_product(_product(), Decimal("1"))

    window._cart_table.cellDoubleClicked.emit(0, 2)

    assert window._cart_prices == {"product-1": Decimal("300")}
    assert window._cart_table.item(0, 2).text() == "300 ֏"
    assert window._cart_table.item(0, 3).text() == "100 ֏"


def test_discount_button_applies_discount_to_selected_product(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("ui.checkout_window.confirm", lambda *_args: True)
    window = _window()
    qtbot.addWidget(window)
    window._add_product(_product(), Decimal("1"))
    window._cart_table.selectRow(0)

    qtbot.mouseClick(window._discount_button, Qt.MouseButton.LeftButton)

    assert window._cart_prices == {"product-1": Decimal("300")}
    assert window._discount_button.text() == "Հեռացնել զեղչը"


def test_entering_received_cash_shows_change_due(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _window()
    qtbot.addWidget(window)
    window.resize(1200, 800)
    window.show()
    window._add_product(_product(), Decimal("12.5"))

    qtbot.mouseClick(window._received_amount, Qt.MouseButton.LeftButton)
    qtbot.keyClicks(window._received_amount, "10,000")

    assert window._received_amount.text() == "10,000"
    assert window._change_due.text() == "Վերադարձ՝ 5000 ֏"
    assert 42 <= window._received_amount.minimumHeight() < 64

    window._received_amount.clear()

    assert window._change_due.text() == "Վերադարձ՝ 0 ֏"


def test_received_cash_input_does_not_trigger_product_lookup(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    window = _window()
    qtbot.addWidget(window)
    window.show()
    looked_up_codes: list[str] = []
    monkeypatch.setattr(window, "_lookup_scanned_code", looked_up_codes.append)

    qtbot.mouseClick(window._received_amount, Qt.MouseButton.LeftButton)
    qtbot.keyClicks(window._received_amount, "20000")
    qtbot.keyClick(window._received_amount, Qt.Key.Key_Return)

    assert window._received_amount.text() == "20000"
    assert looked_up_codes == []


@pytest.mark.parametrize("column", [0, 1, 2])
def test_clicking_any_product_cell_adds_the_product(qtbot, column: int) -> None:  # type: ignore[no-untyped-def]
    window = _window()
    qtbot.addWidget(window)

    window._product_list.cellClicked.emit(0, column)

    assert window._cart == {"product-1": Decimal("1")}


def test_entering_barcode_adds_product_and_clears_scanner_field(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _window()
    qtbot.addWidget(window)
    window._search.setText("123456789")

    qtbot.keyClick(window._search, Qt.Key.Key_Return)

    assert window._cart == {"product-1": Decimal("1")}
    assert window._search.text() == ""


def test_shift_enter_submits_the_sale(qtbot) -> None:  # type: ignore[no-untyped-def]
    sale_service = _FakeSaleService()
    window = CheckoutWindow(
        _FakeProductService(), sale_service, "session-1", "terminal-1"
    )
    window._on_products_loaded([_product()])
    window._cart = {"product-1": Decimal("1")}
    qtbot.addWidget(window)

    qtbot.keyClick(window._search, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)

    assert sale_service.called is True


def test_checkout_trims_trailing_zeros_from_sale_quantity(
    qtbot,
) -> None:  # type: ignore[no-untyped-def]
    sale_service = _FakeSaleService()
    window = CheckoutWindow(
        _FakeProductService(), sale_service, "session-1", "terminal-1"
    )
    window._on_products_loaded([_product()])
    window._add_product(_product(), Decimal("1.0000"))
    qtbot.addWidget(window)

    window._submit_sale()

    assert sale_service.items == [("product-1", "1", "400")]


def test_checkout_sends_explicit_price_for_discounted_item(
    qtbot,
) -> None:  # type: ignore[no-untyped-def]
    sale_service = _FakeSaleService()
    window = CheckoutWindow(
        _FakeProductService(), sale_service, "session-1", "terminal-1"
    )
    window._on_products_loaded([_product()])
    window._cart = {"product-1": Decimal("1")}
    window._cart_prices = {"product-1": Decimal("350")}
    qtbot.addWidget(window)

    window._submit_sale()

    assert sale_service.items == [("product-1", "1", "350")]


def test_child_selection_starts_at_zero_and_ignores_zero_quantities(qtbot) -> None:  # type: ignore[no-untyped-def]
    children = [
        ProductPayload(
            id="fish",
            sku="FISH-1",
            barcode=None,
            name="Barbecue Fish",
            unit="piece",
            selling_price="5.00",
            available_stock="10",
            parent_product_id="parent",
        ),
        ProductPayload(
            id="meat",
            sku="MEAT-1",
            barcode=None,
            name="Barbecue Meat",
            unit="piece",
            selling_price="6.00",
            available_stock="10",
            parent_product_id="parent",
        ),
    ]
    dialog = ChildProductSelectionDialog("Barbecue", children)
    qtbot.addWidget(dialog)

    assert dialog._quantities == {"fish": 0, "meat": 0}
    assert dialog._decrement_buttons["fish"].isEnabled() is False

    dialog._change_quantity("fish", 1)
    dialog._change_quantity("fish", -1)
    dialog._change_quantity("fish", -1)
    dialog._change_quantity("meat", 2)

    assert dialog._quantities == {"fish": 0, "meat": 2}
    assert dialog._decrement_buttons["fish"].isEnabled() is False
    assert [(child.id, quantity) for child, quantity in dialog.selected_children(children)] == [
        ("meat", Decimal("2"))
    ]


def test_barbecue_parent_is_action_not_sellable_product_row(qtbot) -> None:  # type: ignore[no-untyped-def]
    parent = ProductPayload(
        id="barbecue",
        sku="BBQ-1",
        barcode=None,
        name="barbecue",
        unit="barbecue",
        selling_price=None,
        available_stock=None,
    )
    child = ProductPayload(
        id="fish",
        sku="FISH-1",
        barcode=None,
        name="fish",
        unit="piece",
        selling_price="5.00",
        available_stock="10",
        parent_product_id="barbecue",
    )
    window = CheckoutWindow(
        _FakeProductService(), _FakeSaleService(), "session-1", "terminal-1"
    )
    window._on_products_loaded([parent, child])
    qtbot.addWidget(window)

    assert window._product_list.rowCount() == 1
    assert window._product_list.item(0, 0).text() == "Barbecue -> Fish"
    assert len(window._barbecue_buttons) == 1
    assert "Խորոված" in window._barbecue_buttons[0].text()
