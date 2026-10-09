"""Domain model for POS. A plain value object, not ORM-mapped — POS no
longer owns a database connection (see .claude/specs/2/task-plan.md).
Admin remains the system of record for users and is reached only
through AdminConnection (networking/connection.py)."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass


class Role(enum.Enum):
    ADMIN = "admin"
    EMPLOYEE = "employee"


@dataclass(frozen=True)
class User:
    id: uuid.UUID
    username: str
    full_name: str
    role: Role
    is_active: bool
    auth_token: str | None = None
    token_expires_at: str | None = None
