"""Repository: owns Session usage for the users table."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from models import (
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Supplier,
    SupplierPayment,
)

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")
_CONFIRMED_STATUSES = (
    PurchaseStatus.OPEN,
    PurchaseStatus.PARTIALLY_PAID,
    PurchaseStatus.PAID,
)


class SupplierRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_all(self) -> list[Supplier]:
        with self._session_factory() as session:
            return list(session.scalars(select(Supplier).order_by(Supplier.name)))

    def get(self, supplier_id: uuid.UUID) -> Supplier | None:
        with self._session_factory() as session:
            return session.get(Supplier, supplier_id)

    def save(self, supplier: Supplier) -> Supplier:
        with self._session_factory() as session:
            managed = session.merge(supplier)
            session.commit()
            session.refresh(managed)
            return managed

    def list_with_summaries(self) -> list[tuple[Supplier, int, Decimal, Decimal, datetime | None]]:
        with self._session_factory() as session:
            purchase_totals = (
                select(
                    Purchase.supplier_id,
                    func.count(Purchase.id).label("purchase_count"),
                    func.coalesce(func.sum(Purchase.total), 0).label("total"),
                    func.max(Purchase.purchase_date).label("last_purchase_date"),
                )
                .where(
                    Purchase.status.in_(
                        (
                            PurchaseStatus.OPEN,
                            PurchaseStatus.PARTIALLY_PAID,
                            PurchaseStatus.PAID,
                        )
                    )
                )
                .group_by(Purchase.supplier_id)
                .subquery()
            )
            payment_totals = (
                select(
                    SupplierPayment.supplier_id,
                    func.coalesce(func.sum(SupplierPayment.amount), 0).label("paid"),
                )
                .group_by(SupplierPayment.supplier_id)
                .subquery()
            )
            statement = (
                select(
                    Supplier,
                    func.coalesce(purchase_totals.c.purchase_count, 0),
                    func.coalesce(purchase_totals.c.total, 0),
                    func.coalesce(payment_totals.c.paid, 0),
                    purchase_totals.c.last_purchase_date,
                )
                .outerjoin(purchase_totals, purchase_totals.c.supplier_id == Supplier.id)
                .outerjoin(payment_totals, payment_totals.c.supplier_id == Supplier.id)
                .order_by(Supplier.name)
            )
            return list(session.execute(statement).all())

    def get_history(
        self, supplier_id: uuid.UUID
    ) -> tuple[list[tuple[Purchase, str, Decimal]], list[SupplierPayment]]:
        with self._session_factory() as session:
            payments = list(
                session.scalars(
                    select(SupplierPayment)
                    .where(SupplierPayment.supplier_id == supplier_id)
                    .order_by(SupplierPayment.payment_date, SupplierPayment.id)
                )
            )
            payment_totals = (
                select(SupplierPayment.purchase_id, func.sum(SupplierPayment.amount).label("paid"))
                .where(SupplierPayment.purchase_id.is_not(None))
                .group_by(SupplierPayment.purchase_id)
                .subquery()
            )
            purchases = list(
                session.execute(
                    select(Purchase, Supplier.name, func.coalesce(payment_totals.c.paid, 0))
                    .join(Supplier, Supplier.id == Purchase.supplier_id)
                    .outerjoin(payment_totals, payment_totals.c.purchase_id == Purchase.id)
                    .where(Purchase.supplier_id == supplier_id)
                    .order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
                ).all()
            )
            return [(row[0], row[1], row[2]) for row in purchases], payments

    def get_account(
        self,
        supplier_id: uuid.UUID,
        from_datetime: datetime | None,
        to_datetime: datetime | None,
    ) -> tuple[
        list[tuple[Purchase, Decimal, Decimal]],
        list[tuple[SupplierPayment, str | None]],
        Decimal,
    ]:
        """Documents and payments dated in ``[from, to)`` plus all-time debt."""
        with self._session_factory() as session:
            paid_total = (
                select(func.coalesce(func.sum(SupplierPayment.amount), 0))
                .where(SupplierPayment.purchase_id == Purchase.id)
                .correlate(Purchase)
                .scalar_subquery()
            )
            item_quantity = (
                select(func.coalesce(func.sum(PurchaseItem.quantity), 0))
                .where(PurchaseItem.purchase_id == Purchase.id)
                .correlate(Purchase)
                .scalar_subquery()
            )
            purchases_statement = (
                select(Purchase, paid_total, item_quantity)
                .where(Purchase.supplier_id == supplier_id)
                .order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
            )
            payments_statement = (
                select(SupplierPayment, Purchase.purchase_number)
                .outerjoin(Purchase, Purchase.id == SupplierPayment.purchase_id)
                .where(SupplierPayment.supplier_id == supplier_id)
                .order_by(
                    SupplierPayment.payment_date.desc(), SupplierPayment.id.desc()
                )
            )
            if from_datetime is not None:
                purchases_statement = purchases_statement.where(
                    Purchase.purchase_date >= from_datetime
                )
                payments_statement = payments_statement.where(
                    SupplierPayment.payment_date >= from_datetime
                )
            if to_datetime is not None:
                purchases_statement = purchases_statement.where(
                    Purchase.purchase_date < to_datetime
                )
                payments_statement = payments_statement.where(
                    SupplierPayment.payment_date < to_datetime
                )
            purchases = [
                (row[0], Decimal(row[1]), Decimal(row[2]))
                for row in session.execute(purchases_statement).all()
            ]
            payments = [
                (row[0], row[1]) for row in session.execute(payments_statement).all()
            ]
            purchased = session.scalar(
                select(func.coalesce(func.sum(Purchase.total), 0)).where(
                    Purchase.supplier_id == supplier_id,
                    Purchase.status.in_(_CONFIRMED_STATUSES),
                )
            )
            paid = session.scalar(
                select(func.coalesce(func.sum(SupplierPayment.amount), 0)).where(
                    SupplierPayment.supplier_id == supplier_id
                )
            )
            return purchases, payments, Decimal(purchased or 0) - Decimal(paid or 0)

