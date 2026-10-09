from __future__ import annotations

import uuid
from decimal import Decimal

from PySide6.QtCore import Qt

from models import Product, Unit
from ui.products_window import ProductsWindow


def _make_product(name: str, sku: str) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name=name,
        sku=sku,
        unit=Unit.PIECE,
        cost_price=Decimal("2.00"),
        selling_price=Decimal("3.00"),
        quantity_in_stock=Decimal("5"),
    )
    product.stock_status = "in_stock"  # type: ignore[attr-defined]
    return product


class _FakeProductService:
    def __init__(self, products: list[Product]) -> None:
        self.products = products
        self.search_terms: list[str] = []

    def list_products(self) -> list[Product]:
        return self.products

    def search_products(self, term: str) -> list[Product]:
        self.search_terms.append(term)
        return [
            product for product in self.products if term.lower() in product.name.lower()
        ]


def test_products_window_renders_products_and_filters_search(qtbot) -> None:  # type: ignore[no-untyped-def]
    salmon = _make_product("Fresh Salmon", "SAL-001")
    tuna = _make_product("Frozen Tuna", "TUN-001")
    service = _FakeProductService([salmon, tuna])
    window = ProductsWindow(service)
    qtbot.addWidget(window)

    qtbot.waitUntil(lambda: window._model.rowCount() == 2, timeout=2000)
    assert window._model.item(0, 0).text() == "Fresh Salmon"

    window.search_edit.setText("tuna")
    window.search_products()

    qtbot.waitUntil(lambda: window._model.rowCount() == 1, timeout=2000)
    assert window._model.item(0, 0).text() == "Frozen Tuna"
    assert service.search_terms == ["tuna"]


def test_products_window_groups_metadata_and_selects_across_tables(qtbot) -> None:
    parent = Product(id=uuid.uuid4(), name="Barbecue", sku="BBQ", unit=Unit.BARBECUE)
    child = _make_product("Fish", "BBQ-FISH")
    child.parent_product_id = parent.id
    child.is_for_sale = False
    own = _make_product("Cleaning", "OWN")
    own.is_for_sale = False
    sale = _make_product("Salmon", "SALE")
    service = _FakeProductService([parent, child, own, sale])
    window = ProductsWindow(service)
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window._tables["barbecue"].row_count() == 1)
    assert window._tables["sale"].row_count() == 1
    assert window._tables["own"].row_count() == 1
    bbq = window._tables["barbecue"]
    assert window._counts["barbecue"].text() == "1 ապրանք"
    assert window._tabs.count() == 3
    assert window._tabs.tabText(1) == "Խորոված (1)"
    assert parent in window._products
    assert bbq.item_model.item(0, 0).text() == "Barbecue -> Fish"
    for table in window._tables.values():
        assert table.minimumHeight() == 360
        assert table.maximumHeight() > 360
        headers = [
            table.item_model.headerData(i, Qt.Orientation.Horizontal)
            for i in range(table.item_model.columnCount())
        ]
        assert "Վաճառքի գին" not in headers
        assert "Վաճառքի համար" not in headers
    window._tables["sale"].selectRow(0)
    assert window._selected_product() is sale
    window._tabs.setCurrentIndex(1)
    assert window._selected_product() is None
    assert not window._edit_button.isEnabled()
    bbq.selectRow(0)
    assert window._selected_product() is child
    assert not window._tables["sale"].selectionModel().hasSelection()
    assert window._edit_button.isEnabled()
    # A metadata edit moves the product on the next database reload.
    sale.is_for_sale = False
    window.reload_products()
    qtbot.waitUntil(lambda: window._tables["own"].row_count() == 2)
    assert window._tables["sale"].row_count() == 0
    assert not window._edit_button.isEnabled()


def test_search_result_without_barbecue_parent_stays_in_barbecue_table(qtbot) -> None:
    child = _make_product("Fish", "BBQ-FISH")
    child.parent_product_id = uuid.uuid4()
    window = ProductsWindow(_FakeProductService([child]))
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window._tables["barbecue"].row_count() == 1)
    assert window._tables["barbecue"].item_model.item(0, 0).text() == "Fish"
