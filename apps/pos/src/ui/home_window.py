"""POS home screen and session-scoped selling/history views."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from exceptions import AdminUnavailableError, AuthenticationError
from models import User
from networking.protocol import (
    CustomerPayload,
    ProductPayload,
    SalePayload,
    SessionPayload,
)
from printing import CloseoutReport, ThermalPrinterService
from services import CustomerService, ProductService, SaleService
from ui.checkout_window import CheckoutWindow
from ui.components.cash_withdrawal_dialog import CashWithdrawalDialog
from ui.components.closeout_report_dialog import CloseoutReportDialog
from ui.components.icons import pos_icon
from ui.components import (
    ActionBar,
    CancelButton,
    CreditCustomerDialog,
    EditButton,
    IconLabel,
    Panel,
    PrimaryButton,
    QuitButton,
    RefreshButton,
    SaleEditDialog,
    SaveButton,
    SecondaryButton,
    SimpleTable,
    UnlockKeyDialog,
    choose_unsaved_action,
    confirm,
    prompt_text,
    report_error,
    warn,
)
from ui.session_status import (
    HEARTBEAT_INTERVAL_MS,
    PosSessionService,
    connection_status_label,
    session_status_label,
)
from ui.style import (
    configure_page_layout,
    format_currency,
    format_quantity,
)
from ui.workers import run_in_background, wait_for_pending_threads

logger = logging.getLogger(__name__)

_ADMIN_UNAVAILABLE_MESSAGE = "Ադմինիստրատոր հասանելի չէ։"
_CLOSE_SESSION_CONFIRM_TITLE = "Հաստատում"
_CLOSE_SESSION_CONFIRM_TEXT = "Ավարտե՞լ աշխատանքային սեսիան։"
_CASH_DIFFERENCE_CONFIRM_TITLE = "Դրամարկղի տարբերություն"


class HomeWindow(QWidget):
    """`session_closed` fires once the session has actually been
    closed on the backend; the caller (main.py) decides what screen to
    show next (session page or login), not this widget."""

    session_closed = Signal()

    def __init__(
        self,
        employee: User,
        session_service: PosSessionService,
        session: SessionPayload,
        product_service: ProductService | None = None,
        sale_service: SaleService | None = None,
        customer_service: CustomerService | None = None,
        printer_service: ThermalPrinterService | None = None,
        opening_cash: Decimal | None = None,
        reconnect_admin: Callable[[], object] | None = None,
    ) -> None:
        super().__init__()
        self._session_service = session_service
        self._employee_name = employee.full_name
        self._session_id = session.id
        self._terminal_id = session.terminal_id
        self._reconnect_admin = reconnect_admin
        self._printer_service = printer_service
        self._product_service = product_service
        self._sale_service = sale_service
        self._customer_service = customer_service
        self._checkout_window: CheckoutWindow | None = None
        self._opening_cash = opening_cash or Decimal("0")
        self._closed_at = ""
        self._withdrawals = []
        self._withdrawals_total = Decimal("0")
        self._closing_cash: Decimal | None = None
        self._closeout_sales_total: tuple[Decimal, Decimal] | None = None
        self._closeout_repayments_total = Decimal("0")
        self._is_session_closed = False
        self._connection_lost_dialog: QMessageBox | None = None
        self._heartbeat_in_flight = False
        self.setWindowTitle("POS")
        self.setObjectName("homePage")

        welcome_label = IconLabel(
            "✦", f"Բարի գալուստ, {employee.full_name}", "screenTitle"
        )
        welcome_label.setObjectName("welcome_label")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        sell_button = PrimaryButton(
            "Նոր վաճառք",
            on_click=self._open_checkout,
            tooltip="Սկսել նոր վաճառք",
        )

        # Header/status area: session state and connection state are
        # two independent axes (task-4 spec section 3) and must never
        # be combined into a single string/label.
        self._session_status_label = QLabel()
        self._session_status_label.setObjectName("status_text_white")
        self._connection_status_label = QLabel()
        self._connection_status_label.setObjectName("status_text_white")
        self._retry_button = SecondaryButton(
            "Կրկին միանալ", on_click=self._retry_connection
        )
        self._retry_button.setVisible(False)
        self._close_button = CancelButton(
            "Ավարտել աշխատանքը",
            icon=pos_icon("close"), on_click=self._handle_close_session
        )
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(10_000)
        self._retry_timer.timeout.connect(self._retry_connection)
        self._update_status_labels(session)

        self._sale_nav_button = SecondaryButton(
            "Ընթացիկ վաճառք", icon=pos_icon("cart"), on_click=self._open_checkout
        )
        self._history_nav_button = SecondaryButton(
            "Վաճառքների պատմություն",
            icon=pos_icon("history"), on_click=self._show_history
        )
        navigation = ActionBar(
            [
                self._sale_nav_button,
                self._history_nav_button,
                SecondaryButton(
                    "Պարտքով հաճախորդներ",
                    icon=pos_icon("customers"), on_click=self._show_credit_customers
                ),
            ]
        )

        header_panel = Panel()
        header_panel.setObjectName("top_header")
        header_container = QVBoxLayout(header_panel)
        header_container.setContentsMargins(10, 5, 10, 5)
        header_container.setSpacing(3)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)
        header_container.addLayout(header_layout)
        header_layout.addWidget(self._session_status_label)
        header_layout.addWidget(self._connection_status_label)
        header_layout.addWidget(self._retry_button)
        header_layout.addSpacing(12)
        header_layout.addWidget(welcome_label)
        header_layout.addSpacing(12)
        header_layout.addStretch()
        navigation_row = QHBoxLayout()
        navigation_row.addWidget(navigation)
        navigation_row.addStretch()
        header_container.addLayout(navigation_row)
        withdrawal_button = SecondaryButton(
            "Գումար վերցնել", icon=pos_icon("cash"), on_click=self._withdraw_cash
        )
        navigation_row.addWidget(withdrawal_button)
        navigation_row.addWidget(self._close_button)
        navigation_row.addWidget(QuitButton(on_click=self._quit_app))
        header_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        for button in header_panel.findChildren(QPushButton):
            button.setMinimumHeight(28)
            button.setMaximumHeight(28)
            button.setIconSize(QSize(16, 16))

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(header_panel)
        self._content = QStackedWidget()
        if product_service is not None and sale_service is not None:
            self._checkout_window = CheckoutWindow(
                product_service,
                sale_service,
                self._session_id,
                self._terminal_id,
                printer_service,
                customer_service,
            )
            self._content.addWidget(self._checkout_window)
        else:
            self._content.addWidget(sell_button)
        self._history = _SalesHistoryView(
            sale_service, product_service, customer_service, self._session_id
        )
        self._content.addWidget(self._history)
        layout.addWidget(self._content, 1)
        self._content.currentChanged.connect(self._update_navigation)
        self._update_navigation(self._content.currentIndex())
        self.setLayout(layout)

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(HEARTBEAT_INTERVAL_MS)
        self._heartbeat_timer.timeout.connect(self._send_heartbeat)
        self._heartbeat_timer.start()
        self._send_heartbeat()

    def _update_status_labels(self, session: SessionPayload) -> None:
        self._session_status_label.setText(
            f"Սեսիա։ {session_status_label(session.status)}"
        )
        self._connection_status_label.setText(
            f"Կապ։ {connection_status_label(session.connection_status)}"
        )

    def _update_navigation(self, index: int) -> None:
        for page, button in (
            (0, self._sale_nav_button),
            (1, self._history_nav_button),
        ):
            is_current = index == page
            button.setProperty("current", is_current)
            button.setEnabled(not is_current)
            button.style().unpolish(button)
            button.style().polish(button)

    def _show_credit_customers(self) -> None:
        if self._customer_service is None:
            return
        run_in_background(
            self,
            lambda: self._customer_service.search_customers(""),
            self._open_credit_customers_dialog,
            lambda _error: report_error(
                self, "Չհաջողվեց բեռնել պարտքով հաճախորդներին։"
            ),
        )

    def _open_credit_customers_dialog(self, customers: list[CustomerPayload]) -> None:
        dialog = CreditCustomerDialog(
            customers, self._customer_service, self, self._session_id
        )
        dialog.payment_recorded.connect(self._on_repayment_recorded)
        dialog.exec()

    def _on_repayment_recorded(self, amount: object) -> None:
        self._closeout_repayments_total += Decimal(str(amount))

    def _send_heartbeat(self) -> None:
        if self._heartbeat_in_flight:
            return
        self._heartbeat_in_flight = True
        run_in_background(
            self,
            lambda: self._session_service.heartbeat(self._session_id),
            self._on_heartbeat_succeeded,
            self._on_heartbeat_failed,
        )

    def _on_heartbeat_succeeded(self, session: SessionPayload) -> None:
        self._heartbeat_in_flight = False
        self._close_connection_lost_dialog()
        self._retry_timer.stop()
        self._retry_button.setEnabled(True)
        self._retry_button.setVisible(False)
        self._update_status_labels(session)

    def _on_heartbeat_failed(self, error: Exception) -> None:
        self._heartbeat_in_flight = False
        if isinstance(error, (AdminUnavailableError, AuthenticationError)):
            # Network/auth failure: flip the connection indicator locally
            # without touching session state; the user can retry once the
            # admin is reachable again and the token has been refreshed.
            self._connection_status_label.setText(
                f"Կապ։ {connection_status_label('disconnected')}"
            )
            self._retry_button.setEnabled(True)
            self._retry_button.setVisible(True)
            self._retry_timer.start()
            self._show_connection_lost_dialog()
        else:
            # SessionNotFoundError/SessionClosedError: the backend no
            # longer considers this session usable. Never swallow
            # silently - log it; the user will discover this on their
            # next action (e.g. a future selling-screen call) rather
            # than via a disruptive popup on a background timer tick.
            logger.warning("home_window op=heartbeat outcome=%s", type(error).__name__)

    def _retry_connection(self) -> None:
        if self._heartbeat_in_flight:
            return
        self._retry_timer.stop()
        self._retry_button.setEnabled(False)
        self._heartbeat_in_flight = True
        run_in_background(
            self,
            self._retry_heartbeat,
            self._on_heartbeat_succeeded,
            self._on_heartbeat_failed,
        )

    def _retry_heartbeat(self) -> SessionPayload:
        if self._reconnect_admin is not None:
            self._reconnect_admin()
        return self._session_service.heartbeat(self._session_id)

    def _show_connection_lost_dialog(self) -> None:
        if getattr(self, "_connection_lost_dialog", None) is not None:
            return
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Կապի խափանում")
        dialog.setText("Կապը ադմինիստրատորի հետ ընդհատված է։")
        retry_button = dialog.addButton(
            "Կրկին միանալ", QMessageBox.ButtonRole.AcceptRole
        )
        quit_button = dialog.addButton(
            "Փակել ծրագիրը", QMessageBox.ButtonRole.RejectRole
        )
        dialog.setModal(True)
        dialog.finished.connect(lambda _result: self._clear_connection_lost_dialog())
        retry_button.clicked.connect(self._retry_connection)
        quit_button.clicked.connect(self._quit_application)
        self._connection_lost_dialog = dialog
        dialog.open()

    def _quit_application(self) -> None:
        QApplication.quit()

    def _clear_connection_lost_dialog(self) -> None:
        self._connection_lost_dialog = None

    def _close_connection_lost_dialog(self) -> None:
        dialog = getattr(self, "_connection_lost_dialog", None)
        if dialog is not None:
            dialog.close()
            self._connection_lost_dialog = None

    def _withdraw_cash(self):
        run_in_background(
            self,
            lambda: self._session_service.cash_request("list_cash_recipients")[
                "recipients"
            ],
            self._choose_cash_recipient,
            lambda error: report_error(self, str(error)),
        )

    def _choose_cash_recipient(self, recipients):
        import uuid

        if not recipients:
            report_error(self, "Գումար վերցնող ակտիվ անձ չկա։ Դիմեք ադմինիստրատորին։")
            return
        dialog = CashWithdrawalDialog(recipients, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        recipient_id, value, reason = dialog.values()
        fields = dict(
            withdrawal_id=str(uuid.uuid4()),
            session_id=self._session_id,
            recipient_id=recipient_id,
            amount=str(value),
            reason=reason,
        )
        run_in_background(
            self,
            lambda: self._session_service.cash_request(
                "record_cash_withdrawal", **fields
            ),
            lambda _: QMessageBox.information(self, "Գումար վերցնել", "Գրանցված է։"),
            lambda error: report_error(self, str(error)),
        )

    def _prompt_closing_cash(self) -> Decimal | None:
        closing_cash, ok = QInputDialog.getDouble(
            self,
            "Դրամարկղի մնացորդ",
            "Քանի դրամ եք թողնելու դրամարկղում վերջում։",
            float(self._opening_cash),
            0.0,
            1_000_000_000.0,
            2,
        )
        if not ok:
            return None
        return Decimal(str(closing_cash))

    def _load_session_sales_total(self) -> tuple[Decimal, Decimal]:
        cash_total = Decimal("0")
        credit_total = Decimal("0")
        if self._sale_service is None:
            return cash_total, credit_total
        try:
            sales = self._sale_service.list_session_sales(self._session_id)
        except Exception:
            return cash_total, credit_total
        for sale in sales:
            if str(sale.status).lower() != "completed":
                continue
            try:
                amount = Decimal(str(sale.total))
                if sale.credit_customer_id:
                    credit_total += amount
                else:
                    cash_total += amount
            except Exception:
                continue
        return cash_total, credit_total

    def _show_closeout_report(
        self, sales_totals: tuple[Decimal, Decimal] | None = None
    ) -> None:
        cash_total, credit_total = sales_totals or (Decimal("0"), Decimal("0"))
        dialog = CloseoutReportDialog(
            opening_cash=self._opening_cash,
            cash_sales=cash_total,
            credit_sales=credit_total,
            repayments=self._closeout_repayments_total,
            withdrawals_total=self._withdrawals_total,
            closing_cash=self._closing_cash or Decimal("0"),
            withdrawals=self._withdrawals,
            parent=self,
        )
        dialog.exec()

    def _handle_close_session(self) -> None:
        if not confirm(self, _CLOSE_SESSION_CONFIRM_TITLE, _CLOSE_SESSION_CONFIRM_TEXT):
            return

        try:
            self._withdrawals = self._session_service.cash_request(
                "list_cash_withdrawals", session_id=self._session_id
            )["withdrawals"]
            self._withdrawals_total = sum(
                (Decimal(r["amount"]) for r in self._withdrawals), Decimal("0")
            )
        except Exception as error:
            report_error(self, str(error))
            return
        self._closeout_sales_total = self._load_session_sales_total()
        cash_total, _credit_total = self._closeout_sales_total
        handover_total = (
            cash_total + self._closeout_repayments_total - self._withdrawals_total
        )
        expected_cash = self._opening_cash + handover_total
        closing_cash = self._prompt_closing_cash()
        if closing_cash is None:
            return
        if closing_cash != expected_cash and not confirm(
            self,
            _CASH_DIFFERENCE_CONFIRM_TITLE,
            (
                f"Ակնկալվող դրամարկղը {format_currency(expected_cash)} է, "
                f"իսկ դուք մուտքագրել եք {format_currency(closing_cash)}։\n\n"
                "Համոզվա՞ծ եք, որ ցանկանում եք թողնել այս գումարը։"
            ),
        ):
            return
        self._closing_cash = closing_cash

        self._close_button.setEnabled(False)
        run_in_background(
            self,
            lambda: self._session_service.close_session(
                self._session_id, self._closing_cash
            ),
            self._on_session_closed,
            self._on_close_session_failed,
        )

    def _on_session_closed(self, session: SessionPayload) -> None:
        self._closed_at = session.closed_at or ""
        self._is_session_closed = True
        self._stop_heartbeat()
        self._update_status_labels(session)
        if self._closing_cash is not None:
            from ui.session_window import save_last_cash_balance

            save_last_cash_balance(self._terminal_id, self._closing_cash)
            self._show_closeout_report(self._closeout_sales_total)
            self._print_closeout_report(self._closeout_sales_total)
        self.session_closed.emit()

    def _print_closeout_report(
        self, sales_totals: tuple[Decimal, Decimal] | None
    ) -> None:
        printer = self._printer_service
        if printer is None or not printer.enabled or self._closing_cash is None:
            return
        cash_sales, credit_sales = sales_totals or (Decimal("0"), Decimal("0"))
        handover_total = (
            cash_sales + self._closeout_repayments_total - self._withdrawals_total
        )
        expected_cash = self._opening_cash + handover_total
        closing_cash = self._closing_cash
        report = CloseoutReport(
            session_id=self._session_id,
            terminal_id=self._terminal_id,
            employee_name=self._employee_name,
            closed_at=self._closed_at
            or datetime.now().astimezone().isoformat(timespec="minutes"),
            opening_cash=self._opening_cash,
            cash_sales=cash_sales,
            credit_sales=credit_sales,
            repayments=self._closeout_repayments_total,
            handover_total=handover_total,
            expected_cash=expected_cash,
            closing_cash=closing_cash,
            difference=expected_cash - closing_cash,
            withdrawals=tuple(
                f"{r['taken_at']} | {r['recipient_name']} | "
                f"{r['amount']} AMD | {r['reason']}"
                for r in self._withdrawals
            ),
        )
        try:
            printer.print_closeout_report(report)
        except Exception:
            logger.exception("home_window op=print_closeout outcome=failed")
            report_error(self, "Չհաջողվեց տպել սեսիայի ամփոփագիրը։")

    def _on_close_session_failed(self, error: Exception) -> None:
        self._close_button.setEnabled(True)
        report_error(self, _ADMIN_UNAVAILABLE_MESSAGE)

    def _open_checkout(self) -> None:
        if self._is_session_closed:
            return
        self._content.setCurrentIndex(0)

    def _show_history(self) -> None:
        if self._is_session_closed:
            return
        self._content.setCurrentIndex(1)
        self._history.reload()

    def _quit_app(self) -> None:
        if confirm(self, "Դուրս գալ", "Փակե՞լ հավելվածը։"):
            self.window().close()

    def _stop_heartbeat(self) -> None:
        # Idempotent and safe to call twice (explicit close, then
        # closeEvent) - a leaked running timer would otherwise keep
        # firing heartbeats against a closed/gone session.
        self._heartbeat_timer.stop()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._stop_heartbeat()
        if not self._is_session_closed:
            try:
                self._session_service.disconnect(self._session_id)
            except Exception:
                logger.warning("home_window op=disconnect outcome=failed")
        wait_for_pending_threads(self)
        super().closeEvent(event)


def _payment_text(value: dict[str, object] | None) -> str:
    if not value or value.get("payment") != "credit":
        return "Կանխիկ"
    name = value.get("customer")
    return f"Պարտքով՝ {name}" if name else "Պարտքով"


class _SalesHistoryView(QWidget):
    def __init__(
        self,
        sale_service: SaleService | None,
        product_service: ProductService | None,
        customer_service: CustomerService | None,
        session_id: str,
    ) -> None:
        super().__init__()
        self._sale_service = sale_service
        self._product_service = product_service
        self._customer_service = customer_service
        self._session_id = session_id
        self._sales: list[SalePayload] = []
        self._selected_sale: SalePayload | None = None
        self._selection_to_restore: str | None = None
        self._editor: SaleEditDialog | None = None
        self._page_stack = QStackedWidget()
        self._table = SimpleTable(
            ["ID", "Կարգավիճակ", "Վճարման ձև", "Գումար", "Ամսաթիվ"]
        )
        self._detail = QLabel("Ընտրեք վաճառք՝ մանրամասները տեսնելու համար։")
        self._detail.setWordWrap(True)
        self._unlock_button = EditButton(
            "Բացել խմբագրման համար",
            icon="🔓",
            on_click=self._unlock_selected,
            enabled=False,
            min_height=56,
            tooltip="Բացել ավարտված վաճառքը խմբագրելու համար",
        )
        self._edit_button = EditButton(
            "Խմբագրել վաճառքը",
            icon="✎",
            on_click=self._edit_selected,
            enabled=False,
            min_height=56,
            tooltip="Խմբագրել բացված վաճառքը",
        )
        self._cancel_button = CancelButton(
            "Չեղարկել վաճառքը",
            icon="×",
            on_click=self._cancel_selected,
            enabled=False,
            min_height=56,
            tooltip="Չեղարկել բացված վաճառքը",
        )
        self._save_button = SaveButton(
            "Պահպանել փոփոխությունները",
            icon="💾",
            on_click=self._save_editor,
            enabled=False,
            min_height=56,
            tooltip="Պահպանել բացված վաճառքի փոփոխությունները",
        )
        self._table.itemSelectionChanged.connect(self._show_selected_detail)
        layout = QVBoxLayout()
        layout.addWidget(RefreshButton(on_click=self.reload))
        layout.addWidget(self._table)
        detail_panel = Panel()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(18, 16, 18, 16)
        detail_layout.setSpacing(8)
        detail_layout.addWidget(self._detail)
        layout.addWidget(detail_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        history_page = QWidget()
        history_page.setLayout(layout)
        self._page_stack.addWidget(history_page)

        actions_panel = Panel()
        action_panel_layout = QVBoxLayout(actions_panel)
        action_panel_layout.setContentsMargins(16, 14, 16, 14)
        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addWidget(self._unlock_button, stretch=1)
        actions.addWidget(self._edit_button, stretch=1)
        actions.addWidget(self._cancel_button, stretch=1)
        actions.addWidget(self._save_button, stretch=1)
        action_panel_layout.addLayout(actions)

        outer_layout = QVBoxLayout(self)
        configure_page_layout(outer_layout)
        outer_layout.addWidget(self._page_stack)
        outer_layout.addWidget(actions_panel)

    def reload(self) -> None:
        sale_service = self._sale_service
        if sale_service is None:
            return
        self._selection_to_restore = (
            self._selected_sale.id if self._selected_sale is not None else None
        )
        self._selected_sale = None
        self._set_action_availability()
        self._detail.setText("Ընտրեք վաճառք՝ մանրամասները տեսնելու համար։")
        run_in_background(
            self,
            lambda: sale_service.list_session_sales(self._session_id),
            self._loaded,
            self._failed,
        )

    def _loaded(self, sales: list[SalePayload]) -> None:
        selection_to_restore = self._selection_to_restore
        self._selection_to_restore = None
        self._sales = sales
        self._selected_sale = None
        self._set_action_availability()
        self._detail.setText("Ընտրեք վաճառք՝ մանրամասները տեսնելու համար։")
        self._table.set_rows(
            [
                sale.id,
                sale.status,
                "Պարտքով" if sale.credit_customer_id else "Կանխիկ",
                format_currency(sale.total),
                sale.created_at,
            ]
            for sale in sales
        )
        if selection_to_restore is not None:
            selected_row = next(
                (
                    index
                    for index, sale in enumerate(sales)
                    if sale.id == selection_to_restore
                ),
                -1,
            )
            if selected_row >= 0:
                self._table.selectRow(selected_row)

    def _show_selected_detail(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._sales):
            self._selected_sale = None
            self._set_action_availability()
            self._detail.setText("Ընտրեք վաճառք՝ մանրամասները տեսնելու համար։")
            return
        sale_service = self._sale_service
        if sale_service is None:
            return
        sale = self._sales[row]
        self._selected_sale = None
        self._set_action_availability()
        self._detail.setText("Վաճառքի տվյալները բեռնվում են…")

        def on_detail_loaded(detail: SalePayload) -> None:
            self._detail_loaded_if_selected(sale.id, detail)

        run_in_background(
            self,
            lambda: sale_service.get_sale_detail(self._session_id, sale.id),
            on_detail_loaded,
            self._failed,
        )

    def _detail_loaded_if_selected(self, sale_id: str, sale: SalePayload) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._sales) and self._sales[row].id == sale_id:
            self._detail_loaded(sale)

    def _detail_loaded(self, sale: SalePayload) -> None:
        self._selected_sale = sale
        is_confirmed = sale.status == "completed"
        is_editing = sale.status == "editing"
        self._set_action_availability(
            can_unlock=is_confirmed,
            can_edit=is_editing,
            can_cancel=is_editing,
            can_save=self._editor is not None,
        )
        if is_editing:
            self._unlock_button.setText("✓  Արդեն բացված է")
            self._unlock_button.setToolTip("Այս վաճառքն արդեն բացված է խմբագրման համար")
        else:
            self._unlock_button.setText("🔓  Բացել խմբագրման համար")
            self._unlock_button.setToolTip("Բացել ավարտված վաճառքը խմբագրելու համար")
        payment_type = "Պարտքով" if sale.credit_customer_id else "Կանխիկ"
        line_texts = []
        for item in sale.items:
            discount = (
                format_currency(item.discount_amount)
                if item.discount_amount != "0"
                else "-"
            )
            line_texts.append(
                f"{item.product_name} x {format_quantity(item.quantity)} "
                f"Գին՝ {format_currency(item.unit_price)} Զեղչ՝ {discount} "
                f"= {format_currency(item.line_total)}"
            )
        lines = "; ".join(line_texts)
        changes = [
            event
            for event in sale.audit_events
            if event.event_type == "PAYMENT_TYPE_CHANGED"
        ]
        payment_note = ""
        if changes:
            last = changes[-1]
            before = _payment_text(last.old_value)
            after = _payment_text(last.new_value)
            payment_note = f" (փոխվել է՝ {before} → {after})"
        self._detail.setText(
            f"Վճարման ձև՝ {payment_type}{payment_note}\n"
            f"Ապրանքներ՝ {lines or '-'}"
            + (
                f"\nՉեղարկման պատճառ՝ {sale.cancellation_reason}"
                if sale.cancellation_reason
                else ""
            )
        )

    def _set_action_availability(
        self,
        *,
        can_unlock: bool = False,
        can_edit: bool = False,
        can_cancel: bool = False,
        can_save: bool = False,
    ) -> None:
        self._unlock_button.setEnabled(can_unlock)
        self._edit_button.setEnabled(can_edit)
        self._cancel_button.setEnabled(can_cancel)
        self._save_button.setEnabled(can_save)

    def _unlock_selected(self) -> None:
        if self._selected_sale is None or self._sale_service is None:
            return
        dialog = UnlockKeyDialog(self)
        if dialog.exec() != UnlockKeyDialog.DialogCode.Accepted:
            return
        secret_key = dialog.key()
        if not secret_key:
            warn(self, "Գաղտնի բանալին պարտադիր է։")
            return
        run_in_background(
            self,
            lambda: self._sale_service.unlock_sale(
                self._session_id, self._selected_sale.id, secret_key
            ),
            self._unlock_completed,
            self._failed,
        )

    def _unlock_completed(self, sale: SalePayload) -> None:
        self._detail_loaded(sale)
        if self._product_service is None:
            return
        run_in_background(
            self,
            self._product_service.list_products,
            lambda products: self._open_editor(products, sale),
            self._failed,
        )

    def _edit_selected(self) -> None:
        if (
            self._selected_sale is None
            or self._sale_service is None
            or self._product_service is None
        ):
            return
        run_in_background(
            self,
            self._product_service.list_products,
            lambda products: self._open_editor(products, self._selected_sale),
            self._failed,
        )

    def _open_editor(
        self, products: list[ProductPayload], sale: SalePayload | None
    ) -> None:
        if sale is None or self._sale_service is None:
            return
        editor = SaleEditDialog(
            sale, products, self, customer_service=self._customer_service
        )
        editor.set_save_button_visible(False)
        self._editor = editor
        self._save_button.setEnabled(True)
        editor.back_requested.connect(self._editor_back)
        editor.save_requested.connect(self._save_editor)
        self._page_stack.addWidget(editor)
        self._page_stack.setCurrentWidget(editor)

    def _editor_back(self) -> None:
        if self._editor is None:
            return
        if not self._editor.is_dirty():
            self._leave_editor()
            return
        action = choose_unsaved_action(self)
        if action == "save":
            self._save_editor()
        elif action == "discard":
            self._leave_editor()

    def _save_editor(self) -> None:
        if (
            self._editor is None
            or self._selected_sale is None
            or self._sale_service is None
        ):
            return
        self._save_button.setEnabled(False)
        run_in_background(
            self,
            lambda: self._sale_service.update_sale(
                self._session_id,
                self._selected_sale.id,
                self._editor.items(),
                self._editor.credit_customer_id(),
            ),
            self._editor_saved,
            self._failed,
        )

    def _editor_saved(self, sale: SalePayload) -> None:
        if self._editor is not None:
            self._editor.mark_saved()
        self._detail_loaded(sale)
        self._leave_editor()

    def _leave_editor(self) -> None:
        if self._editor is not None:
            self._page_stack.removeWidget(self._editor)
            self._editor.deleteLater()
            self._editor = None
        self._page_stack.setCurrentIndex(0)
        self.reload()

    def _cancel_selected(self) -> None:
        sale = self._selected_sale
        sale_service = self._sale_service
        if sale is None or sale_service is None:
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
        run_in_background(
            self,
            lambda: sale_service.cancel_sale(self._session_id, sale.id, reason),
            self._detail_loaded,
            self._failed,
        )

    def _failed(self, error: Exception) -> None:
        if self._editor is not None:
            self._save_button.setEnabled(True)
        message = str(error)
        if "invalid_unlock_key" in message:
            message = "Գաղտնի բանալին սխալ է կամ անջատված։"
        elif "sale_not_editable" in message:
            message = "Այս վաճառքը այլևս խմբագրման ենթակա չէ։"
        elif not message:
            message = "Չհաջողվեց բեռնել վաճառքների պատմությունը։"
        report_error(self, message)
