"""Administration monitoring section for POS sessions
(.claude/specs/4/input/task-4-pos-session-lifecycle.md section 8): a
near-real-time table of every POS terminal, its current user, session
status, connection status, and activity timestamps.

Polls on a QTimer (~3s) rather than pushing updates, matching "near
real-time... if the existing architecture supports it" (section 9) —
this repo has no server-push channel from Admin to its own UI, only a
POS -> Admin TCP link, so polling the local service is the simplest
mechanism that fits."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
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
    DataTable,
    DatePeriodFilter,
    FilterBar,
    GhostButton,
    PageTitle,
    RefreshButton,
    SearchField,
    StatCard,
    StatusChecks,
    TabBar,
)
from ui.sale_history import item_action_label, item_data_text, sale_timeline_rows
from ui.style import configure_page_layout, format_currency, format_quantity
from ui.workers import run_in_background, wait_for_pending_threads

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")

if TYPE_CHECKING:
    from services import SalesHistoryService

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 3_000

_HEADERS = [
    "POS տերմինալ",
    "Օգտատեր",
    "Սեսիայի կարգավիճակ",
    "Կապի կարգավիճակ",
    "Սկիզբ",
    "Ավարտ",
    "Վերջին ակտիվություն",
    "Տևողություն",
    "Սկզբնական դրամարկղ",
    "Փակման դրամարկղ",
    "Փոխանցման գումար",
    "Պարտքով վաճառք",
    "Վերադարձված գումար",
]

_SESSION_STATUS_LABELS = {
    "active": "Ակտիվ",
    "closed": "Փակված",
}

_CONNECTION_STATUS_LABELS = {
    "connected": "Կապակցված է",
    "disconnected": "Կապն ընդհատված է",
}

_SALE_STATUS_LABELS = {
    "completed": "Կատարված",
    "cancelled": "Չեղարկված",
}


def _session_status_label(status: str) -> str:
    return _SESSION_STATUS_LABELS.get(status, status)


def _connection_status_label(status: str) -> str:
    return _CONNECTION_STATUS_LABELS.get(status, status)


def _sale_status_label(status: str) -> str:
    return _SALE_STATUS_LABELS.get(status, status)


@dataclass(frozen=True)
class PosSessionRow:
    """The shape `PosSessionMonitoringService.list_sessions()` must
    return one of, per row. `user_full_name` is a display name resolved
    server-side (the window must not do its own user lookups - see
    .claude/rules/database.md "avoid N+1 queries"). Timestamps are
    timezone-aware `datetime` objects (this is Admin's own process, no
    wire serialization involved, unlike the POS-facing `SessionPayload`)."""

    terminal_id: str
    user_full_name: str
    status: str
    connection_status: str
    started_at: datetime
    closed_at: datetime | None
    last_activity_at: datetime
    session_id: object = None
    opening_cash: Decimal = Decimal("0")
    closing_cash: Decimal | None = None
    cash_difference: Decimal | None = None
    repayments_total: Decimal = Decimal("0")
    credit_sales_total: Decimal = Decimal("0")


class PosSessionMonitoringService(Protocol):
    def list_sessions(self) -> list[PosSessionRow]:
        """Returns one row per POS session (active and closed, for
        history/auditing per section 6), newest-active-first or in
        whatever order is most useful for the admin to scan."""
        ...


class PosSessionsWindow(QWidget):
    def __init__(
        self,
        pos_session_service: PosSessionMonitoringService,
        sales_history_service: SalesHistoryService | None = None,
    ) -> None:
        super().__init__()
        self._pos_session_service = pos_session_service
        self._sales_history_service = sales_history_service
        self._all_rows: list[PosSessionRow] = []
        self._strict_filters = False
        self._detail_session_id: object = None
        self._sales_loading = False
        self._sale_detail_generation = 0
        self._selected_sale_id: uuid.UUID | None = None
        self._sale_history_loading = False
        self._sale_history_loaded = False

        self._stack = QStackedWidget()
        self._overview = self._build_overview()
        self._detail = self._build_detail()
        self._stack.addWidget(self._overview)
        self._stack.addWidget(self._detail)

        layout = QVBoxLayout()
        configure_page_layout(layout)
        layout.addWidget(self._stack, stretch=1)
        self.setLayout(layout)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self.reload_sessions)
        self._poll_timer.start()
        self.reload_sessions()

    def _build_overview(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        title = PageTitle("POS սեսիաներ")
        layout.addWidget(title)

        self._period = DatePeriodFilter(
            on_change=lambda: self._apply_filters(strict=True)
        )
        self._period.set_period("today", notify=False)
        self._search = SearchField(
            "POS տերմինալ կամ աշխատակից",
            on_submit=lambda: self._apply_filters(strict=True),
        )
        self._search.textChanged.connect(lambda _text: self._apply_filters(strict=True))
        self._status_checks = StatusChecks(
            on_change=lambda: self._apply_filters(strict=True)
        )
        filters = FilterBar(
            [
                ("Ժամանակահատված", self._period),
                ("Որոնում", self._search),
                ("Կարգավիճակ", self._status_checks),
            ],
            title="Զտիչներ",
        )
        filters.add_field(None, RefreshButton(on_click=self.reload_sessions))
        layout.addWidget(filters)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self._active_stat = StatCard("Ակտիվ սեսիաներ", "0", tone="success")
        self._closed_stat = StatCard("Փակված սեսիաներ", "0", tone="danger")
        self._visible_stat = StatCard("Ցուցադրված սեսիաներ", "0", tone="info")
        for card in (self._active_stat, self._closed_stat, self._visible_stat):
            stats.addWidget(card)
        layout.addLayout(stats)

        self._table = DataTable(
            _HEADERS,
            on_double_click=self._on_row_activated,
        )
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._model = self._table.item_model
        self._empty_state = QLabel("Ընտրված զտիչներով սեսիաներ չկան։")
        self._empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_state.hide()
        layout.addWidget(self._empty_state)
        layout.addWidget(self._table, stretch=1)
        return page

    def _build_detail(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        back = GhostButton("← Վերադառնալ", on_click=self._show_overview)
        header.addWidget(back)
        self._detail_title = PageTitle("Սեսիայի մանրամասներ")
        header.addWidget(self._detail_title)
        header.addStretch()
        layout.addLayout(header)
        detail_stats = QHBoxLayout()
        self._detail_quantity_stat = StatCard("Ապրանքների քանակ", "0", tone="info")
        self._detail_total_stat = StatCard("Ընդհանուր վաճառք", "0 ֏", tone="default")
        self._detail_income_stat = StatCard("Եկամուտ", "0 ֏", tone="success")
        self._detail_repayments_stat = StatCard(
            "Վերադարձված գումար", "0 ֏", tone="warning"
        )
        self._detail_credit_sales_stat = StatCard(
            "Պարտքով վաճառք", "0 ֏", tone="danger"
        )
        for card in (
            self._detail_quantity_stat,
            self._detail_total_stat,
            self._detail_income_stat,
            self._detail_repayments_stat,
            self._detail_credit_sales_stat,
        ):
            detail_stats.addWidget(card)
        layout.addLayout(detail_stats)
        self._sale_table = DataTable(
            [
                "Ամսաթիվ",
                "POS տերմինալ",
                "Կարգավիճակ",
                "Վճարման ձև",
                "Հաճախորդ",
                "Գումար",
            ],
            on_double_click=self._open_sale_detail,
            on_selection_changed=self._open_sale_detail,
        )
        self._sale_model = self._sale_table.item_model
        layout.addWidget(self._sale_table, stretch=1)
        self._sale_items = DataTable(
            [
                "Ապրանք",
                "Կոդ",
                "Չափման միավոր",
                "Քանակ",
                "Ինքնարժեք",
                "Վաճառքի գին",
                "Զեղչ",
                "Եկամուտ",
                "Ընդհանուր",
            ],
            min_height=150,
        )
        self._sale_detail_stack = QStackedWidget()
        items_page = QWidget()
        items_layout = QVBoxLayout(items_page)
        items_layout.addWidget(self._sale_items, 1)
        self._sale_detail_stack.addWidget(items_page)

        activity_page = QWidget()
        activity_layout = QVBoxLayout(activity_page)
        self._sale_activity_status = QLabel(
            "Ընտրեք «Վաճառքի ընթացք» բաժինը՝ պատմությունը դիտելու համար։"
        )
        activity_layout.addWidget(self._sale_activity_status)
        self._sale_timeline = DataTable(
            [
                "Ամսաթիվ և ժամ",
                "Իրադարձություն",
                "Մանրամասներ",
                "Կատարող",
            ]
        )
        activity_layout.addWidget(self._sale_timeline, 1)
        self._sale_detail_stack.addWidget(activity_page)

        changes_page = QWidget()
        changes_layout = QVBoxLayout(changes_page)
        self._sale_changes_status = QLabel(
            "Ընտրեք «Ապրանքների փոփոխություններ» բաժինը՝ գրառումները դիտելու համար։"
        )
        changes_layout.addWidget(self._sale_changes_status)
        self._sale_changes = DataTable(
            [
                "Ամսաթիվ և ժամ",
                "Գործողություն",
                "Ապրանք",
                "Նախկին տվյալներ",
                "Նոր տվյալներ",
                "Կատարող",
            ]
        )
        changes_layout.addWidget(self._sale_changes, 1)
        self._sale_detail_stack.addWidget(changes_page)

        self._sale_detail_tabs = TabBar(
            [
                "Ապրանքներ",
                "Վաճառքի ընթացք",
                "Ապրանքների փոփոխություններ",
            ],
            on_change=self._select_sale_detail_section,
        )
        layout.addWidget(self._sale_detail_tabs)
        layout.addWidget(self._sale_detail_stack, stretch=1)
        return page

    def _select_sale_detail_section(self, index: int) -> None:
        self._sale_detail_stack.setCurrentIndex(index)
        if index in (1, 2):
            self._load_sale_history()

    def reload_sessions(self) -> None:
        run_in_background(
            self,
            self._pos_session_service.list_sessions,
            self._on_sessions_loaded,
            self._on_load_failed,
        )

    def _on_sessions_loaded(self, rows: list[PosSessionRow]) -> None:
        self._all_rows = rows
        self._apply_filters()

    def _apply_filters(self, *, strict: bool = False) -> None:
        if not hasattr(self, "_table"):
            return
        self._strict_filters = self._strict_filters or strict
        start_value, end_value = self._period.values()
        start = start_value.date() if start_value is not None else None
        end = (end_value - timedelta(microseconds=1)).date() if end_value else None
        statuses = self._status_checks.selected()
        search = self._search.value().casefold()
        rows = [
            row
            for row in self._all_rows
            if row.status in statuses
            and (
                (row.status == "active" and not self._strict_filters)
                or (
                    (start is None or start <= self._local_date(row.started_at))
                    and (end is None or self._local_date(row.started_at) <= end)
                )
            )
            and (
                not search
                or search in row.terminal_id.casefold()
                or search in row.user_full_name.casefold()
            )
        ]
        self._render_rows(rows)
        self._empty_state.setVisible(not rows)
        active_count = sum(row.status == "active" for row in self._all_rows)
        closed_count = sum(row.status == "closed" for row in self._all_rows)
        self._active_stat.value_label.setText(str(active_count))
        self._closed_stat.value_label.setText(str(closed_count))
        self._visible_stat.value_label.setText(str(len(rows)))

    def _render_rows(self, rows: list[PosSessionRow]) -> None:
        self._table.clear_rows()
        for row in rows:
            terminal_item = QStandardItem(row.terminal_id)
            terminal_item.setData(row.session_id, Qt.ItemDataRole.UserRole)
            self._table.append_row(
                [
                    terminal_item,
                    row.user_full_name,
                    _session_status_label(row.status),
                    _connection_status_label(row.connection_status),
                    self._format_timestamp(row.started_at),
                    self._format_timestamp(row.closed_at),
                    self._format_timestamp(row.last_activity_at),
                    self._format_duration(row.started_at, row.closed_at),
                    format_currency(row.opening_cash),
                    format_currency(row.closing_cash)
                    if row.closing_cash is not None
                    else "—",
                    self._format_cash_difference(row.cash_difference),
                    format_currency(row.credit_sales_total),
                    format_currency(row.repayments_total),
                ]
            )

    @staticmethod
    def _format_cash_difference(value: Decimal | None) -> str:
        if value is None:
            return "—"
        return format_currency(value)

    def _on_row_activated(self) -> None:
        row = self._table.selected_row()
        if row < 0:
            return
        item = self._model.item(row, 0)
        session_id = None if item is None else item.data(Qt.ItemDataRole.UserRole)
        if session_id is not None and self._sales_history_service is not None:
            self._show_session_detail(session_id)

    def _show_session_detail(self, session_id: object) -> None:
        if not isinstance(session_id, uuid.UUID):
            return
        self._detail_session_id = session_id
        row = next(
            (item for item in self._all_rows if item.session_id == session_id),
            None,
        )
        if row is not None:
            self._detail_title.setText(
                f"Սեսիա՝ {row.terminal_id} / {row.user_full_name}"
            )
            self._detail_repayments_stat.value_label.setText(
                format_currency(row.repayments_total)
            )
            self._detail_credit_sales_stat.value_label.setText(
                format_currency(row.credit_sales_total)
            )
        self._sale_detail_generation += 1
        self._selected_sale_id = None
        self._sale_history_loading = False
        self._sale_history_loaded = False
        self._sale_model.removeRows(0, self._sale_model.rowCount())
        self._sale_items.clear_rows()
        self._sale_timeline.clear_rows()
        self._sale_changes.clear_rows()
        self._sale_detail_stack.setCurrentIndex(0)
        self._sale_detail_tabs.set_active(0)
        self._stack.setCurrentWidget(self._detail)
        self._load_session_sales()

    def _load_session_sales(self) -> None:
        service = self._sales_history_service
        if service is None or not isinstance(self._detail_session_id, uuid.UUID):
            return
        self._sales_loading = True
        filters = SalesFilters(session_id=self._detail_session_id)
        run_in_background(
            self,
            lambda: service.summarize_sales(filters),
            self._session_summary_loaded,
            self._on_load_failed,
        )
        run_in_background(
            self,
            lambda: service.list_sales(filters, None),
            self._session_sales_loaded,
            self._on_load_failed,
        )

    def _session_summary_loaded(self, summary: SalesSummary) -> None:
        self._detail_quantity_stat.value_label.setText(
            format_quantity(summary.item_quantity_total)
        )
        self._detail_total_stat.value_label.setText(
            format_currency(summary.revenue_total)
        )
        self._detail_income_stat.value_label.setText(
            format_currency(summary.income_total)
        )

    def _session_sales_loaded(self, page: SalesPage) -> None:
        self._sales_loading = False
        self._sale_model.removeRows(0, self._sale_model.rowCount())
        for row in page.items:
            item = QStandardItem(self._format_timestamp(row.created_at))
            item.setData(row.id, Qt.ItemDataRole.UserRole)
            self._sale_table.append_row(
                [
                    item,
                    row.terminal_id,
                    _sale_status_label(row.status),
                    "Պարտքով" if row.credit_amount is not None else "Կանխիկ",
                    row.credit_customer_name or "—",
                    format_currency(row.total),
                ]
            )

    def _open_sale_detail(self) -> None:
        row = self._sale_table.selected_row()
        item = None if row < 0 else self._sale_model.item(row, 0)
        sale_id = None if item is None else item.data(Qt.ItemDataRole.UserRole)
        service = self._sales_history_service
        if isinstance(sale_id, uuid.UUID) and service is not None:
            self._sale_detail_generation += 1
            generation = self._sale_detail_generation
            self._selected_sale_id = sale_id
            self._sale_history_loading = False
            self._sale_history_loaded = False
            self._sale_detail_stack.setCurrentIndex(0)
            self._sale_detail_tabs.set_active(0)
            self._sale_timeline.clear_rows()
            self._sale_changes.clear_rows()
            self._sale_activity_status.setText(
                "Ընտրեք «Վաճառքի ընթացք» բաժինը՝ պատմությունը դիտելու համար։"
            )
            self._sale_changes_status.setText(
                "Ընտրեք «Ապրանքների փոփոխություններ» բաժինը՝ գրառումները դիտելու համար։"
            )
            run_in_background(
                self,
                lambda: service.get_sale_detail(sale_id, include_history=False),
                lambda detail: self._sale_detail_loaded(generation, detail),
                self._on_load_failed,
            )

    def _sale_detail_loaded(self, generation: int, detail: SaleDetail) -> None:
        if generation != self._sale_detail_generation:
            return
        self._sale_items.clear_rows()
        for item in detail.items:
            cost_price = item.cost_price or Decimal("0")
            item_income = (item.unit_price - cost_price) * item.quantity
            self._sale_items.append_row(
                [
                    item.product_name,
                    item.product_sku,
                    item.unit,
                    format_quantity(item.quantity),
                    format_currency(cost_price),
                    format_currency(item.unit_price),
                    (
                        format_currency(item.discount_amount)
                        if item.discount_amount
                        else ""
                    ),
                    format_currency(item_income),
                    format_currency(item.line_total),
                ]
            )
        self._sale_detail_stack.setCurrentIndex(0)

    def _load_sale_history(self) -> None:
        service = self._sales_history_service
        sale_id = self._selected_sale_id
        if (
            service is None
            or sale_id is None
            or self._sale_history_loading
            or self._sale_history_loaded
        ):
            return
        generation = self._sale_detail_generation
        self._sale_history_loading = True
        self._sale_activity_status.setText("Վաճառքի ընթացքը բեռնվում է…")
        self._sale_changes_status.setText("Փոփոխությունների պատմությունը բեռնվում է…")
        run_in_background(
            self,
            lambda: service.get_sale_history(sale_id),
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
        if generation != self._sale_detail_generation:
            return
        self._sale_history_loading = False
        self._sale_history_loaded = True
        revisions, changes, audit_events = history
        timeline = sale_timeline_rows(revisions, audit_events)
        self._sale_timeline.clear_rows()
        for happened_at, action, details, actor in timeline:
            self._sale_timeline.append_row(
                [self._format_timestamp(happened_at), action, details, actor]
            )
        self._sale_activity_status.setText(
            "Վաճառքի ստեղծման, բացման, պահպանման և չեղարկման ժամանակագրություն։"
            if timeline
            else "Այս վաճառքի համար ընթացքի տվյալներ չկան։"
        )
        self._sale_changes.clear_rows()
        for change in changes:
            self._sale_changes.append_row(
                [
                    self._format_timestamp(change.created_at),
                    item_action_label(change.action),
                    change.product_name,
                    item_data_text(change.old_data),
                    item_data_text(change.new_data),
                    change.user_full_name,
                ]
            )
        self._sale_changes_status.setText(
            f"Փոփոխությունների գրառում՝ {len(changes)}"
            if changes
            else "Ապրանքների փոփոխություններ չեն գրանցվել։"
        )

    def _sale_history_failed(self, generation: int, error: Exception) -> None:
        if generation != self._sale_detail_generation:
            return
        self._sale_history_loading = False
        self._sale_activity_status.setText("Վաճառքի ընթացքը չհաջողվեց բեռնել։")
        self._sale_changes_status.setText(
            "Փոփոխությունների պատմությունը չհաջողվեց բեռնել։"
        )
        self._on_load_failed(error)

    def _show_overview(self) -> None:
        self._stack.setCurrentWidget(self._overview)

    @staticmethod
    def _local_date(value: datetime) -> date:
        return value.astimezone(ARMENIA_TIMEZONE).date()

    def _on_load_failed(self, error: Exception) -> None:
        self._sales_loading = False
        logger.exception("pos_sessions_window op=load outcome=failed")

    @staticmethod
    def _format_timestamp(value: datetime | None) -> str:
        if value is None:
            return ""
        return value.astimezone(ARMENIA_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _format_duration(started_at: datetime, closed_at: datetime | None) -> str:
        end = closed_at or datetime.now(ARMENIA_TIMEZONE)
        elapsed = end - started_at
        total_seconds = max(0, int(elapsed.total_seconds()))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._poll_timer.stop()
        wait_for_pending_threads(self)
        super().closeEvent(event)
