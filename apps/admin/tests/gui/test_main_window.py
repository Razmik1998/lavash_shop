from __future__ import annotations

import uuid
from decimal import Decimal
from typing import cast

from PySide6.QtWidgets import QPushButton

from models import Product, Role, Unit, User
from services import EmployeeService, ProductService
from ui.main_window import AdminMainWindow


class _FakeEmployeeService:
    def list_employees(self) -> list[User]:
        return []


class _FakeProductService:
    def list_products(self) -> list[Product]:
        return []

    def search_products(self, term: str) -> list[Product]:
        return []

    def create_product(
        self,
        name: str,
        sku: str,
        barcode: str | None,
        unit: Unit,
        cost_price: Decimal | None,
        selling_price: Decimal,
        quantity_in_stock: Decimal,
        low_stock_threshold: Decimal | None,
        is_active: bool,
    ) -> Product:
        return Product(
            id=uuid.uuid4(),
            name=name,
            sku=sku,
            barcode=barcode,
            unit=unit,
            cost_price=cost_price,
            selling_price=selling_price,
            quantity_in_stock=quantity_in_stock,
            low_stock_threshold=low_stock_threshold,
            is_active=is_active,
        )

    def update_product(
        self,
        product_id: uuid.UUID,
        name: str,
        sku: str,
        barcode: str | None,
        unit: Unit,
        cost_price: Decimal | None,
        selling_price: Decimal,
        quantity_in_stock: Decimal,
        low_stock_threshold: Decimal | None,
        is_active: bool,
    ) -> Product:
        product = self.create_product(
            name,
            sku,
            barcode,
            unit,
            cost_price,
            selling_price,
            quantity_in_stock,
            low_stock_threshold,
            is_active,
        )
        product.id = product_id
        return product


def _admin_user() -> User:
    return User(
        id=uuid.uuid4(),
        username="admin",
        full_name="Admin",
        hashed_password="x",
        role=Role.ADMIN,
        is_active=True,
    )


def test_main_window_has_products_nav_button(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = AdminMainWindow(
        cast(EmployeeService, _FakeEmployeeService()),
        _admin_user(),
        cast(ProductService, _FakeProductService()),
    )
    qtbot.addWidget(window)

    button_labels = [button.text() for button in window.findChildren(QPushButton)]

    assert "Ապրանքներ" in button_labels


def test_sidebar_navigation_scrolls_horizontally_for_long_labels(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = AdminMainWindow(
        cast(EmployeeService, _FakeEmployeeService()),
        _admin_user(),
        cast(ProductService, _FakeProductService()),
    )
    qtbot.addWidget(window)
    window.resize(900, 420)
    window.show()
    qtbot.wait(300)

    scroll_area = window._nav_scroll
    horizontal_scrollbar = scroll_area.horizontalScrollBar()

    assert horizontal_scrollbar.maximum() > 0
    horizontal_scrollbar.setValue(horizontal_scrollbar.maximum())
    horizontal_position = horizontal_scrollbar.value()

    window._select_page(len(window._nav_buttons) - 1)
    qtbot.wait(300)
    last_button = window._nav_buttons[-1]
    button_top = last_button.mapTo(
        scroll_area.viewport(), last_button.rect().topLeft()
    ).y()

    assert horizontal_scrollbar.value() == horizontal_position
    assert last_button.isVisible()
    assert button_top >= 0
    assert button_top + last_button.height() <= scroll_area.viewport().height()


def test_sidebar_groups_collapse_and_keep_page_selection(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = AdminMainWindow(
        cast(EmployeeService, _FakeEmployeeService()), _admin_user()
    )
    qtbot.addWidget(window)
    window.show()
    groups = window._nav_groups
    assert len(groups) == 5
    assert groups[0][0].isChecked()
    assert all(not toggle.isChecked() for toggle, _ in groups[1:])

    groups[1][0].click()
    qtbot.wait(300)
    assert not groups[0][1].isVisible()
    assert groups[1][1].isVisible()
    for index in (1, 2, 3, 11):
        window._nav_buttons[index].click()
        assert window._pages.currentIndex() == index
        assert window._header_title.text() == window._page_labels[index]
        assert window._nav_buttons[index].property("active") == "true"

    groups[1][0].click()
    qtbot.wait(300)
    assert not groups[1][1].isVisible()
    assert window._pages.currentIndex() == 11
    window._select_page(12)
    qtbot.wait(300)
    assert groups[2][1].isVisible()
    assert not groups[1][1].isVisible()
    assert sum(button.isChecked() for button in window._nav_buttons) == 1


def test_sidebar_animation_handles_rapid_toggles(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = AdminMainWindow(
        cast(EmployeeService, _FakeEmployeeService()), _admin_user()
    )
    qtbot.addWidget(window)
    window.show()
    toggle, children = window._nav_groups[1]
    toggle.click()
    qtbot.wait(80)
    assert 0 < children.maximumHeight() < children.layout().sizeHint().height()
    toggle.click()
    qtbot.wait(40)
    toggle.click()
    qtbot.wait(300)
    assert toggle.isChecked()
    assert children.isVisible()
    assert children.maximumHeight() == children.layout().sizeHint().height()
    toggle.click()
    qtbot.wait(300)
    assert not children.isVisible()
    assert children.maximumHeight() == 0
