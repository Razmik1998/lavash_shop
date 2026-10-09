from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import cast

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from networking.protocol import CustomerPayload, ProductPayload, SalePayload
from printing import ThermalPrinterService
from printing.models import Receipt, receipt_from_sale
from services import CustomerService, ProductService, SaleService
from ui.components import (
    ActionBar,
    AddButton,
    ChangeDueLabel,
    ChildProductSelectionDialog,
    ConfirmButton,
    CreditCustomerDialog,
    DeleteButton,
    DiscountDialog,
    IconLabel,
    MoneyField,
    Panel,
    QuantityDialog,
    SearchField,
    SecondaryButton,
    SimpleTable,
    report_error,
    warn,
)
from ui.components.icons import pos_icon
from ui.style import format_currency, format_quantity
from ui.workers import run_in_background, wait_for_pending_threads

logger = logging.getLogger(__name__)

POS_THEME_QSS = """
QWidget#root_view {
    background-color: #0c3a33;
    color: #ffffff;
    font-family: 'Segoe UI', system-ui, Arial, sans-serif;
    font-size: 13px;
}
QFrame#card_container {
    background-color: #114e45;
    border: 1px solid #186055;
    border-radius: 10px;
}
QFrame#header_bar {
    background-color: #0c3a33;
    border-bottom: 1px solid #186055;
}
QLineEdit {
    background-color: #186055;
    border: 1px solid #1b6b5e;
    border-radius: 8px;
    padding: 8px 12px;
    color: #ffffff;
    selection-background-color: #ffcc00;
    selection-color: #0c3a33;
}
QLineEdit:focus { border: 2px solid #ffcc00; }
QPushButton#primary_button {
    background-color: #ffcc00;
    color: #0c3a33;
    font-weight: bold;
    font-size: 16px;
    border: none;
    border-radius: 8px;
    padding: 12px 20px;
    min-height: 50px;
}
QPushButton#primary_button:hover { background-color: #e6b800; }
QPushButton#primary_button:pressed { background-color: #cca300; }
QPushButton#secondary_button {
    background-color: #186055;
    color: #ffffff;
    border: 1px solid #1b6b5e;
    border-radius: 15px;
    padding: 3px 14px;
    min-height: 30px;
}
QPushButton#secondary_button:hover { background-color: #1b6b5e; }
QLabel#checkout_header_title {
    color: #ffffff;
    font-size: 17px;
    font-weight: bold;
}
QLabel#checkout_header_subtitle,
QLabel#sectionTitle { color: #a0c4be; }
QLabel#cartTotal {
    color: #ffcc00;
    font-size: 34px;
    font-weight: bold;
}
QLabel#changeDue {
    color: #ff6b6b;
    font-size: 34px;
    font-weight: bold;
}
QLineEdit#moneyField {
    min-height: 42px;
    font-size: 30px;
    font-weight: bold;
    padding: 2px 12px;
}
QLabel#statusLabel { color: #a0c4be; }
QFrame#payCard, QFrame#payCardTotal, QFrame#payCardChange {
    background-color: #0f433c;
    border: 1px solid #1f7a6b;
    border-radius: 12px;
}
QFrame#payCardTotal {
    background-color: #12493f;
    border: 2px solid #ffcc00;
}
QFrame#payCardChange { border-color: #7a4a4f; }
QLabel#paymentCaption {
    color: #8fc2b8; font-size: 11px; font-weight: 600;
    letter-spacing: 1px; background: transparent; border: none;
}
QFrame#payCard QLabel, QFrame#payCardTotal QLabel,
QFrame#payCardChange QLabel { background: transparent; border: none; }
QTableWidget {
    background-color: #114e45;
    gridline-color: transparent;
    border: 1px solid #186055;
    border-radius: 6px;
    color: #ffffff;
    selection-background-color: #186055;
    selection-color: #ffcc00;
    alternate-background-color: #14564c;
}
QTableWidget::item {
    padding: 4px 6px;
}
QHeaderView::section {
    background-color: #114e45;
    color: #ffffff;
    font-weight: bold;
    padding: 4px 6px;
    border: none;
    border-bottom: 1px solid #1b6b5e;
}
QTableCornerButton::section {
    background-color: #186055;
    border: none;
}
QTabWidget::pane { border: none; background-color: transparent; }
QTabBar::tab {
    background-color: #186055;
    color: #a0c4be;
    padding: 8px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background-color: #114e45;
    color: #ffffff;
    border-bottom: 2px solid #ffcc00;
    font-weight: bold;
}

QFrame#productPanel, QFrame#cartPanel {
    background: #10473f; border: 1px solid #28695c; border-radius: 14px;
}
QFrame#card_container { background: #0c3a33; border: none; }
QTableWidget { background: #10473f; alternate-background-color: #164f46;
    border: none; selection-background-color: #267969; selection-color: #ffffff; }
QHeaderView::section { background: #10473f; color: #a0c4be;
    padding: 10px 8px; border-bottom: 1px solid #28695c; }
QLineEdit { background: #0c3a33; border: 1px solid #28695c; }
QPushButton#primary_button { border-radius: 12px; }
QLabel#sectionTitle { color: #d6efe9; font-size: 17px; font-weight: bold; }
"""

_UNIT_LABELS = {
    "piece": "Հատ",
    "kg": "Կգ",
    "g": "Գրամ",
    "l": "Լիտր",
    "barbecue": "Խորոված",
}


def _unit_label(unit: str) -> str:
    return _UNIT_LABELS.get(unit, unit)


def _quantity_for_request(quantity: Decimal) -> str:
    value = format(quantity, "f")
    if "." in value:
        return value.rstrip("0").rstrip(".")
    return value


class CheckoutWindow(QWidget):
    def __init__(self, product_service: ProductService, sale_service: SaleService,
                 session_id: str, terminal_id: str,
                 printer_service: ThermalPrinterService | None = None,
                 customer_service: CustomerService | None = None) -> None:
        super().__init__()
        self.setStyleSheet(POS_THEME_QSS)
        self.setObjectName("root_view")
        self._product_service = product_service
        self._sale_service = sale_service
        self._session_id = session_id
        self._terminal_id = terminal_id
        self._printer_service = printer_service
        self._customer_service = customer_service
        self._last_receipt: Receipt | None = None
        self._products: list[ProductPayload] = []
        self._cart: dict[str, Decimal] = {}
        self._cart_prices: dict[str, Decimal] = {}
        self._scan_buffer = ""
        self._product_list = SimpleTable(["Անուն", "Կոդ", "Գին"])
        self._product_list.setWordWrap(False)
        self._product_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._barbecue_actions = ActionBar()
        self._barbecue_buttons: list[AddButton] = []
        self._search = SearchField(
            "Որոնել անունով, SKU-ով կամ շտրիխ կոդով",
            on_changed=self._render_products,
            on_submit=self._add_scanned_product,
        )
        self._remove_button = DeleteButton(
            "Հեռացնել ընտրվածը",
            icon=pos_icon("close"), on_click=self._remove_selected_line
        )
        self._discount_button = SecondaryButton(
            "Ավելացնել զեղչ",
            icon=pos_icon("discount"), on_click=self._toggle_selected_discount
        )
        self._checkout_button = ConfirmButton(
            "Կատարել վաճառք",
            icon=pos_icon("check", "#0c3a33"), on_click=self._submit_sale
        )
        self._credit_button = SecondaryButton(
            "Վաճառք պարտքով",
            icon=pos_icon("customers"), on_click=self._start_credit_sale
        )
        self._reprint_button = SecondaryButton(
            "Կրկին տպել վերջին կտրոնը",
            icon=pos_icon("print"),
            on_click=self._reprint_last_receipt,
        )
        # Keep its slot in the footer from the start so the table never loses
        # height when a receipt becomes available after checkout.
        self._reprint_button.setEnabled(False)
        self._cart_table = SimpleTable(["Ապրանք", "Քանակ", "Գին", "Գումար"])
        self._cart_table.setShowGrid(False)
        self._product_list.setShowGrid(False)
        self._cart_table.setWordWrap(False)
        self._cart_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._cart_table.verticalHeader().setDefaultSectionSize(34)
        self._cart_total = QLabel("0 ֏")
        self._cart_total_amount = Decimal("0")
        self._received_amount = MoneyField(
            "", on_changed=self._update_change_due
        )
        self._received_amount.setAccessibleName("Ստացված գումար")
        self._change_due = ChangeDueLabel("0 ֏")
        self._received_caption = QLabel("Ստացված գումար")
        self._total_caption = QLabel("Ընդամենը")
        self._change_caption = QLabel("Վերադարձ")
        for caption in (
            self._received_caption,
            self._total_caption,
            self._change_caption,
        ):
            caption.setObjectName("paymentCaption")
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status = QLabel()
        self.setWindowTitle("Վաճառք")
        self._status.setObjectName("statusLabel")
        self._product_list.cellClicked.connect(self._add_product_row)
        self._cart_table.cellDoubleClicked.connect(self._discount_selected_line)
        self._cart_table.itemSelectionChanged.connect(self._update_discount_button)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(14, 4, 14, 4)
        header_layout.setSpacing(10)
        header_layout.addWidget(
            IconLabel("▣", "Վաճառք", "checkout_header_title")
        )
        header_layout.addStretch()
        header_layout.addWidget(
            IconLabel("●", "POS տերմինալ", "checkout_header_subtitle")
        )
        header_panel = Panel()
        header_panel.setObjectName("top_header")
        header_panel.setLayout(header_layout)

        product_layout = QVBoxLayout()
        product_layout.setContentsMargins(12, 12, 12, 12)
        product_layout.setSpacing(12)
        product_layout.addWidget(self._search)
        product_layout.addWidget(self._product_list, 1)
        product_layout.addWidget(self._barbecue_actions)
        cart_layout = QVBoxLayout()
        cart_layout.setContentsMargins(12, 12, 12, 12)
        cart_layout.setSpacing(12)
        cart_layout.addWidget(self._cart_table, 1)
        payment_layout = QHBoxLayout()
        payment_layout.setSpacing(12)
        for layout_, caption_, value_, card_name in (
            (received_layout := QVBoxLayout(), self._received_caption, self._received_amount, "payCard"),
            (total_layout := QVBoxLayout(), self._total_caption, self._cart_total, "payCardTotal"),
            (change_layout := QVBoxLayout(), self._change_caption, self._change_due, "payCardChange"),
        ):
            layout_.setContentsMargins(10, 8, 10, 10)
            layout_.setSpacing(2)
            layout_.addWidget(caption_)
            layout_.addWidget(value_, 1)
            card = Panel()
            card.setObjectName(card_name)
            card.setLayout(layout_)
            payment_layout.addWidget(
                card, {"payCard": 3, "payCardTotal": 5, "payCardChange": 3}[card_name]
            )
        cart_layout.addLayout(payment_layout)
        cart_layout.addWidget(self._checkout_button)
        footer_actions = QHBoxLayout()
        footer_actions.setSpacing(8)
        footer_actions.addWidget(self._credit_button, 1)
        footer_actions.addWidget(self._reprint_button, 1)
        cart_layout.addLayout(footer_actions)
        cart_layout.addWidget(self._status)
        self._cart_total.setObjectName("cartTotal")
        self._remove_button.setObjectName("secondary_button")
        self._checkout_button.setObjectName("primary_button")
        tables_heading = QHBoxLayout()
        tables_heading.setContentsMargins(10, 0, 10, 0)
        tables_heading.setSpacing(6)
        tables_heading.addWidget(IconLabel("⌕", "Ապրանքներ", "sectionTitle"), 2)
        tables_heading.addWidget(IconLabel("▤", "Պատվերի ցանկ", "sectionTitle"))
        tables_heading.addStretch(1)
        tables_heading.addWidget(self._remove_button)
        tables_heading.addWidget(self._discount_button)
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(12)
        tables_layout = QHBoxLayout()
        tables_layout.setSpacing(16)
        products_panel = Panel()
        products_panel.setObjectName("productPanel")
        products_panel.setLayout(product_layout)
        cart_panel = Panel()
        cart_panel.setObjectName("cartPanel")
        cart_panel.setLayout(cart_layout)
        tables_layout.addWidget(products_panel, 2)
        tables_layout.addWidget(cart_panel, 3)
        content_layout.addLayout(tables_heading)
        content_layout.addLayout(tables_layout, 1)
        content_panel = Panel()
        content_panel.setObjectName("card_container")
        content_panel.setLayout(content_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(header_panel)
        layout.addWidget(content_panel, 1)
        self.setLayout(layout)
        self._cart_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._configure_cart_columns()
        QApplication.instance().installEventFilter(self)
        run_in_background(self, self._product_service.list_products,
                          self._on_products_loaded, self._on_load_failed)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Keep payment controls compact enough for the cart on short displays."""
        super().resizeEvent(event)
        compact = self.height() < 850
        very_compact = self.height() < 700
        label_size = 28 if compact else 34
        total_size = 48 if compact else 60
        field_size = 16 if compact else 20
        self._cart_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cart_total.setWordWrap(False)
        self._change_due.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cart_total.setStyleSheet(
            f"font-size: {total_size}px; font-weight: bold; color: #ffcc00;"
        )
        self._change_due.setStyleSheet(
            f"font-size: {label_size}px; font-weight: bold; color: #ff6b6b;"
        )
        self._received_amount.setStyleSheet(
            f"font-size: {field_size}px; font-weight: bold; "
            f"min-height: {32 if compact else 38}px; padding: 2px 8px;"
        )
        row_height = 30 if very_compact else 36 if compact else 42
        self._cart_table.verticalHeader().setDefaultSectionSize(row_height)
        self._product_list.verticalHeader().setDefaultSectionSize(row_height)

    def _on_products_loaded(self, products: list[ProductPayload]) -> None:
        self._products = products
        self._render_products()
        self._render_barbecue_actions()

    def _on_load_failed(self, error: Exception) -> None:
        self._status.setText("Չհաջողվեց բեռնել ապրանքները։")

    def _render_products(self) -> None:
        term = self._search.text().strip().lower()
        product_by_id = {product.id: product for product in self._products}
        self._product_list.setRowCount(0)
        for product in self._products:
            if product.unit == "barbecue":
                continue
            display_name = self._display_product_name(product, product_by_id)
            searchable = (product.name, product.sku, product.barcode or "")
            searchable = (*searchable, display_name)
            if term and not any(term in value.lower() for value in searchable):
                continue
            row = self._product_list.rowCount()
            self._product_list.insertRow(row)
            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, product)
            self._product_list.setItem(row, 0, name_item)
            self._product_list.setItem(row, 1, QTableWidgetItem(product.sku))
            self._product_list.setItem(
                row,
                2,
                QTableWidgetItem(
                    "-"
                    if product.selling_price is None
                    else format_currency(product.selling_price)
                ),
            )

    def _render_barbecue_actions(self) -> None:
        for button in self._barbecue_buttons:
            button.setVisible(False)
        self._barbecue_buttons.clear()
        for parent in self._barbecue_parents():
            button = AddButton(
                "Խորոված",
                on_click=lambda selected_parent=parent: self._request_child_quantities(
                    selected_parent
                ),
            )
            self._barbecue_buttons.append(button)
            self._barbecue_actions.add(button)

    def _barbecue_parents(self) -> list[ProductPayload]:
        return [
            product for product in self._products if product.unit == "barbecue"
        ]

    @staticmethod
    def _display_product_name(
        product: ProductPayload, product_by_id: dict[str, ProductPayload]
    ) -> str:
        if product.parent_product_id is None:
            return product.name.title()
        parent = product_by_id.get(product.parent_product_id)
        if parent is None:
            return product.name.title()
        return f"{parent.name.title()} -> {product.name.title()}"

    def _add_product_row(self, row: int, _column: int) -> None:
        item = self._product_list.item(row, 0)
        if item is None:
            return
        product = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(product, ProductPayload):
            self._request_quantity(product)

    def _add_scanned_product(self) -> None:
        code = self._search.text().strip()
        if not code or not code.isdigit():
            return
        self._search.clear()
        self._lookup_scanned_code(code)

    def _lookup_scanned_code(self, code: str) -> None:
        product = next(
            (
                candidate
                for candidate in self._products
                if candidate.barcode == code
            ),
            None,
        )
        if product is None:
            warn(self, f"Կոդ՝ {code}, ապրանք չի գտնվել։", "Ապրանքը չի գտնվել")
            return
        self._request_quantity(product)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if QApplication.activeModalWidget() is not None:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.KeyPress:
            if self._received_amount.hasFocus():
                return super().eventFilter(watched, event)
            key_event = cast(QKeyEvent, event)
            if key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if key_event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._submit_sale()
                    return True
                if not isinstance(watched, QLineEdit):
                    self._submit_scan_buffer()
                    return True
            text = key_event.text()
            if text.isdigit() and not isinstance(watched, QLineEdit):
                self._scan_buffer += text
                return True
        return super().eventFilter(watched, event)

    def _submit_scan_buffer(self) -> None:
        code = self._scan_buffer
        self._scan_buffer = ""
        if not code:
            return
        self._lookup_scanned_code(code)

    def _request_quantity(self, product: ProductPayload) -> None:
        if product.unit == "barbecue":
            self._request_child_quantities(product)
            return
        product_by_id = {candidate.id: candidate for candidate in self._products}
        dialog = QuantityDialog(
            _unit_label(product.unit),
            product_name=self._display_product_name(product, product_by_id),
            parent=self,
        )
        if dialog.exec() == QuantityDialog.DialogCode.Accepted:
            quantity = dialog.quantity()
            if quantity is not None:
                self._add_product(product, quantity)

    def _request_child_quantities(self, parent: ProductPayload) -> None:
        children = [
            product
            for product in self._products
            if product.parent_product_id == parent.id
            and product.selling_price is not None
        ]
        if not children:
            warn(self, "Այս խորովածի համար ենթաապրանք չկա։", "Ապրանքները բացակայում են")
            return
        dialog = ChildProductSelectionDialog(parent.name, children, parent=self)
        if dialog.exec() != ChildProductSelectionDialog.DialogCode.Accepted:
            return
        for child, quantity in dialog.selected_children(children):
            self._add_product(child, quantity)

    def _add_product(self, product: ProductPayload, requested: Decimal) -> None:
        total_quantity = self._cart.get(product.id, Decimal("0")) + requested
        self._cart[product.id] = total_quantity
        self._cart_prices.setdefault(product.id, Decimal(product.selling_price or "0"))
        self._render_cart()

    def _remove_selected_line(self) -> None:
        row = self._cart_table.currentRow()
        if row < 0:
            return
        item = self._cart_table.item(row, 0)
        if item is None:
            return
        product_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(product_id, str):
            self._cart.pop(product_id, None)
            self._cart_prices.pop(product_id, None)
            self._render_cart()

    def _render_cart(self) -> None:
        product_by_id = {product.id: product for product in self._products}
        self._cart_table.setRowCount(0)
        total = Decimal("0")
        has_discount = any(
            self._cart_prices.get(product_id, Decimal(product_by_id[product_id].selling_price or "0"))
            < Decimal(product_by_id[product_id].selling_price or "0")
            for product_id in self._cart
        )
        if has_discount:
            self._cart_table.setColumnCount(5)
            self._cart_table.setHorizontalHeaderLabels(["Ապրանք", "Քանակ", "Գին", "Զեղչ", "Գումար"])
        else:
            self._cart_table.setColumnCount(4)
            self._cart_table.setHorizontalHeaderLabels(["Ապրանք", "Քանակ", "Գին", "Գումար"])
        self._configure_cart_columns()
        for product_id, quantity in self._cart.items():
            product = product_by_id[product_id]
            original_price = Decimal(product.selling_price or "0")
            price = self._cart_prices.get(product_id, original_price)
            line_total = price * quantity
            total += line_total
            row = self._cart_table.rowCount()
            self._cart_table.insertRow(row)
            name_item = QTableWidgetItem(
                self._display_product_name(product, product_by_id)
            )
            name_item.setData(Qt.ItemDataRole.UserRole, product.id)
            self._cart_table.setItem(row, 0, name_item)
            self._cart_table.setItem(
                row,
                1,
                QTableWidgetItem(
                    f"{format_quantity(quantity)} {_unit_label(product.unit)}"
                ),
            )
            self._cart_table.setItem(
                row, 2, QTableWidgetItem(format_currency(price))
            )
            if has_discount:
                discount = (original_price - price) * quantity
                self._cart_table.setItem(row, 3, QTableWidgetItem(format_currency(discount) if discount else ""))
                self._cart_table.setItem(row, 4, QTableWidgetItem(format_currency(line_total)))
            else:
                self._cart_table.setItem(row, 3, QTableWidgetItem(format_currency(line_total)))
            for column in range(1, self._cart_table.columnCount()):
                item = self._cart_table.item(row, column)
                if item is not None:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cart_total_amount = total
        self._cart_total.setText(format_currency(total))
        self._discount_button.setEnabled(bool(self._cart))
        self._update_discount_button()
        self._update_change_due()

    def _configure_cart_columns(self) -> None:
        header = self._cart_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, self._cart_table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

    def _update_change_due(self) -> None:
        received = self._received_amount.decimal_value()
        change = max(Decimal("0"), (received or Decimal("0")) - self._cart_total_amount)
        self._change_due.setText(format_currency(change))

    def _submit_sale(self) -> None:
        self._submit_sale_for_customer(None)

    def _start_credit_sale(self) -> None:
        if not self._cart or self._customer_service is None:
            self._status.setText("Ավելացրեք ապրանք և միացեք հաճախորդների ծառայությանը։")
            return
        self._credit_button.setEnabled(False)
        run_in_background(
            self,
            lambda: self._customer_service.search_customers(""),
            self._show_credit_customer_dialog,
            self._on_credit_failed,
        )

    def _show_credit_customer_dialog(self, customers: list[CustomerPayload]) -> None:
        self._credit_button.setEnabled(True)
        dialog = CreditCustomerDialog(
            customers, self._customer_service, self, self._session_id
        )
        if dialog.exec() != CreditCustomerDialog.DialogCode.Accepted:
            return
        selection = dialog.selection()
        if selection is None:
            return
        self._submit_sale_for_customer(selection)

    def _submit_sale_for_customer(self, selection: object | None) -> None:
        if not self._cart:
            self._status.setText("Զամբյուղը դատարկ է։")
            return
        items = [
            (
                product_id,
                _quantity_for_request(quantity),
                str(self._cart_prices.get(product_id, Decimal("0"))),
            )
            for product_id, quantity in self._cart.items()
        ]
        self._checkout_button.setEnabled(False)
        self._credit_button.setEnabled(False)

        def submit() -> SalePayload:
            customer_id = getattr(selection, "customer_id", None)
            if customer_id is None:
                if self._customer_service is None:
                    raise RuntimeError("Customer service is not configured")
                customer = self._customer_service.create_customer(
                    selection.first_name,
                    selection.last_name,
                    selection.phone,
                    selection.address,
                    selection.notes,
                )
                customer_id = customer.id
            return self._sale_service.create_sale(
                self._session_id,
                self._terminal_id,
                str(uuid.uuid4()),
                items,
                customer_id,
            )

        run_in_background(
            self,
            submit if selection is not None else lambda: self._sale_service.create_sale(
                self._session_id, self._terminal_id, str(uuid.uuid4()), items
            ),
            lambda receipt: self._on_sale_created(receipt, selection is not None),
            self._on_sale_failed,
        )

    def _on_sale_created(self, receipt: object, is_credit: bool = False) -> None:
        self._checkout_button.setEnabled(True)
        self._credit_button.setEnabled(True)
        if not isinstance(receipt, SalePayload):
            self._status.setText("Ստացվել է անվավեր կտրոն։")
            return
        self._cart.clear()
        self._cart_prices.clear()
        self._received_amount.clear()
        self._render_cart()
        self._status.setText(
            "Վաճառքը պահվեց պարտքով։" if is_credit else "Վաճառքը կատարված է։"
        )
        self._last_receipt = receipt_from_sale(receipt)
        if self._printer_service is not None and self._printer_service.enabled:
            self._reprint_button.setEnabled(True)
            self._print_receipt(self._last_receipt)

    def _print_receipt(self, receipt: Receipt) -> None:
        printer_service = self._printer_service
        if printer_service is None:
            return
        run_in_background(
            self,
            lambda: printer_service.print_receipt(receipt),
            lambda _printed: self._status.setText(
                "Վաճառքը կատարված է։ Կտրոնը տպվեց։"
            ),
            self._on_print_failed,
        )

    def _reprint_last_receipt(self) -> None:
        if self._last_receipt is not None:
            self._print_receipt(self._last_receipt)

    def _on_print_failed(self, error: Exception) -> None:
        self._status.setText("Վաճառքը պահպանված է, բայց կտրոնը չտպվեց։")
        logger.warning(
            "printing op=receipt outcome=failed sale_id=%s error=%s",
            (
                self._last_receipt.sale_id
                if self._last_receipt is not None
                else "unknown"
            ),
            error,
            exc_info=(type(error), error, error.__traceback__),
        )

    def _on_credit_failed(self, error: Exception) -> None:
        self._credit_button.setEnabled(True)
        report_error(self, f"Չհաջողվեց բեռնել պարտապանների ցանկը։\n{error}")

    def _discount_selected_line(self, row: int, _column: int) -> None:
        self._toggle_discount(row)

    def _toggle_selected_discount(self) -> None:
        self._toggle_discount(self._cart_table.currentRow())

    def _toggle_discount(self, row: int) -> None:
        if row < 0 or row >= self._cart_table.rowCount():
            return
        item = self._cart_table.item(row, 0)
        product_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(product_id, str):
            return
        product = next((item for item in self._products if item.id == product_id), None)
        if product is None or product.minimum_price is None:
            return
        minimum_price = Decimal(product.minimum_price)
        current_price = self._cart_prices.get(product_id, Decimal(product.selling_price or "0"))
        original_price = Decimal(product.selling_price or "0")
        dialog = DiscountDialog(
            product.name, original_price, minimum_price, current_price, self
        )
        if dialog.exec() != DiscountDialog.DialogCode.Accepted:
            return
        self._cart_prices[product_id] = dialog.price()
        self._render_cart()
        for current_row in range(self._cart_table.rowCount()):
            current_item = self._cart_table.item(current_row, 0)
            if current_item is not None and current_item.data(Qt.ItemDataRole.UserRole) == product_id:
                self._cart_table.selectRow(current_row)
                break

    def _update_discount_button(self) -> None:
        row = self._cart_table.currentRow()
        if row < 0 or row >= self._cart_table.rowCount():
            self._discount_button.setText("Ավելացնել զեղչ")
            return
        item = self._cart_table.item(row, 0)
        product_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        product = next((candidate for candidate in self._products if candidate.id == product_id), None)
        if product is None or product.minimum_price is None:
            self._discount_button.setText("Ավելացնել զեղչ")
            return
        current_price = self._cart_prices.get(product.id, Decimal(product.selling_price or "0"))
        self._discount_button.setText(
            "Փոփոխել զեղչը"
            if current_price < Decimal(product.selling_price or "0")
            else "Ավելացնել զեղչ"
        )

    def _on_sale_failed(self, error: Exception) -> None:
        self._checkout_button.setEnabled(True)
        report_error(self, f"Չհաջողվեց պահպանել վաճառքը։\n{error}")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        QApplication.instance().removeEventFilter(self)
        wait_for_pending_threads(self)
        super().closeEvent(event)
