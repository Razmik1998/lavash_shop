"""add customer credit tables

Revision ID: i0a1b2c3d4e5
Revises: a3b4c5d6e7f8, h9c0d1e2f3a4
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i0a1b2c3d4e5"
down_revision: tuple[str, str] = ("a3b4c5d6e7f8", "h9c0d1e2f3a4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credit_customers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("first_name", sa.String(length=128), nullable=False),
        sa.Column("last_name", sa.String(length=128), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("address", sa.String(length=512), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone", name="uq_credit_customers_phone"),
    )
    op.create_index(
        "ix_credit_customers_first_name", "credit_customers", ["first_name"]
    )
    op.create_index("ix_credit_customers_last_name", "credit_customers", ["last_name"])

    op.create_table(
        "customer_credit_sales",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("sale_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount >= 0", name="ck_customer_credit_sales_amount_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["credit_customers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sale_id", name="uq_customer_credit_sales_sale"),
    )
    op.create_index(
        "ix_customer_credit_sales_customer_created",
        "customer_credit_sales",
        ["customer_id", "created_at"],
    )
    op.create_index(
        "ix_customer_credit_sales_sale_id", "customer_credit_sales", ["sale_id"]
    )

    op.create_table(
        "customer_credit_payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("pos_session_id", sa.UUID(), nullable=False),
        sa.Column("pos_user_id", sa.UUID(), nullable=False),
        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount > 0", name="ck_customer_credit_payments_amount_positive"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["credit_customers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["pos_session_id"], ["pos_sessions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["pos_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_credit_payments_customer_paid_at",
        "customer_credit_payments",
        ["customer_id", "paid_at"],
    )
    op.create_index(
        "ix_customer_credit_payments_session",
        "customer_credit_payments",
        ["pos_session_id"],
    )
    op.create_index(
        "ix_customer_credit_payments_user", "customer_credit_payments", ["pos_user_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_credit_payments_user", table_name="customer_credit_payments"
    )
    op.drop_index(
        "ix_customer_credit_payments_session", table_name="customer_credit_payments"
    )
    op.drop_index(
        "ix_customer_credit_payments_customer_paid_at",
        table_name="customer_credit_payments",
    )
    op.drop_table("customer_credit_payments")
    op.drop_index(
        "ix_customer_credit_sales_sale_id", table_name="customer_credit_sales"
    )
    op.drop_index(
        "ix_customer_credit_sales_customer_created", table_name="customer_credit_sales"
    )
    op.drop_table("customer_credit_sales")
    op.drop_index("ix_credit_customers_last_name", table_name="credit_customers")
    op.drop_index("ix_credit_customers_first_name", table_name="credit_customers")
    op.drop_table("credit_customers")
