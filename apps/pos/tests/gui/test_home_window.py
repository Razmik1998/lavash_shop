from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import cast

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QLabel, QMessageBox
from pytestqt.qtbot import QtBot

from exceptions import AdminUnavailableError, SessionClosedError, SessionNotFoundError
from models import Role, User
from networking.protocol import (
    SaleAuditPayload,
    SaleItemPayload,
    SalePayload,
    SessionPayload,
)
from services import SaleService
from ui.home_window import HomeWindow, _SalesHistoryView


def _run_synchronously(
    owner: QObject,
    fn: Callable[[], object],
    on_success: Callable[[object], None],
    on_failure: Callable[[Exception], None],
) -> None:
    """See test_session_window.py's identical fixture docstring: swaps
    the real QThread for a synchronous call so these widget-wiring
    tests don't depend on QThread teardown timing."""
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 - mirrors _CallableThread.run
        on_failure(exc)
        return
    on_success(result)


@pytest.fixture(autouse=True)
def _synchronous_background(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ui.home_window.run_in_background", _run_synchronously)


def _make_session(
    status: str = "active", connection_status: str = "connected"
) -> SessionPayload:
    return SessionPayload(
        id=str(uuid.uuid4()),
        terminal_id="pos-1",
        user_id=str(uuid.uuid4()),
        status=status,
        connection_status=connection_status,
        started_at="2026-01-01T00:00:00+00:00",
        closed_at=None,
        last_connected_at="2026-01-01T00:00:00+00:00",
        last_activity_at="2026-01-01T00:00:00+00:00",
    )


def _employee(full_name: str = "Employee One") -> User:
    return User(
        id=uuid.uuid4(),
        username="emp1",
        full_name=full_name,
        role=Role.EMPLOYEE,
        is_active=True,
    )


def _sale_payload(status: str) -> SalePayload:
    return SalePayload(
        id=str(uuid.uuid4()),
        session_id="session-1",
        terminal_id="pos-1",
        employee_user_id=str(uuid.uuid4()),
        status=status,
        total="250",
        created_at="2026-01-01T00:00:00+00:00",
        items=[
            SaleItemPayload(
                product_id=str(uuid.uuid4()),
                product_name="Tea",
                product_sku="TEA",
                unit="pcs",
                quantity="1",
                unit_price="250",
                line_total="250",
            )
        ],
        audit_events=[],
    )


class _FakePosSessionService:
    def __init__(
        self,
        heartbeat_result: SessionPayload | None = None,
        heartbeat_error: Exception | None = None,
    ) -> None:
        self.heartbeat_calls: list[str] = []
        self.close_calls: list[str] = []
        self.disconnect_calls: list[str] = []
        self._heartbeat_result = heartbeat_result or _make_session()
        self._heartbeat_error = heartbeat_error

    def start_session(
        self, user_id: str, terminal_id: str, opening_cash: Decimal = Decimal("0")
    ) -> SessionPayload:
        raise AssertionError("not used by HomeWindow")

    def close_session(
        self, session_id: str, closing_cash: Decimal | None = None
    ) -> SessionPayload:
        self.close_calls.append(session_id)
        return _make_session(status="closed", connection_status="disconnected")

    def disconnect(self, session_id: str) -> SessionPayload:
        self.disconnect_calls.append(session_id)
        return _make_session(status="active", connection_status="disconnected")

    def heartbeat(self, session_id: str) -> SessionPayload:
        self.heartbeat_calls.append(session_id)
        if self._heartbeat_error is not None:
            raise self._heartbeat_error
        assert self._heartbeat_result is not None
        return self._heartbeat_result

    def get_current_session(self, terminal_id: str) -> SessionPayload | None:
        raise AssertionError("not used by HomeWindow")


def test_home_window_shows_welcome_message(qtbot) -> None:  # type: ignore[no-untyped-def]
    employee = _employee("Անի Հակոբյան")
    window = HomeWindow(employee, _FakePosSessionService(), _make_session())
    qtbot.addWidget(window)

    labels_text = " ".join(label.text() for label in window.findChildren(QLabel))
    assert "Անի Հակոբյան" in labels_text


class _FakeSaleHistoryService:
    def __init__(self, sale: SalePayload) -> None:
        self._sale = sale

    def list_session_sales(self, session_id: str) -> list[SalePayload]:
        return [self._sale]

    def get_sale_detail(self, session_id: str, sale_id: str) -> SalePayload:
        assert sale_id == self._sale.id
        return self._sale


def test_sales_history_actions_follow_sale_status(qtbot: QtBot) -> None:
    view = _SalesHistoryView(None, None, None, "session-1")
    qtbot.addWidget(view)
    buttons = (view._unlock_button, view._edit_button, view._cancel_button)

    assert [button.isEnabled() for button in buttons] == [False, False, False]

    view._detail_loaded(_sale_payload("completed"))

    assert [button.isEnabled() for button in buttons] == [True, False, False]

    view._detail_loaded(_sale_payload("editing"))

    assert [button.isEnabled() for button in buttons] == [False, True, True]
    assert "Արդեն բացված է" in view._unlock_button.text()

    view._detail_loaded(_sale_payload("cancelled"))

    assert [button.isEnabled() for button in buttons] == [False, False, False]
    assert all(button.minimumHeight() == 56 for button in buttons)


def test_sales_history_save_stays_available_during_editing(qtbot: QtBot) -> None:
    sale = _sale_payload("editing")
    view = _SalesHistoryView(
        cast(SaleService, _FakeSaleHistoryService(sale)), None, None, "session-1"
    )
    qtbot.addWidget(view)
    view._detail_loaded(sale)

    assert not view._save_button.isEnabled()

    view._open_editor([], sale)

    assert view._save_button.isEnabled()
    assert view._page_stack.currentWidget() is view._editor
    assert view._editor is not None
    assert view._editor._save.isHidden()


def test_saved_sale_remains_selected_and_editable_after_returning_to_history(
    qtbot: QtBot,
) -> None:
    sale = _sale_payload("editing")

    view = _SalesHistoryView(
        cast(SaleService, _FakeSaleHistoryService(sale)), None, None, "session-1"
    )
    qtbot.addWidget(view)
    view._detail_loaded(sale)
    view._open_editor([], sale)

    view._editor_saved(sale)

    assert view._page_stack.currentIndex() == 0
    assert view._table.currentRow() == 0
    assert view._selected_sale is not None
    assert view._selected_sale.id == sale.id
    assert [button.isEnabled() for button in (
        view._unlock_button,
        view._edit_button,
        view._cancel_button,
        view._save_button,
    )] == [False, True, True, False]


def test_home_window_shows_session_and_connection_status_header(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = HomeWindow(
        _employee(),
        _FakePosSessionService(),
        _make_session(status="active", connection_status="connected"),
    )
    qtbot.addWidget(window)

    assert "Ակտիվ" in window._session_status_label.text()
    assert "Կապակցված է" in window._connection_status_label.text()


def test_close_session_confirmed_emits_session_closed_and_stops_heartbeat(
    qtbot,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(
        "ui.home_window.QInputDialog.getDouble",
        lambda *args, **kwargs: (50000.0, True),
    )
    session = _make_session()
    service = _FakePosSessionService()
    window = HomeWindow(_employee(), service, session, opening_cash=Decimal("100000"))
    qtbot.addWidget(window)
    assert window._heartbeat_timer.isActive()

    with qtbot.waitSignal(window.session_closed, timeout=2000):
        window._handle_close_session()

    assert service.close_calls == [session.id]
    assert not window._heartbeat_timer.isActive()
    assert "Փակված" in window._session_status_label.text()


def test_close_session_declined_does_not_close(
    qtbot,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    service = _FakePosSessionService()
    window = HomeWindow(_employee(), service, _make_session())
    qtbot.addWidget(window)

    window._handle_close_session()

    assert service.close_calls == []
    assert window._heartbeat_timer.isActive()


def test_heartbeat_tick_updates_status_labels(qtbot) -> None:  # type: ignore[no-untyped-def]
    service = _FakePosSessionService(
        heartbeat_result=_make_session(
            status="active", connection_status="connected"
        )
    )
    window = HomeWindow(
        _employee(),
        service,
        _make_session(status="active", connection_status="disconnected"),
    )
    qtbot.addWidget(window)

    assert service.heartbeat_calls == [window._session_id]
    assert "Կապակցված է" in window._connection_status_label.text()


def test_heartbeat_network_failure_flips_connection_indicator_only(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    service = _FakePosSessionService(
        heartbeat_error=AdminUnavailableError("unreachable")
    )
    window = HomeWindow(
        _employee(),
        service,
        _make_session(status="active", connection_status="connected"),
    )
    qtbot.addWidget(window)
    window.show()

    window._send_heartbeat()

    assert "Կապն ընդհատված է" in window._connection_status_label.text()
    assert window._retry_button.isVisible()
    # Session status is left untouched — a network failure alone must
    # never flip session state (task-4 spec: connection state and
    # session state are independent axes).
    assert "Ակտիվ" in window._session_status_label.text()


def test_retry_button_recovers_connection_after_admin_is_back(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    service = _FakePosSessionService(
        heartbeat_error=AdminUnavailableError("unreachable")
    )
    window = HomeWindow(
        _employee(),
        service,
        _make_session(status="active", connection_status="connected"),
    )
    qtbot.addWidget(window)
    window.show()

    window._send_heartbeat()
    assert "Կապն ընդհատված է" in window._connection_status_label.text()

    service._heartbeat_error = None
    service._heartbeat_result = _make_session(
        status="active", connection_status="connected"
    )
    window._retry_connection()

    assert "Կապակցված է" in window._connection_status_label.text()
    assert not window._retry_button.isVisible()


def test_heartbeat_session_gone_does_not_crash_or_touch_labels(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    service = _FakePosSessionService(
        heartbeat_error=SessionNotFoundError("gone")
    )
    window = HomeWindow(
        _employee(),
        service,
        _make_session(status="active", connection_status="connected"),
    )
    qtbot.addWidget(window)

    window._send_heartbeat()

    assert "Ակտիվ" in window._session_status_label.text()
    assert "Կապակցված է" in window._connection_status_label.text()


def test_window_close_disconnects_active_session(qtbot) -> None:  # type: ignore[no-untyped-def]
    session = _make_session(status="active", connection_status="connected")
    service = _FakePosSessionService()
    window = HomeWindow(_employee(), service, session)
    qtbot.addWidget(window)

    window.close()

    assert service.disconnect_calls == [session.id]


def test_window_close_after_explicit_session_close_does_not_disconnect(
    qtbot,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    session = _make_session()
    service = _FakePosSessionService()
    window = HomeWindow(_employee(), service, session)
    qtbot.addWidget(window)

    window._handle_close_session()
    service.disconnect_calls.clear()
    window.close()

    assert service.disconnect_calls == []


def test_closeout_report_uses_sales_total_before_session_is_closed(
    qtbot,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeSaleService:
        def __init__(self) -> None:
            self.is_closed = False

        def list_session_sales(self, session_id: str) -> list[SalePayload]:
            if self.is_closed:
                raise SessionClosedError("session already closed")
            return [
                SalePayload(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    terminal_id="pos-1",
                    employee_user_id=str(uuid.uuid4()),
                    status="completed",
                    total="1500.00",
                    created_at="2026-01-01T00:00:00+00:00",
                    items=[
                        SaleItemPayload(
                            product_id=str(uuid.uuid4()),
                            product_name="Tea",
                            product_sku="TEA",
                            unit="pcs",
                            quantity="3",
                            unit_price="500.00",
                            line_total="1500.00",
                        )
                    ],
                    audit_events=[
                        SaleAuditPayload(
                            event_type="created",
                            field_name=None,
                            old_value=None,
                            new_value={"total": "1500.00"},
                            actor_user_id=str(uuid.uuid4()),
                            created_at="2026-01-01T00:00:00+00:00",
                        )
                    ],
                )
            ]

    class _FakeSessionService(_FakePosSessionService):
        def __init__(self) -> None:
            super().__init__()
            self.closed = False

        def close_session(
            self, session_id: str, closing_cash: Decimal | None = None
        ) -> SessionPayload:
            self.closed = True
            return _make_session(status="closed", connection_status="disconnected")

    sale_service = _FakeSaleService()
    session_service = _FakeSessionService()
    session = _make_session()
    monkeypatch.setattr(
        "ui.home_window.QInputDialog.getDouble",
        lambda *args, **kwargs: (20000.0, True),
    )
    monkeypatch.setattr("ui.home_window.QDialog.exec", lambda *args, **kwargs: None)

    window = HomeWindow(
        _employee(),
        session_service,
        session,
        product_service=None,
        sale_service=sale_service,
        opening_cash=Decimal("10000"),
    )
    qtbot.addWidget(window)

    window._handle_close_session()

    assert window._closeout_sales_total == Decimal("1500.00")
