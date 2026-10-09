"""One-off seed script: creates the default admin user if it doesn't
already exist, and prints its generated credentials once.

Usage (from apps/admin/): python src/seed.py
"""

from __future__ import annotations

import secrets
import uuid

from config import load_settings
from db import create_session_factory
from models import Role, User
from repository import UserRepository
from security import hash_password

DEFAULT_ADMIN_USERNAME = "admin"


def main() -> int:
    settings = load_settings()
    repository = UserRepository(create_session_factory(settings))

    if repository.get_by_username(DEFAULT_ADMIN_USERNAME) is not None:
        print(f"Admin user '{DEFAULT_ADMIN_USERNAME}' already exists; not modified.")
        return 0

    generated_password = secrets.token_urlsafe(12)
    admin_user = User(
        id=uuid.uuid4(),
        username=DEFAULT_ADMIN_USERNAME,
        full_name="Admin",
        hashed_password=hash_password(generated_password),
        role=Role.ADMIN,
        is_active=True,
    )
    repository.add(admin_user)

    print("Seed admin user created. Share these credentials with the stakeholder:")
    print(f"  username: {DEFAULT_ADMIN_USERNAME}")
    print(f"  password: {generated_password}")
    print("This password is shown only once and is not stored anywhere in source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
