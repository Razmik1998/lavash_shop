from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base

# The single row this task ever creates. Keyed by `device_id` (a
# UniqueConstraint, not a bare singleton PK) so the schema itself does
# not become the thing that prevents ever running a second Desktop
# Admin instance later -- see apps/admin architecture doc §5.
DEFAULT_DEVICE_ID = "default"


class OrderSyncState(Base):
	"""Durable bookkeeping of how far this Admin instance has consumed
	Django's `OrderEvent` stream. Survives restart as an ordinary
	Postgres row."""

	__tablename__ = "order_sync_state"
	__table_args__ = (
		UniqueConstraint("device_id", name="uq_order_sync_state_device_id"),
	)

	id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
	device_id: Mapped[str] = mapped_column(String(128))
	last_event_id: Mapped[int | None] = mapped_column(nullable=True)
	last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
	updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

	def __repr__(self) -> str:
		return f"OrderSyncState(device_id={self.device_id!r}, last_event_id={self.last_event_id!r})"

__all__ = ["DEFAULT_DEVICE_ID", "OrderSyncState"]
