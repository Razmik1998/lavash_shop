from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class WasteDocument(Base):
    __tablename__ = "waste_documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'locked')", name="ck_waste_documents_status"
        ),
        CheckConstraint(
            "total_cost >= 0", name="ck_waste_documents_total_cost_nonnegative"
        ),
        Index("ix_waste_documents_created_at", "created_at"),
        Index("ix_waste_documents_locked_at", "locked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WasteDocumentItem(Base):
    __tablename__ = "waste_document_items"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0", name="ck_waste_document_items_quantity_positive"
        ),
        CheckConstraint(
            "unit_cost >= 0", name="ck_waste_document_items_cost_nonnegative"
        ),
        CheckConstraint(
            "line_total >= 0", name="ck_waste_document_items_total_nonnegative"
        ),
        Index("ix_waste_document_items_product", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("waste_documents.id", ondelete="CASCADE")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    product_name: Mapped[str] = mapped_column(String(255))
    product_sku: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(32))
    reason_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    unit: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
