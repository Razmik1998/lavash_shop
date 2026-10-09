from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from schemas import (
    SaleAuditHistoryRow,
    SaleDetail,
    SaleItemChangeRow,
    SaleRevisionRow,
    SalesFilters,
    SalesPage,
    SalesSummary,
)
from ui.components import (
    CancelButton,
    DataTable,
    DatePeriodFilter,
    FilterBar,
    GhostButton,
    PageTitle,
    Panel,
    RefreshButton,
    SectionHeading,
    StatCard,
    TabBar,
    TextField,
    prompt_text,
    report_error,
)
from ui.sale_history import item_action_label, item_data_text, sale_timeline_rows
from ui.style import configure_page_layout, format_currency, format_quantity
from ui.workers import run_in_background, wait_for_pending_threads

if TYPE_CHECKING:
    from services import SalesHistoryService

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")
logger = logging.getLogger(__name__)


class SalesHistoryWindow(QWidget):
    def __init__(
        self,
        service: SalesHistoryService,
        *,
        barbecue_only: bool = False,
        actor_user_id: uuid.UUID | None = None,
    ) -> None:
        super().__init__()
        self._actor_user_id = actor_user_id
        self._selected_status: str | None = None
        self._service = service
        self._barbecue_only = barbecue_only
        self._generation = 0
        self._detail_generation = 0
        self._selected_sale_id: uuid.UUID | None = None
        self._sale_history_loading = False
        self._sale_history_loaded = False
        self._loading = False
        self._cursor: str | None = None
        self._filters = SalesFilters(barbecue_only=barbecue_only)
        self._stack = QStackedWidget()
        self._history = self._build_history()
        self._detail = self._build_detail()
        self._stack.addWidget(self._history)
        self._stack.addWidget(self._detail)
        layout = QVBoxLayout()
        configure_page_layout(layout)
        layout.addWidget(self._stack, 1)
        self.setLayout(layout)
        self._reload()

    def _build_history(self) -> QWidget:
        page = QWidget()
        page.setObjectName("salesHistoryPage")
        page.setStyleSheet("""
            QWidget#salesHistoryPage QLabel#statValue { font-size: 24px; }
            QWidget#salesHistoryPage QTableView {
                border: none; border-radius: 0;
                alternate-background-color: #f7f9fc;
            }
            QWidget#salesHistoryPage QTableView::item { padding: 0 10px; }
            QWidget#salesHistoryPage QHeaderView::section {
                background: #edf2f8; color: #34465e; padding: 12px 10px;
            }
        """)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        title = "Խորովածի վաճառք" if self._barbecue_only else "Վաճառքի պատմություն"
        layout.addWidget(PageTitle(title), 0, Qt.AlignmentFlag.AlignTop)
        self._terminal = TextField("POS տերմինալ", on_submit=self._apply_filters)
        self._terminal.setClearButtonEnabled(True)
        self._period = DatePeriodFilter(on_change=self._apply_filters)
        self._history_filters = FilterBar(
            [("Ժամանակահատված", self._period), ("Տերմինալ", self._terminal)],
            title="Զտիչներ",
        )
        self._history_filters.add_field(
            None, RefreshButton(on_click=self._apply_filters)
        )
        self._history_filters.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self._history_filters)
        summary = QHBoxLayout()
        summary.setSpacing(10)
        self._sale_count = StatCard("Վաճառքների քանակ", "0", tone="default")
        self._item_count = StatCard("Ապրանքների քանակ", "0", tone="info")
        self._total = StatCard("Ընդհանուր վաճառք", "0 ֏", tone="primary")
        self._income = StatCard("Եկամուտ", "0 ֏", tone="success")
        self._credit_total = StatCard("Պարտքով վաճառք", "0 ֏", tone="danger")
        for card in (
            self._sale_count,
            self._item_count,
            self._total,
            self._income,
            self._credit_total,
        ):
            card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            card.layout().setContentsMargins(16, 12, 14, 12)
            summary.addWidget(card, 1)
        layout.addLayout(summary)
        table_panel = Panel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(1, 1, 1, 1)
        table_layout.setSpacing(0)
        table_heading = QHBoxLayout()
        table_heading.setContentsMargins(16, 12, 16, 12)
        table_heading.addWidget(SectionHeading("Վաճառքներ"))
        table_heading.addStretch()
        hint = QLabel("Կրկնակի սեղմեք՝ մանրամասները բացելու համար")
        hint.setObjectName("pageSubtitle")
        table_heading.addWidget(hint)
        table_layout.addLayout(table_heading)
        self._table = DataTable(
            [
                "POS տերմինալ",
                "Աշխատակից",
                "Սեսիա",
                "Ընդհանուր",
                "Պարտքով / հաճախորդ",
                "Եկամուտ",
                "Կարգավիճակ",
                "Ամսաթիվ",
            ],
            on_double_click=self._open_detail,
            min_height=280,
        )
        self._table.verticalHeader().setDefaultSectionSize(38)
        self._table.setTextElideMode(Qt.TextElideMode.ElideRight)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(100)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._model = self._table.item_model
        table_layout.addWidget(self._table, 1)
        layout.addWidget(table_panel, 1)
        return page

    def _build_detail(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        header.addWidget(GhostButton("← Վերադառնալ", on_click=self._show_history))
        self._detail_title = PageTitle("Վաճառքի մանրամասներ")
        header.addWidget(self._detail_title)
        header.addStretch()
        self._cancel_button = CancelButton(
            "Չեղարկել վաճառքը", on_click=self._cancel_sale, enabled=False
        )
        header.addWidget(self._cancel_button)
        layout.addLayout(header)
        self._detail_meta = QLabel()
        self._detail_meta.setWordWrap(True)
        layout.addWidget(self._detail_meta)
        stats = QHBoxLayout()
        self._detail_total = StatCard("Ընդհանուր վաճառք", "0 ֏")
        self._detail_income = StatCard("Եկամուտ", "0 ֏", tone="success")
        stats.addWidget(self._detail_total)
        stats.addWidget(self._detail_income)
        layout.addLayout(stats)
        self._items = DataTable(
            [
                "Ապրանք",
                "Կոդ",
                "Քանակ",
                "Ինքնարժեք",
                "Վաճառքի գին",
                "Զեղչ",
                "Եկամուտ",
                "Ընդհանուր",
            ]
        )
        self._items.setMinimumHeight(220)
        self._items.setMaximumHeight(360)
        self._items.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._items.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._detail_sections = QStackedWidget()
        items_page = QWidget()
        items_layout = QVBoxLayout(items_page)
        items_layout.addWidget(self._items, 1)
        self._detail_sections.addWidget(items_page)

        activity_page = QWidget()
        activity_layout = QVBoxLayout(activity_page)
        self._activity_status = QLabel(
            "Բացեք այս բաժինը՝ վաճառքի ընթացքը դիտելու համար։"
        )
        activity_layout.addWidget(self._activity_status)
        self._timeline = DataTable(
            [
                "Ամսաթիվ և ժամ",
                "Իրադարձություն",
                "Մանրամասներ",
                "Կատարող",
            ]
        )
        activity_layout.addWidget(self._timeline, 1)
        self._detail_sections.addWidget(activity_page)

        changes_page = QWidget()
        changes_layout = QVBoxLayout(changes_page)
        self._changes_status = QLabel(
            "Բացեք այս բաժինը՝ ապրանքների փոփոխությունները դիտելու համար։"
        )
        changes_layout.addWidget(self._changes_status)
        self._changes = DataTable(
            [
                "Ամսաթիվ և ժամ",
                "Գործողություն",
                "Ապրանք",
                "Նախկին տվյալներ",
                "Նոր տվյալներ",
                "Կատարող",
            ]
        )
        changes_layout.addWidget(self._changes, 1)
        self._detail_sections.addWidget(changes_page)

        self._detail_tabs = TabBar(
            [
                "Ապրանքներ",
                "Վաճառքի ընթացք",
                "Ապրանքների փոփոխություններ",
            ],
            on_change=self._select_detail_section,
        )
        layout.addWidget(self._detail_tabs)
        layout.addWidget(self._detail_sections, 1)
        return page

    def _select_detail_section(self, index: int) -> None:
        self._detail_sections.setCurrentIndex(index)
        if index in (1, 2):
            self._load_sale_history()

    def _apply_filters(self) -> None:
        self._generation += 1
        from_value, to_value = self._period.values()
        self._filters = SalesFilters(
            from_datetime=(
                from_value.replace(tzinfo=ARMENIA_TIMEZONE) if from_value else None
            ),
            to_datetime=to_value.replace(tzinfo=ARMENIA_TIMEZONE) if to_value else None,
            terminal_id=self._terminal.value() or None,
            barbecue_only=self._barbecue_only,
        )
        self._reload()

    def _reload(self) -> None:
        self._cursor = None
        self._loading = False
        self._model.removeRows(0, self._model.rowCount())
        generation = self._generation
        self._load_page(generation)
        run_in_background(
            self,
            lambda: self._service.summarize_sales(self._filters),
            self._summary_loaded,
            self._failed,
        )

    def _load_page(self, generation: int) -> None:
        if self._loading:
            return
        self._loading = True
        run_in_background(
            self,
            lambda: self._service.list_sales(self._filters, self._cursor),
            lambda page: self._page_loaded(generation, page),
            self._failed,
        )

    def _page_loaded(self, generation: int, page: SalesPage) -> None:
        self._loading = False
        if generation != self._generation:
            return
        for row in page.items:
            session = QStandardItem(str(row.session_id)[:8] + "…")
            session.setToolTip(str(row.session_id))
            item = QStandardItem(self._format_timestamp(row.created_at))
            item.setData(row.id, Qt.ItemDataRole.UserRole)
            cells = self._table.append_row(
                [
                    row.terminal_id,
                    row.employee_full_name,
                    session,
                    format_currency(row.total),
                    (
                        f"{format_currency(row.credit_amount)} / "
                        f"{row.credit_customer_name}"
                        if row.credit_amount is not None
                        else "Կանխիկ"
                    ),
                    format_currency(row.income_total),
                    _sale_status_label(row.status),
                    item,
                ]
            )
            for column in (3, 5):
                cells[column].setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            status_color = {
                "completed": "#087765",
                "editing": "#a16207",
                "voided": "#c24145",
                "cancelled": "#c24145",
            }.get(row.status, "#52606d")
            cells[6].setForeground(QColor(status_color))
            for cell in cells:
                if not cell.toolTip():
                    cell.setToolTip(cell.text())
        self._cursor = page.next_cursor
        if self._cursor is not None:
            self._load_page(generation)

    def _summary_loaded(self, summary: SalesSummary) -> None:
        self._sale_count.value_label.setText(str(summary.sale_count))
        self._item_count.value_label.setText(
            format_quantity(summary.item_quantity_total)
        )
        self._total.value_label.setText(format_currency(summary.revenue_total))
        self._income.value_label.setText(format_currency(summary.income_total))
        self._credit_total.value_label.setText(format_currency(summary.credit_total))

    def _open_detail(self) -> None:
        row = self._table.selected_row()
        item = None if row < 0 else self._model.item(row, 7)
        sale_id = None if item is None else item.data(Qt.ItemDataRole.UserRole)
        if isinstance(sale_id, uuid.UUID):
            self._detail_generation += 1
            generation = self._detail_generation
            self._selected_sale_id = sale_id
            self._sale_history_loading = False
            self._sale_history_loaded = False
            self._detail_sections.setCurrentIndex(0)
            self._detail_tabs.set_active(0)
            self._timeline.clear_rows()
            self._changes.clear_rows()
            self._activity_status.setText(
                "Բացեք այս բաժինը՝ վաճառքի ընթացքը դիտելու համար։"
            )
            self._changes_status.setText(
                "Բացեք այս բաժինը՝ ապրանքների փոփոխությունները դիտելու համար։"
            )
            run_in_background(
                self,
                lambda: self._service.get_sale_detail(
                    sale_id,
                    barbecue_only=self._barbecue_only,
                    include_history=False,
                ),
                lambda detail: self._detail_loaded(generation, detail),
                self._failed,
            )

    def _detail_loaded(self, generation: int, detail: SaleDetail) -> None:
        if generation != self._detail_generation:
            return
        self._detail_title.setText(f"Վաճառք՝ {detail.terminal_id}")
        self._selected_status = detail.status
        self._cancel_button.setEnabled(
            self._actor_user_id is not None
            and detail.status in {"completed", "editing"}
        )
        self._detail_meta.setText(
            f"Աշխատակից՝ {detail.employee_full_name}    "
            f"Սեսիա՝ {detail.session_id}    "
            f"Ամսաթիվ՝ {self._format_timestamp(detail.created_at)}    "
            f"Կարգավիճակ՝ {_sale_status_label(detail.status)}"
        )
        if detail.cancellation_reason:
            self._detail_meta.setText(
                f"{self._detail_meta.text()}\n"
                f"Չեղարկման պատճառ՝ {detail.cancellation_reason}"
            )
        self._detail_total.value_label.setText(format_currency(detail.total))
        self._items.clear_rows()
        income = Decimal("0")
        for item in detail.items:
            cost = item.cost_price or Decimal("0")
            line_income = (item.unit_price - cost) * item.quantity
            income += line_income
            self._items.append_row(
                [
                    item.product_name,
                    item.product_sku,
                    format_quantity(item.quantity),
                    format_currency(cost),
                    format_currency(item.unit_price),
                    (
                        format_currency(item.discount_amount)
                        if item.discount_amount
                        else ""
                    ),
                    format_currency(line_income),
                    format_currency(item.line_total),
                ]
            )
        self._detail_income.value_label.setText(format_currency(income))
        credit_text = (
            f"Պարտքով՝ {format_currency(detail.credit_amount)} | "
            f"Հաճախորդ՝ {detail.credit_customer_name}"
            if detail.credit_amount is not None
            else "Վաճառքը կատարվել է կանխիկ։"
        )
        self._detail_meta.setText(f"{self._detail_meta.text()}    {credit_text}")
        self._stack.setCurrentWidget(self._detail)

    def _cancel_sale(self) -> None:
        sale_id = self._selected_sale_id
        actor_user_id = self._actor_user_id
        if sale_id is None or actor_user_id is None:
            return
        reason = prompt_text(
            self,
            "Չեղարկել վաճառքը",
            "Նշեք վաճառքը չեղարկելու պատճառը։",
            placeholder="Չեղարկման պատճառը",
            confirm_text="Չեղարկել վաճառքը",
            confirm_variant="danger",
        )
        if reason is None:
            return
        self._cancel_button.setEnabled(False)
        generation = self._detail_generation
        run_in_background(
            self,
            lambda: self._service.cancel_sale(sale_id, actor_user_id, reason),
            lambda detail: self._cancelled(generation, detail),
            self._cancel_failed,
        )

    def _cancelled(self, generation: int, detail: SaleDetail) -> None:
        self._detail_loaded(generation, detail)
        self._reload()

    def _cancel_failed(self, error: Exception) -> None:
        self._cancel_button.setEnabled(
            self._selected_status in {"completed", "editing"}
        )
        report_error(self, str(error) or "Չհաջողվեց չեղարկել վաճառքը։")

    def _load_sale_history(self) -> None:
        if (
            self._selected_sale_id is None
            or self._sale_history_loading
            or self._sale_history_loaded
        ):
            return
        sale_id = self._selected_sale_id
        generation = self._detail_generation
        self._sale_history_loading = True
        self._activity_status.setText("Վաճառքի ընթացքը բեռնվում է…")
        self._changes_status.setText("Փոփոխությունների պատմությունը բեռնվում է…")
        run_in_background(
            self,
            lambda: self._service.get_sale_history(sale_id),
            lambda history: self._sale_history_loaded_for_detail(generation, history),
            lambda error: self._sale_history_failed(generation, error),
        )

    def _sale_history_loaded_for_detail(
        self,
        generation: int,
        history: tuple[
            list[SaleRevisionRow], list[SaleItemChangeRow], list[SaleAuditHistoryRow]
        ],
    ) -> None:
        if generation != self._detail_generation:
            return
        self._sale_history_loading = False
        self._sale_history_loaded = True
        revisions, changes, audit_events = history
        timeline = sale_timeline_rows(revisions, audit_events)
        self._timeline.clear_rows()
        for happened_at, action, details, actor in timeline:
            self._timeline.append_row(
                [self._format_timestamp(happened_at), action, details, actor]
            )
        self._activity_status.setText(
            "Վաճառքի ստեղծման, բացման, պահպանման և չեղարկման ժամանակագրություն։"
            if timeline
            else "Այս վաճառքի համար ընթացքի տվյալներ չկան։"
        )
        self._changes.clear_rows()
        for change in changes:
            self._changes.append_row(
                [
                    self._format_timestamp(change.created_at),
                    item_action_label(change.action),
                    change.product_name,
                    item_data_text(change.old_data),
                    item_data_text(change.new_data),
                    change.user_full_name,
                ]
            )
        self._changes_status.setText(
            f"Փոփոխությունների գրառում՝ {len(changes)}"
            if changes
            else "Ապրանքների փոփոխություններ չեն գրանցվել։"
        )

    def _sale_history_failed(self, generation: int, error: Exception) -> None:
        if generation != self._detail_generation:
            return
        self._sale_history_loading = False
        self._activity_status.setText("Վաճառքի ընթացքը չհաջողվեց բեռնել։")
        self._changes_status.setText("Փոփոխությունների պատմությունը չհաջողվեց բեռնել։")
        self._failed(error)

    def _show_history(self) -> None:
        self._stack.setCurrentWidget(self._history)

    @staticmethod
    def _format_timestamp(value: datetime) -> str:
        return value.astimezone(ARMENIA_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    def _failed(self, error: Exception) -> None:
        self._loading = False
        logger.error("sales_history_window op=load outcome=failed error=%s", error)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)


def _sale_status_label(status: str) -> str:
    return {
        "completed": "Կատարված",
        "voided": "Չեղարկված",
        "editing": "Խմբագրվում է",
        "cancelled": "Չեղարկված",
    }.get(status, status)
