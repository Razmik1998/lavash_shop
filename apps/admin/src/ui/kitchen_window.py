"""Kitchen stock issue documents, using the existing product stock balance."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Protocol

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from models import Product, Unit, User
from schemas import (
    KitchenExportDetail,
    KitchenExportLineInput,
    KitchenExportRow,
    KitchenProductionLineInput,
    KitchenProductionRow,
)
from schemas.kitchen import KitchenProductionDetail
from services import KitchenService
from ui.components import (
    ActionBar,
    AddButton,
    BackButton,
    CloseButton,
    DataTable,
    DatePeriodFilter,
    EditButton,
    FormField,
    NotificationBanner,
    PageHeader,
    PageSubtitle,
    PageTitle,
    Panel,
    PrimaryButton,
    ProfileHeader,
    QuantityField,
    SaveButton,
    SearchButton,
    SearchField,
    SectionHeading,
    StatCard,
    StatusBadge,
    SummaryBanner,
    TabBar,
    TextField,
    confirm,
    inform,
    report_error,
    warn,
)
from ui.product_form_dialog import unit_label
from ui.style import configure_page_layout, format_currency, format_quantity
from ui.workers import run_in_background

_DOC_ROLE = Qt.ItemDataRole.UserRole + 1
_PRODUCT_ROLE = Qt.ItemDataRole.UserRole + 2


class ProductCatalog(Protocol):
    def list_products(self) -> list[Product]: ...


class KitchenExportPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], object],
        on_save: Callable[
            [
                KitchenExportDetail | None,
                str | None,
                list[KitchenExportLineInput],
                bool,
            ],
            object,
        ],
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_back = on_back
        self._on_save = on_save
        self._products: list[Product] = []
        self._lines: dict[uuid.UUID, Decimal] = {}
        self._costs: dict[uuid.UUID, Decimal] = {}
        self._detail: KitchenExportDetail | None = None
        self._lock_after_save = False
        self._dirty = False

        self._product_search = SearchField("Փնտրել ապրանքի անունով, կոդով կամ շտրիխով")
        self._product_search.textChanged.connect(lambda _text: self._render_catalog())
        self._catalog_table = DataTable(
            ["Ապրանք", "Կոդ", "Առկա պաշար", "Ինքնարժեք"],
            on_double_click=self._add_product,
            on_selection_changed=self._sync_product_action,
            min_height=140,
        )
        self._catalog_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        # Keep the catalog compact; its own scrollbar handles long product lists.
        self._catalog_table.setFixedHeight(280)
        self._catalog_table.setSortingEnabled(True)
        self._product_search_button = SearchButton(
            "Մաքրել",
            on_click=lambda: self._product_search.clear(),
        )
        self._quantity = QuantityField(text="1")
        self._notes = TextField("Նշումներ")
        self._notes.setMaxLength(2000)
        self._notes.textEdited.connect(lambda _text: self._mark_dirty())
        self._items = DataTable(
            ["Ապրանք", "Փաստաթղթի քանակ", "Առկա պաշար", "Ինքնարժեք", "Ընդհանուր"],
            on_selection_changed=self._sync_line_action,
            min_height=120,
        )
        self._items.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # Keep the selected list bounded so totals, warnings and save actions remain
        # reachable; long selections scroll inside the table.
        self._items.setFixedHeight(280)
        self._total_card = StatCard(
            "Փաստաթղթի ընդհանուր ինքնարժեք",
            format_currency(Decimal("0")),
            tone="primary",
        )
        self._stock_warning = NotificationBanner()
        self._add_line = AddButton("Ավելացնել", on_click=self._add_product)
        self._remove_line = CloseButton(
            "Հեռացնել ընտրվածը", on_click=self._remove_product
        )
        self._back = BackButton(on_click=self._go_back)
        self._save = SaveButton("Պահպանել սևագիրը", on_click=self._save_draft)
        self._save_lock = PrimaryButton(
            "Պահպանել և հաստատել փոխանցումը", on_click=self._save_locked
        )
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.addWidget(
            PageHeader(
                "🍳 Խոհանոցին փոխանցում",
                "Կազմեք խոհանոցի փոխանցման փաստաթուղթը։ "
                "Պաշարը կհանվի միայն հաստատելուց հետո։",
            )
        )

        workspace = QHBoxLayout()
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(12)

        selection = Panel()
        selection.setMinimumWidth(390)
        selection_layout = QVBoxLayout(selection)
        selection_layout.setContentsMargins(14, 14, 14, 14)
        selection_layout.setSpacing(10)
        selection_layout.addWidget(SectionHeading("Պահեստի ապրանքներ"))
        selection_layout.addWidget(
            PageSubtitle("Փնտրեք ապրանքը, նշեք քանակը և ավելացրեք փաստաթղթին։")
        )
        catalog_search_row = QHBoxLayout()
        catalog_search_row.setSpacing(8)
        catalog_search_row.addWidget(self._product_search, stretch=1)
        catalog_search_row.addWidget(self._product_search_button)
        selection_layout.addLayout(catalog_search_row)
        selection_layout.addWidget(self._catalog_table, stretch=1)
        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.setSpacing(8)
        add_row.addWidget(FormField("Քանակ", self._quantity), stretch=1)
        add_row.addWidget(self._add_line, alignment=Qt.AlignmentFlag.AlignBottom)
        selection_layout.addLayout(add_row)
        workspace.addWidget(selection, stretch=5)

        lines_panel = Panel()
        lines_layout = QVBoxLayout(lines_panel)
        lines_layout.setContentsMargins(14, 14, 14, 14)
        lines_layout.setSpacing(10)
        line_heading = QHBoxLayout()
        line_heading.addWidget(SectionHeading("Փոխանցման փաստաթուղթ"))
        line_heading.addStretch()
        line_heading.addWidget(self._remove_line)
        lines_layout.addLayout(line_heading)
        self._items_count = PageSubtitle("Ապրանքներ՝ 0")
        lines_layout.addWidget(self._items_count)
        lines_layout.addWidget(self._items, stretch=1)
        lines_layout.addWidget(self._stock_warning)
        lines_layout.addWidget(self._total_card)
        lines_layout.addWidget(FormField("Նշումներ", self._notes))
        workspace.addWidget(lines_panel, stretch=6)
        content_layout.addLayout(workspace, stretch=1)

        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        footer.addWidget(self._back)
        footer.addStretch()
        footer.addWidget(self._save)
        footer.addWidget(self._save_lock)
        footer_panel = Panel()
        footer_panel.setLayout(footer)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setWidget(content)

        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        layout.addWidget(self._scroll, stretch=1)
        layout.addWidget(footer_panel)
        self._render()
        self._render_catalog()

    def _sync_line_action(self) -> None:
        self._remove_line.setEnabled(self._items.selected_row() >= 0)

    def set_document(
        self,
        products: list[Product],
        detail: KitchenExportDetail | None = None,
        *,
        lock_after_save: bool = False,
    ) -> None:
        self._products = [product for product in products if product.is_active]
        self._detail = detail
        self._lock_after_save = lock_after_save
        self._lines = (
            {line.product_id: Decimal(line.quantity) for line in detail.items}
            if detail is not None
            else {}
        )
        self._costs = (
            {line.product_id: Decimal(line.unit_cost) for line in detail.items}
            if detail is not None
            else {}
        )
        self._notes.setText(detail.export.notes or "" if detail else "")
        self._product_search.clear()
        self._dirty = False
        if lock_after_save:
            self._save.setVisible(False)
            self._save_lock.setText("Պահպանել փոփոխությունները և հաստատել")
        else:
            self._save.setVisible(True)
            self._save_lock.setText("Պահպանել և հաստատել փոխանցումը")
        self._render_catalog()
        self._render()

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _go_back(self) -> None:
        if self._dirty or self._lock_after_save:
            message = "Չպահպանված փոփոխությունները կկորչեն։ "
            if self._lock_after_save:
                message += (
                    "Փաստաթուղթը կմնա բաց վիճակում, իսկ նախկին քանակը "
                    "արդեն վերադարձված է ընդհանուր պաշարին։ "
                )
            message += "Վերադառնա՞լ փաստաթղթերին։"
            if not confirm(self, "Վերադառնալ", message):
                return
        self._on_back()

    def _save_draft(self) -> None:
        self._save_document(lock=False)

    def _save_locked(self) -> None:
        self._save_document(lock=True)

    def _save_document(self, *, lock: bool) -> None:
        if not self._lines:
            warn(self, "Փաստաթուղթը պետք է պարունակի առնվազն մեկ ապրանք։")
            return
        lines = [
            KitchenExportLineInput(product_id, quantity)
            for product_id, quantity in self._lines.items()
        ]
        self._on_save(
            self._detail,
            self._notes.value() or None,
            lines,
            lock or self._lock_after_save,
        )

    def _sync_product_action(self) -> None:
        self._add_line.setEnabled(self._selected_catalog_product() is not None)

    def _selected_catalog_product(self) -> Product | None:
        row = self._catalog_table.selected_row()
        if row < 0:
            return None
        cell = self._catalog_table.item_model.item(row, 0)
        product_id = cell.data(_PRODUCT_ROLE) if cell is not None else None
        return next(
            (product for product in self._products if product.id == product_id),
            None,
        )

    def _render_catalog(self) -> None:
        query = self._product_search.text().strip().casefold()
        matches = [
            product
            for product in self._products
            if not query
            or any(
                query in value.casefold()
                for value in (
                    product.name,
                    product.sku,
                    product.barcode or "",
                )
            )
        ]
        self._catalog_table.clear_rows()
        for product in matches:
            cells = self._catalog_table.append_row(
                [
                    product.name,
                    product.sku,
                    (
                        f"{format_quantity(product.quantity_in_stock or 0)} "
                        f"{unit_label(product.unit)}"
                    ),
                    format_currency(Decimal(product.cost_price or 0)),
                ]
            )
            cells[0].setData(product.id, _PRODUCT_ROLE)
        self._sync_product_action()

    @staticmethod
    def _fit_table_to_rows(table: DataTable) -> None:
        header_height = table.horizontalHeader().height()
        row_height = table.verticalHeader().defaultSectionSize()
        content_height = header_height + table.row_count() * row_height + 8
        table.setFixedHeight(max(table.minimumHeight(), content_height))

    def _add_product(self) -> None:
        product = self._selected_catalog_product()
        quantity = self._quantity.decimal_value()
        if product is None or quantity is None or quantity <= 0:
            warn(self, "Ընտրեք ապրանք և մուտքագրեք դրական քանակ։")
            return
        product_id = product.id
        self._lines[product_id] = self._lines.get(product_id, Decimal("0")) + quantity
        self._dirty = True
        self._render()

    def _remove_product(self) -> None:
        row = self._items.selected_row()
        if row < 0:
            return
        product_id = self._items.item_model.item(row, 0).data(_DOC_ROLE)
        if isinstance(product_id, uuid.UUID):
            self._lines.pop(product_id, None)
            self._dirty = True
            self._render()

    def _render(self) -> None:
        self._items.clear_rows()
        total = Decimal("0")
        by_id = {p.id: p for p in self._products}
        shortages: list[str] = []
        for product_id, quantity in self._lines.items():
            product = by_id.get(product_id)
            if product is None:
                continue
            available = Decimal(product.quantity_in_stock or 0)
            if quantity > available:
                shortages.append(
                    f"{product.name}՝ պահանջվում է {format_quantity(quantity)} "
                    f"{unit_label(product.unit)}, առկա է "
                    f"{format_quantity(available)} {unit_label(product.unit)}"
                )
            cost = self._costs.get(product_id, Decimal(product.cost_price or 0))
            line_total = (cost * quantity).quantize(Decimal("0.01"))
            total += line_total
            cells = self._items.append_row(
                [
                    product.name,
                    f"{format_quantity(quantity)} {unit_label(product.unit)}",
                    f"{format_quantity(available)} {unit_label(product.unit)}",
                    format_currency(cost),
                    format_currency(line_total),
                ]
            )
            cells[0].setData(product_id, _DOC_ROLE)
        self._items_count.setText(
            f"Ապրանքներ՝ {self._items.row_count()} · "
            f"Ընդհանուր քանակ՝ "
            f"{format_quantity(sum(self._lines.values(), Decimal('0')))}"
        )
        self._sync_line_action()
        self._total_card.set_value(format_currency(total))
        if shortages:
            self._stock_warning.show_message(
                "Պաշարը բավարար չէ արտահանման համար։ "
                + " · ".join(shortages)
                + "։ Կարող եք պահպանել սևագիրը, բայց արտահանումը հասանելի կլինի "
                "պաշարը համալրելուց հետո։",
                tone="warning",
            )
            self._save_lock.setEnabled(False)
        else:
            self._stock_warning.hide()
            self._save_lock.setEnabled(True)


class KitchenProductionPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], object],
        on_save: Callable[[str | None, list[KitchenProductionLineInput]], object],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_back = on_back
        self._on_save = on_save
        self._products: list[Product] = []
        self._product_names: dict[uuid.UUID, str] = {}
        self._lines: dict[uuid.UUID, Decimal] = {}
        self._dirty = False
        self._product_search = SearchField("Անուն, կոդ կամ շտրիխ կոդ")
        self._product_search.setClearButtonEnabled(True)
        self._product_search.textChanged.connect(self._render_catalog)
        self._catalog_table = DataTable(
            ["Ապրանք", "Կոդ", "Պահեստում", "Միավոր"],
            on_selection_changed=self._sync_product,
            on_double_click=self._add,
            min_height=180,
        )
        self._catalog_table.setFixedHeight(200)
        self._catalog_table.setSortingEnabled(False)
        self._catalog_count = PageSubtitle()
        self._selection_title = SectionHeading("Ընտրեք ապրանքը ցանկից")
        self._selection_meta = PageSubtitle("Ընտրված ապրանքի տվյալները կերևան այստեղ։")
        self._balance_preview = PageSubtitle()
        self._quantity = QuantityField(text="1")
        self._notes = TextField("Նշումներ")
        self._notes.textEdited.connect(lambda _text: self._mark_dirty())
        self._table = DataTable(
            ["Ապրանք", "Մուտքագրվող քանակ", "Պահեստում հիմա", "Նոր մնացորդ"],
            on_selection_changed=self._sync_remove,
            min_height=120,
        )
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setFixedHeight(300)
        self._remove = CloseButton("Հեռացնել ընտրվածը", on_click=self._remove_line)
        self._add_button = AddButton("Ավելացնել փաստաթղթին", on_click=self._add)
        self._quantity.textChanged.connect(self._sync_product)
        self._quantity.returnPressed.connect(self._add)
        self._save = SaveButton(
            "Գրանցել խոհանոցից վերադարձը", on_click=self._save_entry
        )
        self._back = BackButton(on_click=self._go_back)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        top_row = QHBoxLayout()
        top_row.addWidget(StatusBadge("Նոր փաստաթուղթ", tone="primary"))
        top_row.addStretch()
        top_row.addWidget(PageSubtitle("Խոհանոց  /  Պահեստի վերադարձ"))
        content_layout.addLayout(top_row)
        content_layout.addWidget(
            PageHeader(
                "🥘 Խոհանոցից վերադարձի գրանցում",
                "Ընտրեք պատրաստված ապրանքներն ու քանակները։ "
                "Պահպանելիս դրանք կավելանան ընդհանուր պահեստին։",
            )
        )
        workspace = QHBoxLayout()
        workspace.setSpacing(16)
        entry_panel = Panel()
        entry_panel.setMinimumWidth(360)
        entry_layout = QVBoxLayout(entry_panel)
        entry_layout.setContentsMargins(18, 18, 18, 18)
        entry_layout.setSpacing(12)
        entry_layout.addWidget(SectionHeading("1. Ընտրեք պատրաստի ապրանքը"))
        entry_layout.addWidget(
            PageSubtitle(
                "Փնտրեք անունով կամ ճշգրիտ կոդով։ Կրկնակի սեղմումով ավելացրեք ապրանքը։"
            )
        )
        entry_layout.addWidget(self._product_search)
        entry_layout.addWidget(self._catalog_count)
        entry_layout.addWidget(self._catalog_table)
        preview = Panel()
        preview.setStyleSheet(
            "QFrame#panel { background: #eff6ff; border: 1px solid #bfdbfe; "
            "border-radius: 12px; }"
        )
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(8)
        self._selection_title.setWordWrap(True)
        preview_layout.addWidget(self._selection_title)
        preview_layout.addWidget(self._selection_meta)
        preview_layout.addWidget(FormField("Վերադարձվող քանակ", self._quantity))
        preview_layout.addWidget(self._balance_preview)
        preview_layout.addWidget(self._add_button)
        entry_layout.addWidget(preview)
        entry_layout.addStretch()
        workspace.addWidget(entry_panel, 5)
        selected = Panel()
        selected_layout = QVBoxLayout(selected)
        selected_layout.setContentsMargins(14, 14, 14, 14)
        selected_layout.setSpacing(10)
        heading = QHBoxLayout()
        heading.addWidget(SectionHeading("2. Վերադարձի ապրանքներ"))
        heading.addStretch()
        heading.addWidget(self._remove)
        selected_layout.addLayout(heading)
        totals = QHBoxLayout()
        totals.setSpacing(10)
        self._line_count_card = StatCard("Ապրանքների տողեր", "0")
        self._quantity_card = StatCard("Վերադարձվող քանակ", "0", tone="success")
        self._quantity_card.value_label.setWordWrap(True)
        totals.addWidget(self._line_count_card)
        totals.addWidget(self._quantity_card)
        selected_layout.addLayout(totals)
        self._empty_lines = PageSubtitle(
            "🧺  Դեռ ապրանքներ չկան\n"
            "Ձախ ցանկից ընտրեք ապրանքը, նշեք քանակը և ավելացրեք։"
        )
        self._empty_lines.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lines.setMinimumHeight(112)
        selected_layout.addWidget(self._empty_lines)
        selected_layout.addWidget(self._table)
        selected_layout.addWidget(FormField("Նշումներ", self._notes))
        selected_layout.addStretch()
        workspace.addWidget(selected, 6)
        content_layout.addLayout(workspace, 1)
        footer_panel = Panel()
        footer = QHBoxLayout(footer_panel)
        footer.setContentsMargins(14, 10, 14, 10)
        footer.addWidget(self._back)
        footer.addStretch()
        footer.addWidget(self._save)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.addWidget(scroll, 1)
        layout.addWidget(footer_panel)
        self._render()
        self._sync_product()

    def set_products(self, products: list[Product]) -> None:
        parents = {p.id: p for p in products if p.unit is Unit.BARBECUE}
        self._products = [
            p for p in products if p.is_active and p.unit != Unit.BARBECUE
        ]
        self._product_names = {}
        for product in self._products:
            parent = parents.get(product.parent_product_id)
            self._product_names[product.id] = (
                product.display_name(parent) if parent is not None else product.name
            )
        self._lines.clear()
        self._notes.setText("")
        self._dirty = False
        self._quantity.setText("1")
        self._product_search.clear()
        self._render_catalog()
        self._render()

    def _selected_product(self) -> Product | None:
        row = self._catalog_table.selected_row()
        cell = self._catalog_table.item_model.item(row, 0) if row >= 0 else None
        product_id = cell.data(_PRODUCT_ROLE) if cell else None
        return next((p for p in self._products if p.id == product_id), None)

    def _render_catalog(self) -> None:
        selected = self._selected_product()
        query = self._product_search.text().strip().casefold()
        matches = [
            p
            for p in self._products
            if all(
                term
                in f"{self._product_names[p.id]} {p.sku} {p.barcode or ''}".casefold()
                for term in query.split()
            )
        ]
        # Put exact SKU/barcode matches first, especially for scanner input.
        matches.sort(
            key=lambda p: (
                query not in (p.sku.casefold(), (p.barcode or "").casefold()),
                self._product_names[p.id].casefold(),
            )
        )
        self._catalog_table.setSortingEnabled(False)
        self._catalog_table.clear_rows()
        for product in matches:
            cells = self._catalog_table.append_row(
                [
                    self._product_names[product.id],
                    product.sku,
                    format_quantity(product.quantity_in_stock or 0),
                    unit_label(product.unit),
                ]
            )
            cells[0].setData(product.id, _PRODUCT_ROLE)
        self._catalog_count.setText(
            f"Գտնվել է՝ {len(matches)} / {len(self._products)} ապրանք"
            if matches
            else "Ապրանքներ չեն գտնվել։ Փոխեք որոնումը։"
        )
        target = next(
            (i for i, p in enumerate(matches) if selected and p.id == selected.id), None
        )
        if target is None and len(matches) == 1:
            target = 0
        if target is not None:
            self._catalog_table.selectRow(target)
        self._catalog_table.setSortingEnabled(False)
        self._sync_product()

    def _sync_product(self) -> None:
        product = self._selected_product()
        quantity = self._quantity.decimal_value()
        valid = product is not None and quantity is not None and quantity > 0
        self._add_button.setEnabled(valid)
        if product is None:
            self._selection_title.setText("Ընտրեք ապրանքը ցանկից")
            self._selection_meta.setText("Ընտրված ապրանքի տվյալները կերևան այստեղ։")
            self._balance_preview.setText("")
            return
        unit = unit_label(product.unit)
        stock = Decimal(product.quantity_in_stock or 0)
        pending = self._lines.get(product.id, Decimal("0"))
        self._selection_title.setText(self._product_names[product.id])
        self._selection_meta.setText(
            f"Կոդ՝ {product.sku} · Պահեստում՝ {format_quantity(stock)} {unit}"
            f"\nՓաստաթղթում՝ {format_quantity(pending)} {unit}"
        )
        self._balance_preview.setText(
            f"Ավելացնելուց հետո՝ {format_quantity(stock + pending + quantity)} {unit}"
            if valid
            else "Մուտքագրեք դրական քանակ։"
        )

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _go_back(self) -> None:
        if self._dirty and not confirm(
            self, "Վերադառնալ", "Չպահպանված մուտքագրումը կկորչի։ Վերադառնա՞լ։"
        ):
            return
        self._on_back()

    def _save_entry(self) -> None:
        if not self._lines:
            warn(self, "Ընտրեք առնվազն մեկ պատրաստված ապրանք։")
            return
        lines = [
            KitchenProductionLineInput(product_id, quantity)
            for product_id, quantity in self._lines.items()
        ]
        self._on_save(self._notes.value() or None, lines)

    def _sync_remove(self) -> None:
        self._remove.setEnabled(self._table.selected_row() >= 0)

    def _render(self) -> None:
        self._table.clear_rows()
        by_id = {product.id: product for product in self._products}
        for product_id, quantity in self._lines.items():
            product = by_id.get(product_id)
            if product is None:
                continue
            current = Decimal(product.quantity_in_stock or 0)
            cells = self._table.append_row(
                [
                    self._product_names[product.id],
                    f"{format_quantity(quantity)} {unit_label(product.unit)}",
                    f"{format_quantity(current)} {unit_label(product.unit)}",
                    f"{format_quantity(current + quantity)} {unit_label(product.unit)}",
                ]
            )
            cells[0].setData(product_id, _DOC_ROLE)
        has_lines = self._table.row_count() > 0
        self._empty_lines.setVisible(not has_lines)
        self._table.setVisible(has_lines)
        totals_by_unit: dict[Unit, Decimal] = {}
        for product_id, quantity in self._lines.items():
            product = by_id.get(product_id)
            if product:
                totals_by_unit[product.unit] = (
                    totals_by_unit.get(product.unit, Decimal("0")) + quantity
                )
        self._line_count_card.set_value(str(self._table.row_count()))
        self._quantity_card.set_value(
            " · ".join(
                f"{format_quantity(total)} {unit_label(unit)}"
                for unit, total in totals_by_unit.items()
            )
            or "0"
        )
        self._save.setEnabled(has_lines)
        self._sync_product()
        self._sync_remove()

    def _add(self) -> None:
        product = self._selected_product()
        product_id = product.id if product else None
        quantity = self._quantity.decimal_value()
        if not isinstance(product_id, uuid.UUID) or quantity is None or quantity <= 0:
            warn(self, "Ընտրեք ապրանք և մուտքագրեք դրական քանակ։")
            return
        self._lines[product_id] = self._lines.get(product_id, Decimal("0")) + quantity
        self._dirty = True
        self._render()

    def _remove_line(self) -> None:
        row = self._table.selected_row()
        if row < 0:
            return
        cell = self._table.item_model.item(row, 0)
        product_id = cell.data(_DOC_ROLE) if cell else None
        if isinstance(product_id, uuid.UUID):
            self._lines.pop(product_id, None)
            self._dirty = True
            self._render()


class KitchenProductionDetailPage(QWidget):
    def __init__(
        self, on_back: Callable[[], object], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._on_back = on_back
        self._heading = PageTitle("Խոհանոցից ընդունված ապրանքներ")
        self._meta = PageSubtitle("")
        self._quantity_card = StatCard("Ընդունված քանակ", "0", tone="success")
        self._table = DataTable(
            ["Ապրանք", "Կոդ", "Ընդունված քանակ", "Պահեստում հիմա"], min_height=160
        )
        self._notes = PageSubtitle("")
        self._back = BackButton(on_click=self._on_back)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        content_layout.addWidget(PageHeader("↩ Խոհանոցից վերադարձի փաստաթուղթ"))
        summary = Panel()
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        summary_layout.setSpacing(6)
        summary_layout.addWidget(self._heading)
        summary_layout.addWidget(self._meta)
        summary_layout.addWidget(self._quantity_card)
        content_layout.addWidget(summary)
        products_panel = Panel()
        products_layout = QVBoxLayout(products_panel)
        products_layout.setContentsMargins(14, 14, 14, 14)
        products_layout.setSpacing(8)
        products_layout.addWidget(SectionHeading("Ընդունված ապրանքներ"))
        products_layout.addWidget(self._table, 1)
        content_layout.addWidget(products_panel, 1)
        self._notes_panel = Panel()
        notes_layout = QVBoxLayout(self._notes_panel)
        notes_layout.setContentsMargins(14, 12, 14, 12)
        notes_layout.addWidget(SectionHeading("Նշումներ"))
        notes_layout.addWidget(self._notes)
        content_layout.addWidget(self._notes_panel)
        footer = QHBoxLayout()
        footer.addWidget(self._back)
        footer.addStretch()
        content_layout.addLayout(footer)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.addWidget(scroll)

    def set_detail(
        self,
        row: KitchenProductionRow,
        detail: KitchenProductionDetail,
        products: list[Product],
    ) -> None:
        by_id = {product.id: product for product in products}
        self._heading.setText(row.document_number)
        self._quantity_card.set_value(format_quantity(row.total_quantity))
        self._table.set_rows(
            [
                [
                    item.product_name,
                    item.product_sku,
                    f"{format_quantity(item.quantity)} {unit_label(Unit(item.unit))}",
                    (
                        f"{
                            format_quantity(
                                Decimal(by_id[item.product_id].quantity_in_stock or 0)
                            )
                        } "
                        f"{unit_label(Unit(item.unit))}"
                        if item.product_id in by_id
                        else "—"
                    ),
                ]
                for item in detail.items
            ]
        )
        self._meta.setText(
            f"Ստեղծող՝ {detail.created_by_name} · "
            f"Ամսաթիվ՝ {row.created_at:%d.%m.%Y %H:%M}"
        )
        self._notes.setText(detail.production.notes or "")
        self._notes_panel.setVisible(bool(detail.production.notes))


class KitchenExportDetailPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], object],
        on_edit: Callable[[KitchenExportRow, KitchenExportDetail], object],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_back = on_back
        self._on_edit = on_edit
        self._row: KitchenExportRow | None = None
        self._detail: KitchenExportDetail | None = None
        self._heading = PageTitle("Խոհանոցին տրված ապրանքներ")
        self._meta = PageSubtitle("")
        self._status = StatusBadge("Սևագիր", tone="warning")
        self._quantity_card = StatCard("Տրված քանակ", "0", tone="primary")
        self._cost_card = StatCard(
            "Ընդհանուր ինքնարժեք", format_currency(Decimal("0")), tone="primary"
        )
        self._table = DataTable(
            ["Ապրանք", "Կոդ", "Տրված քանակ", "Ինքնարժեք", "Ընդհանուր"],
            min_height=160,
        )
        self._notes = PageSubtitle("")
        self._back = BackButton(on_click=self._on_back)
        self._edit = EditButton("Խմբագրել", on_click=self._edit_document)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        content_layout.addWidget(PageHeader("📦 Խոհանոցին փոխանցման փաստաթուղթ"))
        summary = Panel()
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        summary_layout.setSpacing(8)
        heading_row = QHBoxLayout()
        heading_row.addWidget(self._heading)
        heading_row.addStretch()
        heading_row.addWidget(self._status)
        summary_layout.addLayout(heading_row)
        summary_layout.addWidget(self._meta)
        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        metrics.addWidget(self._quantity_card)
        metrics.addWidget(self._cost_card)
        summary_layout.addLayout(metrics)
        content_layout.addWidget(summary)
        products_panel = Panel()
        products_layout = QVBoxLayout(products_panel)
        products_layout.setContentsMargins(14, 14, 14, 14)
        products_layout.setSpacing(8)
        products_layout.addWidget(SectionHeading("Փոխանցված ապրանքներ"))
        products_layout.addWidget(self._table, 1)
        content_layout.addWidget(products_panel, 1)
        self._notes_panel = Panel()
        notes_layout = QVBoxLayout(self._notes_panel)
        notes_layout.setContentsMargins(14, 12, 14, 12)
        notes_layout.addWidget(SectionHeading("Նշումներ"))
        notes_layout.addWidget(self._notes)
        content_layout.addWidget(self._notes_panel)
        footer = QHBoxLayout()
        footer.addWidget(self._back)
        footer.addStretch()
        footer.addWidget(self._edit)
        content_layout.addLayout(footer)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.addWidget(scroll)

    def set_detail(self, row: KitchenExportRow, detail: KitchenExportDetail) -> None:
        self._row = row
        self._detail = detail
        self._heading.setText(row.document_number)
        locked = row.status == "locked"
        self._status.set_status(
            "Ավարտված" if locked else "Սևագիր",
            "success" if locked else "warning",
        )
        self._quantity_card.set_value(format_quantity(row.total_quantity))
        self._cost_card.set_value(format_currency(row.total_cost))
        self._meta.setText(
            f"Ստեղծող՝ {detail.created_by_name} · "
            f"Ամսաթիվ՝ {row.created_at:%d.%m.%Y %H:%M}"
        )
        self._table.set_rows(
            [
                [
                    item.product_name,
                    item.product_sku,
                    f"{format_quantity(item.quantity)} {item.unit}",
                    format_currency(item.unit_cost),
                    format_currency(item.line_total),
                ]
                for item in detail.items
            ]
        )
        self._notes.setText(detail.export.notes or "")
        self._notes_panel.setVisible(bool(detail.export.notes))

    def _edit_document(self) -> None:
        if self._row is not None and self._detail is not None:
            self._on_edit(self._row, self._detail)


class KitchenWindow(QWidget):
    def __init__(
        self,
        service: KitchenService,
        product_service: ProductCatalog,
        admin_user: User,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._products_service = product_service
        self._user = admin_user
        self._rows: list[KitchenExportRow] = []
        self._production_rows: list[KitchenProductionRow] = []
        self._active_tab = 0
        self._analytics_direction: str | None = None
        self._return_tab = 0
        self._in_inline_page = False
        self._loading_products = False
        self._period = DatePeriodFilter(on_change=self.reload)
        self._search = SearchField("Փաստաթուղթ կամ ապրանք", on_submit=self.reload)
        self._table = DataTable(
            ["Փաստաթուղթ", "Ամսաթիվ", "Ստեղծող", "Քանակ", "Ինքնարժեք", "Կարգավիճակ"],
            on_double_click=self._open_selected,
            on_selection_changed=self._sync_actions,
        )
        self._production_table = DataTable(
            ["Փաստաթուղթ", "Ամսաթիվ", "Ստեղծող", "Տողեր", "Մուտքագրված քանակ"],
            on_double_click=self._open_production,
            on_selection_changed=self._sync_production_actions,
        )
        self._open_production_button = EditButton(
            "Տեսնել մուտքագրված ապրանքները",
            on_click=self._open_production,
            enabled=False,
        )
        self._new = AddButton("Նոր փոխանցում", on_click=self._create)
        self._produce = AddButton("Գրանցել վերադարձը", on_click=self._create_production)
        self._open = EditButton(
            "Բացել փաստաթուղթը", on_click=self._open_selected, enabled=False
        )
        self._lock = PrimaryButton(
            "Հաստատել փոխանցումը",
            on_click=self._lock_selected,
            enabled=False,
        )
        self._refresh = SearchButton("Որոնել", on_click=self.reload)
        self._documents_stat = StatCard("📄  Փաստաթղթեր", "0")
        self._drafts_stat = StatCard("◷  Սևագրեր", "0", tone="warning")
        self._locked_stat = StatCard("✓  Ավարտված", "0", tone="success")
        self._production_docs_stat = StatCard("📋  Վերադարձի փաստաթղթեր", "0")
        self._production_qty_stat = StatCard(
            "🥘  Վերադարձված քանակ", "0", tone="success"
        )
        stats = QHBoxLayout()
        stats.setSpacing(10)
        stats.addWidget(self._documents_stat)
        stats.addWidget(self._drafts_stat)
        stats.addWidget(self._locked_stat)
        self._stack = QStackedWidget()
        history = QWidget()
        history_layout = QVBoxLayout(history)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_layout.setSpacing(10)
        history_layout.addLayout(stats)
        filters = Panel()
        filters_layout = QHBoxLayout(filters)
        filters_layout.setContentsMargins(12, 8, 12, 8)
        filters_layout.setSpacing(8)
        filters_layout.addWidget(SectionHeading("Գտնել փաստաթուղթ"))
        filters_layout.addWidget(self._search, 1)
        filters_layout.addWidget(self._refresh)
        history_layout.addWidget(filters)
        history_surface = Panel()
        history_surface_layout = QVBoxLayout(history_surface)
        history_surface_layout.setContentsMargins(12, 10, 12, 10)
        history_surface_layout.setSpacing(8)
        history_actions = QHBoxLayout()
        history_actions.addWidget(SectionHeading("Խոհանոցին փոխանցումներ"))
        history_actions.addStretch()
        history_actions.addWidget(self._new)
        history_actions.addWidget(self._lock)
        history_surface_layout.addLayout(history_actions)
        history_surface_layout.addWidget(
            PageSubtitle(
                "Ընտրեք տող՝ փաստաթուղթը դիտելու կամ սևագիրը շարունակելու համար։"
            )
        )
        history_surface_layout.addWidget(self._table, stretch=1)
        self._history_empty = PageSubtitle("Այս ժամանակահատվածում փոխանցումներ չկան։")
        history_surface_layout.addWidget(self._history_empty)
        history_layout.addWidget(history_surface, stretch=1)
        history_layout.addWidget(ActionBar([self._open], align_right=True))

        production_landing = QWidget()
        production_landing_layout = QVBoxLayout(production_landing)
        production_landing_layout.setContentsMargins(0, 0, 0, 0)
        production_landing_layout.setSpacing(10)
        production_header = ProfileHeader()
        production_header.set_profile(
            "Խոհանոցից վերադարձ",
            "Ընդունեք պատրաստի արտադրանքը և թարմացրեք պահեստի մնացորդը։",
            "Պահեստի մուտք",
            "success",
        )
        production_landing_layout.addWidget(production_header)
        production_stats = QHBoxLayout()
        production_stats.setSpacing(10)
        production_stats.addWidget(self._production_docs_stat)
        production_stats.addWidget(self._production_qty_stat)
        production_landing_layout.addLayout(production_stats)
        for card in (
            self._documents_stat,
            self._drafts_stat,
            self._locked_stat,
            self._production_docs_stat,
            self._production_qty_stat,
        ):
            card.setFixedHeight(104)
        production_intro = Panel()
        production_intro_layout = QHBoxLayout(production_intro)
        production_intro_layout.setContentsMargins(16, 12, 16, 12)
        production_intro_layout.addWidget(
            PageSubtitle(
                "Նշեք վերադարձվող պատրաստի ապրանքներն ու քանակները։ "
                "Գրանցելուց հետո դրանք կավելանան պահեստի մնացորդին։"
            ),
            1,
        )
        production_landing_layout.addWidget(production_intro)
        production_surface = Panel()
        production_surface_layout = QVBoxLayout(production_surface)
        production_surface_layout.setContentsMargins(12, 10, 12, 10)
        production_surface_layout.setSpacing(8)
        production_heading = QHBoxLayout()
        production_heading.addWidget(SectionHeading("Վերջին վերադարձի փաստաթղթեր"))
        production_heading.addStretch()
        production_heading.addWidget(self._produce)
        production_surface_layout.addLayout(production_heading)
        production_surface_layout.addWidget(
            PageSubtitle("Ընտրեք փաստաթուղթ՝ ընդունված ապրանքները տեսնելու համար։")
        )
        production_surface_layout.addWidget(self._production_table, stretch=1)
        production_surface_layout.addWidget(
            ActionBar([self._open_production_button], align_right=True)
        )
        self._production_empty = PageSubtitle("Այս ժամանակահատվածում վերադարձներ չկան։")
        production_surface_layout.addWidget(self._production_empty)
        production_landing_layout.addWidget(production_surface, stretch=1)

        self._export_editor = KitchenExportPage(
            self._return_from_export,
            self._save_export,
            parent=self,
        )
        self._production_page = KitchenProductionPage(
            self._return_from_export,
            self._save_production,
            parent=self,
        )
        self._production_detail_page = KitchenProductionDetailPage(
            self._return_from_export,
            parent=self,
        )
        self._export_detail_page = KitchenExportDetailPage(
            self._return_from_export,
            self._edit_export_detail,
            parent=self,
        )
        self._export_stack = QStackedWidget()
        self._export_stack.addWidget(history)
        self._export_stack.addWidget(self._export_editor)
        self._export_stack.addWidget(self._production_page)
        self._export_stack.addWidget(self._production_detail_page)
        self._export_stack.addWidget(self._export_detail_page)
        export_page = QWidget()
        export_layout = QVBoxLayout(export_page)
        export_layout.setContentsMargins(0, 0, 0, 0)
        export_layout.addWidget(self._export_stack)

        analytics_page = QWidget()
        analytics_layout = QVBoxLayout(analytics_page)
        analytics_layout.setContentsMargins(0, 0, 0, 0)
        analytics_layout.setSpacing(12)
        analytics_layout.addWidget(
            PageHeader(
                "📊 Խոհանոցի ամփոփում",
                "Ընտրված ժամանակահատվածի փոխանցումներն ու "
                "պահեստ վերադարձված արտադրանքը։ "
                "Սեղմեք քարտի վրա՝ ապրանքների մանրամասները բացելու համար։",
            )
        )
        self._analytics_qty = StatCard(
            "Խոհանոցին տրված քանակ",
            "0",
            on_click=lambda: self._show_analytics_detail("issue"),
        )
        self._analytics_output = StatCard(
            "Պահեստ վերադարձված պատրաստի քանակ",
            "0",
            tone="success",
            on_click=lambda: self._show_analytics_detail("return"),
        )
        analytics_cards = QHBoxLayout()
        analytics_cards.setSpacing(10)
        analytics_cards.addWidget(self._analytics_qty)
        analytics_cards.addWidget(self._analytics_output)
        analytics_layout.addLayout(analytics_cards)
        for card in (self._analytics_qty, self._analytics_output):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setFixedHeight(112)
        self._analytics_total_cost = SummaryBanner(
            "Ընդհանուր փոխանցման ինքնարժեք",
            format_currency(Decimal("0")),
        )
        analytics_layout.addWidget(self._analytics_total_cost)
        self._analytics_heading = SectionHeading("Ապրանքների շարժի մանրամասներ")
        self._analytics_detail = Panel()
        detail_layout = QVBoxLayout(self._analytics_detail)
        detail_layout.setContentsMargins(14, 12, 14, 12)
        detail_layout.setSpacing(10)
        detail_layout.addWidget(self._analytics_heading)
        self._analytics_table = DataTable(
            ["Փաստաթուղթ", "Ամսաթիվ", "Ապրանք", "Կոդ", "Քանակ", "Ինքնարժեք"]
        )
        detail_layout.addWidget(self._analytics_table, stretch=1)
        self._analytics_placeholder = PageSubtitle(
            "Ընտրեք վերևի ամփոփ քարտերից մեկը՝ շարժի մանրամասները տեսնելու համար։"
        )
        detail_layout.addWidget(self._analytics_placeholder)
        self._analytics_table.setVisible(False)
        analytics_layout.addWidget(self._analytics_detail, stretch=1)

        self._stack.addWidget(export_page)
        self._stack.addWidget(production_landing)
        self._stack.addWidget(analytics_page)
        self._tabs = TabBar(
            [
                "📚  Պատմություն և փոխանցում",
                "🥘  Խոհանոցից վերադարձ",
                "📊  Վերլուծություն",
            ],
            on_change=self._select_tab,
        )
        layout = QVBoxLayout()
        configure_page_layout(layout)
        self._page_header = PageHeader(
            "Խոհանոց",
            "Պահեստից խոհանոց փոխանցումներ և պատրաստի արտադրանքի վերադարձ",
        )
        layout.addWidget(self._page_header)
        layout.addWidget(self._tabs)
        layout.addWidget(self._period)
        layout.addWidget(self._stack, stretch=1)
        self.setLayout(layout)
        self.reload()

    def _select_tab(self, index: int) -> None:
        self._active_tab = index
        self._stack.setCurrentIndex(index)
        if not self._in_inline_page:
            self._period.setVisible(True)

    def _show_analytics_detail(self, direction: str) -> None:
        self._analytics_direction = direction
        start, end = self._period.values()
        self._analytics_heading.setText(
            "Խոհանոցին տրված ապրանքներ"
            if direction == "issue"
            else "Խոհանոցից պահեստ վերադարձված ապրանքներ"
        )
        self._analytics_placeholder.setVisible(False)
        self._analytics_table.clear_rows()
        self._analytics_table.setVisible(True)
        run_in_background(
            self,
            lambda: self._service.analytics_rows(direction, start, end),
            lambda rows: self._analytics_details_loaded(rows, direction),
            self._failed,
        )

    def _analytics_details_loaded(self, rows, direction: str) -> None:
        self._analytics_table.clear_rows()
        if not rows:
            self._analytics_table.setVisible(False)
            self._analytics_placeholder.setText("Այս ժամանակահատվածում տվյալներ չկան։")
            self._analytics_placeholder.setVisible(True)
            return
        self._analytics_placeholder.setVisible(False)
        self._analytics_table.setVisible(True)
        for row in rows:
            self._analytics_table.append_row(
                [
                    row.document_number,
                    row.created_at.strftime("%d.%m.%Y %H:%M"),
                    row.product_name,
                    row.product_sku,
                    f"{format_quantity(row.quantity)} {row.unit}",
                    format_currency(row.amount) if direction == "issue" else "—",
                ]
            )

    def reload(self) -> None:
        run_in_background(self, self._load_all, self._loaded, self._failed)

    def _load_all(self):
        return self._service.list_exports(), self._service.list_productions()

    def _loaded(self, result) -> None:
        rows, production_rows = result
        self._rows = rows
        self._production_rows = production_rows
        start, end = self._period.values()
        period_rows = [
            row
            for row in rows
            if (start is None or row.created_at.replace(tzinfo=None) >= start)
            and (end is None or row.created_at.replace(tzinfo=None) < end)
        ]
        drafts = sum(row.status == "draft" for row in period_rows)
        locked = sum(row.status == "locked" for row in period_rows)
        period_productions = [
            doc
            for doc in production_rows
            if (start is None or doc.created_at.replace(tzinfo=None) >= start)
            and (end is None or doc.created_at.replace(tzinfo=None) < end)
        ]
        self._documents_stat.set_value(str(len(period_rows)))
        self._drafts_stat.set_value(str(drafts))
        self._locked_stat.set_value(str(locked))
        self._production_docs_stat.set_value(str(len(period_productions)))
        self._production_qty_stat.set_value(
            format_quantity(
                sum((doc.total_quantity for doc in period_productions), Decimal("0"))
            )
        )
        completed = [row for row in period_rows if row.status == "locked"]
        self._analytics_total_cost.set_value(
            format_currency(sum((row.total_cost for row in completed), Decimal("0")))
        )
        self._analytics_qty.set_value(
            format_quantity(
                sum((row.total_quantity for row in completed), Decimal("0"))
            )
        )
        self._analytics_output.set_value(
            format_quantity(
                sum(
                    (doc.total_quantity for doc in period_productions),
                    Decimal("0"),
                )
            )
        )
        self._table.clear_rows()
        query = self._search.text().strip().casefold()
        for doc in rows:
            if doc not in period_rows:
                continue
            if (
                query
                and query not in doc.document_number.casefold()
                and query not in doc.created_by_name.casefold()
            ):
                continue
            cells = self._table.append_row(
                [
                    doc.document_number,
                    doc.created_at.strftime("%d.%m.%Y %H:%M"),
                    doc.created_by_name,
                    format_quantity(doc.total_quantity),
                    format_currency(doc.total_cost),
                    "✓  Ավարտված" if doc.status == "locked" else "◷  Սևագիր",
                ]
            )
            cells[0].setData(doc, _DOC_ROLE)
        self._history_empty.setVisible(self._table.row_count() == 0)
        self._table.setVisible(self._table.row_count() > 0)
        self._production_table.clear_rows()
        production_query = self._search.text().strip().casefold()
        for doc in period_productions:
            if (
                production_query
                and production_query not in doc.document_number.casefold()
                and production_query not in doc.created_by_name.casefold()
            ):
                continue
            cells = self._production_table.append_row(
                [
                    doc.document_number,
                    doc.created_at.strftime("%d.%m.%Y %H:%M"),
                    doc.created_by_name,
                    str(doc.item_count),
                    format_quantity(doc.total_quantity),
                ]
            )
            cells[0].setData(doc, _DOC_ROLE)
        self._production_empty.setVisible(self._production_table.row_count() == 0)
        self._production_table.setVisible(self._production_table.row_count() > 0)
        self._sync_actions()
        self._sync_production_actions()
        if self._active_tab == 2 and self._analytics_direction is not None:
            self._show_analytics_detail(self._analytics_direction)

    def _open_production(self) -> None:
        index = self._production_table.selected_row()
        if index < 0:
            return
        cell = self._production_table.item_model.item(index, 0)
        row = cell.data(_DOC_ROLE) if cell else None
        if not isinstance(row, KitchenProductionRow):
            return
        run_in_background(
            self,
            lambda: self._service.get_production_detail(row.id),
            lambda detail: self._show_production_detail(row, detail),
            self._failed,
        )

    def _load_products(self, on_loaded: Callable[[list[Product]], None]) -> None:
        """Keep navigation intact until the catalog is ready to display."""
        if self._loading_products:
            return
        self._loading_products = True
        self._new.setEnabled(False)
        self._produce.setEnabled(False)

        def finished(products: list[Product]) -> None:
            self._finish_product_loading()
            on_loaded(products)

        def failed(error: Exception) -> None:
            self._finish_product_loading()
            self._failed(error)

        run_in_background(self, self._products_service.list_products, finished, failed)

    def _finish_product_loading(self) -> None:
        self._loading_products = False
        self._new.setEnabled(True)
        self._produce.setEnabled(True)

    def _create_production(self) -> None:
        def loaded(products: list[Product]) -> None:
            self._production_page.set_products(products)
            self._show_inline_page(2, tab_index=1)

        self._load_products(loaded)

    def _save_production(
        self, notes: str | None, lines: list[KitchenProductionLineInput]
    ) -> None:
        run_in_background(
            self,
            lambda: self._service.create_production(self._user.id, notes, lines),
            self._production_saved,
            self._failed,
        )

    def _production_saved(self, _result: object) -> None:
        """Return to the document list after a successful stock receipt."""
        self._return_from_export()
        inform(self, "Խոհանոցից վերադարձը գրանցվեց, և պահեստի մնացորդը թարմացվեց։")

    def _show_production_detail(
        self, row: KitchenProductionRow, detail: KitchenProductionDetail
    ) -> None:
        def loaded(products: list[Product]) -> None:
            self._production_detail_page.set_detail(row, detail, products)
            self._show_inline_page(3, tab_index=1)

        self._load_products(loaded)

    def _sync_production_actions(self) -> None:
        self._open_production_button.setEnabled(
            self._production_table.selected_row() >= 0
        )

    def _selected_row(self) -> KitchenExportRow | None:
        row = self._table.selected_row()
        if row < 0:
            return None
        cell = self._table.item_model.item(row, 0)
        value = cell.data(_DOC_ROLE) if cell else None
        return value if isinstance(value, KitchenExportRow) else None

    def _sync_actions(self) -> None:
        row = self._selected_row()
        self._open.setEnabled(row is not None)
        self._lock.setEnabled(row is not None and row.status == "draft")

    def _create(self) -> None:
        self._show_editor(None)

    def _open_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        run_in_background(
            self,
            lambda: self._service.get_detail(row.id),
            lambda detail: self._show_detail(row, detail),
            self._failed,
        )

    def _show_detail(self, row: KitchenExportRow, detail: KitchenExportDetail) -> None:
        self._export_detail_page.set_detail(row, detail)
        self._show_inline_page(4)

    def _edit_export_detail(
        self, row: KitchenExportRow, detail: KitchenExportDetail
    ) -> None:
        if row.status == "locked":
            if not confirm(
                self,
                "Փաստաթղթի խմբագրում",
                "Փաստաթուղթը կբացվի խմբագրման համար, իսկ դրա նախկին "
                "քանակը կվերադարձվի ապրանքի մնացորդին։ Պահպանելուց հետո "
                "կարող եք կրկին կողպել։",
            ):
                return
            run_in_background(
                self,
                lambda: self._service.reopen_for_edit(row.id),
                lambda _doc: self._show_editor(detail, lock_after_save=True),
                self._failed,
            )
            return
        self._show_editor(detail)

    def _show_editor(
        self, detail: KitchenExportDetail | None, *, lock_after_save: bool = False
    ) -> None:
        def loaded(products: list[Product]) -> None:
            self._export_editor.set_document(
                products, detail, lock_after_save=lock_after_save
            )
            self._show_inline_page(1)

        self._load_products(loaded)

    def _show_inline_page(self, index: int, *, tab_index: int = 0) -> None:
        if not self._in_inline_page:
            self._return_tab = self._active_tab
        self._in_inline_page = True
        self._period.setVisible(False)
        self._export_stack.setCurrentIndex(index)
        # All inline forms live in the export stack, even return forms.
        self._stack.setCurrentIndex(0)
        self._tabs.set_active(tab_index)
        self._tabs.setEnabled(False)
        self._page_header.show()
        self._tabs.hide()
        self._period.hide()
        self._period.setEnabled(False)

    def _return_from_export(self) -> None:
        self._export_stack.setCurrentIndex(0)
        self._in_inline_page = False
        self._period.setVisible(True)
        self._active_tab = self._return_tab
        self._stack.setCurrentIndex(self._return_tab)
        self._tabs.set_active(self._return_tab)
        self._tabs.setEnabled(True)
        self._page_header.show()
        self._tabs.show()
        self._period.show()
        self._period.setEnabled(True)
        self.reload()

    def _save_export(
        self,
        detail: KitchenExportDetail | None,
        notes: str | None,
        lines: list[KitchenExportLineInput],
        lock_after_save: bool,
    ) -> None:
        if not lines:
            warn(self, "Փաստաթուղթը պետք է պարունակի առնվազն մեկ ապրանք։")
            return

        def saved(doc: object) -> None:
            if lock_after_save and hasattr(doc, "id"):
                run_in_background(
                    self,
                    lambda: self._service.lock(doc.id),
                    self._export_saved,
                    self._failed,
                )
            else:
                self._export_saved(doc)

        if detail is None:
            run_in_background(
                self,
                lambda: self._service.create_draft(self._user.id, notes, lines),
                saved,
                self._failed,
            )
        else:
            run_in_background(
                self,
                lambda: self._service.update_draft(detail.export.id, notes, lines),
                saved,
                self._failed,
            )

    def _export_saved(self, result: object) -> None:
        self._return_from_export()
        inform(self, "Խոհանոցի փաստաթուղթը պահպանվեց։")

    def _lock_selected(self) -> None:
        row = self._selected_row()
        if row is None or row.status != "draft":
            return
        run_in_background(
            self,
            lambda: self._get_shortages(row.id),
            lambda shortages: self._lock_if_available(row, shortages),
            self._failed,
        )

    def _get_shortages(self, export_id: uuid.UUID) -> list[str]:
        detail = self._service.get_detail(export_id)
        products = {
            product.id: product for product in self._products_service.list_products()
        }
        shortages = []
        for item in detail.items:
            product = products.get(item.product_id)
            available = (
                Decimal(product.quantity_in_stock or 0) if product else Decimal("0")
            )
            if product is None or available < item.quantity:
                shortages.append(
                    f"{item.product_name}՝ պահանջվում է "
                    f"{format_quantity(item.quantity)} {unit_label(Unit(item.unit))}, "
                    f"առկա է {format_quantity(available)} {unit_label(Unit(item.unit))}"
                )
        return shortages

    def _lock_if_available(self, row: KitchenExportRow, shortages: list[str]) -> None:
        if shortages:
            warn(
                self,
                "Պաշարը բավարար չէ արտահանման համար։ "
                + " · ".join(shortages)
                + "։ Համալրեք պաշարը կամ խմբագրեք փաստաթուղթը։",
            )
            return
        if not confirm(
            self,
            "Կողպել փաստաթուղթը",
            "Ապրանքների քանակը կհանվի ընդհանուր պաշարից։ Շարունակե՞լ։",
        ):
            return
        run_in_background(
            self, lambda: self._service.lock(row.id), self._after_save, self._failed
        )

    def _after_save(self, _result: object) -> None:
        inform(self, "Խոհանոցի փաստաթուղթը պահպանվեց։")
        self.reload()

    def _failed(self, error: Exception) -> None:
        message = str(error)
        if message.startswith("Անբավարար պաշար՝"):
            warn(self, message, title="Պաշարը բավարար չէ")
            return
        report_error(self, message, title="Խոհանոցի փաստաթուղթ")
