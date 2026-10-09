"""add purchase item markup snapshot

Revision ID: 5d9e3a7b1c24
Revises: 4c8d2e1f7a90
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5d9e3a7b1c24"
down_revision: str | None = "4c8d2e1f7a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "purchase_items",
        sa.Column(
            "markup_percentage",
            sa.Numeric(8, 3),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column("purchase_items", "markup_percentage", server_default=None)
    op.create_check_constraint(
        "ck_purchase_items_markup_nonnegative",
        "purchase_items",
        "markup_percentage >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_purchase_items_markup_nonnegative",
        "purchase_items",
        type_="check",
    )
    op.drop_column("purchase_items", "markup_percentage")
