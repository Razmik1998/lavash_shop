"""link every sale audit event to its unlock key"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    sale_item_columns = {column["name"] for column in inspector.get_columns("sale_items")}
    if "is_active" not in sale_item_columns:
        op.add_column(
            "sale_items",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "revision_number" not in sale_item_columns:
        op.add_column(
            "sale_items",
            sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
        )
    sale_columns = {column["name"] for column in inspector.get_columns("sales")}
    if "current_unlock_key_id" not in sale_columns:
        op.add_column("sales", sa.Column("current_unlock_key_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_sales_current_unlock_key", "sales", "sale_unlock_keys",
        ["current_unlock_key_id"], ["id"], ondelete="RESTRICT"
    )
    op.add_column("sale_audit_events", sa.Column("authorization_key_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_sale_audit_events_authorization_key", "sale_audit_events", "sale_unlock_keys",
        ["authorization_key_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index(
        "ix_sale_audit_events_key_created_at", "sale_audit_events",
        ["authorization_key_id", "created_at", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_sale_audit_events_key_created_at", table_name="sale_audit_events")
    op.drop_constraint("fk_sale_audit_events_authorization_key", "sale_audit_events", type_="foreignkey")
    op.drop_column("sale_audit_events", "authorization_key_id")
    op.drop_constraint("fk_sales_current_unlock_key", "sales", type_="foreignkey")
    op.drop_column("sales", "current_unlock_key_id")
