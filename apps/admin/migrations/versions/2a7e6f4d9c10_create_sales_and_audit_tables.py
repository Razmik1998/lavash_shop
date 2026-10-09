"""create sales and audit tables

Revision ID: 2a7e6f4d9c10
Revises: fc46b5cf2f59
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2a7e6f4d9c10"
down_revision: str | None = "fc46b5cf2f59"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sale_status = sa.Enum("completed", "voided", name="sale_status")
    op.create_table(
        "sales",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pos_session_id", sa.Uuid(), nullable=False),
        sa.Column("employee_user_id", sa.Uuid(), nullable=False),
        sa.Column("terminal_id", sa.String(length=128), nullable=False),
        sa.Column("client_sale_id", sa.Uuid(), nullable=False),
        sa.Column("status", sale_status, nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("total >= 0", name="ck_sales_total_nonnegative"),
        sa.ForeignKeyConstraint(["pos_session_id"], ["pos_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_sale_id"),
    )
    op.create_index("ix_sales_created_at_id", "sales", ["created_at", "id"])
    op.create_index("ix_sales_pos_session_created_at_id", "sales", ["pos_session_id", "created_at", "id"])
    op.create_index("ix_sales_terminal_created_at_id", "sales", ["terminal_id", "created_at", "id"])
    op.create_index("ix_sales_employee_created_at_id", "sales", ["employee_user_id", "created_at", "id"])

    op.create_table(
        "sale_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("product_sku", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_sale_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_sale_items_unit_price_nonnegative"),
        sa.CheckConstraint("line_total >= 0", name="ck_sale_items_line_total_nonnegative"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sale_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("pos_session_id", sa.Uuid(), nullable=False),
        sa.Column("terminal_id", sa.String(length=128), nullable=False),
        sa.Column("employee_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("authorized_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=True),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pos_session_id"], ["pos_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["authorized_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sale_audit_events_sale_created_at_id", "sale_audit_events", ["sale_id", "created_at", "id"])
    op.create_index("ix_sale_audit_events_session_created_at_id", "sale_audit_events", ["pos_session_id", "created_at", "id"])
    op.create_index("ix_sale_audit_events_actor_created_at_id", "sale_audit_events", ["actor_user_id", "created_at", "id"])
    op.create_index("ix_sale_audit_events_created_at_id", "sale_audit_events", ["created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_sale_audit_events_created_at_id", table_name="sale_audit_events")
    op.drop_index("ix_sale_audit_events_actor_created_at_id", table_name="sale_audit_events")
    op.drop_index("ix_sale_audit_events_session_created_at_id", table_name="sale_audit_events")
    op.drop_index("ix_sale_audit_events_sale_created_at_id", table_name="sale_audit_events")
    op.drop_table("sale_audit_events")
    op.drop_table("sale_items")
    op.drop_index("ix_sales_employee_created_at_id", table_name="sales")
    op.drop_index("ix_sales_terminal_created_at_id", table_name="sales")
    op.drop_index("ix_sales_pos_session_created_at_id", table_name="sales")
    op.drop_index("ix_sales_created_at_id", table_name="sales")
    op.drop_table("sales")
    sa.Enum(name="sale_status").drop(op.get_bind(), checkfirst=True)
