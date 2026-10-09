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
	text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base
from models.enums import Unit


class Product(Base):
	__tablename__ = "products"
	__table_args__ = (
		CheckConstraint("selling_price >= 0", name="ck_products_selling_price_nonnegative"),
		CheckConstraint(
			"minimum_price IS NULL OR selling_price IS NULL OR minimum_price <= selling_price",
			name="ck_products_minimum_price_lte_selling_price",
		),
		CheckConstraint(
			"(parent_product_id IS NULL OR parent_product_id <> id)",
			name="ck_products_parent_not_self",
		),
		Index("ix_products_barcode_unique", "barcode", unique=True, postgresql_where=text("barcode IS NOT NULL")),
	)

	id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
	is_for_sale: Mapped[bool] = mapped_column(
		Boolean, default=True, server_default=text("true"), nullable=False
	)
	sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
	barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
	name: Mapped[str] = mapped_column(String(255))
	unit: Mapped[Unit] = mapped_column(Enum(Unit, name="product_unit"))
	parent_product_id: Mapped[uuid.UUID | None] = mapped_column(
		ForeignKey("products.id", ondelete="SET NULL"),
		nullable=True,
		default=None,
	)
	cost_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
	selling_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
	minimum_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
	quantity_in_stock: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True, default=None)
	low_stock_threshold: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
	is_active: Mapped[bool] = mapped_column(Boolean, default=True)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

	parent: Mapped["Product | None"] = relationship(
		"Product",
		remote_side="Product.id",
		back_populates="children",
		foreign_keys=[parent_product_id],
	)
	children: Mapped[list["Product"]] = relationship(
		"Product",
		back_populates="parent",
		foreign_keys="Product.parent_product_id",
	)

	def display_name(self, parent: "Product | None" = None) -> str:
		if self.parent_product_id is None:
			return self.name
		resolved_parent = parent if parent is not None else getattr(self, "parent", None)
		if resolved_parent is None:
			return self.name
		return f"{resolved_parent.name} -> {self.name}"

__all__ = ["Product"]
