from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base
from models.enums import InventoryMovementType


class InventoryMovement(Base):
	__tablename__ = "inventory_movements"
	__table_args__ = (
		CheckConstraint("quantity > 0", name="ck_inventory_movements_quantity_positive"),
		Index("ix_inventory_movements_product", "product_id"),
		Index("ux_inventory_movements_purchase_item_type", "purchase_item_id", "movement_type", unique=True),
	)
	id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
	purchase_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_items.id", ondelete="RESTRICT"))
	product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
	movement_type: Mapped[InventoryMovementType] = mapped_column(Enum(InventoryMovementType, name="inventory_movement_type", values_callable=lambda enum_cls: [member.value for member in enum_cls]))
	quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

__all__ = ["InventoryMovement"]