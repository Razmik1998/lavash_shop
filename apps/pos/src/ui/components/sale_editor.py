from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from networking.protocol import ProductPayload, SalePayload
from services import CustomerService
from ui.components.buttons import (
    CancelButton,
    DeleteButton,
    GhostButton,
    SaveButton,
    SecondaryButton,
)
from ui.components.customer_dialog import CreditCustomerDialog
from ui.components.discount_dialog import DiscountDialog
from ui.components.feedback import warn
from ui.components.inputs import AmountField, QuantityDialog, SearchField, TextField
from ui.components.panels import DebtorCard
from ui.components.tables import SimpleTable
from ui.style import format_currency, format_quantity
from ui.workers import run_in_background


class UnlockKeyDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Բացել վաճառքը")
        self._key = TextField("Մուտքագրեք գաղտնի բանալին", password=True)
        accept = SaveButton("Բացել", on_click=self.accept)
        cancel = CancelButton("Չեղարկել", on_click=self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(accept)
        layout = QVBoxLayout(self)
        layout.addWidget(self._key)
        layout.addLayout(buttons)

    def key(self) -> str:
        return self._key.value()


class SaleItemEditDialog(QDialog):
    def __init__(
        self,
        product: ProductPayload,
        quantity: Decimal,
        original_price: Decimal,
        current_price: Decimal,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Խմբագրել ապրանքը")
        self._original_price = original_price
        self._minimum_price = Decimal(product.minimum_price or original_price)
        self._price_value = current_price
        self._product_name = product.name
        self._quantity = AmountField(text=format_quantity(quantity))
        self._price = QLabel(format_currency(current_price))
        self._discount_value = QLabel(self._discount_text(current_price))
        self._discount_button = SecondaryButton(on_click=self._choose_discount)
        self._update_discount_button()

        form = QFormLayout()
        form.addRow("Ապրանք", QLabel(product.name))
        form.addRow(f"Քանակ ({product.unit})", self._quantity)
        form.addRow("Վաճառքի գին", QLabel(format_currency(original_price)))
        form.addRow("Ընթացիկ գին", self._price)
        form.addRow("Զեղչ", self._discount_value)
        form.addRow("Գործողություն", self._discount_button)

        buttons = QDialogButtonBox()
        save = buttons.addButton("Պահպանել", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = buttons.addButton("Չեղարկել", QDialogButtonBox.ButtonRole.RejectRole)
        save.clicked.connect(self._accept_if_valid)
        cancel.clicked.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _discount_text(self, price: Decimal) -> str:
        discount = (self._original_price - price) if price < self._original_price else Decimal("0")
        return format_currency(discount) if discount else ""

    def _choose_discount(self) -> None:
        dialog = DiscountDialog(
            self._product_name,
            self._original_price,
            self._minimum_price,
            self._price_value,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._price_value = dialog.price()
        self._price.setText(format_currency(self._price_value))
        self._discount_value.setText(self._discount_text(self._price_value))
        self._update_discount_button()

    def _update_discount_button(self) -> None:
        self._discount_button.setText(
            "Փոփոխել զեղչը"
            if self._price_value < self._original_price
            else "Ավելացնել զեղչ"
        )

    def _accept_if_valid(self) -> None:
        value = self._quantity.decimal_value()
        if value is not None and value > 0:
            self.accept()

    def quantity(self) -> Decimal | None:
        return self._quantity.decimal_value()

    def price(self) -> Decimal:
        return self._price_value

    def discounted(self) -> bool:
        return self._price_value < self._original_price


class SaleEditDialog(QWidget):
    back_requested = Signal()
    save_requested = Signal()
    def __init__(
        self,
        sale: SalePayload,
        products: list[ProductPayload],
        parent: object | None = None,
        *,
        customer_service: CustomerService | None = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self.setWindowTitle("Խմբագրել վաճառքը")
        self._products = products
        self._credit_customer_id = sale.credit_customer_id
        self._customer_service = customer_service
        self._product_by_id = {product.id: product for product in products}
        self._cart: dict[str, Decimal] = {
            item.product_id: Decimal(item.quantity)
            for item in sale.items
            if item.product_id is not None
        }
        self._cart_prices: dict[str, Decimal] = {
            item.product_id: Decimal(item.unit_price)
            for item in sale.items
            if item.product_id is not None
        }
        self._cart_original_prices: dict[str, Decimal] = {
            item.product_id: Decimal(item.original_unit_price)
            for item in sale.items
            if item.product_id is not None
        }
        self._product_list = SimpleTable(["Ապրանք", "Կոդ", "Գին"])
        self._cart_table = SimpleTable(["Ապրանք", "Քանակ", "Գին", "Գումար"])
        self._cart_total = QLabel()
        self._search = SearchField("Որոնել ապրանք", on_changed=self._render_products)
        self._remove = DeleteButton("Հեռացնել ընտրվածը", on_click=self._remove_selected)
        self._discount = SecondaryButton("Ավելացնել զեղչ", on_click=self._toggle_discount)
        self._dirty = False
        self._back = GhostButton("← Վերադառնալ", on_click=self.back_requested.emit)
        self._save = SaveButton("Պահպանել փոփոխությունները", on_click=self.save_requested.emit)
        self._change_customer = SecondaryButton(
            "Փոխել պարտապանին", on_click=self._choose_customer
        )
        self._customer_name: str | None = None
        self._change_customer.setText("⇄  Փոխել պարտապանին")
        self._change_customer.setMinimumHeight(44)
        self._mark_paid = SaveButton("💵  Վճարված է (կանխիկ)", on_click=self._make_cash)
        self._mark_paid.setMinimumHeight(44)
        self._payment_banner = DebtorCard(self._change_customer, self._mark_paid)
        self._update_payment_banner()
        self._load_customer_name()
        self._product_list.cellClicked.connect(self._add_product_row)
        self._cart_table.cellDoubleClicked.connect(self._change_quantity)
        self._render_products()
        self._render_cart()

        controls = QHBoxLayout()
        controls.addWidget(self._remove)
        controls.addWidget(self._discount)
        controls.addStretch()
        controls.addWidget(self._save)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(self._back)
        header.addStretch()
        header.addWidget(self._payment_banner)
        layout.addLayout(header)
        layout.addWidget(self._search)
        tables = QHBoxLayout()
        tables.addWidget(self._product_list, 1)
        cart_layout = QVBoxLayout()
        cart_layout.setContentsMargins(0, 0, 0, 0)
        cart_layout.addWidget(self._cart_table, 1)
        cart_layout.addWidget(self._cart_total)
        cart_panel = QWidget()
        cart_panel.setLayout(cart_layout)
        tables.addWidget(cart_panel, 1)
        layout.addLayout(tables, 1)
        layout.addLayout(controls)

    def items(self) -> list[tuple[str, str, str | None]]:
        return [
            (product_id, str(quantity), str(self._cart_prices.get(product_id, Decimal("0"))))
            for product_id, quantity in self._cart.items()
        ]

    def set_save_button_visible(self, visible: bool) -> None:
        self._save.setVisible(visible)

    def credit_customer_id(self) -> str | None:
        return self._credit_customer_id

    def _make_cash(self) -> None:
        if self._credit_customer_id is None:
            return
        self._credit_customer_id = None
        self._customer_name = None
        self._dirty = True
        self._update_payment_banner()

    def _update_payment_banner(self) -> None:
        is_credit = self._credit_customer_id is not None
        self._mark_paid.setVisible(is_credit)
        self._change_customer.setText(
            "⇄  Փոխել պարտապանին" if is_credit else "👤  Վաճառել պարտքով"
        )
        self._payment_banner.set_state(
            self._credit_customer_id is not None, self._customer_name
        )

    def _load_customer_name(self) -> None:
        customer_id = self._credit_customer_id
        if customer_id is None or self._customer_service is None:
            return
        service = self._customer_service

        def _on_loaded(customers: list[object]) -> None:
            for customer in customers:
                if getattr(customer, "id", None) == customer_id:
                    self._customer_name = (
                        f"{customer.first_name} {customer.last_name}"  # type: ignore[attr-defined]
                    )
            self._update_payment_banner()

        run_in_background(
            self,
            lambda: service.search_customers(""),
            _on_loaded,
            lambda _error: None,
        )

    def _choose_customer(self) -> None:
        if self._customer_service is None:
            return
        self._change_customer.setEnabled(False)
        run_in_background(
            self,
            lambda: self._customer_service.search_customers(""),
            self._show_customer_dialog,
            lambda _error: self._change_customer.setEnabled(True),
        )

    def _show_customer_dialog(self, customers: list[object]) -> None:
        self._change_customer.setEnabled(True)
        dialog = CreditCustomerDialog(
            customers, self._customer_service, self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selection = dialog.selection()
            if selection is not None:
                self._credit_customer_id = selection.customer_id
                self._customer_name = selection.name or None
                self._dirty = True
                self._update_payment_banner()

    def _render_products(self) -> None:
        term = self._search.value().lower()
        matching = [
            product for product in self._products
            if not term or term in product.name.lower() or term in product.sku.lower()
        ]
        self._product_list.set_rows(
            [product.name, product.sku, format_currency(product.selling_price or "0")]
            for product in matching
        )
        self._visible_products = matching

    def _add_product_row(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self._visible_products):
            return
        product = self._visible_products[row]
        dialog = QuantityDialog(product.unit, product_name=product.name, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        quantity = dialog.quantity()
        if quantity is None or quantity <= 0:
            warn(self, "Քանակը պետք է դրական լինի։")
            return
        self._cart[product.id] = self._cart.get(product.id, Decimal("0")) + quantity
        self._cart_prices.setdefault(product.id, Decimal(product.selling_price or "0"))
        self._cart_original_prices.setdefault(product.id, Decimal(product.selling_price or "0"))
        self._dirty = True
        self._render_cart()

    def _change_quantity(self, row: int, _column: int) -> None:
        product_id = self._cart_product_ids[row] if 0 <= row < len(self._cart_product_ids) else None
        if product_id is None:
            return
        product = self._product_by_id.get(product_id)
        if product is None:
            return
        original_price = self._cart_original_prices.get(
            product_id, Decimal(product.selling_price or "0")
        )
        current_price = self._cart_prices.get(product_id, original_price)
        dialog = SaleItemEditDialog(
            product,
            self._cart[product_id],
            original_price,
            current_price,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        quantity = dialog.quantity()
        if quantity is None or quantity <= 0:
            warn(self, "Քանակը պետք է դրական լինի։")
            return
        self._cart[product_id] = quantity
        self._cart_prices[product_id] = dialog.price()
        self._dirty = True
        self._render_cart()

    def _remove_selected(self) -> None:
        row = self._cart_table.currentRow()
        if 0 <= row < len(self._cart_product_ids):
            product_id = self._cart_product_ids[row]
            self._cart.pop(product_id, None)
            self._cart_prices.pop(product_id, None)
            self._cart_original_prices.pop(product_id, None)
            self._dirty = True
            self._render_cart()

    def _render_cart(self) -> None:
        self._cart_product_ids = list(self._cart)
        has_discount = any(
            self._cart_prices.get(product_id, Decimal("0"))
            < self._cart_original_prices.get(product_id, Decimal("0"))
            for product_id in self._cart_product_ids
            if (product := self._product_by_id.get(product_id)) is not None
        )
        if has_discount:
            self._cart_table.setColumnCount(5)
            self._cart_table.setHorizontalHeaderLabels(["Ապրանք", "Քանակ", "Գին", "Զեղչ", "Գումար"])
        else:
            self._cart_table.setColumnCount(4)
            self._cart_table.setHorizontalHeaderLabels(["Ապրանք", "Քանակ", "Գին", "Գումար"])
        rows = []
        total_quantity = Decimal("0")
        total_amount = Decimal("0")
        for product_id in self._cart_product_ids:
            product = self._product_by_id.get(product_id)
            if product is None:
                continue
            quantity = self._cart[product_id]
            original_price = Decimal(product.selling_price or "0")
            original_price = self._cart_original_prices.get(product_id, original_price)
            price = self._cart_prices.get(product_id, original_price)
            total_quantity += quantity
            total_amount += price * quantity
            row = [product.name, format_quantity(quantity), format_currency(price)]
            if has_discount:
                discount = (original_price - price) * quantity
                row.append(format_currency(discount) if discount else "")
            row.append(format_currency(price * quantity))
            rows.append(row)
        self._cart_table.set_rows(rows)
        self._cart_total.setText(
            f"Ընդհանուր քանակ՝ {format_quantity(total_quantity)}    "
            f"Ընդհանուր գումար՝ {format_currency(total_amount)}"
        )
        self._remove.setEnabled(bool(rows))
        self._discount.setEnabled(bool(rows))

    def _toggle_discount(self) -> None:
        row = self._cart_table.currentRow()
        if row < 0 or row >= len(self._cart_product_ids):
            return
        product_id = self._cart_product_ids[row]
        product = self._product_by_id.get(product_id)
        if product is None or product.minimum_price is None:
            return
        original_price = self._cart_original_prices.get(product_id, Decimal(product.selling_price or "0"))
        current_price = self._cart_prices.get(product_id, original_price)
        dialog = DiscountDialog(
            product.name,
            original_price,
            Decimal(product.minimum_price),
            current_price,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._cart_prices[product_id] = dialog.price()
        self._dirty = True
        self._discount.setText(
            "Փոփոխել զեղչը"
            if self._cart_prices[product_id] < original_price
            else "Ավելացնել զեղչ"
        )
        self._render_cart()

    def is_dirty(self) -> bool:
        return self._dirty

    def mark_saved(self) -> None:
        self._dirty = False
