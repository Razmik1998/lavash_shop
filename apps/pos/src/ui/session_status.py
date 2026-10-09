"""Shared UI-facing pieces for the POS session lifecycle screens
(session_window.py, home_window.py): the facade Protocol both screens
call into, the Armenian status-label mapping (kept in one place per
.claude/rules/python.md #24 "do not duplicate business logic" — this
is presentation-only translation, not a business rule, but it must
still not be copy-pasted across screens), and the heartbeat interval
constant.

`PosSessionService` here is a typing-only Protocol, not a concrete
class: `implementer` will add a real `PosSessionService` to
apps/pos/src/services.py (a thin facade over `AdminConnection`, per
.claude/specs/4/task-plan.md) that satisfies this shape exactly. UI
code depends on this Protocol, never on `AdminConnection`/`socket`/
`json` directly."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from networking.protocol import SessionPayload

# Poll frequently enough to notice an Admin shutdown promptly while the
# active POS screen is open. Individual requests are guarded by the UI
# so a slow failed request cannot create overlapping heartbeat calls.
HEARTBEAT_INTERVAL_MS = 2_000

_SESSION_STATUS_LABELS = {
    "not_started": "Չի սկսվել",
    "active": "Ակտիվ",
    "closed": "Փակված",
}

_CONNECTION_STATUS_LABELS = {
    "connected": "Կապակցված է",
    "disconnected": "Կապն ընդհատված է",
}


def session_status_label(status: str) -> str:
    """Armenian label for a session status ("active"/"closed"/etc, as
    carried on `SessionPayload.status`, or the synthetic
    "not_started" used before a session exists)."""
    return _SESSION_STATUS_LABELS.get(status, status)


def connection_status_label(status: str) -> str:
    """Armenian label for a connection status ("connected"/
    "disconnected", as carried on `SessionPayload.connection_status`)."""
    return _CONNECTION_STATUS_LABELS.get(status, status)


class PosSessionService(Protocol):
    """The only surface POS UI code may call for session lifecycle
    operations — never `AdminConnection` directly (see
    .claude/rules/architecture.md). Method names/signatures mirror
    `networking.connection.AdminConnection` 1:1 so the facade in
    services.py can be a near-passthrough."""

    def start_session(
        self,
        user_id: str,
        terminal_id: str,
        opening_cash: Decimal = Decimal("0"),
    ) -> SessionPayload:
        """Raises SessionAlreadyActiveError, AuthenticationError, or
        AdminUnavailableError (see exceptions.py)."""
        ...

    def close_session(
        self, session_id: str, closing_cash: Decimal | None = None
    ) -> SessionPayload:
        """Raises SessionNotFoundError or AdminUnavailableError."""
        ...

    def disconnect(self, session_id: str) -> SessionPayload:
        """Raises SessionNotFoundError or AdminUnavailableError."""
        ...

    def heartbeat(self, session_id: str) -> SessionPayload:
        """Raises SessionNotFoundError, SessionClosedError, or
        AdminUnavailableError."""
        ...

    def get_current_session(self, terminal_id: str) -> SessionPayload | None:
        """Raises AdminUnavailableError."""
        ...
