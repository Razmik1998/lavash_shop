"""allow null price and stock for barbecue parents

Revision ID: 5f6a7b8c9d01
Revises: 4e1c2d3b4a5f
Create Date: 2026-09-14 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f6a7b8c9d01"
down_revision: str | None = "4e1c2d3b4a5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "products",
        "selling_price",
        existing_type=sa.Numeric(precision=10, scale=2),
        nullable=True,
    )
    op.alter_column(
        "products",
        "quantity_in_stock",
        existing_type=sa.Numeric(precision=10, scale=3),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "products",
        "quantity_in_stock",
        existing_type=sa.Numeric(precision=10, scale=3),
        nullable=False,
    )
    op.alter_column(
        "products",
        "selling_price",
        existing_type=sa.Numeric(precision=10, scale=2),
        nullable=False,
    )
