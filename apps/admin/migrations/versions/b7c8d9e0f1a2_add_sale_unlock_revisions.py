"""add controlled sale unlock, revision, and inventory history tables"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "5f6a7b8c9d01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL does not allow a newly-added enum label to be used until the
    # transaction that added it has committed. Keep these labels usable by the
    # following migration, which backfills rows with status `editing`.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE sale_status ADD VALUE IF NOT EXISTS 'editing'")
        op.execute("ALTER TYPE sale_status ADD VALUE IF NOT EXISTS 'cancelled'")
    op.create_table(
        "sale_unlock_keys",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_sale_unlock_keys_active", "sale_unlock_keys", ["is_active"])
    op.create_table(
        "sale_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("unlocked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unlocked_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("sale_id", "revision_number", name="uq_sale_revisions_sale_number"),
    )
    op.create_table(
        "sale_inventory_adjustments",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("sale_id", "revision_number", "product_id", "direction", name="uq_sale_inventory_adjustment"),
    )


def downgrade() -> None:
    op.drop_table("sale_inventory_adjustments")
    op.drop_table("sale_revisions")
    op.drop_index("ix_sale_unlock_keys_active", table_name="sale_unlock_keys")
    op.drop_table("sale_unlock_keys")
