from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
	Boolean,
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
from models.enums import PaymentMethod


class Supplier(Base):
	__tablename__ = "suppliers"
	__table_args__ = (
		CheckConstraint("length(trim(name)) > 0", name="ck_suppliers_name_nonempty"),
		CheckConstraint("opening_debt >= 0", name="ck_suppliers_opening_debt_nonnegative"),
		Index("ix_suppliers_name", "name"),
	)
	id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
	name: Mapped[str] = mapped_column(String(255))
	phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
	description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
	opening_debt: Mapped[Decimal] = mapped_column(
		Numeric(12, 2), default=Decimal("0"), server_default="0"
	)
	is_active: Mapped[bool] = mapped_column(Boolean, default=True)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupplierPayment(Base):
	__tablename__ = "supplier_payments"
	__table_args__ = (
		CheckConstraint("amount > 0", name="ck_supplier_payments_amount_positive"),
		Index("ix_supplier_payments_supplier_date", "supplier_id", "payment_date"),
		Index("ix_supplier_payments_purchase", "purchase_id"),
		Index("ix_supplier_payments_payment_date", "payment_date"),
	)
	id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
	supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"))
	purchase_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchases.id", ondelete="RESTRICT"), nullable=True)
	amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
	payment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
	method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, name="payment_method", values_callable=lambda enum_cls: [member.value for member in enum_cls]))
	notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

__all__ = ["Supplier", "SupplierPayment"]
