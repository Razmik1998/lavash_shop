"""Application layer: AuthService, EmployeeService."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from exceptions import (
    AuthenticationError,
)
from models import (
    Role,
    User,
)
from repository import (
    UserRepository,
)
from security import verify_password

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


class AuthService:
    def __init__(self, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    def login(self, username: str, password: str, required_role: Role) -> User:
        user = self._user_repository.get_by_username(username)
        if user is None or not user.is_active:
            raise AuthenticationError("Invalid username or password.")
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid username or password.")
        if user.role is not required_role:
            raise AuthenticationError("This account is not permitted to log in here.")
        return user

