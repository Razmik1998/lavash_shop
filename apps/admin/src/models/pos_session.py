from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base
from models.enums import PosSessionStatus


class PosSession(Base):
	__tablename__ = "pos_sessions"
	__table_args__ = (
		Index("ix_pos_sessions_terminal_id", "terminal_id"),
		Index("ix_pos_sessions_active_terminal_unique", "terminal_id", unique=True, postgresql_where=text("status = 'active'")),
	)

	id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
	terminal_id: Mapped[str] = mapped_column(String(128))
	user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
	status: Mapped[PosSessionStatus] = mapped_column(Enum(PosSessionStatus, name="pos_session_status", values_callable=lambda enum_cls: [member.value for member in enum_cls]), default=PosSessionStatus.ACTIVE)
	started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
	last_connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	opening_cash: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
	closing_cash: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
	cash_difference: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

	def __repr__(self) -> str:
		return f"PosSession(terminal_id={self.terminal_id!r}, status={self.status!r})"

__all__ = ["PosSession"]