from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from PySide6.QtCore import QObject

from ui.pos_sessions_window import PosSessionRow, PosSessionsWindow


def _run_synchronously(
    owner: QObject,
    fn: Callable[[], object],
    on_success: Callable[[object], None],
    on_failure: Callable[[Exception], None],
) -> None:
    """Swaps the real QThread `run_in_background` uses for a
    synchronous call in this test module, matching the same fixture in
    apps/pos/tests/gui/test_session_window.py: it avoids depending on
    QThread teardown timing while still exercising the window's actual
    load/render wiring."""
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 - mirrors _CallableThread.run
        on_failure(exc)
        return
    on_success(result)


@pytest.fixture(autouse=True)
def _synchronous_background(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ui.pos_sessions_window.run_in_background", _run_synchronously
    )


class _FakePosSessionMonitoringService:
    def __init__(self, rows: list[PosSessionRow]) -> None:
        self._rows = rows

    def list_sessions(self) -> list[PosSessionRow]:
        return self._rows


def _make_row(
    terminal_id: str = "pos-1",
    status: str = "active",
    connection_status: str = "connected",
) -> PosSessionRow:
    now = datetime.now(UTC)
    return PosSessionRow(
        terminal_id=terminal_id,
        user_full_name="Cashier One",
        status=status,
        connection_status=connection_status,
        started_at=now,
        closed_at=None,
        last_activity_at=now,
    )


def test_pos_sessions_window_shows_active_session_row(qtbot) -> None:  # type: ignore[no-untyped-def]
    service = _FakePosSessionMonitoringService([_make_row()])
    window = PosSessionsWindow(service)
    qtbot.addWidget(window)

    assert window._model.rowCount() == 1
    assert window._model.item(0, 0).text() == "pos-1"
    assert window._model.item(0, 1).text() == "Cashier One"
    assert window._model.item(0, 2).text() == "Ակտիվ"
    assert window._model.item(0, 3).text() == "Կապակցված է"


def test_pos_sessions_window_shows_disconnected_session_row(qtbot) -> None:  # type: ignore[no-untyped-def]
    service = _FakePosSessionMonitoringService(
        [_make_row(connection_status="disconnected")]
    )
    window = PosSessionsWindow(service)
    qtbot.addWidget(window)

    assert window._model.item(0, 3).text() == "Կապն ընդհատված է"


def test_pos_sessions_window_reload_replaces_previous_rows(qtbot) -> None:  # type: ignore[no-untyped-def]
    service = _FakePosSessionMonitoringService([_make_row(terminal_id="pos-1")])
    window = PosSessionsWindow(service)
    qtbot.addWidget(window)
    assert window._model.rowCount() == 1

    service._rows = [
        _make_row(terminal_id="pos-1"),
        _make_row(terminal_id="pos-2"),
    ]
    window.reload_sessions()

    assert window._model.rowCount() == 2
