"""create products table

Revision ID: 9b2f4e7a1c63
Revises: 76e11a60b750
Create Date: 2026-09-10 03:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b2f4e7a1c63"
down_revision: str | None = "76e11a60b750"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "unit",
            sa.Enum("PIECE", "KG", "GRAM", "LITER", name="product_unit"),
            nullable=False,
        ),
        sa.Column("cost_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("selling_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "quantity_in_stock",
            sa.Numeric(precision=10, scale=3),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "low_stock_threshold", sa.Numeric(precision=10, scale=3), nullable=True
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "selling_price >= 0", name="ck_products_selling_price_nonnegative"
        ),
        sa.CheckConstraint(
            "quantity_in_stock >= 0", name="ck_products_quantity_nonnegative"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)
    op.create_index(
        "ix_products_barcode_unique",
        "products",
        ["barcode"],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_products_barcode_unique", table_name="products")
    op.drop_index("ix_products_sku", table_name="products")
    op.drop_table("products")
    sa.Enum(name="product_unit").drop(op.get_bind(), checkfirst=True)