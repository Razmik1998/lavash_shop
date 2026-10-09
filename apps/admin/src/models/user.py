from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base
from models.enums import Role


class User(Base):
	"""A login-capable account."""

	__tablename__ = "users"

	id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
	username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
	full_name: Mapped[str] = mapped_column(String(128))
	hashed_password: Mapped[str] = mapped_column(String(255))
	role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"))
	is_active: Mapped[bool] = mapped_column(Boolean, default=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now()
	)

	def __repr__(self) -> str:
		return f"User(username={self.username!r}, role={self.role!r})"

__all__ = ["User"]