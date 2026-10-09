"""add parent product relationship

Revision ID: 4e1c2d3b4a5f
Revises: c3d4e5f6a7b8
Create Date: 2026-09-14 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4e1c2d3b4a5f"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE product_unit ADD VALUE IF NOT EXISTS 'BARBECUE'")
    op.add_column("products", sa.Column("parent_product_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_products_parent_product_id",
        "products",
        "products",
        ["parent_product_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_products_parent_not_self",
        "products",
        "(parent_product_id IS NULL OR parent_product_id <> id)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_products_parent_not_self", "products", type_="check")
    op.drop_constraint("fk_products_parent_product_id", "products", type_="foreignkey")
    op.drop_column("products", "parent_product_id")
