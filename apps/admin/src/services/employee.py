"""Application layer: AuthService, EmployeeService."""

from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo

from models import (
    Role,
    User,
)
from repository import (
    UserRepository,
)
from security import hash_password

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


class EmployeeService:
    def __init__(self, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    def list_employees(self) -> list[User]:
        return self._user_repository.list_by_role(Role.EMPLOYEE)

    def create_employee(
        self, username: str, full_name: str, temp_password: str
    ) -> User:
        employee = User(
            id=uuid.uuid4(),
            username=username,
            full_name=full_name,
            hashed_password=hash_password(temp_password),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        return self._user_repository.add(employee)

