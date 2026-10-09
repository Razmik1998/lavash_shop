"""Align Sale web-order IDs with Django UUID order IDs.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    existing_ids = connection.execute(
        sa.text("SELECT count(*) FROM sales WHERE web_order_id IS NOT NULL")
    ).scalar_one()
    if existing_ids:
        raise RuntimeError(
            "Cannot convert sales.web_order_id from integer to UUID because "
            "existing non-null values require an explicit data migration."
        )

    connection.execute(
        sa.text(
            "ALTER TABLE sales "
            "ALTER COLUMN web_order_id TYPE UUID "
            "USING web_order_id::text::uuid"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    existing_ids = connection.execute(
        sa.text("SELECT count(*) FROM sales WHERE web_order_id IS NOT NULL")
    ).scalar_one()
    if existing_ids:
        raise RuntimeError(
            "Cannot convert sales.web_order_id from UUID to integer while "
            "non-null values exist."
        )

    connection.execute(
        sa.text(
            "ALTER TABLE sales "
            "ALTER COLUMN web_order_id TYPE INTEGER "
            "USING web_order_id::text::integer"
        )
    )
