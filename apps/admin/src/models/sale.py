from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base
from models.enums import SaleStatus


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("total >= 0", name="ck_sales_total_nonnegative"),
        Index("ix_sales_created_at_id", "created_at", "id"),
        Index(
            "ix_sales_pos_session_created_at_id", "pos_session_id", "created_at", "id"
        ),
        Index("ix_sales_terminal_created_at_id", "terminal_id", "created_at", "id"),
        Index(
            "ix_sales_employee_created_at_id", "employee_user_id", "created_at", "id"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pos_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pos_sessions.id", ondelete="RESTRICT")
    )
    employee_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    terminal_id: Mapped[str] = mapped_column(String(128))
    client_sale_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    # The idempotency key for Django-originated (ONLINE) sales, the
    # mirror of client_sale_id for POS-originated sales. NULL never
    # collides with anything under a Postgres unique index/constraint,
    # so a POS sale (which never sets this) is unaffected. See admin
    # architecture doc §6: this unique constraint, not app-level
    # check-then-insert, is the actual order->sale idempotency guarantee.
    web_order_id: Mapped[uuid.UUID | None] = mapped_column(unique=True, nullable=True)
    status: Mapped[SaleStatus] = mapped_column(
        Enum(
            SaleStatus,
            name="sale_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SaleStatus.COMPLETED,
    )
    current_unlock_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sale_unlock_keys.id", ondelete="RESTRICT"), nullable=True
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SaleItem(Base):
    __tablename__ = "sale_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_items_quantity_positive"),
        Index("ix_sale_items_sale_active", "sale_id", "is_active"),
        CheckConstraint("unit_price >= 0", name="ck_sale_items_unit_price_nonnegative"),
        CheckConstraint("original_unit_price >= 0", name="ck_sale_items_original_price_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="ck_sale_items_discount_nonnegative"),
        CheckConstraint("line_total >= 0", name="ck_sale_items_line_total_nonnegative"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales.id", ondelete="RESTRICT")
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(String(255))
    product_sku: Mapped[str] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    original_unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    revision_number: Mapped[int] = mapped_column(default=1)


class SaleAuditEvent(Base):
    __tablename__ = "sale_audit_events"
    __table_args__ = (
        Index("ix_sale_audit_events_sale_created_at_id", "sale_id", "created_at", "id"),
        Index(
            "ix_sale_audit_events_session_created_at_id",
            "pos_session_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_sale_audit_events_actor_created_at_id",
            "actor_user_id",
            "created_at",
            "id",
        ),
        Index("ix_sale_audit_events_created_at_id", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales.id", ondelete="RESTRICT")
    )
    pos_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pos_sessions.id", ondelete="RESTRICT")
    )
    terminal_id: Mapped[str] = mapped_column(String(128))
    employee_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    authorized_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    authorization_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sale_unlock_keys.id", ondelete="RESTRICT"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(32))
    field_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    old_value: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SaleUnlockKey(Base):
    __tablename__ = "sale_unlock_keys"
    __table_args__ = (Index("ix_sale_unlock_keys_active", "is_active"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128))
    key_hash: Mapped[str] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SaleRevision(Base):
    __tablename__ = "sale_revisions"
    __table_args__ = (
        UniqueConstraint(
            "sale_id", "revision_number", name="uq_sale_revisions_sale_number"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales.id", ondelete="RESTRICT")
    )
    revision_number: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(32))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    closed_total: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    unlocked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SaleItemChange(Base):
    __tablename__ = "sale_item_changes"
    __table_args__ = (
        Index("ix_sale_item_changes_sale_created_at", "sale_id", "created_at"),
        Index("ix_sale_item_changes_revision_id", "revision_id"),
        Index("ix_sale_item_changes_sale_item_id", "sale_item_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales.id", ondelete="RESTRICT")
    )
    sale_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sale_items.id", ondelete="RESTRICT")
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sale_revisions.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(32))
    old_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    new_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SaleInventoryAdjustment(Base):
    __tablename__ = "sale_inventory_adjustments"
    __table_args__ = (
        UniqueConstraint(
            "sale_id",
            "revision_number",
            "product_id",
            "direction",
            name="uq_sale_inventory_adjustment",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales.id", ondelete="RESTRICT")
    )
    revision_number: Mapped[int] = mapped_column()
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    direction: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


__all__ = [
    "Sale",
    "SaleAuditEvent",
    "SaleInventoryAdjustment",
    "SaleItem",
    "SaleRevision",
    "SaleUnlockKey",
]
