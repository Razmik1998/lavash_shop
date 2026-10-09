"""Post-login POS session page (Armenian UI): shown instead of the
selling screen immediately after login, per
.claude/specs/4/input/task-4-pos-session-lifecycle.md section 1. The
user must explicitly start a working session here before the caller
(main.py) swaps to HomeWindow.

This widget never decides what happens after a session starts — it
only emits `session_started`; wiring that signal to a HomeWindow swap
is main.py's job (implementer), keeping this screen reusable/testable
in isolation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from exceptions import (
    AdminUnavailableError,
    AuthenticationError,
    SessionAlreadyActiveError,
)
from models import User
from networking.protocol import SessionPayload
from ui.components import ErrorLabel, IconLabel, PrimaryButton, SecondaryButton
from ui.session_status import (
    PosSessionService,
    connection_status_label,
    session_status_label,
)
from ui.workers import run_in_background, wait_for_pending_threads

logger = logging.getLogger(__name__)

_ADMIN_UNAVAILABLE_MESSAGE = "Ադմինիստրատոր հասանելի չէ։"
_SESSION_ALREADY_ACTIVE_MESSAGE = (
    "Այս POS-ը արդեն օգտագործվում է այլ տեղից։ Դիմեք ադմինիստրատորին։"
)


def _last_cash_key(terminal_id: str) -> str:
    return f"pos/session/{terminal_id}/last_cash_balance"


def load_last_cash_balance(terminal_id: str) -> Decimal:
    settings = QSettings("FishShop", "POS")
    value = settings.value(_last_cash_key(terminal_id), 0.0)
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def save_last_cash_balance(terminal_id: str, amount: Decimal) -> None:
    settings = QSettings("FishShop", "POS")
    settings.setValue(_last_cash_key(terminal_id), float(amount))


class SessionWindow(QWidget):
    """Shown after login. `session_started` carries the SessionPayload
    for the newly-started (or already-active, if resumed) session."""

    session_started = Signal(object)

    def __init__(
        self,
        session_service: PosSessionService,
        employee: User,
        terminal_id: str,
        reconnect_admin: Callable[[], object] | None = None,
    ) -> None:
        super().__init__()
        self._session_service = session_service
        self._employee = employee
        self._terminal_id = terminal_id
        self._reconnect_admin = reconnect_admin
        self._current_session: SessionPayload | None = None
        self._opening_cash = load_last_cash_balance(terminal_id)

        self.setWindowTitle("POS սեսիա")
        self.setObjectName("sessionPage")

        title = QLabel("POS-ը պատրաստ է աշխատանքի")
        title.setObjectName("idle_title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        terminal_label = IconLabel(
            "▣", f"Տերմինալ։ {terminal_id}", "status_text_white"
        )
        user_label = IconLabel(
            "●", f"Օգտատեր։ {employee.full_name}", "status_text_white"
        )

        self._session_status_label = QLabel()
        self._session_status_label.setObjectName("status_text_white")
        self._session_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._connection_status_label = QLabel()
        self._connection_status_label.setObjectName("status_text_white")
        self._connection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_status_labels("not_started", "disconnected")

        self._error_label = ErrorLabel()
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._retry_button = SecondaryButton(
            "Կրկին միանալ", on_click=self._retry_connection
        )
        self._retry_button.setVisible(False)

        self._start_button = PrimaryButton(
            "Սկսել աշխատանքը", on_click=self._handle_start_session
        )
        self._start_button.setObjectName("start_work_button")
        self._update_start_button_label()

        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(10_000)
        self._retry_timer.timeout.connect(self._retry_connection)
        self._last_retry_call: tuple[str, str, Decimal] | None = None

        header_frame = QFrame()
        header_frame.setObjectName("top_status_bar")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 16)
        header_layout.setSpacing(12)

        terminal_pill = QFrame()
        terminal_pill.setObjectName("status_pill")
        terminal_layout = QHBoxLayout(terminal_pill)
        terminal_layout.setContentsMargins(10, 6, 10, 6)
        terminal_layout.addWidget(terminal_label)

        user_pill = QFrame()
        user_pill.setObjectName("status_pill")
        user_layout = QHBoxLayout(user_pill)
        user_layout.setContentsMargins(10, 6, 10, 6)
        user_layout.addWidget(user_label)

        header_layout.addWidget(terminal_pill)
        header_layout.addWidget(user_pill)
        header_layout.addStretch()

        session_status_row = QFrame()
        session_status_row.setObjectName("info_row")
        session_status_layout = QHBoxLayout(session_status_row)
        session_status_layout.setContentsMargins(14, 10, 14, 10)
        session_status_layout.addWidget(self._session_status_label)

        connection_status_row = QFrame()
        connection_status_row.setObjectName("info_row")
        connection_status_layout = QHBoxLayout(connection_status_row)
        connection_status_layout.setContentsMargins(14, 10, 14, 10)
        connection_status_layout.addWidget(self._connection_status_label)

        central_card = QFrame()
        central_card.setObjectName("idle_central_card")
        central_card.setFixedWidth(540)
        card_layout = QVBoxLayout(central_card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(16)
        card_layout.addWidget(title)
        card_layout.addWidget(session_status_row)
        card_layout.addWidget(connection_status_row)
        card_layout.addWidget(self._error_label)
        card_layout.addWidget(self._retry_button)
        card_layout.addWidget(self._start_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(0)
        layout.addWidget(header_frame)
        layout.addStretch()
        layout.addWidget(central_card, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        self.setLayout(layout)

        self._load_current_session()

    def _set_status_labels(self, session_status: str, connection_status: str) -> None:
        self._session_status_label.setText(
            f"Սեսիայի կարգավիճակ։ {session_status_label(session_status)}"
        )
        self._connection_status_label.setText(
            f"Կապի կարգավիճակ։ {connection_status_label(connection_status)}"
        )

    def _load_current_session(self) -> None:
        """Reflects a session that may already be active for this
        terminal (e.g. the POS app was restarted while a session was
        still open) rather than always showing a stale "not started".
        Failure here is non-fatal: the page still works, just starting
        from the default "not started" display."""
        run_in_background(
            self,
            lambda: self._session_service.get_current_session(self._terminal_id),
            self._on_current_session_loaded,
            self._on_current_session_load_failed,
        )

    def _update_start_button_label(self) -> None:
        if (
            self._current_session is not None
            and self._current_session.status == "active"
        ):
            self._start_button.setText("Շարունակել աշխատանքը")
        else:
            self._start_button.setText("Սկսել աշխատանքը")

    def _on_current_session_loaded(self, session: SessionPayload | None) -> None:
        self._current_session = session
        if session is None:
            self._set_status_labels("not_started", "disconnected")
            self._update_start_button_label()
            self._retry_button.setVisible(False)
            return
        # A session may already be open for this terminal (e.g. after
        # an app restart) - reflect that in the labels, but still wait
        # for the explicit "Start working" click before proceeding.
        self._set_status_labels(session.status, session.connection_status)
        self._update_start_button_label()
        self._retry_button.setVisible(session.connection_status == "disconnected")

    def _on_current_session_load_failed(self, error: Exception) -> None:
        logger.warning("session_window op=load_current_session outcome=failed")
        if isinstance(error, (AdminUnavailableError, AuthenticationError)):
            self._set_status_labels("not_started", "disconnected")
            self._error_label.setText("Կապն ընդհատված է։")
            self._retry_button.setVisible(True)
            self._retry_timer.start()

    def _handle_start_session(self) -> None:
        self._error_label.setText("")

        if (
            self._current_session is not None
            and self._current_session.status == "active"
        ):
            # Already active on this terminal - resume it directly
            # rather than calling start_session again, which would
            # raise SessionAlreadyActiveError.
            self._opening_cash = self._opening_cash or Decimal("0")
            self.session_started.emit(self._current_session)
            return

        opening_cash, ok = QInputDialog.getDouble(
            self,
            "Սկսել աշխատանքը",
            "Քանի դրամ կա դրամարկղում սկզբում։",
            float(self._opening_cash or Decimal("0")),
            0.0,
            1_000_000_000.0,
            2,
        )
        if not ok:
            return
        self._opening_cash = Decimal(str(opening_cash))
        save_last_cash_balance(self._terminal_id, self._opening_cash)
        self._last_retry_call = (
            str(self._employee.id),
            self._terminal_id,
            self._opening_cash,
        )

        self._start_button.setEnabled(False)
        run_in_background(
            self,
            lambda: self._session_service.start_session(
                self._last_retry_call[0], self._last_retry_call[1], self._last_retry_call[2]
            ),
            self._on_session_started,
            self._on_session_start_failed,
        )

    def _on_session_started(self, session: SessionPayload) -> None:
        self._start_button.setEnabled(True)
        self._retry_timer.stop()
        self._retry_button.setEnabled(True)
        self._retry_button.setVisible(False)
        self._error_label.setText("")
        self._set_status_labels(session.status, session.connection_status)
        self.session_started.emit(session)

    def _on_session_start_failed(self, error: Exception) -> None:
        self._start_button.setEnabled(True)
        if isinstance(error, SessionAlreadyActiveError):
            self._error_label.setText(_SESSION_ALREADY_ACTIVE_MESSAGE)
            self._retry_button.setVisible(False)
            self._retry_timer.stop()
        elif isinstance(error, (AdminUnavailableError, AuthenticationError)):
            self._error_label.setText("Կապն ընդհատված է։")
            self._set_status_labels("not_started", "disconnected")
            self._retry_button.setEnabled(True)
            self._retry_button.setVisible(True)
            self._retry_timer.start()
            QMessageBox.critical(self, "Սխալ", _ADMIN_UNAVAILABLE_MESSAGE)
        else:
            self._error_label.setText("Չհաջողվեց սկսել սեսիան։")
            self._retry_button.setVisible(False)
            self._retry_timer.stop()

    def _retry_connection(self) -> None:
        self._retry_timer.stop()
        if self._last_retry_call is not None:
            self._start_button.setEnabled(False)
            self._error_label.setText("Կապի վերամիացում...")
            run_in_background(
                self,
                self._retry_start_session,
                self._on_session_started,
                self._on_session_start_failed,
            )
            return
        self._error_label.setText("Կապի վերամիացում...")
        self._retry_button.setEnabled(False)
        run_in_background(
            self,
            self._retry_load_current_session,
            self._on_current_session_loaded,
            self._on_current_session_load_failed,
        )

    def _retry_start_session(self) -> SessionPayload:
        if self._reconnect_admin is not None:
            self._reconnect_admin()
        retry_call = self._last_retry_call
        assert retry_call is not None
        return self._session_service.start_session(
            retry_call[0],
            retry_call[1],
            retry_call[2],
        )

    def _retry_load_current_session(self) -> SessionPayload | None:
        if self._reconnect_admin is not None:
            self._reconnect_admin()
        return self._session_service.get_current_session(self._terminal_id)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._retry_timer.stop()
        wait_for_pending_threads(self)
        super().closeEvent(event)
