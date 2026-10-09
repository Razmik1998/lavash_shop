"""Armenian supplier list and lifecycle actions."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from models import PaymentMethod, Product, Unit
from services import (
    PurchaseDetail,
    PurchaseLineInput,
    SupplierAccount,
    SupplierHistory,
    SupplierRow,
    SupplierSummary,
)
from ui.components import (
    ActionBar,
    AddButton,
    AmountField,
    ArchiveButton,
    BackButton,
    CancelButton,
    ConfirmButton,
    DataTable,
    DeleteButton,
    DetailsButton,
    DialogButtonBar,
    Divider,
    EditButton,
    ErrorLabel,
    FormCard,
    FormField,
    MoneyField,
    PageHeader,
    PageSubtitle,
    PageTitle,
    Panel,
    QuantityField,
    RefreshButton,
    RestoreButton,
    SaveButton,
    SearchButton,
    SearchField,
    SectionHeading,
    SelectField,
    StatCard,
    StatusBadge,
    TextArea,
    TextField,
    confirm,
    inform,
    warn,
)
from ui.product_form_dialog import ProductFormDialog, unit_label
from ui.style import (
    configure_page_layout,
    format_currency,
    format_quantity,
)
from ui.supplier_account_page import SupplierAccountPage, SupplierPaymentService
from ui.workers import run_in_background, wait_for_pending_threads

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


def _format_percentage(value: Decimal) -> str:
    return format_quantity(value)


def _selling_price_text(value: Decimal | None) -> str:
    return format_currency(value) if value is not None else "—"


class ProductService(Protocol):
    def list_active_products(self) -> list[Product]: ...

    def search_products(self, term: str) -> list[Product]: ...

    def create_product(
        self,
        name: str,
        sku: str,
        barcode: str | None,
        unit: Unit,
        cost_price: Decimal | None,
        selling_price: Decimal | None,
        minimum_price: Decimal | None,
        quantity_in_stock: Decimal,
        low_stock_threshold: Decimal | None,
        is_active: bool,
        parent_product_id: uuid.UUID | None = None,
        is_for_sale: bool = True,
    ) -> Product: ...


class PurchaseService(Protocol):
    def create_draft(
        self,
        supplier_id: uuid.UUID,
        purchase_date: datetime,
        notes: str | None,
        lines: list[PurchaseLineInput],
    ) -> object: ...

    def confirm(
        self,
        purchase_id: uuid.UUID,
        initial_payment: Decimal = Decimal("0"),
        payment_method: PaymentMethod = PaymentMethod.CASH,
        price_updates: dict[uuid.UUID, Decimal] | None = None,
    ) -> object: ...

    def update_draft(
        self,
        purchase_id: uuid.UUID,
        supplier_id: uuid.UUID,
        purchase_date: datetime,
        notes: str | None,
        lines: list[PurchaseLineInput],
    ) -> object: ...

    def reopen_for_edit(self, purchase_id: uuid.UUID) -> object: ...


class SupplierPurchaseService(PurchaseService, SupplierPaymentService, Protocol):
    pass


class PurchaseDialog(QDialog):
    def __init__(
        self,
        supplier: SupplierRow,
        purchase_service: PurchaseService,
        product_service: ProductService,
        detail: PurchaseDetail | None = None,
        finalize_on_save: bool = False,
        initial_payment: Decimal = Decimal("0"),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Նոր գնում")
        self._supplier = supplier
        self._purchase_service = purchase_service
        self._product_service = product_service
        self._finalize_on_save = finalize_on_save
        self._products: list[Product] = []
        self._selected_index = -1
        self._lines: list[PurchaseLineInput] = []
        self._original_selling_price: Decimal | None = None
        self._original_selling_prices: dict[uuid.UUID, Decimal] = {}
        self._price_updates: dict[uuid.UUID, Decimal] = {}
        self._draft_id = detail.purchase.id if detail is not None else None
        self._purchase_date = (
            detail.purchase.purchase_date
            if detail is not None
            else datetime.now(ARMENIA_TIMEZONE)
        )
        self._search = SearchField(
            "Փնտրել անունով, կոդով կամ շտրիխով", on_submit=self._search_products
        )
        search_button = SearchButton(on_click=self._search_products)
        new_product_button = AddButton("Ստեղծել նոր ապրանք", on_click=self._new_product)
        self._catalog = DataTable(
            ["Ապրանք", "Կոդ", "Վաճառքի գին"],
            on_click=self._catalog_selected,
            min_width=360,
        )
        self._catalog_model = self._catalog.item_model
        self._product_label = SectionHeading("Ընտրեք ապրանք")
        self._unit_display = PageSubtitle("Կատալոգից ապրանք ընտրելուց հետո")
        self._quantity = QuantityField(text="1", digits_only=True)
        self._cost = MoneyField(
            "Գնման գին", digits_only=True, on_changed=self._cost_changed
        )
        self._selling_price = MoneyField(
            "Վաճառքի գին", digits_only=True, on_changed=self._markup_from_selling
        )
        self._markup = AmountField(
            "Մարժա %", digits_only=True, on_changed=self._selling_from_markup
        )
        add_line_button = AddButton("Ավելացնել զամբյուղ", on_click=self._add_line)
        remove_line_button = DeleteButton(
            "Հեռացնել ընտրվածը", on_click=self._remove_line
        )
        self._lines_table = DataTable(
            ["Ապրանք", "Քանակ", "Գնման գին", "Վաճառքի գին", "Մարժա", "Ընդամենը"],
            min_height=220,
            min_width=620,
        )
        self._lines_model = self._lines_table.item_model
        self._lines_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._lines_table.horizontalHeader().setMinimumSectionSize(110)
        self._payment = MoneyField(
            "Կանխավճար",
            text=str(initial_payment),
            on_edited=self._refresh_basket_summary,
        )
        self._item_count = StatCard("Տեսականի", "0", tone="info")
        self._unit_count = StatCard("Ընդհանուր քանակ", "0")
        self._purchase_total = StatCard("Գնման գումար", "0 ֏", tone="primary")
        self._remaining_debt = StatCard("Մնացորդ", "0 ֏", tone="danger")
        save_button = SaveButton("Պահպանել որպես սևագիր", on_click=self._save_draft)
        confirm_button = ConfirmButton("Ավարտել գնումը", on_click=self._confirm)
        if finalize_on_save:
            # Editing an already completed document: saving must re-apply it.
            save_button.setVisible(False)
            confirm_button.setText("Պահպանել")
        cancel_button = CancelButton(on_click=self.reject)

        search_row = QHBoxLayout()
        search_row.addWidget(self._search)
        search_row.addWidget(search_button)
        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(12)
        field_grid.setVerticalSpacing(10)
        for column in range(2):
            field_grid.setColumnStretch(column, 1)
        field_grid.addWidget(FormField("Քանակ", self._quantity), 0, 0)
        field_grid.addWidget(FormField("Գնման գին", self._cost), 0, 1)
        field_grid.addWidget(FormField("Վաճառքի գին", self._selling_price), 1, 0)
        field_grid.addWidget(FormField("Մարժա (%)", self._markup), 1, 1)
        self._selling_field = field_grid.itemAtPosition(1, 0).widget()
        self._markup_field = field_grid.itemAtPosition(1, 1).widget()
        line_actions = ActionBar([add_line_button])
        buttons = DialogButtonBar([cancel_button, save_button, confirm_button])

        catalog_panel = Panel()
        catalog_layout = QVBoxLayout(catalog_panel)
        catalog_layout.setContentsMargins(18, 16, 18, 16)
        catalog_layout.setSpacing(12)
        catalog_header = QHBoxLayout()
        catalog_header.addWidget(
            PageHeader("Ապրանքների կատալոգ", "Գտեք ապրանքը անունով կամ կոդով"), 1
        )
        catalog_header.addWidget(new_product_button)
        catalog_layout.addLayout(catalog_header)
        catalog_layout.addLayout(search_row)
        catalog_layout.addWidget(self._catalog, stretch=1)

        editor_panel = Panel()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(18, 16, 18, 16)
        editor_layout.setSpacing(12)
        editor_layout.addWidget(
            PageHeader("Ապրանքի տվյալներ", "Լրացրեք ընտրված ապրանքի գնման տվյալները")
        )
        selected_product_panel = Panel()
        selected_product_layout = QVBoxLayout(selected_product_panel)
        selected_product_layout.setContentsMargins(14, 12, 14, 12)
        selected_product_layout.setSpacing(4)
        selected_product_layout.addWidget(PageSubtitle("ԸՆՏՐՎԱԾ ԱՊՐԱՆՔ"))
        selected_product_layout.addWidget(self._product_label)
        selected_product_layout.addWidget(self._unit_display)
        editor_layout.addWidget(selected_product_panel)
        editor_layout.addLayout(field_grid)
        editor_layout.addWidget(line_actions)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(catalog_panel)
        splitter.addWidget(editor_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 6)
        splitter.setChildrenCollapsible(False)
        splitter.setMinimumHeight(300)

        heading = "Խմբագրում" if detail is not None else "Նոր գնում"
        header = PageHeader(
            f"{heading} — {supplier.name}",
            "Ընտրեք ապրանքները, ստուգեք գումարները և ավարտեք գնումը",
        )

        self._cart_stack = QStackedWidget()
        empty_cart = QWidget()
        empty_cart_layout = QVBoxLayout(empty_cart)
        empty_cart_layout.setContentsMargins(20, 12, 20, 12)
        empty_cart_message = PageSubtitle(
            "Զամբյուղը դատարկ է․ ընտրեք ապրանք և ավելացրեք այն գնումին։"
        )
        empty_cart_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_cart_layout.addWidget(empty_cart_message)
        self._cart_stack.addWidget(empty_cart)
        self._cart_stack.addWidget(self._lines_table)

        cart_panel = Panel()
        cart_layout = QVBoxLayout(cart_panel)
        cart_layout.setContentsMargins(18, 14, 18, 16)
        cart_layout.setSpacing(10)
        cart_header = QHBoxLayout()
        cart_header.addWidget(
            PageHeader("Գնման զամբյուղ", "Ավելացված ապրանքների ամփոփ ցանկը"), 1
        )
        cart_header.addWidget(remove_line_button)
        cart_layout.addLayout(cart_header)
        cart_layout.addWidget(self._cart_stack, stretch=1)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)
        content_layout.addWidget(splitter, stretch=3)
        content_layout.addWidget(cart_panel, stretch=2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        summary_panel = Panel()
        summary_layout = QVBoxLayout(summary_panel)
        summary_layout.setContentsMargins(18, 14, 18, 14)
        summary_layout.setSpacing(10)
        summary_row = QHBoxLayout()
        summary_row.setSpacing(10)
        summary_row.addWidget(self._item_count, 1)
        summary_row.addWidget(self._unit_count, 1)
        summary_row.addWidget(self._purchase_total, 1)
        summary_row.addWidget(FormField("Կանխավճար", self._payment), 1)
        summary_row.addWidget(self._remaining_debt, 1)
        summary_layout.addLayout(summary_row)
        summary_layout.addWidget(Divider())
        summary_layout.addWidget(buttons)

        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.addWidget(header)
        layout.addWidget(scroll, stretch=1)
        layout.addWidget(summary_panel)
        self.resize(1240, 760)
        self.setMinimumSize(960, 620)
        self._refresh_basket_summary()
        self._load_catalog()
        if detail is not None:
            self._populate_detail(detail)

    def _load_catalog(self) -> None:
        if hasattr(self._product_service, "list_active_products"):
            run_in_background(
                self,
                self._product_service.list_active_products,
                self._products_loaded,
                self._failed,
            )

    def _catalog_selected(self) -> None:
        row = self._catalog.selected_row()
        if row < 0 or row >= len(self._products):
            return
        self._selected_index = row
        self._product_selection_changed()

    def _product_selection_changed(self) -> None:
        index = self._selected_index
        if index < 0 or index >= len(self._products):
            self._original_selling_price = None
            self._product_label.setText("Ընտրեք ապրանք")
            self._unit_display.setText("Կատալոգից ապրանք ընտրելուց հետո")
            self._markup.clear()
            return
        product = self._products[index]
        parent = next(
            (
                candidate
                for candidate in self._products
                if candidate.id == product.parent_product_id
            ),
            None,
        )
        self._product_label.setText(f"{product.display_name(parent)} ({product.sku})")
        self._unit_display.setText(unit_label(product.unit))
        self._quantity.setText("1")
        self._cost.setText(format_quantity(product.cost_price or Decimal("0")))
        self._selling_price.setText(format_quantity(product.selling_price))
        self._markup_from_selling()
        sellable = product.is_for_sale is not False
        self._selling_field.setVisible(sellable)
        self._markup_field.setVisible(sellable)
        self._original_selling_price = self._original_selling_prices.get(
            product.id, product.selling_price
        )

    def _populate_detail(self, detail: PurchaseDetail) -> None:
        for item in detail.items:
            try:
                unit = Unit(item.unit)
            except ValueError:
                continue
            product = Product(
                id=item.product_id,
                name=item.product_name,
                sku=item.product_sku,
                unit=unit,
                selling_price=item.selling_price,
                quantity_in_stock=Decimal("0"),
                is_active=True,
                is_for_sale=item.selling_price is not None,
            )
            self._products.append(product)
            line = PurchaseLineInput(
                item.product_id,
                item.quantity,
                item.unit_cost,
                item.selling_price,
                item.markup_percentage,
            )
            self._lines.append(line)
            self._lines_table.append_row(
                [
                    item.product_name,
                    format_quantity(item.quantity),
                    format_currency(item.unit_cost),
                    _selling_price_text(item.selling_price),
                    (
                        f"{_format_percentage(item.markup_percentage)}%"
                        if item.selling_price is not None
                        else "—"
                    ),
                    format_currency(item.line_total),
                ]
            )
        self._refresh_basket_summary()

    def _search_products(self) -> None:
        term = self._search.text().strip()
        if not term:
            warn(self, "Մուտքագրեք որոնման արժեք։")
            return
        run_in_background(
            self,
            lambda: self._product_service.search_products(term),
            self._products_loaded,
            self._failed,
        )

    def _products_loaded(self, products: list[Product]) -> None:
        self._products = products
        self._original_selling_prices = {
            product.id: product.selling_price for product in products
        }
        self._catalog.clear_rows()
        for product in products:
            parent = next(
                (
                    candidate
                    for candidate in products
                    if candidate.id == product.parent_product_id
                ),
                None,
            )
            self._catalog.append_row(
                [
                    product.display_name(parent),
                    product.sku,
                    _selling_price_text(product.selling_price),
                ]
            )
        self._selected_index = 0 if products else -1
        self._product_selection_changed()
        if not products:
            inform(self, "Ապրանք չի գտնվել։", "Որոնում")

    def _add_line(self) -> None:
        index = self._selected_index
        if index < 0 or index >= len(self._products):
            warn(self, "Ընտրեք ապրանք ցանկից։")
            return
        quantity = self._quantity.decimal_value()
        cost = self._cost.decimal_value()
        product = self._products[self._selected_index]
        sellable = product.is_for_sale is not False
        selling_price = self._selling_price.decimal_value() if sellable else None
        if quantity is None or cost is None or (sellable and selling_price is None):
            warn(self, "Քանակը և պահանջվող գները պետք է լինեն թվեր։")
            return
        if (
            quantity <= 0
            or cost < 0
            or (selling_price is not None and selling_price < 0)
        ):
            warn(self, "Քանակը պետք է լինի դրական, իսկ գները՝ ոչ բացասական։")
            return
        original_selling_price = product.selling_price
        if selling_price is not None and selling_price != original_selling_price:
            if not confirm(
                self,
                "Գնի փոփոխություն",
                f"Նախորդ գին՝ {format_currency(original_selling_price)}\n"
                f"Նոր գին՝ {format_currency(selling_price)}\n\n"
                "Նոր գինը կկիրառվի միայն գնումը ավարտելուց հետո։",
            ):
                return
            self._price_updates[product.id] = selling_price
        markup = (
            (
                (selling_price - cost) / cost * Decimal("100")
                if cost > 0
                else Decimal("0")
            )
            if selling_price is not None
            else Decimal("0")
        )
        line = PurchaseLineInput(product.id, quantity, cost, selling_price, markup)
        self._lines.append(line)
        self._lines_table.append_row(
            [
                product.name,
                format_quantity(quantity),
                format_currency(cost),
                _selling_price_text(selling_price),
                f"{_format_percentage(markup)}%" if selling_price is not None else "—",
                format_currency(quantity * cost),
            ]
        )
        self._quantity.setText("1")
        self._refresh_basket_summary()

    def _remove_line(self) -> None:
        row = self._lines_table.selected_row()
        if row < 0 or row >= len(self._lines):
            warn(self, "Ընտրեք ապրանք հեռացնելու համար։")
            return
        self._lines.pop(row)
        self._lines_model.removeRow(row)
        self._refresh_basket_summary()

    def _refresh_basket_summary(self) -> None:
        total = sum(
            (line.quantity * line.unit_cost for line in self._lines), Decimal("0")
        )
        quantity = sum((line.quantity for line in self._lines), Decimal("0"))
        self._item_count.set_value(format_quantity(Decimal(len(self._lines))))
        self._unit_count.set_value(format_quantity(quantity))
        self._purchase_total.set_value(format_currency(total))

        payment_text = self._payment.text().strip()
        payment = Decimal("0") if not payment_text else self._payment.decimal_value()
        self._remaining_debt.set_value(
            "—" if payment is None else format_currency(total - payment)
        )
        self._cart_stack.setCurrentIndex(1 if self._lines else 0)

    def _cost_changed(self) -> None:
        # The two price fields are the source of truth for the displayed
        # margin. Recalculate it whenever either price is edited.
        self._markup_from_selling()

    def _markup_from_selling(self) -> None:
        cost = self._cost.decimal_value()
        selling = self._selling_price.decimal_value()
        if cost is None or selling is None:
            self._markup.clear()
            return
        markup = (selling - cost) / cost * Decimal("100") if cost else Decimal("0")
        self._markup.setText(_format_percentage(markup))

    def _selling_from_markup(self) -> None:
        cost = self._cost.decimal_value()
        markup = self._markup.decimal_value()
        if cost is None or markup is None:
            return
        selling = cost * (Decimal("1") + markup / Decimal("100"))
        self._selling_price.setText(format_quantity(selling.quantize(Decimal("0.01"))))

    def _new_product(self) -> None:
        dialog = ProductFormDialog(
            parent=self,
            next_sku=self._product_service.next_product_sku(),
            parent_products=self._products,
        )
        dialog.stock_edit.setText("0")
        dialog.stock_edit.setEnabled(False)
        if dialog.exec() != ProductFormDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        run_in_background(
            self,
            lambda: self._product_service.create_product(*values),
            self._product_created,
            self._failed,
        )

    def _product_created(self, product: Product) -> None:
        self._products = [product]
        self._original_selling_prices = {product.id: product.selling_price}
        self._catalog.set_rows(
            [
                [
                    product.name,
                    product.sku,
                    _selling_price_text(product.selling_price),
                ]
            ]
        )
        self._selected_index = 0
        self._product_selection_changed()

    def _save_draft(self) -> None:
        self._create_draft(False)

    def _confirm(self) -> None:
        if not self._lines:
            warn(self, "Գնումը պետք է պարունակի առնվազն մեկ ապրանք։")
            return
        payment = (
            Decimal("0")
            if not self._payment.text().strip()
            else self._payment.decimal_value()
        )
        if payment is None:
            warn(self, "Կանխավճարը պետք է լինի թիվ։")
            return
        total = sum(
            (line.quantity * line.unit_cost for line in self._lines), Decimal("0")
        )
        if payment < 0 or payment > total:
            warn(self, "Կանխավճարը չի կարող գերազանցել գնման գումարը։")
            return
        if not confirm(
            self,
            "Հաստատել գնումը",
            (
                f"Մատակարար՝ {self._supplier.name}\n"
                f"Ընդհանուր՝ {format_currency(total)}\n"
                f"Կանխավճար՝ {format_currency(payment)}\n"
                "Հաստատե՞լ գնումը։"
            ),
        ):
            return
        self._create_draft(True, payment)

    def _create_draft(self, finalize: bool, payment: Decimal = Decimal("0")) -> None:
        if not self._lines:
            warn(self, "Գնումը պետք է պարունակի առնվազն մեկ ապրանք։")
            return
        run_in_background(
            self,
            lambda: (
                self._purchase_service.update_draft(
                    self._draft_id,
                    self._supplier.id,
                    self._purchase_date,
                    None,
                    self._lines,
                )
                if self._draft_id is not None
                else self._purchase_service.create_draft(
                    self._supplier.id,
                    datetime.now(ARMENIA_TIMEZONE),
                    None,
                    self._lines,
                )
            ),
            lambda draft: self._draft_saved(draft, finalize, payment),
            self._failed,
        )

    def _draft_saved(self, draft: object, finalize: bool, payment: Decimal) -> None:
        if not finalize:
            self.accept()
            return
        self._confirm_draft(draft, payment)

    def _confirm_draft(self, draft: object, payment: Decimal) -> None:
        purchase_id = getattr(draft, "id", None)
        if not isinstance(purchase_id, uuid.UUID):
            self._failed(ValueError("Գնումը չի ստեղծվել"))
            return
        run_in_background(
            self,
            lambda: self._purchase_service.confirm(
                purchase_id, payment, price_updates=self._price_updates
            ),
            lambda _result: self.accept(),
            self._failed,
        )

    def _failed(self, _error: Exception) -> None:
        warn(self, "Գնումը չհաջողվեց պահպանել։")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)


class SupplierService(Protocol):
    def list_suppliers(self) -> list[SupplierRow]: ...
    def list_summaries(self) -> list[SupplierSummary]: ...
    def get_history(self, supplier_id: uuid.UUID) -> SupplierHistory: ...

    def get_account(
        self,
        supplier_id: uuid.UUID,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
    ) -> SupplierAccount: ...

    def save_supplier(
        self,
        supplier_id: uuid.UUID | None,
        name: str,
        phone: str | None,
        description: str | None,
        is_active: bool = True,
        opening_debt: Decimal = Decimal("0"),
    ) -> SupplierRow: ...


class SuppliersWindow(QWidget):
    def __init__(
        self,
        service: SupplierService,
        purchase_service: SupplierPurchaseService | None = None,
        product_service: ProductService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._purchase_service = purchase_service
        self._product_service = product_service
        self._summaries: list[SupplierSummary] = []
        self._rows: list[SupplierRow] = []
        self._editing: SupplierRow | None = None
        self._account_page: SupplierAccountPage | None = None
        self._stack = QStackedWidget()
        self._list_page = self._build_list_page()
        self._form_page = self._build_form_page()
        self._stack.addWidget(self._list_page)
        self._stack.addWidget(self._form_page)
        self._account_page: SupplierAccountPage | None = None
        if purchase_service is not None:
            self._account_page = SupplierAccountPage(
                service,
                purchase_service,
                on_back=self._show_list,
                on_changed=self.reload,
                open_editor=(
                    self._open_purchase_editor if product_service is not None else None
                ),
            )
            self._stack.addWidget(self._account_page)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)
        self.reload()

    def _build_list_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("suppliersList")
        page.setStyleSheet("""
            QWidget#suppliersList QFrame#panel,
            QWidget#suppliersList QFrame#statCard {
                background: white; border: 1px solid #dfe7f1; border-radius: 14px;
            }
            QWidget#suppliersList QTableView {
                border: 0; alternate-background-color: #f5f8fd;
            }
            QWidget#suppliersList QTableView::item { padding: 0 10px; }
            QWidget#suppliersList QHeaderView::section {
                background: #edf3fc; color: #344c70; padding: 14px 10px;
            }
        """)
        self._filter = SearchField("Որոնել անունով կամ հեռախոսահամարով")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        self._status_filter = SelectField(
            [
                ("Բոլոր կարգավիճակները", "all"),
                ("Ակտիվ", "active"),
                ("Արխիվացված", "archived"),
                ("Պարտքով", "debt"),
            ],
            on_change=lambda: self._apply_filter(self._filter.text()),
        )
        new_supplier_button = AddButton(
            "Նոր մատակարար", on_click=self._show_create_form
        )
        purchase_button = AddButton("Նոր գնում", on_click=self._new_purchase)
        details_button = DetailsButton(
            icon="≡", on_click=self._open_selected_supplier_history
        )
        edit_button = EditButton(icon="✎", on_click=self._edit)
        archive_button = ArchiveButton(
            icon="↓", on_click=lambda: self._set_active(False)
        )
        reactivate_button = RestoreButton(
            icon="↶", on_click=lambda: self._set_active(True)
        )
        self._table = DataTable(
            [
                "Անուն",
                "Հեռախոսահամար",
                "Կարգավիճակ",
                "Գնումներ",
                "Գումար",
                "Վճարված",
                "Պարտք",
                "Վերջին գնում",
            ],
            on_double_click=self._open_selected_supplier_history,
        )
        self._model = self._table.item_model
        self._table.setShowGrid(False)
        self._table.verticalHeader().setDefaultSectionSize(48)
        self._table.selectionModel().selectionChanged.connect(
            lambda *_args: self._update_supplier_actions()
        )
        self._supplier_actions = [
            purchase_button,
            details_button,
            edit_button,
            archive_button,
            reactivate_button,
        ]
        self._selected_caption = SectionHeading("Ընտրեք մատակարար")
        self._update_supplier_actions()
        header = QHBoxLayout()
        header.addWidget(
            PageHeader("Մատակարարներ", "Կոնտակտներ, գնումներ և վճարումներ՝ մեկ տեղում")
        )
        header.addStretch()
        header.addWidget(RefreshButton(on_click=self.reload))
        header.addWidget(new_supplier_button)

        filter_panel = Panel()
        filter_layout = QVBoxLayout(filter_panel)
        filter_layout.setContentsMargins(16, 14, 16, 14)
        filter_layout.setSpacing(8)
        filter_layout.addWidget(SectionHeading("Որոնում և զտում"))
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)
        filter_row.addWidget(self._filter, 1)
        filter_row.addWidget(self._status_filter)
        filter_row.addWidget(
            SearchButton(on_click=lambda: self._apply_filter(self._filter.text()))
        )
        filter_layout.addLayout(filter_row)

        actions_panel = Panel()
        actions_layout = QVBoxLayout(actions_panel)
        actions_layout.setContentsMargins(16, 14, 16, 14)
        actions_layout.setSpacing(8)
        actions_layout.addWidget(self._selected_caption)
        actions_layout.addWidget(
            ActionBar(
                [
                    purchase_button,
                    details_button,
                    edit_button,
                    archive_button,
                    reactivate_button,
                ]
            )
        )

        self._summary_cards = [
            StatCard("Մատակարարներ", "—", tone="info"),
            StatCard("Գնումների գումար", "—", tone="primary"),
            StatCard("Վճարված գումար", "—", tone="success"),
            StatCard("Ընդհանուր պարտք", "—", tone="danger"),
        ]
        summary_row = QHBoxLayout()
        summary_row.setSpacing(14)
        for card in self._summary_cards:
            summary_row.addWidget(card, 1)
        results = Panel()
        results_layout = QVBoxLayout(results)
        results_layout.setContentsMargins(16, 16, 16, 16)
        results_heading = QHBoxLayout()
        results_heading.addWidget(SectionHeading("Մատակարարների ցանկ"))
        results_heading.addStretch()
        self._result_count = StatusBadge("Բեռնվում է")
        results_heading.addWidget(self._result_count)
        results_layout.addLayout(results_heading)
        self._list_message = PageSubtitle(
            "Կրկնակի սեղմեք մատակարարի վրա՝ հաշիվը բացելու համար։"
        )
        results_layout.addWidget(self._list_message)
        results_layout.addWidget(self._table, 1)
        layout = QVBoxLayout(page)
        configure_page_layout(layout)
        layout.addLayout(header)
        layout.addLayout(summary_row)
        layout.addWidget(filter_panel)
        layout.addWidget(actions_panel)
        layout.addWidget(results, stretch=1)
        return page

    def _build_form_page(self) -> QWidget:
        page = QWidget()
        self._name = TextField("Օր.՝ Արարատ ՍՊԸ", on_submit=self._save)
        self._phone = TextField("Օր.՝ 077 123456", on_submit=self._save)
        self._description = TextArea(
            "Ապրանքատեսակներ, կոնտակտային անձ, վճարման պայմաններ…"
        )
        self._opening_debt = MoneyField("Սկզբնական պարտք", text="0")
        self._form_error = ErrorLabel()
        self._form_error.hide()
        self._name.textEdited.connect(lambda _text: self._form_error.hide())
        self._form_title = PageTitle("Նոր մատակարար")
        self._form_subtitle = PageSubtitle()

        headings = QVBoxLayout()
        headings.setSpacing(2)
        headings.addWidget(self._form_title)
        headings.addWidget(self._form_subtitle)
        header = QVBoxLayout()
        header.setSpacing(12)
        header.addWidget(
            BackButton(on_click=self._show_list),
            alignment=Qt.AlignmentFlag.AlignLeft,
        )
        header.addLayout(headings)

        contact_row = QHBoxLayout()
        contact_row.setSpacing(16)
        contact_row.addWidget(FormField("Անուն", self._name, required=True), stretch=3)
        contact_row.addWidget(FormField("Հեռախոսահամար", self._phone), stretch=2)

        self._save_button = SaveButton(on_click=self._save)
        card = FormCard()
        card.body.addWidget(SectionHeading("Հիմնական տվյալներ"))
        card.body.addLayout(contact_row)
        card.body.addWidget(
            FormField(
                "Նկարագրություն",
                self._description,
                hint="Ոչ պարտադիր․ տեսանելի է միայն ադմինիստրատորներին։",
            )
        )
        card.body.addWidget(
            FormField(
                "Նախկին պարտք (դրամ)",
                self._opening_debt,
                hint="Նախկինում առաջացած, դեռ չվճարված պարտք։ Նոր մատակարարի համար՝ 0։",
            )
        )
        card.body.addWidget(self._form_error)
        card.body.addWidget(Divider())
        card.body.addWidget(
            DialogButtonBar([CancelButton(on_click=self._show_list), self._save_button])
        )

        layout = QVBoxLayout(page)
        configure_page_layout(layout)
        layout.addLayout(header)
        layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        return page

    def _show_create_form(self) -> None:
        self._open_form(None)

    def _open_form(self, supplier: SupplierRow | None) -> None:
        self._editing = supplier
        if supplier is None:
            self._form_title.setText("Նոր մատակարար")
            self._form_subtitle.setText(
                "Լրացրեք տվյալները՝ մատակարարին ցանկում ավելացնելու համար։"
            )
        else:
            self._form_title.setText(f"Խմբագրել՝ {supplier.name}")
            self._form_subtitle.setText("Թարմացրեք մատակարարի տվյալները։")
        self._name.setText(supplier.name if supplier else "")
        self._phone.setText((supplier.phone or "") if supplier else "")
        self._description.setPlainText((supplier.description or "") if supplier else "")
        self._opening_debt.setText(
            str(supplier.opening_debt if supplier else Decimal("0"))
        )
        self._opening_debt.setReadOnly(supplier is not None)
        self._form_error.hide()
        self._save_button.setEnabled(True)
        self._stack.setCurrentWidget(self._form_page)
        self._name.setFocus()

    def _show_list(self) -> None:
        self._editing = None
        self._stack.setCurrentWidget(self._list_page)

    def _save(self) -> None:
        name = self._name.value()
        if not name:
            self._form_error.setText("Մատակարարի անունը պարտադիր է։")
            self._form_error.show()
            self._name.setFocus()
            return
        supplier = self._editing
        phone = self._phone.value() or None
        description = self._description.value() or None
        opening_debt = self._opening_debt.decimal_value()
        if opening_debt is None or not opening_debt.is_finite() or opening_debt < 0:
            self._form_error.setText("Նախկին պարտքը պետք է լինի 0 կամ դրական գումար։")
            self._form_error.show()
            self._opening_debt.setFocus()
            return
        self._save_button.setEnabled(False)
        run_in_background(
            self,
            lambda: self._service.save_supplier(
                supplier.id if supplier else None,
                name,
                phone,
                description,
                supplier.is_active if supplier else True,
                opening_debt,
            ),
            lambda _: self._supplier_saved(),
            self._save_failed,
        )

    def _save_failed(self, _error: Exception) -> None:
        self._save_button.setEnabled(True)
        self._form_error.setText("Չհաջողվեց պահպանել մատակարարին։ Փորձեք կրկին։")
        self._form_error.show()

    def _supplier_saved(self) -> None:
        self._show_list()
        self.reload()

    def _selected_supplier(self) -> SupplierRow | None:
        row = self._table.selected_row()
        if row < 0 or row >= len(self._rows):
            warn(self, "Ընտրեք մատակարար։")
            return None
        return self._rows[row]

    def _edit(self) -> None:
        supplier = self._selected_supplier()
        if supplier is None:
            return
        self._open_form(supplier)

    def _set_active(self, is_active: bool) -> None:
        supplier = self._selected_supplier()
        if supplier is None or supplier.is_active is is_active:
            return
        action = "վերականգնել" if is_active else "արխիվացնել"
        if not confirm(self, "Հաստատել", f"{action.capitalize()} մատակարարի՞ն։"):
            return
        run_in_background(
            self,
            lambda: self._service.save_supplier(
                supplier.id,
                supplier.name,
                supplier.phone,
                supplier.description,
                is_active,
                supplier.opening_debt,
            ),
            lambda _: self.reload(),
            self._failed,
        )

    def reload(self) -> None:
        run_in_background(
            self, self._load_summaries, self._loaded_summaries, self._failed
        )

    def _load_summaries(self) -> list[SupplierSummary]:
        if hasattr(self._service, "list_summaries"):
            return self._service.list_summaries()
        return [
            SupplierSummary(row, 0, Decimal("0"), Decimal("0"), Decimal("0"), None)
            for row in self._service.list_suppliers()
        ]

    def _loaded_summaries(self, rows: list[SupplierSummary]) -> None:
        self._summaries = rows
        self._rows = [row.supplier for row in rows]
        self._table.set_rows(
            [
                row.supplier.name,
                row.supplier.phone or "",
                "●  Ակտիվ" if row.supplier.is_active else "○  Արխիվացված",
                str(row.purchase_count),
                format_currency(row.purchase_total),
                format_currency(row.paid_total),
                format_currency(row.debt),
                row.last_purchase_date.date().isoformat()
                if row.last_purchase_date
                else "",
            ]
            for row in rows
        )
        for index, summary in enumerate(rows):
            self._model.item(index, 2).setForeground(
                QColor("#087765" if summary.supplier.is_active else "#7c8798")
            )
            for column in range(3, 7):
                self._model.item(index, column).setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            if summary.debt > 0:
                self._model.item(index, 6).setForeground(QColor("#b43d4b"))
        self._apply_filter(self._filter.text())

    def _update_supplier_actions(self) -> None:
        index = self._table.selected_row()
        supplier = self._rows[index] if 0 <= index < len(self._rows) else None
        if supplier is not None and self._table.isRowHidden(index):
            supplier = None
        purchase, details, edit, archive, restore = self._supplier_actions
        purchase.setEnabled(
            bool(
                supplier
                and supplier.is_active
                and self._purchase_service
                and self._product_service
            )
        )
        details.setEnabled(supplier is not None and self._account_page is not None)
        edit.setEnabled(supplier is not None)
        archive.setEnabled(bool(supplier and supplier.is_active))
        restore.setEnabled(bool(supplier and not supplier.is_active))
        self._selected_caption.setText(
            f"Ընտրված մատակարար · {supplier.name}" if supplier else "Ընտրեք մատակարար"
        )

    def _apply_filter(self, text: str) -> None:
        search_text = text.strip().casefold()
        status = self._status_filter.currentData()
        visible = []
        for row_index, supplier in enumerate(self._rows):
            searchable_text = f"{supplier.name} {supplier.phone or ''}".casefold()
            summary = self._summaries[row_index]
            hidden = (
                (bool(search_text) and search_text not in searchable_text)
                or (status == "active" and not supplier.is_active)
                or (status == "archived" and supplier.is_active)
                or (status == "debt" and summary.debt <= 0)
            )
            self._table.setRowHidden(row_index, hidden)
            if not hidden:
                visible.append(summary)
        if self._table.selected_row() >= 0 and self._table.isRowHidden(
            self._table.selected_row()
        ):
            self._table.clearSelection()
            self._table.setCurrentIndex(self._model.index(-1, -1))
        values = [str(len(visible))] + [
            format_currency(sum((getattr(row, field) for row in visible), Decimal("0")))
            for field in ("purchase_total", "paid_total", "debt")
        ]
        for card, value in zip(self._summary_cards, values, strict=True):
            card.set_value(value)
        self._result_count.set_status(f"{len(visible)} / {len(self._rows)} մատակարար")
        self._list_message.setText(
            "Կրկնակի սեղմեք մատակարարի վրա՝ հաշիվը բացելու համար։"
            if visible
            else "Մատակարարներ չեն գտնվել։ Փոխեք որոնումը կամ ավելացրեք նոր մատակարար։"
        )
        self._update_supplier_actions()

    def _open_selected_supplier_history(self) -> None:
        supplier = self._selected_supplier()
        if supplier is None:
            return
        if self._account_page is None:
            warn(self, "Գնումների ծառայությունը հասանելի չէ։")
            return
        self._account_page.open(supplier)
        self._stack.setCurrentWidget(self._account_page)

    @staticmethod
    def _status(status: str) -> str:
        return {
            "draft": "Բաց",
            "open": "Ավարտված",
            "partially_paid": "Ավարտված",
            "paid": "Ավարտված",
            "cancelled": "Չեղարկված",
        }.get(status, status)

    @staticmethod
    def _payment_method(method: PaymentMethod) -> str:
        return {
            PaymentMethod.CASH: "Կանխիկ",
            PaymentMethod.CARD: "Քարտ",
            PaymentMethod.TRANSFER: "Փոխանցում",
            PaymentMethod.OTHER: "Այլ",
        }.get(method, method.value)

    def _open_purchase_editor(
        self,
        supplier: SupplierRow,
        detail: PurchaseDetail,
        finalize_on_save: bool,
        initial_payment: Decimal,
    ) -> bool:
        if self._purchase_service is None or self._product_service is None:
            return False
        dialog = PurchaseDialog(
            supplier,
            self._purchase_service,
            self._product_service,
            detail=detail,
            finalize_on_save=finalize_on_save,
            initial_payment=initial_payment,
            parent=self,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _new_purchase(self) -> None:
        if self._purchase_service is None or self._product_service is None:
            warn(self, "Գնումների ծառայությունը հասանելի չէ։")
            return
        row = self._table.selected_row()
        if row < 0 or row >= len(self._rows):
            warn(self, "Ընտրեք մատակարար։")
            return
        dialog = PurchaseDialog(
            self._rows[row],
            self._purchase_service,
            self._product_service,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _loaded(self, rows: list[SupplierRow]) -> None:
        self._loaded_summaries(
            [
                SupplierSummary(row, 0, Decimal("0"), Decimal("0"), Decimal("0"), None)
                for row in rows
            ]
        )

    def _failed(self, _error: Exception) -> None:
        warn(self, "Չհաջողվեց բեռնել մատակարարների տվյալները։")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)
