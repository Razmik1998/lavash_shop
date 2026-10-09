"""Online Selling screen (spec task 9: Django <-> Desktop Admin).

Pending Orders / History tabs, an order detail view (customer info, full
item table, financial breakdown), Confirm/Reject actions with a
reject-reason capture dialog, and a new-order notification banner --
per `.claude/specs/9/input/task-9-online-selling.md` §4-6, §16 and
`.claude/specs/9/admin-architecture.md`.

Built exclusively from `ui/components/` per `.claude/rules/ui-components.md`
-- no raw `QPushButton`/`QTableView`/`QLineEdit`/`QMessageBox`/
`setObjectName`/`setStyleSheet` here. New components added for this
screen: `ui.components.layouts.TabBar` (+ `buttons.TabButton`),
`ui.components.inputs.TextArea`, `ui.components.feedback.prompt_text`,
`ui.components.panels.NotificationBanner`.

**Interface this screen is coded against** (both are currently stubs --
see their module docstrings for the full contract; `implementer` fills
in the bodies without changing these signatures):

  - `services.online_orders.OnlineOrderService`:
    `list_pending_orders(cursor)`, `list_history(cursor)`,
    `get_order_detail(id)`, `confirm_order(id)`, `reject_order(id, reason)`,
    `retry_conversion(id)`.
  - `services.sync.SyncService` Qt signals (all `Signal(object)`):
    `new_online_order` (payload: `OnlineOrderRow`), `order_confirmed`
    (payload: `uuid.UUID`), `order_rejected` (payload: `uuid.UUID`),
    `connection_changed` (payload: `bool`), `synchronization_completed`
    (payload: `int`, unused by this screen today but connectable later).

This screen never imports sockets/SQL/repositories -- only the two
services above, matching `SalesHistoryWindow`'s pattern
(`ui/sales_history_window.py`) of a list/detail `QStackedWidget` pair
backed by `run_in_background`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from models import OnlineOrderBusinessStatus, OnlineOrderConversionStatus
from schemas.online_orders import OnlineOrderDetail, OnlineOrderRow, OnlineOrdersPage
from ui.components import (
    AcceptButton,
    CancelButton,
    DataTable,
    EditButton,
    GhostButton,
    NotificationBanner,
    PageTitle,
    Panel,
    RefreshButton,
    StatCard,
    StatusBadge,
    TabBar,
    prompt_text,
    report_error,
)
from ui.style import configure_page_layout, format_currency, format_quantity
from ui.workers import run_in_background, wait_for_pending_threads

if TYPE_CHECKING:
    from services import OnlineOrderService
    from services.sync import SyncService

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")
logger = logging.getLogger(__name__)

_PENDING_TAB = 0
_HISTORY_TAB = 1


class OnlineSellingWindow(QWidget):
    def __init__(
        self,
        service: OnlineOrderService,
        sync_service: SyncService | None = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._sync_service = sync_service
        self._pending_cursor: str | None = None
        self._history_cursor: str | None = None
        self._pending_loading = False
        self._history_loading = False
        self._detail_id: uuid.UUID | None = None

        self._banner = NotificationBanner()
        self._stack = QStackedWidget()
        self._list_page = self._build_list_page()
        self._detail_page = self._build_detail_page()
        self._stack.addWidget(self._list_page)
        self._stack.addWidget(self._detail_page)

        layout = QVBoxLayout()
        configure_page_layout(layout)
        layout.addWidget(self._banner)
        layout.addWidget(self._stack, 1)
        self.setLayout(layout)

        if sync_service is not None:
            sync_service.new_online_order.connect(self._on_new_online_order)
            sync_service.order_confirmed.connect(self._on_order_changed)
            sync_service.order_rejected.connect(self._on_order_changed)
            sync_service.connection_changed.connect(self._on_connection_changed)
            self._on_connection_changed(sync_service.is_connected)

        self._reload_pending()
        self._reload_history()

    # -- construction -------------------------------------------------------

    def _build_list_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(PageTitle("Օնլայն վաճառք"))

        header = QHBoxLayout()
        self._tabs = TabBar(
            ["Սպասող պատվերներ", "Պատմություն"], on_change=self._on_tab_changed
        )
        header.addWidget(self._tabs)
        header.addStretch()
        self._connection_badge = StatusBadge("Կապը հաստատված չէ", tone="warning")
        header.addWidget(self._connection_badge)
        header.addWidget(RefreshButton(on_click=self._reload_active_tab))
        layout.addLayout(header)

        self._pending_count = StatCard("Սպասող պատվերներ", "0")
        layout.addWidget(self._pending_count)

        self._tables_stack = QStackedWidget()
        self._pending_table = DataTable(
            ["Համար", "Հաճախորդ", "Ընդհանուր", "Ամսաթիվ"],
            on_double_click=self._open_pending_detail,
        )
        self._history_table = DataTable(
            ["Համար", "Հաճախորդ", "Ընդհանուր", "Կարգավիճակ", "Տերմինալ", "Ամսաթիվ"],
            on_double_click=self._open_history_detail,
        )
        self._tables_stack.addWidget(self._pending_table)
        self._tables_stack.addWidget(self._history_table)
        layout.addWidget(self._tables_stack, 1)
        return page

    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        header.addWidget(GhostButton("← Վերադառնալ", on_click=self._show_list))
        self._detail_title = PageTitle("Պատվերի մանրամասներ")
        header.addWidget(self._detail_title)
        header.addStretch()
        layout.addLayout(header)

        info_panel = Panel()
        info_layout = QVBoxLayout(info_panel)
        self._detail_customer = QLabel()
        self._detail_customer.setWordWrap(True)
        self._detail_status = StatusBadge("")
        info_layout.addWidget(self._detail_customer)
        info_layout.addWidget(self._detail_status)
        layout.addWidget(info_panel)

        stats = QHBoxLayout()
        self._detail_subtotal = StatCard("Ենթագումար", "0 ֏")
        self._detail_delivery = StatCard("Առաքման վճար", "0 ֏")
        self._detail_discount = StatCard("Զեղչ", "0 ֏")
        self._detail_total = StatCard("Ընդհանուր", "0 ֏", tone="success")
        for card in (
            self._detail_subtotal,
            self._detail_delivery,
            self._detail_discount,
            self._detail_total,
        ):
            stats.addWidget(card)
        layout.addLayout(stats)

        self._detail_items = DataTable(
            ["Ապրանք", "Միավոր", "Քանակ", "Գին", "Ընդհանուր"]
        )
        layout.addWidget(self._detail_items, 1)

        self._detail_error = QLabel()
        self._detail_error.setWordWrap(True)
        layout.addWidget(self._detail_error)

        actions = QHBoxLayout()
        actions.addStretch()
        self._retry_button = EditButton(
            "Կրկնել փոխարկումը", on_click=self._retry_current
        )
        self._reject_button = CancelButton("Մերժել", on_click=self._reject_current)
        self._confirm_button = AcceptButton(on_click=self._confirm_current)
        actions.addWidget(self._retry_button)
        actions.addWidget(self._reject_button)
        actions.addWidget(self._confirm_button)
        layout.addLayout(actions)
        return page

    # -- list loading ---------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        self._tables_stack.setCurrentIndex(index)

    def _reload_active_tab(self) -> None:
        if self._tables_stack.currentIndex() == _PENDING_TAB:
            self._reload_pending()
        else:
            self._reload_history()

    def _reload_pending(self) -> None:
        self._pending_cursor = None
        self._pending_loading = False
        self._pending_table.clear_rows()
        self._load_pending_page()

    def _load_pending_page(self) -> None:
        if self._pending_loading:
            return
        self._pending_loading = True
        run_in_background(
            self,
            lambda: self._service.list_pending_orders(self._pending_cursor),
            self._pending_page_loaded,
            self._failed,
        )

    def _pending_page_loaded(self, page: OnlineOrdersPage) -> None:
        self._pending_loading = False
        for row in page.items:
            self._append_pending_row(row)
        self._pending_count.value_label.setText(str(self._pending_table.row_count()))
        self._pending_cursor = page.next_cursor
        if self._pending_cursor is not None:
            self._load_pending_page()

    def _append_pending_row(self, row: OnlineOrderRow) -> None:
        item = QStandardItem(self._format_timestamp(row.order_date))
        item.setData(row.id, Qt.ItemDataRole.UserRole)
        self._pending_table.append_row(
            [row.order_number, row.customer_name, format_currency(row.total), item]
        )

    def _reload_history(self) -> None:
        self._history_cursor = None
        self._history_loading = False
        self._history_table.clear_rows()
        self._load_history_page()

    def _load_history_page(self) -> None:
        if self._history_loading:
            return
        self._history_loading = True
        run_in_background(
            self,
            lambda: self._service.list_history(self._history_cursor),
            self._history_page_loaded,
            self._failed,
        )

    def _history_page_loaded(self, page: OnlineOrdersPage) -> None:
        self._history_loading = False
        for row in page.items:
            self._append_history_row(row)
        self._history_cursor = page.next_cursor
        if self._history_cursor is not None:
            self._load_history_page()

    def _append_history_row(self, row: OnlineOrderRow) -> None:
        item = QStandardItem(self._format_timestamp(row.order_date))
        item.setData(row.id, Qt.ItemDataRole.UserRole)
        terminal = (
            "ONLINE"
            if row.business_status == OnlineOrderBusinessStatus.CONFIRMED
            else "-"
        )
        self._history_table.append_row(
            [
                row.order_number,
                row.customer_name,
                format_currency(row.total),
                _business_status_label(row.business_status),
                terminal,
                item,
            ]
        )

    # -- detail -----------------------------------------------------------

    def _open_pending_detail(self) -> None:
        self._open_detail(self._pending_table)

    def _open_history_detail(self) -> None:
        self._open_detail(self._history_table)

    def _open_detail(self, table: DataTable) -> None:
        row = table.selected_row()
        if row < 0:
            return
        last_column = table.item_model.columnCount() - 1
        cell = table.item_model.item(row, last_column)
        order_id = None if cell is None else cell.data(Qt.ItemDataRole.UserRole)
        if isinstance(order_id, uuid.UUID):
            run_in_background(
                self,
                lambda: self._service.get_order_detail(order_id),
                self._detail_loaded,
                self._failed,
            )

    def _detail_loaded(self, detail: OnlineOrderDetail) -> None:
        self._detail_id = detail.id
        self._detail_title.setText(f"Պատվեր {detail.order_number}")
        self._detail_customer.setText(
            f"Հաճախորդ՝ {detail.customer_name}    Հեռախոս՝ {detail.customer_phone}\n"
            f"Հասցե՝ {detail.customer_address}    "
            f"Ամսաթիվ՝ {self._format_timestamp(detail.order_date)}"
        )
        self._detail_status.set_status(
            _business_status_label(detail.business_status),
            tone=_business_status_tone(detail.business_status),
        )
        self._detail_subtotal.value_label.setText(format_currency(detail.subtotal))
        self._detail_delivery.value_label.setText(format_currency(detail.delivery_fee))
        self._detail_discount.value_label.setText(format_currency(detail.discount))
        self._detail_total.value_label.setText(format_currency(detail.total))
        self._detail_items.clear_rows()
        for line in detail.items:
            self._detail_items.append_row(
                [
                    line.product_name,
                    line.unit,
                    format_quantity(line.quantity),
                    format_currency(line.unit_price),
                    format_currency(line.subtotal),
                ]
            )
        if detail.conversion_status == OnlineOrderConversionStatus.FAILED:
            self._detail_error.setText(
                f"Փոխարկումը ձախողվել է՝ {detail.conversion_error or ''}"
            )
        elif detail.rejection_reason:
            self._detail_error.setText(f"Մերժման պատճառ՝ {detail.rejection_reason}")
        else:
            self._detail_error.setText("")

        pending = detail.business_status == OnlineOrderBusinessStatus.PENDING
        failed = detail.conversion_status == OnlineOrderConversionStatus.FAILED
        self._confirm_button.setVisible(pending)
        self._reject_button.setVisible(pending)
        self._retry_button.setVisible(failed)
        self._stack.setCurrentWidget(self._detail_page)

    def _show_list(self) -> None:
        self._stack.setCurrentWidget(self._list_page)

    # -- actions ------------------------------------------------------------

    def _confirm_current(self) -> None:
        if self._detail_id is None:
            return
        order_id = self._detail_id
        self._set_actions_enabled(False)
        run_in_background(
            self,
            lambda: self._service.confirm_order(order_id),
            self._action_succeeded,
            self._action_failed,
        )

    def _reject_current(self) -> None:
        if self._detail_id is None:
            return
        reason = prompt_text(
            self,
            "Մերժման պատճառ",
            "Նշեք պատվերի մերժման պատճառը։",
            confirm_text="Մերժել",
            confirm_variant="danger",
        )
        if not reason:
            return
        order_id = self._detail_id
        self._set_actions_enabled(False)
        run_in_background(
            self,
            lambda: self._service.reject_order(order_id, reason),
            self._action_succeeded,
            self._action_failed,
        )

    def _retry_current(self) -> None:
        if self._detail_id is None:
            return
        order_id = self._detail_id
        self._set_actions_enabled(False)
        run_in_background(
            self,
            lambda: self._service.retry_conversion(order_id),
            self._action_succeeded,
            self._action_failed,
        )

    def _set_actions_enabled(self, enabled: bool) -> None:
        self._confirm_button.setEnabled(enabled)
        self._reject_button.setEnabled(enabled)
        self._retry_button.setEnabled(enabled)

    def _action_succeeded(self, detail: OnlineOrderDetail) -> None:
        self._set_actions_enabled(True)
        self._detail_loaded(detail)
        self._reload_pending()
        self._reload_history()

    def _action_failed(self, error: Exception) -> None:
        self._set_actions_enabled(True)
        logger.error(
            "online_selling_window op=order_action outcome=failed error=%s", error
        )
        report_error(self, "Գործողությունը հնարավոր չէ կատարել։")

    # -- SyncService signal handlers ----------------------------------------

    def _on_new_online_order(self, row: object) -> None:
        if not isinstance(row, OnlineOrderRow):
            logger.warning(
                "online_selling_window op=new_online_order outcome=unexpected_payload"
            )
            return
        self._banner.show_message(
            f"Նոր պատվեր ստացվեց՝ {row.order_number} ({row.customer_name})"
        )
        self._append_pending_row(row)
        self._pending_count.value_label.setText(str(self._pending_table.row_count()))

    def _on_order_changed(self, online_order_id: object) -> None:
        self._reload_pending()
        self._reload_history()
        if (
            isinstance(online_order_id, uuid.UUID)
            and self._detail_id == online_order_id
        ):
            run_in_background(
                self,
                lambda: self._service.get_order_detail(online_order_id),
                self._detail_loaded,
                self._failed,
            )

    def _on_connection_changed(self, connected: object) -> None:
        if connected:
            self._connection_badge.set_status("Կապակցված է", tone="success")
        else:
            self._connection_badge.set_status("Կապը հաստատված չէ", tone="warning")

    # -- shared helpers -------------------------------------------------

    @staticmethod
    def _format_timestamp(value: datetime) -> str:
        return value.astimezone(ARMENIA_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    def _failed(self, error: Exception) -> None:
        logger.error("online_selling_window op=load outcome=failed error=%s", error)
        report_error(self, "Տվյալները հնարավոր չէ բեռնել։")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)


def _business_status_label(status: OnlineOrderBusinessStatus) -> str:
    return {
        OnlineOrderBusinessStatus.PENDING: "Սպասող",
        OnlineOrderBusinessStatus.CONFIRMED: "Հաստատված",
        OnlineOrderBusinessStatus.REJECTED: "Մերժված",
    }[status]


def _business_status_tone(status: OnlineOrderBusinessStatus) -> str:
    return {
        OnlineOrderBusinessStatus.PENDING: "warning",
        OnlineOrderBusinessStatus.CONFIRMED: "success",
        OnlineOrderBusinessStatus.REJECTED: "danger",
    }[status]
