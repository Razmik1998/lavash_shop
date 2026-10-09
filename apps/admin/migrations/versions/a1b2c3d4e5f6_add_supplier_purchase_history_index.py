"""add supplier purchase history index

Revision ID: a1b2c3d4e5f6
Revises: 5d9e3a7b1c24
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "5d9e3a7b1c24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_purchases_supplier_purchase_date_id",
        "purchases",
        ["supplier_id", "purchase_date", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_purchases_supplier_purchase_date_id", table_name="purchases")
