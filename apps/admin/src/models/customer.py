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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CreditCustomer(Base):
    __tablename__ = "credit_customers"
    __table_args__ = (
        UniqueConstraint("phone", name="uq_credit_customers_phone"),
        Index("ix_credit_customers_first_name", "first_name"),
        Index("ix_credit_customers_last_name", "last_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str] = mapped_column(String(128))
    phone: Mapped[str] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CustomerCreditSale(Base):
    __tablename__ = "customer_credit_sales"
    __table_args__ = (
        UniqueConstraint("sale_id", name="uq_customer_credit_sales_sale"),
        CheckConstraint(
            "amount >= 0", name="ck_customer_credit_sales_amount_nonnegative"
        ),
        Index("ix_customer_credit_sales_customer_created", "customer_id", "created_at"),
        Index("ix_customer_credit_sales_sale_id", "sale_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("credit_customers.id", ondelete="RESTRICT")
    )
    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CustomerCreditPayment(Base):
    __tablename__ = "customer_credit_payments"
    __table_args__ = (
        CheckConstraint(
            "amount > 0", name="ck_customer_credit_payments_amount_positive"
        ),
        Index("ix_customer_credit_payments_customer_paid_at", "customer_id", "paid_at"),
        Index("ix_customer_credit_payments_session", "pos_session_id"),
        Index("ix_customer_credit_payments_paid_at", "paid_at"),
        Index("ix_customer_credit_payments_user", "pos_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("credit_customers.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    pos_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pos_sessions.id", ondelete="RESTRICT")
    )
    pos_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


__all__ = ["CreditCustomer", "CustomerCreditSale", "CustomerCreditPayment"]
