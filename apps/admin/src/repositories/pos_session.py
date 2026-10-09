"""Repository: owns Session usage for the users table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from exceptions import (
    SessionAlreadyActiveError,
)
from models import (
    PosSession,
    PosSessionStatus,
    User,
)
from models.cash_withdrawal import CashWithdrawal

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


class PosSessionRepository:
    """The only module (besides db.py) touching SQL for the POS session
    feature. Translates the partial unique index violation on
    ``ix_pos_sessions_active_terminal_unique`` into
    ``SessionAlreadyActiveError``, matching how ``ProductRepository``
    translates SKU/barcode collisions above."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_active_by_terminal(self, terminal_id: str) -> PosSession | None:
        with self._session_factory() as session:
            return session.scalar(
                select(PosSession).where(
                    PosSession.terminal_id == terminal_id,
                    PosSession.status == PosSessionStatus.ACTIVE,
                )
            )

    def get_by_id(self, session_id: uuid.UUID) -> PosSession | None:
        with self._session_factory() as session:
            return session.get(PosSession, session_id)

    def create(
        self, user_id: uuid.UUID, terminal_id: str, opening_cash: Decimal = Decimal("0")
    ) -> PosSession:
        pos_session = PosSession(
            id=uuid.uuid4(),
            terminal_id=terminal_id,
            user_id=user_id,
            status=PosSessionStatus.ACTIVE,
            opening_cash=opening_cash,
        )
        with self._session_factory() as session:
            session.add(pos_session)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise SessionAlreadyActiveError(terminal_id) from exc
            session.refresh(pos_session)
            return pos_session

    def close(
        self,
        session_id: uuid.UUID,
        closing_cash: Decimal | None = None,
        cash_difference: Decimal | None = None,
    ) -> PosSession | None:
        """Idempotent: a session already CLOSED is returned unchanged
        rather than updated again."""
        with self._session_factory() as session:
            pos_session = session.scalar(
                select(PosSession).where(PosSession.id == session_id).with_for_update()
            )
            if pos_session is None:
                return None
            if pos_session.status is PosSessionStatus.CLOSED:
                return pos_session
            if cash_difference is not None:
                withdrawn = session.scalar(
                    select(func.coalesce(func.sum(CashWithdrawal.amount), 0)).where(
                        CashWithdrawal.session_id == session_id
                    )
                )
                cash_difference -= Decimal(withdrawn)
            pos_session.closing_cash = closing_cash
            pos_session.cash_difference = cash_difference
            pos_session.status = PosSessionStatus.CLOSED
            pos_session.closed_at = datetime.now(ARMENIA_TIMEZONE)
            session.commit()
            session.refresh(pos_session)
            return pos_session

    def disconnect(self, session_id: uuid.UUID) -> PosSession | None:
        """Marks the session as disconnected without changing its status
        (leaving it ACTIVE if it was active)."""
        with self._session_factory() as session:
            pos_session = session.get(PosSession, session_id)
            if pos_session is None:
                return None
            if pos_session.status is PosSessionStatus.CLOSED:
                return pos_session
            pos_session.last_connected_at = datetime.fromtimestamp(0, UTC)
            session.commit()
            session.refresh(pos_session)
            return pos_session

    def update_heartbeat(self, session_id: uuid.UUID) -> PosSession | None:
        with self._session_factory() as session:
            pos_session = session.get(PosSession, session_id)
            if pos_session is None:
                return None
            now = datetime.now(ARMENIA_TIMEZONE)
            pos_session.last_connected_at = now
            pos_session.last_activity_at = now
            session.commit()
            session.refresh(pos_session)
            return pos_session

    def list_all(self) -> list[PosSession]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(PosSession).order_by(PosSession.started_at.desc())
                )
            )

    def list_all_with_user_names(self) -> list[tuple[PosSession, str]]:
        """Single joined query so the service layer can resolve
        ``user_full_name`` per row without an N+1 per-row user lookup
        (.claude/rules/database.md "avoid N+1 queries")."""
        with self._session_factory() as session:
            rows = session.execute(
                select(PosSession, User.full_name)
                .join(User, PosSession.user_id == User.id)
                .order_by(PosSession.started_at.desc())
            )
            return [(pos_session, full_name) for pos_session, full_name in rows]
