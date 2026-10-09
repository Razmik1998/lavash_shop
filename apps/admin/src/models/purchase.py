from __future__ import annotations

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
	func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base
from models.enums import PurchaseStatus


class Purchase(Base):
	__tablename__ = "purchases"
	__table_args__ = (
		CheckConstraint("total >= 0", name="ck_purchases_total_nonnegative"),
		Index("ix_purchases_supplier_date", "supplier_id", "purchase_date"),
		Index("ix_purchases_supplier_purchase_date_id", "supplier_id", "purchase_date", "id"),
		Index("ix_purchases_date", "purchase_date"),
	)
	id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
	purchase_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
	supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"))
	purchase_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
	total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
	status: Mapped[PurchaseStatus] = mapped_column(Enum(PurchaseStatus, name="purchase_status", values_callable=lambda enum_cls: [member.value for member in enum_cls]), default=PurchaseStatus.DRAFT)
	notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PurchaseItem(Base):
	__tablename__ = "purchase_items"
	__table_args__ = (
		CheckConstraint("quantity > 0", name="ck_purchase_items_quantity_positive"),
		CheckConstraint("unit_cost >= 0", name="ck_purchase_items_cost_nonnegative"),
		CheckConstraint("selling_price >= 0", name="ck_purchase_items_price_nonnegative"),
		CheckConstraint("line_total >= 0", name="ck_purchase_items_total_nonnegative"),
		Index("ix_purchase_items_product", "product_id"),
	)
	id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
	purchase_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchases.id", ondelete="RESTRICT"))
	product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
	product_name: Mapped[str] = mapped_column(String(255))
	product_sku: Mapped[str] = mapped_column(String(64))
	unit: Mapped[str] = mapped_column(String(16))
	quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
	unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
	line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
	selling_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
	markup_percentage: Mapped[Decimal] = mapped_column(Numeric(8, 3), default=Decimal("0"))

__all__ = ["Purchase", "PurchaseItem"]
