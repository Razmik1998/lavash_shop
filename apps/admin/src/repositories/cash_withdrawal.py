import uuid
from decimal import Decimal

from sqlalchemy import select

from models import CashRecipient, CashWithdrawal, PosSession, PosSessionStatus, User


class CashWithdrawalRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def recipients(self, active_only=False):
        with self._session_factory() as db:
            query = select(CashRecipient).order_by(CashRecipient.name)
            if active_only:
                query = query.where(CashRecipient.is_active)
            return [
                {"id": str(r.id), "name": r.name, "is_active": r.is_active}
                for r in db.scalars(query)
            ]

    def save_recipient(self, name, recipient_id=None, active=True):
        name = name.strip()
        if not name or len(name) > 256:
            raise ValueError("Recipient name is required (maximum 256 characters).")
        with self._session_factory() as db:
            row = (
                db.get(CashRecipient, uuid.UUID(recipient_id))
                if recipient_id
                else CashRecipient()
            )
            if row is None:
                raise ValueError("Recipient not found")
            row.name, row.is_active = name, active
            db.add(row)
            db.commit()

    def history(self, session_id=None):
        with self._session_factory() as db:
            query = (
                select(CashWithdrawal, PosSession, User)
                .outerjoin(PosSession, CashWithdrawal.session_id == PosSession.id)
                .outerjoin(User, CashWithdrawal.cashier_id == User.id)
                .order_by(CashWithdrawal.taken_at.desc())
            )
            if session_id is not None:
                query = query.where(CashWithdrawal.session_id == session_id)
            return [
                {
                    **self._payload(withdrawal),
                    "session_name": (
                        f"{session.terminal_id} · {session.started_at:%d.%m.%Y %H:%M}"
                        if session else "—"
                    ),
                    "cashier_name": (cashier.full_name or cashier.username) if cashier else "—",
                }
                for withdrawal, session, cashier in db.execute(query)
            ]

    def total(self, session_id):
        return sum(
            (Decimal(r["amount"]) for r in self.history(session_id)), Decimal("0")
        )

    def record(self, withdrawal_id, session_id, user_id, recipient_id, amount, reason):
        reason = reason.strip()
        if (
            not amount.is_finite()
            or amount <= 0
            or amount >= Decimal("10000000000")
            or amount.as_tuple().exponent < -2
        ):
            raise ValueError("Enter a positive amount with at most two decimal places.")
        if not reason or len(reason) > 1000:
            raise ValueError("Reason is required (maximum 1000 characters).")
        with self._session_factory() as db:
            pos = db.scalar(
                select(PosSession).where(PosSession.id == session_id).with_for_update()
            )
            if pos is None or pos.user_id != user_id:
                raise ValueError("Session does not belong to this cashier.")
            existing = db.get(CashWithdrawal, withdrawal_id)
            if existing:
                if (
                    existing.session_id,
                    existing.cashier_id,
                    existing.recipient_id,
                    existing.amount,
                    existing.reason,
                ) != (session_id, user_id, recipient_id, amount, reason):
                    raise ValueError("Withdrawal identifier conflict")
                return self._payload(existing)
            if pos.status != PosSessionStatus.ACTIVE:
                raise ValueError("Session is closed.")
            recipient = db.scalar(
                select(CashRecipient)
                .where(CashRecipient.id == recipient_id)
                .with_for_update()
            )
            if recipient is None or not recipient.is_active:
                raise ValueError("Recipient is not authorized.")
            row = CashWithdrawal(
                id=withdrawal_id,
                session_id=session_id,
                cashier_id=user_id,
                recipient_id=recipient_id,
                recipient_name=recipient.name,
                amount=amount,
                reason=reason,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._payload(row)

    @staticmethod
    def _payload(row):
        return {
            "id": str(row.id),
            "session_id": str(row.session_id),
            "recipient_id": str(row.recipient_id),
            "recipient_name": row.recipient_name,
            "cashier_id": str(row.cashier_id),
            "amount": str(row.amount),
            "reason": row.reason,
            "taken_at": row.taken_at.isoformat(),
        }
