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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from models import Product, Unit, User
from schemas.waste import WASTE_REASONS, WasteDetail, WasteLineInput, WasteRow
from services.waste import WasteService
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
    QuantityField,
    SaveButton,
    SearchButton,
    SearchField,
    SectionHeading,
    SelectField,
    StatCard,
    StatusBadge,
    TextField,
    confirm,
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


class WasteEditorPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], object],
        on_save: Callable[
            [
                WasteDetail | None,
                str | None,
                list[WasteLineInput],
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
        self._reasons: dict[uuid.UUID, tuple[str, str | None]] = {}
        self._costs: dict[uuid.UUID, Decimal] = {}
        self._detail: WasteDetail | None = None
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
        self._reason = SelectField(
            [(label, key) for key, label in WASTE_REASONS.items()]
        )
        self._reason_note = TextField("Պատճառի մանրամասներ")
        self._reason_note.setMaxLength(2000)
        self._quantity = QuantityField(text="1")
        self._notes = TextField("Նշումներ")
        self._notes.setMaxLength(2000)
        self._notes.textEdited.connect(lambda _text: self._mark_dirty())
        self._items = DataTable(
            [
                "Ապրանք",
                "Փաստաթղթի քանակ",
                "Առկա պաշար",
                "Ինքնարժեք",
                "Ընդհանուր",
                "Պատճառ",
            ],
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
            "Պահպանել և հաստատել դուրսգրումը", on_click=self._save_locked
        )
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.addWidget(
            PageHeader(
                "🍳 Ապրանքների դուրսգրում · Отход",
                "Կազմեք դուրսգրման փաստաթուղթը։ Պաշարը կհանվի միայն հաստատելուց հետո։",
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
        selection_layout.addWidget(FormField("Դուրսգրման պատճառ", self._reason))
        selection_layout.addWidget(FormField("Պատճառի նշում", self._reason_note))
        selection_layout.addLayout(add_row)
        workspace.addWidget(selection, stretch=5)

        lines_panel = Panel()
        lines_layout = QVBoxLayout(lines_panel)
        lines_layout.setContentsMargins(14, 14, 14, 14)
        lines_layout.setSpacing(10)
        line_heading = QHBoxLayout()
        line_heading.addWidget(SectionHeading("Դուրսգրման փաստաթուղթ"))
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
        detail: WasteDetail | None = None,
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
        self._reasons = (
            {line.product_id: (line.reason, line.reason_note) for line in detail.items}
            if detail
            else {}
        )
        self._costs = (
            {line.product_id: Decimal(line.unit_cost) for line in detail.items}
            if detail is not None
            else {}
        )
        self._notes.setText(detail.document.notes or "" if detail else "")
        self._product_search.clear()
        self._dirty = False
        if lock_after_save:
            self._save.setVisible(False)
            self._save_lock.setText("Պահպանել փոփոխությունները և հաստատել")
        else:
            self._save.setVisible(True)
            self._save_lock.setText("Պահպանել և հաստատել դուրսգրումը")
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
            WasteLineInput(product_id, quantity, *self._reasons[product_id])
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
        reason = self._reason.currentData()
        note = self._reason_note.value() or None
        if reason == "custom" and not note:
            warn(self, "Այլ պատճառի համար գրեք նշում։")
            return
        product_id = product.id
        self._reasons[product_id] = (reason, note)
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
        snapshots = (
            {item.product_id: item for item in self._detail.items}
            if self._detail
            else {}
        )
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
                    snapshots[product_id].product_name
                    if product_id in snapshots
                    else product.name,
                    f"{format_quantity(quantity)} {unit_label(product.unit)}",
                    f"{format_quantity(available)} {unit_label(product.unit)}",
                    format_currency(cost),
                    format_currency(line_total),
                    WASTE_REASONS[self._reasons[product_id][0]]
                    + (
                        f": {self._reasons[product_id][1]}"
                        if self._reasons[product_id][1]
                        else ""
                    ),
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
                "Պաշարը բավարար չէ դուրսգրման համար։ "
                + " · ".join(shortages)
                + "։ Կարող եք պահպանել սևագիրը, բայց դուրսգրումը հասանելի կլինի "
                "պաշարը համալրելուց հետո։",
                tone="warning",
            )
            self._save_lock.setEnabled(False)
        else:
            self._stock_warning.hide()
            self._save_lock.setEnabled(True)


class WasteDetailPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], object],
        on_edit: Callable[[WasteRow, WasteDetail], object],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_back = on_back
        self._on_edit = on_edit
        self._row: WasteRow | None = None
        self._detail: WasteDetail | None = None
        self._heading = PageTitle("Դուրսգրված ապրանքներ")
        self._meta = PageSubtitle("")
        self._status = StatusBadge("Սևագիր", tone="warning")
        self._quantity_card = StatCard("Դուրսգրված քանակ", "0", tone="primary")
        self._cost_card = StatCard(
            "Ընդհանուր ինքնարժեք", format_currency(Decimal("0")), tone="primary"
        )
        self._table = DataTable(
            ["Ապրանք", "Կոդ", "Դուրսգրված քանակ", "Ինքնարժեք", "Ընդհանուր", "Պատճառ"],
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
        products_layout.addWidget(SectionHeading("Դուրսգրված ապրանքներ"))
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

    def set_detail(self, row: WasteRow, detail: WasteDetail) -> None:
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
                    WASTE_REASONS[item.reason]
                    + (f": {item.reason_note}" if item.reason_note else ""),
                ]
                for item in detail.items
            ]
        )
        self._notes.setText(detail.document.notes or "")
        self._notes_panel.setVisible(bool(detail.document.notes))

    def _edit_document(self) -> None:
        if self._row is not None and self._detail is not None:
            self._on_edit(self._row, self._detail)


class WasteWindow(QWidget):
    def __init__(
        self,
        service: WasteService,
        product_service: ProductCatalog,
        admin_user: User,
        business_timezone: str = "Asia/Yerevan",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        from zoneinfo import ZoneInfo

        self._timezone = ZoneInfo(business_timezone)
        self._service = service
        self._products_service = product_service
        self._user = admin_user
        self._busy = False
        self._period = DatePeriodFilter(
            on_change=self.reload,
            business_timezone=business_timezone,
            periods=[
                ("Ամբողջ պատմություն", "all"),
                ("Այսօր", "today"),
                ("Վերջին 7 օր", "7_days"),
                ("Վերջին 1 ամիս", "1_month"),
                ("Վերջին 3 ամիս", "3_months"),
                ("Վերջին 6 ամիս", "6_months"),
                ("Վերջին 1 տարի", "12_months"),
                ("Անհատական միջակայք", "custom"),
            ],
        )
        self._search = SearchField("Փաստաթուղթ կամ ստեղծող", on_submit=self.reload)
        self._table = DataTable(
            ["Փաստաթուղթ", "Ամսաթիվ", "Ստեղծող", "Քանակ", "Ինքնարժեք", "Կարգավիճակ"],
            on_double_click=self._open_selected,
            on_selection_changed=self._sync_actions,
        )
        self._new = AddButton(
            "Նոր դուրսգրում", on_click=lambda: self._show_editor(None)
        )
        self._open = EditButton(
            "Բացել փաստաթուղթը", on_click=self._open_selected, enabled=False
        )
        self._lock = PrimaryButton(
            "Ավարտել դուրսգրումը", on_click=self._lock_selected, enabled=False
        )
        self._documents = StatCard("Փաստաթղթեր", "0")
        self._quantity_card = StatCard("Դուրսգրված քանակ ըստ միավորի", "0")
        self._cost_card = StatCard(
            "Կորուստ՝ ինքնարժեքով", format_currency(Decimal("0"))
        )
        self._stack = QStackedWidget()
        self._history = QWidget()
        history = QVBoxLayout(self._history)
        history.addWidget(
            PageHeader(
                "Ապրանքների դուրսգրում · Отход",
                "Փչացած, ժամկետանց կամ վնասված ապրանքներ։ "
                "Կորուստը հաշվարկվում է ինքնարժեքով։",
            )
        )
        stats = QHBoxLayout()
        for card in (self._documents, self._quantity_card, self._cost_card):
            stats.addWidget(card)
        history.addLayout(stats)
        history.addWidget(self._period)
        filters = QHBoxLayout()
        filters.addWidget(self._search, 1)
        filters.addWidget(SearchButton("Որոնել", on_click=self.reload))
        history.addLayout(filters)
        history.addWidget(ActionBar([self._new, self._open, self._lock]))
        history.addWidget(
            PageSubtitle("Ընդհանուր կորուստը ներառում է միայն ավարտված փաստաթղթերը։")
        )
        history.addWidget(self._table, 1)
        self._empty = PageSubtitle("Այս միջակայքում դուրսգրումներ չկան։")
        history.addWidget(self._empty)
        self._editor = WasteEditorPage(self._back, self._save)
        self._detail = WasteDetailPage(self._back, self._edit)
        for page in (self._history, self._editor, self._detail):
            self._stack.addWidget(page)
        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.addWidget(self._stack)

    def closeEvent(self, event) -> None:
        from ui.workers import wait_for_pending_threads

        wait_for_pending_threads(self)
        super().closeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._stack.currentIndex() == 0:
            self.reload()

    def _run(self, work, done) -> None:
        if self._busy:
            return
        self._busy = True
        self._history.setEnabled(False)
        self._editor.setEnabled(False)
        self._detail.setEnabled(False)

        def finish(result):
            self._set_idle()
            done(result)

        def failed(error):
            self._set_idle()
            report_error(self, "Դուրսգրման սխալ", error)

        run_in_background(self, work, finish, failed)

    def _set_idle(self) -> None:
        self._busy = False
        for page in (self._history, self._editor, self._detail):
            page.setEnabled(True)

    def reload(self) -> None:
        try:
            start, end = self._bounds()
        except ValueError as error:
            report_error(self, "Դուրսգրման սխալ", error)
            return
        self._run(lambda: self._load_report(start, end), self._loaded)

    def _bounds(self):
        from datetime import UTC

        start, end = self._period.values()
        if start and end and start >= end:
            raise ValueError("Միջակայքի սկիզբը պետք է լինի ավարտից առաջ։")
        return (
            start.replace(tzinfo=self._timezone).astimezone(UTC) if start else None,
            end.replace(tzinfo=self._timezone).astimezone(UTC) if end else None,
        )

    def _load_report(self, start, end):
        rows = self._service.list_documents()
        from datetime import UTC

        rows = [
            row
            for row in rows
            if (
                start is None
                or (
                    row.created_at
                    if row.created_at.tzinfo
                    else row.created_at.replace(tzinfo=UTC)
                )
                >= start
            )
            and (
                end is None
                or (
                    row.created_at
                    if row.created_at.tzinfo
                    else row.created_at.replace(tzinfo=UTC)
                )
                < end
            )
        ]
        return rows, [
            self._service.get_detail(row.id) for row in rows if row.status == "locked"
        ]

    def _loaded(self, result) -> None:
        rows, details = result
        self._documents.set_value(str(len(rows)))
        self._cost_card.set_value(
            format_currency(
                sum((detail.document.total_cost for detail in details), Decimal("0"))
            )
        )
        totals = {}
        for detail in details:
            for item in detail.items:
                totals[item.unit] = totals.get(item.unit, Decimal("0")) + item.quantity
        self._quantity_card.set_value(
            " · ".join(
                f"{format_quantity(quantity)} {unit_label(Unit(unit))}"
                for unit, quantity in sorted(totals.items())
            )
            or "0"
        )
        self._table.clear_rows()
        query = self._search.value().casefold()
        for row in rows:
            if (
                query
                and query not in row.document_number.casefold()
                and query not in row.created_by_name.casefold()
            ):
                continue
            from datetime import UTC

            created = row.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            cells = self._table.append_row(
                [
                    row.document_number,
                    created.astimezone(self._timezone).strftime("%d.%m.%Y %H:%M"),
                    row.created_by_name,
                    format_quantity(row.total_quantity),
                    format_currency(row.total_cost),
                    "Ավարտված" if row.status == "locked" else "Սևագիր",
                ]
            )
            cells[0].setData(row, _DOC_ROLE)
        self._empty.setVisible(self._table.row_count() == 0)
        self._sync_actions()

    def _selected(self):
        index = self._table.selected_row()
        cell = self._table.item_model.item(index, 0) if index >= 0 else None
        return cell.data(_DOC_ROLE) if cell else None

    def _sync_actions(self) -> None:
        row = self._selected()
        self._open.setEnabled(row is not None)
        self._lock.setEnabled(row is not None and row.status == "draft")

    def _open_selected(self) -> None:
        row = self._selected()
        if row is None:
            return

        def loaded(detail):
            self._detail.set_detail(row, detail)
            self._stack.setCurrentIndex(2)

        self._run(lambda: self._service.get_detail(row.id), loaded)

    def _show_editor(self, detail, *, lock_after_save=False) -> None:
        def loaded(products):
            self._editor.set_document(products, detail, lock_after_save=lock_after_save)
            self._stack.setCurrentIndex(1)

        self._run(self._products_service.list_products, loaded)

    def _edit(self, row, detail) -> None:
        if row.status == "locked":
            if not confirm(
                self,
                "Բացել խմբագրման համար",
                "Նախկին քանակները կվերադարձվեն պահեստին։ "
                "Ավարտելիս դրանք կրկին կհանվեն։",
            ):
                return

            def reopen():
                self._service.reopen_for_edit(row.id)
                return self._service.get_detail(
                    row.id
                ), self._products_service.list_products()

            def loaded(result):
                current, products = result
                self._editor.set_document(products, current, lock_after_save=True)
                self._stack.setCurrentIndex(1)

            self._run(reopen, loaded)
        else:
            self._show_editor(detail)

    def _save(self, detail, notes, lines, lock) -> None:
        def save():
            doc = (
                self._service.create_draft(self._user.id, notes, lines, complete=lock)
                if detail is None
                else self._service.update_draft(
                    detail.document.id, notes, lines, complete=lock
                )
            )
            return doc

        def saved(doc):
            self._back()

        self._run(save, saved)

    def _lock_selected(self) -> None:
        row = self._selected()
        if row and confirm(
            self, "Ավարտել դուրսգրումը", "Քանակները կհանվեն պահեստից։ Շարունակե՞լ։"
        ):
            self._run(lambda: self._service.lock(row.id), lambda _doc: self.reload())

    def _back(self) -> None:
        self._stack.setCurrentIndex(0)
        self.reload()
