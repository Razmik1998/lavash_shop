from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QLabel

from exceptions import AdminUnavailableError, SessionAlreadyActiveError
from models import Role, User
from networking.protocol import SessionPayload
from ui.session_window import SessionWindow


def _run_synchronously(
    owner: QObject,
    fn: Callable[[], object],
    on_success: Callable[[object], None],
    on_failure: Callable[[Exception], None],
) -> None:
    """Replaces `run_in_background`'s real QThread with a synchronous
    call for this test module. SessionWindow's threading mechanism
    itself is already covered by ui/workers.py's own tests (implied by
    the desktop skill's worker pattern); what these tests verify is the
    widget's wiring (signals, labels, error handling) given a
    success/failure result, which this fake exercises identically
    without the overhead/flakiness of real QThread teardown across many
    widget instances in one test session."""
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 - mirrors _CallableThread.run
        on_failure(exc)
        return
    on_success(result)


@pytest.fixture(autouse=True)
def _synchronous_background(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ui.session_window.run_in_background", _run_synchronously)


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


def _employee() -> User:
    return User(
        id=uuid.uuid4(),
        username="emp1",
        full_name="Employee One",
        role=Role.EMPLOYEE,
        is_active=True,
    )


class _FakeSessionService:
    def __init__(
        self,
        current: SessionPayload | None = None,
        start_result: SessionPayload | None = None,
        start_error: Exception | None = None,
    ) -> None:
        self._current = current
        self._start_result = start_result
        self._start_error = start_error
        self.start_calls: list[tuple[str, str]] = []

    def start_session(
        self, user_id: str, terminal_id: str, opening_cash: Decimal = Decimal("0")
    ) -> SessionPayload:
        self.start_calls.append((user_id, terminal_id))
        if self._start_error is not None:
            raise self._start_error
        assert self._start_result is not None
        return self._start_result

    def close_session(
        self, session_id: str, closing_cash: Decimal | None = None
    ) -> SessionPayload:
        raise AssertionError("not used by SessionWindow")

    def disconnect(self, session_id: str) -> SessionPayload:
        raise AssertionError("not used by SessionWindow")

    def heartbeat(self, session_id: str) -> SessionPayload:
        raise AssertionError("not used by SessionWindow")

    def get_current_session(self, terminal_id: str) -> SessionPayload | None:
        return self._current


def test_session_window_shows_terminal_and_user(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SessionWindow(_FakeSessionService(), _employee(), "pos-1")
    qtbot.addWidget(window)

    labels_text = " ".join(label.text() for label in window.findChildren(QLabel))
    assert "pos-1" in labels_text
    assert "Employee One" in labels_text


def test_start_session_success_emits_session_started_and_updates_status(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    employee = _employee()
    session = _make_session()
    service = _FakeSessionService(current=None, start_result=session)
    window = SessionWindow(service, employee, "pos-1")
    qtbot.addWidget(window)
    assert "Չի սկսվել" in window._session_status_label.text()

    with qtbot.waitSignal(window.session_started, timeout=2000) as blocker:
        qtbot.mouseClick(window._start_button, Qt.MouseButton.LeftButton)

    assert blocker.args[0] is session
    assert service.start_calls == [(str(employee.id), "pos-1")]
    assert "Ակտիվ" in window._session_status_label.text()


def test_start_session_already_active_shows_armenian_error(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    service = _FakeSessionService(
        current=None,
        start_error=SessionAlreadyActiveError("pos-1"),
    )
    window = SessionWindow(service, _employee(), "pos-1")
    qtbot.addWidget(window)

    qtbot.mouseClick(window._start_button, Qt.MouseButton.LeftButton)

    assert "Դիմեք ադմինիստրատորին" in window._error_label.text()
    assert window._start_button.isEnabled()


def test_existing_active_session_is_shown_on_load_without_clicking_start(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    """Reflects a session that is already active when the page loads
    (e.g. the POS app restarted while a session was open) — see
    SessionWindow._load_current_session's docstring."""
    session = _make_session()
    service = _FakeSessionService(current=session)

    window = SessionWindow(service, _employee(), "pos-1")
    qtbot.addWidget(window)

    assert "Ակտիվ" in window._session_status_label.text()
    assert "Շարունակել աշխատանքը" in window._start_button.text()


def test_existing_active_session_does_not_auto_emit_session_started(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    session = _make_session()
    service = _FakeSessionService(current=None)
    window = SessionWindow(service, _employee(), "pos-1")
    qtbot.addWidget(window)
    received: list[SessionPayload] = []
    window.session_started.connect(received.append)

    window._on_current_session_loaded(session)

    assert received == []


def test_existing_active_session_resumes_on_start_button_click(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    """Even when a session is already active on this terminal, the
    user must explicitly click "Start working" before proceeding —
    clicking it then resumes the existing session without re-calling
    start_session (which would raise SessionAlreadyActiveError)."""
    session = _make_session()
    service = _FakeSessionService(current=None)
    window = SessionWindow(service, _employee(), "pos-1")
    qtbot.addWidget(window)
    window._on_current_session_loaded(session)
    received: list[SessionPayload] = []
    window.session_started.connect(received.append)

    window._start_button.click()

    assert received == [session]


def test_start_session_prompts_for_opening_cash_before_new_session(
    qtbot,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _make_session()
    service = _FakeSessionService(current=None, start_result=session)
    window = SessionWindow(service, _employee(), "pos-1")
    qtbot.addWidget(window)

    monkeypatch.setattr(
        "ui.session_window.QInputDialog.getDouble",
        lambda *args, **kwargs: (100000.0, True),
    )

    window._handle_start_session()

    assert window._opening_cash == 100000
    assert service.start_calls == [(str(window._employee.id), "pos-1")]


def test_admin_unavailable_on_start_shows_critical_dialog(
    qtbot,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _FakeSessionService(
        current=None, start_error=AdminUnavailableError("unreachable")
    )
    window = SessionWindow(service, _employee(), "pos-1")
    qtbot.addWidget(window)
    window.show()

    shown: list[str] = []
    monkeypatch.setattr(
        "ui.session_window.QMessageBox.critical",
        lambda *args, **kwargs: shown.append(args[2]),
    )

    qtbot.mouseClick(window._start_button, Qt.MouseButton.LeftButton)

    assert len(shown) == 1
    assert "հասանելի չէ" in shown[0]
    assert window._retry_button.isVisible()


def test_retry_button_attempts_reconnect_when_admin_is_back(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    service = _FakeSessionService(current=None, start_error=AdminUnavailableError("unreachable"))
    window = SessionWindow(service, _employee(), "pos-1")
    qtbot.addWidget(window)
    window.show()

    window._start_button.click()
    assert window._retry_button.isVisible()

    service._start_error = None
    service._start_result = _make_session(status="active", connection_status="connected")
    window._retry_connection()

    assert "Կապակցված է" in window._connection_status_label.text()
    assert not window._retry_button.isVisible()
