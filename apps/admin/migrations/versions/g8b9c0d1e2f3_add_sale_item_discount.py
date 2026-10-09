"""add sale item original price and discount amount

Revision ID: g8b9c0d1e2f3
Revises: f7a8b9c0d1e2
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g8b9c0d1e2f3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sale_items", sa.Column("original_unit_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("sale_items", sa.Column("discount_amount", sa.Numeric(12, 2), nullable=True))
    op.execute("UPDATE sale_items SET original_unit_price = unit_price, discount_amount = 0")
    op.alter_column("sale_items", "original_unit_price", nullable=False)
    op.alter_column("sale_items", "discount_amount", nullable=False, server_default=sa.text("0"))
    op.create_check_constraint(
        "ck_sale_items_original_price_nonnegative", "sale_items", "original_unit_price >= 0"
    )
    op.create_check_constraint(
        "ck_sale_items_discount_nonnegative", "sale_items", "discount_amount >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_sale_items_discount_nonnegative", "sale_items", type_="check")
    op.drop_constraint("ck_sale_items_original_price_nonnegative", "sale_items", type_="check")
    op.drop_column("sale_items", "discount_amount")
    op.drop_column("sale_items", "original_unit_price")