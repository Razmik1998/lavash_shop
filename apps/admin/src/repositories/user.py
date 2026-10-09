"""Repository: owns Session usage for the users table."""

from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from exceptions import (
    UsernameAlreadyExistsError,
)
from models import (
    Role,
    User,
)

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


class UserRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_by_username(self, username: str) -> User | None:
        with self._session_factory() as session:
            return session.scalar(select(User).where(User.username == username))

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        with self._session_factory() as session:
            return session.get(User, user_id)

    def list_by_role(self, role: Role) -> list[User]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(User).where(User.role == role).order_by(User.username)
                )
            )

    def add(self, user: User) -> User:
        with self._session_factory() as session:
            session.add(user)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise UsernameAlreadyExistsError(user.username) from exc
            session.refresh(user)
            return user

