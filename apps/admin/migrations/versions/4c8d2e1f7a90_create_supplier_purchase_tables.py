"""create supplier and purchase tables

Revision ID: 4c8d2e1f7a90
Revises: 2a7e6f4d9c10
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4c8d2e1f7a90"
down_revision: str | None = "2a7e6f4d9c10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    purchase_status = sa.Enum(
        "draft", "open", "partially_paid", "paid", "cancelled",
        name="purchase_status",
    )
    payment_method = sa.Enum("cash", "card", "transfer", "other", name="payment_method")
    movement_type = sa.Enum("receipt", "reversal", name="inventory_movement_type")
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_suppliers_name_nonempty"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])
    op.create_table(
        "purchases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purchase_number", sa.String(32), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", purchase_status, nullable=False),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("total >= 0", name="ck_purchases_total_nonnegative"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("purchase_number"),
    )
    op.create_index("ix_purchases_supplier_date", "purchases", ["supplier_id", "purchase_date"])
    op.create_index("ix_purchases_date", "purchases", ["purchase_date"])
    op.create_table(
        "purchase_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purchase_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("product_sku", sa.String(64), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("selling_price", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_items_quantity_positive"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_purchase_items_cost_nonnegative"),
        sa.CheckConstraint("selling_price >= 0", name="ck_purchase_items_price_nonnegative"),
        sa.CheckConstraint("line_total >= 0", name="ck_purchase_items_total_nonnegative"),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchase_items_product", "purchase_items", ["product_id"])
    op.create_table(
        "supplier_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", payment_method, nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_supplier_payments_amount_positive"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supplier_payments_supplier_date", "supplier_payments", ["supplier_id", "payment_date"])
    op.create_index("ix_supplier_payments_purchase", "supplier_payments", ["purchase_id"])
    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purchase_item_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("movement_type", movement_type, nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_movements_quantity_positive"),
        sa.ForeignKeyConstraint(["purchase_item_id"], ["purchase_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("purchase_item_id", "movement_type", name="ux_inventory_movements_purchase_item_type"),
    )
    op.create_index("ix_inventory_movements_product", "inventory_movements", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_inventory_movements_product", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_index("ix_supplier_payments_purchase", table_name="supplier_payments")
    op.drop_index("ix_supplier_payments_supplier_date", table_name="supplier_payments")
    op.drop_table("supplier_payments")
    op.drop_index("ix_purchase_items_product", table_name="purchase_items")
    op.drop_table("purchase_items")
    op.drop_index("ix_purchases_date", table_name="purchases")
    op.drop_index("ix_purchases_supplier_date", table_name="purchases")
    op.drop_table("purchases")
    op.drop_index("ix_suppliers_name", table_name="suppliers")
    op.drop_table("suppliers")
    for enum_name in ("inventory_movement_type", "payment_method", "purchase_status"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)