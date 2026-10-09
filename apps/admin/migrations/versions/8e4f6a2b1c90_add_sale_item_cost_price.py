"""store product cost on sale item snapshots

Revision ID: 8e4f6a2b1c90
Revises: a1b2c3d4e5f6
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e4f6a2b1c90"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sale_items",
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE sale_items AS sale_item
            SET cost_price = product.cost_price
            FROM products AS product
            WHERE sale_item.product_id = product.id
            """
        )
    )


def downgrade() -> None:
    op.drop_column("sale_items", "cost_price")