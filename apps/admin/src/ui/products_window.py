"""Product list, search, and add/edit actions for the admin application."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Protocol

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from models import Product, Unit
from ui.components import (
    ActionBar,
    AddButton,
    DataTable,
    EditButton,
    PageTitle,
    RefreshButton,
    SearchButton,
    SearchField,
    SyncButton,
    inform,
    report_error,
)
from ui.product_form_dialog import ProductFormDialog, unit_label
from ui.products_style import PRODUCTS_STYLE, catalogue_icon
from ui.style import configure_page_layout, format_quantity
from ui.workers import run_in_background, wait_for_pending_threads


class ProductService(Protocol):
    def list_products(self) -> list[Product]: ...

    def search_products(self, term: str) -> list[Product]: ...

    def next_product_sku(self) -> str | None: ...

    def create_product(
        self,
        name: str,
        sku: str,
        barcode: str | None,
        unit: Any,
        cost_price: Decimal | None,
        selling_price: Decimal | None,
        minimum_price: Decimal | None,
        quantity_in_stock: Decimal,
        low_stock_threshold: Decimal | None,
        is_active: bool,
        parent_product_id: uuid.UUID | None = None,
        is_for_sale: bool = True,
    ) -> Product: ...

    def update_product(
        self,
        product_id: uuid.UUID,
        name: str,
        sku: str,
        barcode: str | None,
        unit: Any,
        cost_price: Decimal | None,
        selling_price: Decimal | None,
        minimum_price: Decimal | None,
        quantity_in_stock: Decimal,
        low_stock_threshold: Decimal | None,
        is_active: bool,
        parent_product_id: uuid.UUID | None = None,
        is_for_sale: bool = True,
    ) -> Product: ...


class WebSyncService(Protocol):
    def synchronize_barbecue_products(self) -> dict[str, object]: ...


_HEADERS = [
    "Անուն",
    "SKU",
    "Շտրիխ կոդ",
    "Միավոր",
    "Ինքնարժեք",
    "Պաշար",
    "Նվազագույն պաշար",
    "Կարգավիճակ",
]

_PRODUCT_ROLE = Qt.ItemDataRole.UserRole + 1


def _stock_marker(quantity: Decimal) -> tuple[str, QColor, int]:
    if quantity < 0:
        return "●  Կրիտիկական", QColor("#d9534f"), 0
    if quantity < 5:
        return "●  Ցածր", QColor("#e89b9b"), 1
    if quantity <= 10:
        return "●  Նորմալ", QColor("#5f9f93"), 2
    if quantity <= 20:
        return "●  Ուշադրություն", QColor("#c99822"), 3
    return "●  Բավարար", QColor("#3ca374"), 4


class ProductsWindow(QWidget):
    def __init__(
        self,
        product_service: ProductService,
        parent: QWidget | None = None,
        web_sync_service: WebSyncService | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("productsPage")
        self.setStyleSheet(PRODUCTS_STYLE)
        self._product_service = product_service
        self._web_sync_service = web_sync_service
        self._products: list[Product] = []

        self.search_edit = SearchField(
            "Փնտրել անունով, կոդով կամ շտրիխով", on_submit=self.search_products
        )
        search_button = SearchButton("Փնտրել", on_click=self.search_products)
        refresh_button = RefreshButton(on_click=self.reload_products)

        self._tables: dict[str, DataTable] = {}
        self._counts: dict[str, QLabel] = {}
        self._active_table: DataTable | None = None
        self._tabs = QTabWidget()
        self._tabs.setObjectName("productTabs")
        self._tabs.setDocumentMode(False)
        self._tabs.tabBar().setDrawBase(False)
        self._tabs.setIconSize(QSize(20, 20))
        self._tab_headings: dict[str, str] = {}
        for key, heading, description, accent in (
            (
                "sale",
                "Վաճառքի ապրանքներ",
                "Վաճառքի համար նախատեսված ապրանքներ",
                "#2563eb",
            ),
            ("barbecue", "Խորոված", "Խորովածի տեսակներ և բաղադրիչներ", "#059669"),
            ("own", "Սեփական օգտագործման", "Ներքին օգտագործման ապրանքներ", "#7c3aed"),
        ):
            card = QFrame()
            card.setObjectName("productSection")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(20, 20, 20, 20)
            card_layout.setSpacing(14)
            header = QHBoxLayout()
            label = QLabel(heading)
            label.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {accent};")
            count = QLabel("0 ապրանք")
            count.setStyleSheet(
                f"color: {accent}; background: #f1f5f9; "
                "padding: 5px 12px; border-radius: 10px;"
            )
            symbol = QLabel()
            symbol.setPixmap(catalogue_icon(key, accent).pixmap(26, 26))
            symbol.setFixedSize(32, 32)
            header.addWidget(symbol)
            header.addWidget(label)
            header.addStretch()
            header.addWidget(count)
            card_layout.addLayout(header)
            subtitle = QLabel(description)
            subtitle.setStyleSheet("color: #64748b; font-size: 13px;")
            card_layout.addWidget(subtitle)
            table = DataTable(_HEADERS, on_double_click=self._handle_edit_product)
            table.setObjectName("productTable")
            table.setShowGrid(False)
            table.verticalHeader().setDefaultSectionSize(44)
            table.setMinimumHeight(360)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            table.item_model.setSortRole(Qt.ItemDataRole.UserRole)
            table.setSortingEnabled(True)
            table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
            table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Interactive
            )
            table.horizontalHeader().setStretchLastSection(True)
            table.setColumnWidth(0, 300)
            table.setColumnWidth(1, 100)
            table.setColumnWidth(2, 140)
            table.setColumnWidth(6, 180)
            table.selectionModel().selectionChanged.connect(
                lambda *_args, current=table: self._activate_table(current)
            )
            card_layout.addWidget(table, stretch=1)
            self._tabs.addTab(card, catalogue_icon(key, accent), heading)
            self._tab_headings[key] = heading
            self._tables[key] = table
            self._counts[key] = count
        self._table = self._tables["sale"]
        self._model = self._table.item_model

        self._add_button = AddButton("Ապրանք", on_click=self._handle_add_product)
        self._edit_button = EditButton(
            on_click=self._handle_edit_product, enabled=False
        )
        action_buttons = [self._edit_button, self._add_button]
        if self._web_sync_service is not None:
            self._sync_button = SyncButton(on_click=self._handle_sync_with_web)
            action_buttons.insert(0, self._sync_button)

        search_button.setIcon(catalogue_icon("search"))
        refresh_button.setIcon(catalogue_icon("refresh"))
        self._edit_button.setIcon(catalogue_icon("edit"))
        title = PageTitle("Ապրանքներ")
        subtitle = QLabel("Կառավարեք ապրանքները, պաշարները և օգտագործման տեսակները")
        subtitle.setObjectName("catalogueSubtitle")
        hint = QLabel("Խմբագրելու համար կրկնակի սեղմեք ապրանքի վրա")
        hint.setObjectName("catalogueHint")

        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)
        search_layout.addWidget(self.search_edit)
        search_layout.addWidget(search_button)
        search_layout.addWidget(refresh_button)
        actions = ActionBar(action_buttons, align_right=True)

        layout = QVBoxLayout()
        configure_page_layout(layout)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(search_layout)
        layout.addWidget(self._tabs, stretch=1)
        footer = QHBoxLayout()
        footer.addWidget(hint)
        footer.addStretch()
        footer.addWidget(actions)
        layout.addLayout(footer)
        self.setLayout(layout)

        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.reload_products()

    def _on_tab_changed(self, _index: int) -> None:
        self._active_table = None
        for table in self._tables.values():
            table.clearSelection()
            table.setCurrentIndex(table.item_model.index(-1, -1))
        self._sync_edit_button()

    def _sync_edit_button(self) -> None:
        self._edit_button.setEnabled(self._selected_product() is not None)

    def search_products(self) -> None:
        term = self.search_edit.text().strip()
        operation = (
            self._product_service.list_products
            if not term
            else lambda: self._product_service.search_products(term)
        )
        run_in_background(
            self, operation, self._on_products_loaded, self._on_operation_failed
        )

    def reload_products(self) -> None:
        run_in_background(
            self,
            self._product_service.list_products,
            self._on_products_loaded,
            self._on_operation_failed,
        )

    def _on_products_loaded(self, products: list[Product]) -> None:
        self._products = products
        self._render_products()

    def _product_display_name(self, product: Product) -> str:
        if product.parent_product_id is None:
            return product.name
        parent = next(
            (
                candidate
                for candidate in self._products
                if candidate.id == product.parent_product_id
            ),
            None,
        )
        return product.name if parent is None else product.display_name(parent)

    def _activate_table(self, table: DataTable) -> None:
        if not table.selectionModel().hasSelection():
            self._sync_edit_button()
            return
        self._active_table = table
        for other in self._tables.values():
            if other is not table:
                other.clearSelection()
                other.setCurrentIndex(other.item_model.index(-1, -1))
        self._sync_edit_button()

    @staticmethod
    def _product_group(product: Product) -> str:
        if product.unit is Unit.BARBECUE or product.parent_product_id is not None:
            return "barbecue"
        return "own" if product.is_for_sale is False else "sale"

    def _render_products(self) -> None:
        self._active_table = None
        term = self.search_edit.text().strip().casefold()
        counts = dict.fromkeys(self._tables, 0)
        for table in self._tables.values():
            table.setSortingEnabled(False)
            table.clear_rows()
        for product in sorted(self._products, key=lambda item: item.name.casefold()):
            if product.unit is Unit.BARBECUE:
                continue
            if term and not any(
                term in value.casefold()
                for value in (
                    self._product_display_name(product),
                    product.name,
                    product.sku,
                    product.barcode or "",
                )
            ):
                continue
            group = self._product_group(product)
            counts[group] += 1
            self._append_product_row(
                product,
                table=self._tables[group],
            )
        for index, (group, table) in enumerate(self._tables.items()):
            table.setSortingEnabled(True)
            self._counts[group].setText(f"{counts[group]} ապրանք")
            self._tabs.setTabText(
                index, f"{self._tab_headings[group]} ({counts[group]})"
            )
        self._sync_edit_button()

    def _append_product_row(
        self,
        product: Product,
        *,
        table: DataTable,
    ) -> None:
        quantity = Decimal(product.quantity_in_stock or 0)
        status_text, status_color, status_order = _stock_marker(quantity)
        name = self._product_display_name(product)
        values = [
            name,
            product.sku,
            product.barcode or "",
            unit_label(product.unit),
            self._display_value(product.cost_price),
            self._stock_with_unit(product),
            self._display_value(product.low_stock_threshold),
            status_text,
        ]
        sort_values: list[object] = [
            product.name.casefold(),
            product.sku.casefold(),
            (product.barcode or "").casefold(),
            product.unit.value,
            float(product.cost_price or 0),
            float(quantity),
            float(product.low_stock_threshold or 0),
            status_order,
        ]
        items = [QStandardItem(value) for value in values]
        for item, sort_value in zip(items, sort_values, strict=True):
            item.setData(sort_value, Qt.ItemDataRole.UserRole)
        items[0].setData(product, _PRODUCT_ROLE)
        items[0].setData(name.strip(), Qt.ItemDataRole.ToolTipRole)
        items[7].setForeground(QBrush(status_color))
        table.item_model.appendRow(items)

    @staticmethod
    def _display_value(value: Any) -> str:
        return "" if value is None else format_quantity(value)

    @staticmethod
    def _stock_with_unit(product: Product) -> str:
        return (
            f"{format_quantity(product.quantity_in_stock)} {unit_label(product.unit)}"
        )

    @staticmethod
    def _stock_status(product: Product) -> str:
        status = getattr(product, "stock_status", "")
        return {
            "in_stock": "Առկա",
            "low_stock": "Քիչ է",
            "out_of_stock": "Չկա",
        }.get(status, str(status))

    def _selected_product(self) -> Product | None:
        table = self._active_table
        if table is None or not table.selectionModel().hasSelection():
            return None
        index = table.currentIndex()
        if not index.isValid():
            return None
        item = table.item_model.item(index.row(), 0)
        if item is None:
            return None
        product = item.data(_PRODUCT_ROLE)
        return product if isinstance(product, Product) else None

    def _handle_add_product(self) -> None:
        dialog = ProductFormDialog(
            parent=self,
            next_sku=self._product_service.next_product_sku(),
            parent_products=self._products,
        )
        if dialog.exec() != ProductFormDialog.DialogCode.Accepted:
            return
        self._save_product(dialog, None)

    def _handle_edit_product(self, _index=None) -> None:  # type: ignore[no-untyped-def]
        product = self._selected_product()
        if product is None:
            return
        dialog = ProductFormDialog(product, self, parent_products=self._products)
        if dialog.exec() != ProductFormDialog.DialogCode.Accepted:
            return
        self._save_product(dialog, product)

    def _save_product(self, dialog: ProductFormDialog, product: Product | None) -> None:
        values = dialog.values()

        def operation() -> Product:
            if product is None:
                return self._product_service.create_product(*values)
            return self._product_service.update_product(product.id, *values)

        self._add_button.setEnabled(False)
        self._edit_button.setEnabled(False)
        run_in_background(
            self, operation, self._on_product_saved, self._on_operation_failed
        )

    def _on_product_saved(self, _product: Product) -> None:
        self._add_button.setEnabled(True)
        self.reload_products()

    def _handle_sync_with_web(self) -> None:
        if self._web_sync_service is None:
            return
        self._sync_button.setEnabled(False)
        run_in_background(
            self,
            self._web_sync_service.synchronize_barbecue_products,
            self._on_sync_succeeded,
            self._on_sync_failed,
        )

    def _on_sync_succeeded(self, result: dict[str, object]) -> None:
        self._sync_button.setEnabled(True)
        inform(
            self,
            f"Ստեղծված՝ {result.get('created', 0)}, "
            f"թարմացված՝ {result.get('updated', 0)}, "
            f"ձախողված՝ {result.get('failed', 0)}",
            title="Համաժամեցումն ավարտված է",
        )

    def _on_sync_failed(self, _error: Exception) -> None:
        self._sync_button.setEnabled(True)
        report_error(self, "Չհաջողվեց համաժամեցնել կայքի հետ։")

    def _on_operation_failed(self, error: Exception) -> None:
        self._add_button.setEnabled(True)
        self._edit_button.setEnabled(self._selected_product() is not None)
        error_name = type(error).__name__
        if error_name == "SkuAlreadyExistsError":
            message = "Այս ապրանքի կոդն արդեն օգտագործվում է։"
        elif error_name == "BarcodeAlreadyExistsError":
            message = "Այս շտրիխն արդեն օգտագործվում է։"
        else:
            message = "Չհաջողվեց պահպանել ապրանքը կամ միանալ շտեմարանին։"
        report_error(self, message)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)
