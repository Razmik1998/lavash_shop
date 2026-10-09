"""Authorized cash recipients and immutable session withdrawal documents."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CashRecipient(Base):
    __tablename__ = "cash_recipients"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CashWithdrawal(Base):
    __tablename__ = "cash_withdrawals"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_cash_withdrawal_positive"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pos_sessions.id"), index=True
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cash_recipients.id"))
    recipient_name: Mapped[str] = mapped_column(String(256))
    cashier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(String(1000))
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
