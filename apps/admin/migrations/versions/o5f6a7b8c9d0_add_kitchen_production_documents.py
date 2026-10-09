"""add kitchen production documents"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "o5f6a7b8c9d0"
down_revision: str | None = "n4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kitchen_productions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_number", sa.String(32), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kitchen_productions_document_number", "kitchen_productions", ["document_number"], unique=True)
    op.create_index("ix_kitchen_productions_created_at", "kitchen_productions", ["created_at"])
    op.create_table(
        "kitchen_production_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("production_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("product_sku", sa.String(64), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_kitchen_production_items_quantity_positive"),
        sa.ForeignKeyConstraint(["production_id"], ["kitchen_productions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kitchen_production_items_product", "kitchen_production_items", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_kitchen_production_items_product", table_name="kitchen_production_items")
    op.drop_table("kitchen_production_items")
    op.drop_index("ix_kitchen_productions_created_at", table_name="kitchen_productions")
    op.drop_index("ix_kitchen_productions_document_number", table_name="kitchen_productions")
    op.drop_table("kitchen_productions")
