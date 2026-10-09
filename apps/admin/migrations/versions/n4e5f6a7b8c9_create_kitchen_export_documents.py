"""create Kitchen export document tables

Revision ID: n4e5f6a7b8c9
Revises: m3d4e5f6a7b8
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n4e5f6a7b8c9"
down_revision: str | None = "m3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kitchen_exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_number", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="draft", nullable=False
        ),
        sa.Column("total_cost", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "total_cost >= 0", name="ck_kitchen_exports_total_cost_nonnegative"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_kitchen_exports_document_number",
        "kitchen_exports",
        ["document_number"],
        unique=True,
    )
    op.create_index("ix_kitchen_exports_created_at", "kitchen_exports", ["created_at"])
    op.create_table(
        "kitchen_export_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("export_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("product_sku", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint(
            "quantity > 0", name="ck_kitchen_export_items_quantity_positive"
        ),
        sa.CheckConstraint(
            "unit_cost >= 0", name="ck_kitchen_export_items_cost_nonnegative"
        ),
        sa.CheckConstraint(
            "line_total >= 0", name="ck_kitchen_export_items_total_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["export_id"], ["kitchen_exports.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_kitchen_export_items_product", "kitchen_export_items", ["product_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_kitchen_export_items_product", table_name="kitchen_export_items")
    op.drop_table("kitchen_export_items")
    op.drop_index("ix_kitchen_exports_created_at", table_name="kitchen_exports")
    op.drop_index("ix_kitchen_exports_document_number", table_name="kitchen_exports")
    op.drop_table("kitchen_exports")
