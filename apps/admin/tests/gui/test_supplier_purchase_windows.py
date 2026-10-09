from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from PySide6.QtWidgets import QPushButton

from models import PaymentMethod, Product, Purchase, PurchaseStatus, Unit
from services import (
    PurchaseDetail,
    PurchaseRow,
    SupplierAccount,
    SupplierPaymentRow,
    SupplierReportRow,
    SupplierRow,
)
from ui.purchases_window import PurchasesWindow
from ui.supplier_account_page import SupplierAccountPage
from ui.supplier_report_window import SupplierReportWindow
from ui.suppliers_window import PurchaseDialog, SuppliersWindow


class _SupplierService:
    def list_suppliers(self) -> list[SupplierRow]:
        return [SupplierRow(uuid.uuid4(), "Արև", "091000000", None, True)]

    def save_supplier(
        self,
        supplier_id: uuid.UUID | None,
        name: str,
        phone: str | None,
        description: str | None,
        is_active: bool = True,
        opening_debt: Decimal = Decimal("0"),
    ) -> SupplierRow:
        return SupplierRow(
            supplier_id or uuid.uuid4(), name, phone, description, is_active, opening_debt
        )


class _PurchaseService:
    def list_purchases(self, supplier_id: uuid.UUID | None = None) -> list[PurchaseRow]:
        return [
            PurchaseRow(
                uuid.uuid4(),
                "PUR-001",
                "Արև",
                datetime.now(UTC),
                Decimal("1250.00"),
                Decimal("250.00"),
                Decimal("1000.00"),
                "partially_paid",
            )
        ]

    def get_detail(self, purchase_id: uuid.UUID) -> PurchaseDetail:
        raise NotImplementedError

    def confirm(
        self,
        purchase_id: uuid.UUID,
        initial_payment: Decimal = Decimal("0"),
        payment_method: PaymentMethod = PaymentMethod.CASH,
        price_updates: dict[uuid.UUID, Decimal] | None = None,
    ) -> object:
        raise NotImplementedError

    def cancel(self, purchase_id: uuid.UUID) -> object:
        raise NotImplementedError

    def supplier_report(self, filters=None) -> list[SupplierReportRow]:
        return [
            SupplierReportRow(
                uuid.uuid4(),
                "Արև",
                2,
                Decimal("5"),
                Decimal("1250.00"),
                Decimal("250.00"),
                Decimal("1000.00"),
            )
        ]


class _ProductService:
    def list_active_products(self) -> list[Product]:
        return []

    def search_products(self, term: str) -> list[Product]:
        return []


def test_purchase_dialog_shows_added_line_in_order_list(qtbot: Any) -> None:
    supplier = SupplierRow(uuid.uuid4(), "Արև", None, None, True)
    product = Product(
        id=uuid.uuid4(),
        name="Սաղմոն",
        sku="SAL-001",
        unit=Unit.KG,
        selling_price=Decimal("2500.00"),
        quantity_in_stock=Decimal("0"),
        is_active=True,
    )
    dialog = PurchaseDialog(
        supplier, _PurchaseService(), _ProductService()
    )
    qtbot.addWidget(dialog)
    dialog._products_loaded([product])
    dialog._quantity.setText("10")
    dialog._cost.setText("2000")
    dialog._selling_price.setText("2500")
    dialog._add_line()

    assert dialog._lines_model.rowCount() == 1
    assert dialog._lines_model.item(0, 0).text() == "Սաղմոն"
    assert dialog._lines_table.minimumHeight() >= 220


def test_purchase_dialog_uses_selected_product_price_baseline(qtbot: Any) -> None:
    supplier = SupplierRow(uuid.uuid4(), "Արև", None, None, True)
    first = Product(
        id=uuid.uuid4(),
        name="Առաջին",
        sku="ONE",
        unit=Unit.PIECE,
        selling_price=Decimal("250"),
        quantity_in_stock=Decimal("0"),
        is_active=True,
    )
    selected = Product(
        id=uuid.UUID("7ee5cd76-d37e-465d-bf05-8315ca227bd3"),
        name="bobla",
        sku="3",
        barcode="3",
        unit=Unit.PIECE,
        selling_price=Decimal("400"),
        quantity_in_stock=Decimal("0"),
        is_active=True,
    )
    dialog = PurchaseDialog(supplier, _PurchaseService(), _ProductService())
    qtbot.addWidget(dialog)
    dialog._products_loaded([first, selected])
    dialog._selected_index = 1
    dialog._product_selection_changed()

    assert dialog._original_selling_price == Decimal("400")
    assert dialog._selling_price.text() == "400"


def test_purchase_dialog_updates_checkout_summary(qtbot: Any) -> None:
    supplier = SupplierRow(uuid.uuid4(), "Արև", None, None, True)
    product = Product(
        id=uuid.uuid4(),
        name="Թեյ",
        sku="TEA-001",
        unit=Unit.PIECE,
        cost_price=Decimal("200"),
        selling_price=Decimal("250"),
        quantity_in_stock=Decimal("0"),
        is_active=True,
    )
    dialog = PurchaseDialog(supplier, _PurchaseService(), _ProductService())
    qtbot.addWidget(dialog)
    assert dialog._cart_stack.currentIndex() == 0

    dialog._products_loaded([product])
    dialog._quantity.setText("3")
    dialog._cost.setText("200")
    dialog._selling_price.setText("250")
    dialog._add_line()

    assert dialog._cart_stack.currentWidget() is dialog._lines_table
    assert dialog._item_count.value_label.text() == "1"
    assert dialog._unit_count.value_label.text() == "3"
    assert dialog._purchase_total.value_label.text() == "600 ֏"

    dialog._payment.setText("200")
    dialog._refresh_basket_summary()
    assert dialog._remaining_debt.value_label.text() == "400 ֏"


def test_supplier_window_uses_armenian_labels(qtbot: Any) -> None:
    window = SuppliersWindow(_SupplierService())
    qtbot.addWidget(window)

    qtbot.waitUntil(lambda: window._model.rowCount() == 1, timeout=2000)
    assert window.windowTitle() == ""
    assert window._name.placeholderText() == "Օր.՝ Արարատ ՍՊԸ"
    assert window._phone.placeholderText() == "Օր.՝ 077 123456"
    assert window._model.horizontalHeaderItem(0).text() == "Անուն"
    assert window._model.item(0, 2).text() == "Ակտիվ"
    button_labels = [button.text() for button in window.findChildren(QPushButton)]
    assert "Խմբագրել" in button_labels
    assert "Արխիվացնել" in button_labels
    assert "Վերականգնել" in button_labels


def test_new_supplier_opens_form_page_and_returns_to_list_on_save(
    qtbot: Any,
) -> None:
    window = SuppliersWindow(_SupplierService())
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window._model.rowCount() == 1, timeout=2000)

    window._show_create_form()
    assert window._stack.currentWidget() is window._form_page

    window._show_list()
    assert window._stack.currentWidget() is window._list_page

    window._show_create_form()
    assert window._name.text() == ""
    window._name.setText("Նոր")
    window._save()
    qtbot.waitUntil(
        lambda: window._stack.currentWidget() is window._list_page, timeout=2000
    )


def test_purchase_window_renders_armenian_status_and_dram_currency(
    qtbot: Any,
) -> None:
    window = PurchasesWindow(_PurchaseService())
    qtbot.addWidget(window)

    qtbot.waitUntil(lambda: window._model.rowCount() == 1, timeout=2000)
    assert window._model.item(0, 3).text() == "1'250 ֏"
    assert window._model.item(0, 4).text() == "250 ֏"
    assert window._model.item(0, 5).text() == "1'000 ֏"
    assert window._model.item(0, 6).text() == "Ավարտված"


def test_supplier_report_window_renders_armenian_aggregate_columns(qtbot: Any) -> None:
    window = SupplierReportWindow(_PurchaseService(), _SupplierService())
    qtbot.addWidget(window)

    qtbot.waitUntil(lambda: window._model.rowCount() == 1, timeout=2000)
    assert window._model.horizontalHeaderItem(0).text() == "Մատակարար"
    assert window._model.horizontalHeaderItem(5).text() == "Ընթացիկ պարտք"
    assert window._model.item(0, 3).text() == "1'250 ֏"
    assert window._model.item(0, 5).text() == "1'000 ֏"
    assert window._model.item(0, 5).text() == "1'000 ֏"


class _AccountSupplierService(_SupplierService):
    def __init__(self) -> None:
        self.supplier = SupplierRow(uuid.uuid4(), "Արև", "091000000", None, True)
        self.periods: list[tuple[datetime | None, datetime | None]] = []

    def list_suppliers(self) -> list[SupplierRow]:
        return [self.supplier]

    def get_account(
        self,
        supplier_id: uuid.UUID,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
    ) -> SupplierAccount:
        self.periods.append((from_datetime, to_datetime))
        purchase = PurchaseRow(
            uuid.uuid4(),
            "PUR-001",
            "Արև",
            datetime(2026, 9, 1, tzinfo=UTC),
            Decimal("1000"),
            Decimal("400"),
            Decimal("600"),
            "partially_paid",
            Decimal("2"),
        )
        payment = SupplierPaymentRow(
            uuid.uuid4(),
            datetime(2026, 9, 2, tzinfo=UTC),
            Decimal("400"),
            PaymentMethod.CASH,
            "PUR-001",
            None,
        )
        return SupplierAccount(
            self.supplier,
            [purchase],
            [payment],
            Decimal("1000"),
            Decimal("400"),
            Decimal("600"),
            Decimal("400"),
            Decimal("900"),
        )


class _AccountPurchaseService(_PurchaseService):
    def __init__(self) -> None:
        self.debt_payments: list[Decimal] = []

    def add_payment(self, *args: object, **kwargs: object) -> object:
        return None

    def pay_supplier_debt(
        self,
        supplier_id: uuid.UUID,
        amount: Decimal,
        method: PaymentMethod,
        payment_date: datetime,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
    ) -> int:
        self.debt_payments.append(amount)
        return 1


def test_supplier_double_click_opens_account_page_with_back_navigation(
    qtbot: Any, monkeypatch: Any
) -> None:
    supplier_service = _AccountSupplierService()
    purchase_service = _AccountPurchaseService()
    window = SuppliersWindow(supplier_service, purchase_service)  # type: ignore[arg-type]
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window._model.rowCount() == 1, timeout=2000)

    window._table.selectRow(0)
    window._open_selected_supplier_history()
    page = window._account_page
    assert page is not None
    assert window._stack.currentWidget() is page

    page.show_documents()
    documents = page.documents_view
    qtbot.waitUntil(lambda: documents._table.row_count() == 1, timeout=2000)
    assert documents._table.item_model.item(0, 4).text() == "600 ֏"
    assert documents._debt.value_label.text() == "600 ֏"
    assert documents._total_debt.value_label.text() == "900 ֏"
    assert supplier_service.periods[-1] == (None, None)

    monkeypatch.setattr(
        documents, "_ask_payment", lambda _outstanding: (Decimal("600"), PaymentMethod.CASH)
    )
    documents._pay_debt()
    qtbot.waitUntil(lambda: purchase_service.debt_payments == [Decimal("600")], timeout=2000)

    page.show_menu()
    page.show_payments()
    payments = page.payments_view
    qtbot.waitUntil(lambda: payments._table.row_count() == 1, timeout=2000)
    assert payments._table.item_model.item(0, 2).text() == "400 ֏"

    window._show_list()
    assert window._stack.currentWidget() is window._list_page


def test_supplier_overview_shows_totals_and_edits_selected_document(
    qtbot: Any, monkeypatch: Any
) -> None:
    supplier_service = _AccountSupplierService()
    purchase_service = _AccountPurchaseService()
    reopened: list[uuid.UUID] = []
    edited: list[tuple[bool, Decimal]] = []

    def _detail(purchase_id: uuid.UUID) -> PurchaseDetail:
        purchase = Purchase(
            id=purchase_id,
            purchase_number="PUR-001",
            supplier_id=supplier_service.supplier.id,
            purchase_date=datetime(2026, 9, 1, tzinfo=UTC),
            total=Decimal("1000"),
            status=PurchaseStatus.PARTIALLY_PAID,
        )
        return PurchaseDetail(purchase, [], [])

    monkeypatch.setattr(purchase_service, "get_detail", _detail, raising=False)
    monkeypatch.setattr(
        purchase_service, "reopen_for_edit", reopened.append, raising=False
    )
    monkeypatch.setattr("ui.purchase_document.confirm", lambda *_args: True)

    def _editor(
        _supplier: SupplierRow,
        _detail: PurchaseDetail,
        finalize: bool,
        paid: Decimal,
    ) -> bool:
        edited.append((finalize, paid))
        return True

    page = SupplierAccountPage(
        supplier_service,
        purchase_service,  # type: ignore[arg-type]
        on_back=lambda: None,
        on_changed=lambda: None,
        open_editor=_editor,
    )
    qtbot.addWidget(page)
    page.open(supplier_service.supplier)
    qtbot.waitUntil(lambda: page._debt.value_label.text() == "900 ֏", timeout=2000)
    assert page._documents.value_label.text() == "1"

    page.show_documents()
    documents = page.documents_view
    qtbot.waitUntil(lambda: documents._table.row_count() == 1, timeout=2000)
    documents._table.selectRow(0)
    documents._edit_document()
    qtbot.waitUntil(lambda: edited == [(True, Decimal("400"))], timeout=2000)
    assert len(reopened) == 1
