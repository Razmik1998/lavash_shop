from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class OnlineOrderBusinessStatus(enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class OnlineOrderSyncStatus(enum.Enum):
    # NOT_RECEIVED is a placeholder value for a future "expected but not
    # yet arrived" row; every OnlineOrder persisted today is only ever
    # created once RECEIVED, per the admin architecture doc (spec 9 §4).
    NOT_RECEIVED = "not_received"
    RECEIVED = "received"
    ACKNOWLEDGED = "acknowledged"


class OnlineOrderConversionStatus(enum.Enum):
    NOT_CREATED = "not_created"
    CREATED = "created"
    FAILED = "failed"


class OnlineOrder(Base):
    """Local mirror of a Django `Order`. Three status dimensions
    (business/sync/conversion) are kept as separate columns per spec §33
    -- never overloaded onto one column."""

    __tablename__ = "online_orders"
    __table_args__ = (
        UniqueConstraint("web_order_id", name="uq_online_orders_web_order_id"),
        CheckConstraint("subtotal >= 0", name="ck_online_orders_subtotal_nonnegative"),
        CheckConstraint(
            "delivery_fee >= 0", name="ck_online_orders_delivery_fee_nonnegative"
        ),
        CheckConstraint("discount >= 0", name="ck_online_orders_discount_nonnegative"),
        CheckConstraint("total >= 0", name="ck_online_orders_total_nonnegative"),
        Index(
            "ix_online_orders_business_status_order_date",
            "business_status",
            "order_date",
        ),
        Index("ix_online_orders_sync_status", "sync_status"),
        Index("ix_online_orders_conversion_status", "conversion_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    web_order_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    order_number: Mapped[str] = mapped_column(String(64))
    customer_name: Mapped[str] = mapped_column(String(255))
    customer_phone: Mapped[str] = mapped_column(String(32))
    customer_address: Mapped[str] = mapped_column(String(500))
    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    business_status: Mapped[OnlineOrderBusinessStatus] = mapped_column(
        Enum(
            OnlineOrderBusinessStatus,
            name="online_order_business_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=OnlineOrderBusinessStatus.PENDING,
    )
    sync_status: Mapped[OnlineOrderSyncStatus] = mapped_column(
        Enum(
            OnlineOrderSyncStatus,
            name="online_order_sync_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=OnlineOrderSyncStatus.RECEIVED,
    )
    conversion_status: Mapped[OnlineOrderConversionStatus] = mapped_column(
        Enum(
            OnlineOrderConversionStatus,
            name="online_order_conversion_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=OnlineOrderConversionStatus.NOT_CREATED,
    )
    conversion_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sale_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sales.id", ondelete="RESTRICT"), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"OnlineOrder(web_order_id={self.web_order_id!r}, "
            f"business_status={self.business_status!r})"
        )


class OnlineOrderItem(Base):
    """Line item snapshot, same reasoning as `SaleItem`: `product_id` is
    nullable + ON DELETE SET NULL because a Django product may not map
    1:1 to an admin `Product`; the snapshot fields are what conversion
    actually uses."""

    __tablename__ = "online_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_online_order_items_quantity_positive"),
        CheckConstraint(
            "unit_price >= 0", name="ck_online_order_items_unit_price_nonnegative"
        ),
        CheckConstraint(
            "subtotal >= 0", name="ck_online_order_items_subtotal_nonnegative"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    online_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("online_orders.id", ondelete="CASCADE")
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))


__all__ = [
    "OnlineOrder",
    "OnlineOrderBusinessStatus",
    "OnlineOrderConversionStatus",
    "OnlineOrderItem",
    "OnlineOrderSyncStatus",
]
