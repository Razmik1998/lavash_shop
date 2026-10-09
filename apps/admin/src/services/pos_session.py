"""Application layer: AuthService, EmployeeService."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from exceptions import (
    AuthenticationError,
    SessionClosedError,
    SessionNotFoundError,
)
from models import (
    PosSession,
    PosSessionStatus,
    Role,
    SaleStatus,
)
from repository import (
    CustomerRepository,
    PosSessionRepository,
    SaleRepository,
    UserRepository,
)
from schemas import SalesFilters
from ui.pos_sessions_window import PosSessionRow

# How long a POS terminal may go without a heartbeat before the admin
# panel/UI shows its connection as DISCONNECTED. Kept a small multiple
# (3x) of `HEARTBEAT_INTERVAL_MS` (15s) in
# apps/pos/src/ui/session_status.py, per that module's docstring
# ("the backend's connected/disconnected threshold must be kept a
# small multiple of this, e.g. 2-3x, so a single missed beat doesn't
# flip the indicator") and the networking/server.py PosSessionService
# Protocol docstring assuming this exact computation.
HEARTBEAT_TIMEOUT_SECONDS = 45
ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


class PosSessionService:
    """Satisfies the `PosSessionService` Protocol in
    apps/admin/src/networking/server.py (POS-facing lifecycle
    operations) and the `PosSessionMonitoringService` Protocol in
    apps/admin/src/ui/pos_sessions_window.py (admin monitoring panel),
    without importing either Protocol - only the models/repositories/
    exceptions it actually needs."""

    def __init__(
        self,
        pos_session_repository: PosSessionRepository,
        user_repository: UserRepository,
        sale_repository: SaleRepository | None = None,
        customer_repository: CustomerRepository | None = None,
        cash_repository=None,
    ) -> None:
        self._pos_session_repository = pos_session_repository
        self._user_repository = user_repository
        self._sale_repository = sale_repository
        self._customer_repository = customer_repository
        self.cash_repository = cash_repository

    def start_session(
        self,
        user_id: uuid.UUID,
        terminal_id: str,
        opening_cash: Decimal = Decimal("0"),
    ) -> PosSession:
        user = self._user_repository.get_by_id(user_id)
        if user is None or not user.is_active or user.role is not Role.EMPLOYEE:
            raise AuthenticationError("Invalid user for POS session.")
        if opening_cash == Decimal("0"):
            pos_session = self._pos_session_repository.create(user_id, terminal_id)
        else:
            pos_session = self._pos_session_repository.create(
                user_id, terminal_id, opening_cash
            )
        return self._decorate_session(pos_session)

    def close_session(
        self, session_id: uuid.UUID, closing_cash: Decimal | None = None
    ) -> PosSession:
        existing = self._pos_session_repository.get_by_id(session_id)
        if existing is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        cash_difference = None
        if closing_cash is not None and self._sale_repository is not None:
            summary = self._sale_repository.summarize_sales(
                SalesFilters(session_id=session_id, status=SaleStatus.COMPLETED)
            )
            credit_sales = summary[4] if len(summary) > 4 else Decimal("0")
            cash_sales = summary[2] - credit_sales
            repayments = Decimal("0")
            if self._customer_repository is not None:
                repayments = self._customer_repository.payment_totals_by_sessions(
                    [session_id]
                ).get(session_id, Decimal("0"))
            cash_difference = (
                (existing.opening_cash or Decimal("0"))
                + cash_sales
                + repayments
                - closing_cash
            )
        if closing_cash is None and cash_difference is None:
            pos_session = self._pos_session_repository.close(session_id)
        else:
            pos_session = self._pos_session_repository.close(
                session_id, closing_cash, cash_difference
            )
        if pos_session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return self._decorate_session(pos_session)

    def disconnect(self, session_id: uuid.UUID) -> PosSession:
        existing = self._pos_session_repository.get_by_id(session_id)
        if existing is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        pos_session = self._pos_session_repository.disconnect(session_id)
        if pos_session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return self._decorate_session(pos_session)

    def heartbeat(self, session_id: uuid.UUID) -> PosSession:
        existing = self._pos_session_repository.get_by_id(session_id)
        if existing is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        if existing.status is PosSessionStatus.CLOSED:
            raise SessionClosedError(f"Session already closed: {session_id}")
        pos_session = self._pos_session_repository.update_heartbeat(session_id)
        if pos_session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return self._decorate_session(pos_session)

    def get_current_session(self, terminal_id: str) -> PosSession | None:
        pos_session = self._pos_session_repository.get_active_by_terminal(terminal_id)
        if pos_session is None:
            return None
        return self._decorate_session(pos_session)

    def list_sessions(self) -> list[PosSessionRow]:
        rows = self._pos_session_repository.list_all_with_user_names()
        repayment_totals = (
            self._customer_repository.payment_totals_by_sessions(
                [pos_session.id for pos_session, _full_name in rows]
            )
            if self._customer_repository is not None
            else {}
        )
        credit_sales_totals = (
            self._sale_repository.credit_totals_by_sessions(
                [pos_session.id for pos_session, _full_name in rows]
            )
            if self._sale_repository is not None
            else {}
        )
        return [
            PosSessionRow(
                session_id=pos_session.id,
                terminal_id=pos_session.terminal_id,
                user_full_name=full_name,
                status=pos_session.status.value,
                connection_status=self._connection_status(pos_session),
                started_at=pos_session.started_at,
                closed_at=pos_session.closed_at,
                last_activity_at=pos_session.last_activity_at,
                opening_cash=pos_session.opening_cash or Decimal("0"),
                closing_cash=pos_session.closing_cash,
                cash_difference=pos_session.cash_difference,
                repayments_total=repayment_totals.get(pos_session.id, Decimal("0")),
                credit_sales_total=credit_sales_totals.get(
                    pos_session.id, Decimal("0")
                ),
            )
            for pos_session, full_name in rows
        ]

    @classmethod
    def _decorate_session(cls, pos_session: PosSession) -> PosSession:
        pos_session.connection_status = cls._connection_status(  # type: ignore[attr-defined]
            pos_session
        )
        return pos_session

    @staticmethod
    def _connection_status(pos_session: PosSession) -> str:
        if pos_session.status is PosSessionStatus.CLOSED:
            return "disconnected"
        elapsed = datetime.now(ARMENIA_TIMEZONE) - pos_session.last_connected_at
        if elapsed.total_seconds() > HEARTBEAT_TIMEOUT_SECONDS:
            return "disconnected"
        return "connected"
