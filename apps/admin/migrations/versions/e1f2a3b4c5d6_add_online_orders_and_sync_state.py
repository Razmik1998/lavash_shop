"""add online orders, order sync state, sale.web_order_id

Revision ID: e1f2a3b4c5d6
Revises: d9e0f1a2b3c4
Create Date: 2026-09-19 00:30:00.000000

"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from models.constants import (
    ONLINE_SYSTEM_USER_ID,
    ONLINE_SYSTEM_USERNAME,
    ONLINE_TERMINAL_ID,
)

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    business_status = sa.Enum(
        "pending", "confirmed", "rejected", name="online_order_business_status"
    )
    sync_status = sa.Enum(
        "not_received", "received", "acknowledged", name="online_order_sync_status"
    )
    conversion_status = sa.Enum(
        "not_created", "created", "failed", name="online_order_conversion_status"
    )

    op.create_table(
        "online_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("web_order_id", sa.Uuid(), nullable=False),
        sa.Column("order_number", sa.String(length=64), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.Column("customer_phone", sa.String(length=32), nullable=False),
        sa.Column("customer_address", sa.String(length=500), nullable=False),
        sa.Column("order_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("delivery_fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("business_status", business_status, nullable=False),
        sa.Column("sync_status", sync_status, nullable=False),
        sa.Column("conversion_status", conversion_status, nullable=False),
        sa.Column("conversion_error", sa.String(length=1000), nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column("sale_id", sa.Uuid(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
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
            "subtotal >= 0", name="ck_online_orders_subtotal_nonnegative"
        ),
        sa.CheckConstraint(
            "delivery_fee >= 0", name="ck_online_orders_delivery_fee_nonnegative"
        ),
        sa.CheckConstraint(
            "discount >= 0", name="ck_online_orders_discount_nonnegative"
        ),
        sa.CheckConstraint("total >= 0", name="ck_online_orders_total_nonnegative"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("web_order_id", name="uq_online_orders_web_order_id"),
    )
    op.create_index(
        "ix_online_orders_business_status_order_date",
        "online_orders",
        ["business_status", "order_date"],
    )
    op.create_index("ix_online_orders_sync_status", "online_orders", ["sync_status"])
    op.create_index(
        "ix_online_orders_conversion_status", "online_orders", ["conversion_status"]
    )

    op.create_table(
        "online_order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("online_order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint(
            "quantity > 0", name="ck_online_order_items_quantity_positive"
        ),
        sa.CheckConstraint(
            "unit_price >= 0", name="ck_online_order_items_unit_price_nonnegative"
        ),
        sa.CheckConstraint(
            "subtotal >= 0", name="ck_online_order_items_subtotal_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["online_order_id"], ["online_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "order_sync_state",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("last_event_id", sa.Integer(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", name="uq_order_sync_state_device_id"),
    )

    op.add_column("sales", sa.Column("web_order_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint("uq_sales_web_order_id", "sales", ["web_order_id"])

    _seed_online_system_user_and_session()


def _seed_online_system_user_and_session() -> None:
    """Idempotent seeding (INSERT ... ON CONFLICT DO NOTHING) of the
    permanent ONLINE terminal's owning system user and its always-active
    PosSession row. Safe to run against a database that already has
    them (re-running `alembic upgrade head` after a partial apply, or
    a second admin instance's migration run against a shared DB).

    The system user's password is a random, never-communicated Argon2
    hash -- this account is never used for interactive login, only as
    the FK target for PosSession.user_id / Sale.employee_user_id. It
    is generated the same way apps/admin/src/security.py hashes real
    passwords, so the stored value is a well-formed hash even though
    it is never verified against.
    """
    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    random_password_hash = hasher.hash(uuid.uuid4().hex)

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO users
                (id, username, full_name, hashed_password, role, is_active)
            VALUES (:id, :username, :full_name, :hashed_password, :role, true)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": str(ONLINE_SYSTEM_USER_ID),
            "username": ONLINE_SYSTEM_USERNAME,
            "full_name": "Online Store (system account)",
            "hashed_password": random_password_hash,
            "role": "EMPLOYEE",
        },
    )
    # ON CONFLICT targets ix_pos_sessions_active_terminal_unique (the
    # partial unique index on terminal_id WHERE status = 'active') --
    # this is the actual "never duplicated" guarantee, not this check.
    connection.execute(
        sa.text(
            """
            INSERT INTO pos_sessions (id, terminal_id, user_id, status)
            VALUES (:id, :terminal_id, :user_id, 'active')
            ON CONFLICT (terminal_id) WHERE status = 'active' DO NOTHING
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "terminal_id": ONLINE_TERMINAL_ID,
            "user_id": str(ONLINE_SYSTEM_USER_ID),
        },
    )


def downgrade() -> None:
    # The seeded pos_sessions/users rows are intentionally left in
    # place on downgrade: dropping them here could delete a row that
    # by now owns real Sale/OnlineOrder history created after this
    # migration ran, which downgrade must never do. Only the schema
    # objects this migration introduced are reverted.
    op.drop_constraint("uq_sales_web_order_id", "sales", type_="unique")
    op.drop_column("sales", "web_order_id")

    op.drop_table("order_sync_state")

    op.drop_table("online_order_items")

    op.drop_index("ix_online_orders_conversion_status", table_name="online_orders")
    op.drop_index("ix_online_orders_sync_status", table_name="online_orders")
    op.drop_index(
        "ix_online_orders_business_status_order_date", table_name="online_orders"
    )
    op.drop_table("online_orders")

    sa.Enum(name="online_order_conversion_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="online_order_sync_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="online_order_business_status").drop(op.get_bind(), checkfirst=True)
