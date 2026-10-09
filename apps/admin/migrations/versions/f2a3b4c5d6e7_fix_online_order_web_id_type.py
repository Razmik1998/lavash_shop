"""Align online order web IDs with Django UUID order IDs.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    existing_rows = connection.execute(
        sa.text("SELECT count(*) FROM online_orders")
    ).scalar_one()
    if existing_rows:
        raise RuntimeError(
            "Cannot convert online_orders.web_order_id from integer to UUID "
            "because the table contains existing rows; migrate those IDs "
            "explicitly before applying this revision."
        )

    connection.execute(
        sa.text(
            "ALTER TABLE online_orders "
            "ALTER COLUMN web_order_id TYPE UUID "
            "USING web_order_id::text::uuid"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    existing_rows = connection.execute(
        sa.text("SELECT count(*) FROM online_orders")
    ).scalar_one()
    if existing_rows:
        raise RuntimeError(
            "Cannot convert online_orders.web_order_id from UUID to integer "
            "while the table contains rows."
        )

    connection.execute(
        sa.text(
            "ALTER TABLE online_orders "
            "ALTER COLUMN web_order_id TYPE INTEGER "
            "USING web_order_id::text::integer"
        )
    )
