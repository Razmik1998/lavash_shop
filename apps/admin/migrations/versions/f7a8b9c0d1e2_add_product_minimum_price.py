"""add product minimum price

Revision ID: f7a8b9c0d1e2
Revises: 8e4f6a2b1c90
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "8e4f6a2b1c90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("minimum_price", sa.Numeric(10, 2), nullable=True))
    op.execute("UPDATE products SET minimum_price = selling_price")
    op.create_check_constraint(
        "ck_products_minimum_price_lte_selling_price",
        "products",
        "minimum_price IS NULL OR selling_price IS NULL OR minimum_price <= selling_price",
    )


def downgrade() -> None:
    op.drop_constraint("ck_products_minimum_price_lte_selling_price", "products", type_="check")
    op.drop_column("products", "minimum_price")