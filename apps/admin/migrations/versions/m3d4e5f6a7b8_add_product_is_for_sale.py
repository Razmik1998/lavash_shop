"""add product sale availability and internal purchase pricing

Revision ID: m3d4e5f6a7b8
Revises: l2c3d4e5f6a7
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m3d4e5f6a7b8"
down_revision: str | None = "l2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "is_for_sale", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
    )
    op.alter_column(
        "purchase_items",
        "selling_price",
        existing_type=sa.Numeric(12, 2),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE purchase_items SET selling_price = 0 WHERE selling_price IS NULL"
    )
    op.alter_column(
        "purchase_items",
        "selling_price",
        existing_type=sa.Numeric(12, 2),
        nullable=False,
    )
    op.drop_column("products", "is_for_sale")
