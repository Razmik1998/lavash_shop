"""Repository: owns Session usage for the users table."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from models import (
    InventoryMovement,
    InventoryMovementType,
    PaymentMethod,
    Product,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Supplier,
    SupplierPayment,
    Sale,
    SaleItem,
    SaleStatus,
    Unit,
)

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


class PurchaseRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def procurement_recommendations(self) -> list[dict[str, Any]]:
        """Combine current stock, recent sales, and confirmed supplier costs."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        with self._session_factory() as session:
            sales = (
                select(SaleItem.product_id, func.coalesce(func.sum(SaleItem.quantity), 0).label("sold_30d"))
                .join(Sale, Sale.id == SaleItem.sale_id)
                .join(Product, Product.id == SaleItem.product_id)
                .where(Sale.status == SaleStatus.COMPLETED, SaleItem.is_active, Product.is_for_sale.is_(True), Sale.created_at >= cutoff)
                .group_by(SaleItem.product_id)
                .subquery()
            )
            costs = (
                select(
                    PurchaseItem.product_id,
                    Supplier.id.label("supplier_id"),
                    Supplier.name.label("supplier_name"),
                    Supplier.phone.label("supplier_phone"),
                    Supplier.is_active.label("supplier_active"),
                    (
                        func.sum(PurchaseItem.unit_cost * PurchaseItem.quantity)
                        / func.nullif(func.sum(PurchaseItem.quantity), 0)
                    ).label("average_cost"),
                    func.min(PurchaseItem.unit_cost).label("lowest_cost"),
                    func.max(Purchase.purchase_date).label("last_purchase"),
                    func.count(func.distinct(Purchase.id)).label("purchase_count"),
                )
                .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
                .join(Supplier, Supplier.id == Purchase.supplier_id)
                .where(Purchase.status.in_((PurchaseStatus.OPEN, PurchaseStatus.PARTIALLY_PAID, PurchaseStatus.PAID)))
                .group_by(PurchaseItem.product_id, Supplier.id, Supplier.name, Supplier.phone, Supplier.is_active)
                .subquery()
            )
            statement = (
                select(Product, func.coalesce(sales.c.sold_30d, 0), costs.c.supplier_id,
                       costs.c.supplier_name, costs.c.supplier_phone, costs.c.supplier_active,
                       costs.c.average_cost, costs.c.lowest_cost,
                       costs.c.last_purchase, costs.c.purchase_count)
                .outerjoin(sales, sales.c.product_id == Product.id)
                .outerjoin(costs, costs.c.product_id == Product.id)
                .where(Product.is_active, Product.is_for_sale.is_(True), Product.unit != Unit.BARBECUE)
                .order_by(Product.name, costs.c.average_cost)
            )
            records: dict[uuid.UUID, dict[str, Any]] = {}
            for product, sold, supplier_id, supplier_name, phone, active, avg, low, last, count in session.execute(statement):
                row = records.setdefault(product.id, {"product": product, "sold_30d": Decimal(sold or 0), "suppliers": []})
                if supplier_id is not None:
                    row["suppliers"].append({"id": supplier_id, "name": supplier_name,
                        "phone": phone, "active": active,
                        "average_cost": Decimal(avg), "lowest_cost": Decimal(low),
                        "last_purchase": last, "purchase_count": int(count)})
            return list(records.values())

    def create_draft(
        self,
        purchase: Purchase,
        items: list[PurchaseItem],
    ) -> Purchase:
        with self._session_factory() as session:
            supplier = session.get(Supplier, purchase.supplier_id)
            if supplier is None or not supplier.is_active:
                raise ValueError("Supplier not found")
            session.add(purchase)
            session.flush()
            for item in items:
                item.purchase_id = purchase.id
                session.add(item)
            session.commit()
            session.refresh(purchase)
            return purchase

    def list_purchases(
        self, filters: Any = None
    ) -> list[tuple[Purchase, str, Decimal, Decimal]]:
        with self._session_factory() as session:
            payments = (
                select(SupplierPayment.purchase_id, func.coalesce(func.sum(SupplierPayment.amount), 0).label("paid"))
                .where(SupplierPayment.purchase_id.is_not(None))
                .group_by(SupplierPayment.purchase_id)
                .subquery()
            )
            item_totals = (
                select(PurchaseItem.purchase_id, func.coalesce(func.sum(PurchaseItem.quantity), 0).label("item_quantity"))
                .group_by(PurchaseItem.purchase_id)
                .subquery()
            )
            statement = (
                select(Purchase, Supplier.name, func.coalesce(payments.c.paid, 0), func.coalesce(item_totals.c.item_quantity, 0))
                .join(Supplier, Supplier.id == Purchase.supplier_id)
                .outerjoin(payments, payments.c.purchase_id == Purchase.id)
                .outerjoin(item_totals, item_totals.c.purchase_id == Purchase.id)
                .order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
            )
            if filters is not None:
                if filters.from_datetime is not None:
                    statement = statement.where(
                        Purchase.purchase_date >= filters.from_datetime
                    )
                if filters.to_datetime is not None:
                    statement = statement.where(
                        Purchase.purchase_date <= filters.to_datetime
                    )
                if filters.supplier_id is not None:
                    statement = statement.where(
                        Purchase.supplier_id == filters.supplier_id
                    )
                if filters.status is not None:
                    statement = statement.where(Purchase.status == filters.status)
                if filters.search:
                    pattern = f"%{filters.search}%"
                    matching_product = select(PurchaseItem.id).where(
                        PurchaseItem.purchase_id == Purchase.id,
                        or_(
                            PurchaseItem.product_name.ilike(pattern),
                            PurchaseItem.product_sku.ilike(pattern),
                        ),
                    ).exists()
                    statement = statement.where(
                        or_(
                            Purchase.purchase_number.ilike(pattern),
                            Supplier.name.ilike(pattern),
                            matching_product,
                        )
                    )
            return [
                (row[0], row[1], row[2], row[3])
                for row in session.execute(statement).all()
            ]

    def list_purchase_page(
        self, filters: Any, offset: int, limit: int
    ) -> list[tuple[Purchase, str, Decimal, Decimal]]:
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
            statement = (
                select(Purchase, Supplier.name, paid_total, item_quantity)
                .join(Supplier, Supplier.id == Purchase.supplier_id)
                .order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
                .offset(offset)
                .limit(limit)
            )
            if filters.supplier_id is not None:
                statement = statement.where(Purchase.supplier_id == filters.supplier_id)
            if filters.status is not None:
                statement = statement.where(Purchase.status == filters.status)
            return [
                (row[0], row[1], Decimal(row[2]), Decimal(row[3]))
                for row in session.execute(statement).all()
            ]
    def summarize_purchases(self, filters: Any = None) -> tuple[int, Decimal, Decimal, int]:
        with self._session_factory() as session:
            statement = select(Purchase.id, Purchase.total, Purchase.status)
            if filters is not None:
                if filters.from_datetime is not None:
                    statement = statement.where(Purchase.purchase_date >= filters.from_datetime)
                if filters.to_datetime is not None:
                    statement = statement.where(Purchase.purchase_date <= filters.to_datetime)
                if filters.supplier_id is not None:
                    statement = statement.where(Purchase.supplier_id == filters.supplier_id)
                if filters.status is not None:
                    statement = statement.where(Purchase.status == filters.status)
                if filters.search:
                    pattern = f"%{filters.search}%"
                    statement = statement.where(Purchase.purchase_number.ilike(pattern))
            filtered = statement.subquery()
            item_totals = (
                select(PurchaseItem.purchase_id, func.sum(PurchaseItem.quantity).label("quantity"))
                .group_by(PurchaseItem.purchase_id)
                .subquery()
            )
            row = session.execute(
                select(
                    func.count(filtered.c.id),
                    func.coalesce(func.sum(filtered.c.total), 0),
                    func.coalesce(func.sum(item_totals.c.quantity), 0),
                    func.coalesce(func.sum((filtered.c.status == PurchaseStatus.DRAFT).cast(Integer)), 0),
                ).select_from(filtered.outerjoin(item_totals, filtered.c.id == item_totals.c.purchase_id))
            ).one()
            return int(row[0]), Decimal(row[1]), Decimal(row[2]), int(row[3])

    def supplier_report(
        self, filters: Any = None
    ) -> list[tuple[uuid.UUID, str, int, Decimal, Decimal, Decimal]]:
        with self._session_factory() as session:
            purchases = select(Purchase.id, Purchase.supplier_id, Purchase.total)
            purchases = purchases.where(
                Purchase.status.in_(
                    (
                        PurchaseStatus.OPEN,
                        PurchaseStatus.PARTIALLY_PAID,
                        PurchaseStatus.PAID,
                    )
                )
            )
            if filters is not None:
                if filters.from_datetime is not None:
                    purchases = purchases.where(
                        Purchase.purchase_date >= filters.from_datetime
                    )
                if filters.to_datetime is not None:
                    purchases = purchases.where(
                        Purchase.purchase_date <= filters.to_datetime
                    )
                if filters.supplier_id is not None:
                    purchases = purchases.where(
                        Purchase.supplier_id == filters.supplier_id
                    )
                if filters.search:
                    pattern = f"%{filters.search}%"
                    matching_product = select(PurchaseItem.id).where(
                        PurchaseItem.purchase_id == Purchase.id,
                        or_(
                            PurchaseItem.product_name.ilike(pattern),
                            PurchaseItem.product_sku.ilike(pattern),
                        ),
                    ).exists()
                    purchases = purchases.join(
                        Supplier, Supplier.id == Purchase.supplier_id
                    ).where(
                        or_(Supplier.name.ilike(pattern), matching_product)
                    )
            purchase_rows = purchases.subquery()
            purchase_totals = (
                select(
                    purchase_rows.c.supplier_id,
                    func.count(purchase_rows.c.id).label("purchase_count"),
                    func.coalesce(func.sum(purchase_rows.c.total), 0).label("amount"),
                )
                .group_by(purchase_rows.c.supplier_id)
                .subquery()
            )
            quantities = (
                select(
                    purchase_rows.c.supplier_id,
                    func.coalesce(func.sum(PurchaseItem.quantity), 0).label(
                        "quantity"
                    ),
                )
                .join(
                    PurchaseItem,
                    PurchaseItem.purchase_id == purchase_rows.c.id,
                )
                .group_by(purchase_rows.c.supplier_id)
                .subquery()
            )
            payments = (
                select(
                    purchase_rows.c.supplier_id,
                    func.coalesce(func.sum(SupplierPayment.amount), 0).label("paid"),
                )
                .join(
                    SupplierPayment,
                    SupplierPayment.purchase_id == purchase_rows.c.id,
                )
                .group_by(purchase_rows.c.supplier_id)
                .subquery()
            )
            statement = (
                select(
                    Supplier.id,
                    Supplier.name,
                    purchase_totals.c.purchase_count,
                    quantities.c.quantity,
                    purchase_totals.c.amount,
                    func.coalesce(payments.c.paid, 0),
                )
                .join(purchase_totals, purchase_totals.c.supplier_id == Supplier.id)
                .outerjoin(quantities, quantities.c.supplier_id == Supplier.id)
                .outerjoin(payments, payments.c.supplier_id == Supplier.id)
                .order_by(Supplier.name)
            )
            return [
                (
                    row[0],
                    row[1],
                    int(row[2]),
                    Decimal(row[3] or 0),
                    Decimal(row[4] or 0),
                    Decimal(row[5] or 0),
                )
                for row in session.execute(statement).all()
            ]

    def update_draft(
        self, purchase_id: uuid.UUID, purchase: Purchase, items: list[PurchaseItem]
    ) -> Purchase:
        with self._session_factory() as session:
            managed = session.scalar(
                select(Purchase).where(Purchase.id == purchase_id).with_for_update()
            )
            if managed is None or managed.status not in {
                PurchaseStatus.DRAFT,
                PurchaseStatus.OPEN,
            }:
                raise ValueError("Only open purchases can be edited")
            supplier = session.get(Supplier, purchase.supplier_id)
            if supplier is None or not supplier.is_active:
                raise ValueError("Supplier not found or inactive")
            managed.supplier_id = purchase.supplier_id
            managed.purchase_date = purchase.purchase_date
            managed.notes = purchase.notes
            managed.total = purchase.total
            session.query(PurchaseItem).filter(
                PurchaseItem.purchase_id == purchase_id
            ).delete(synchronize_session=False)
            for item in items:
                item.id = uuid.uuid4()
                item.purchase_id = purchase_id
                session.add(item)
            session.commit()
            session.refresh(managed)
            return managed

    def reopen_for_edit(self, purchase_id: uuid.UUID) -> Purchase:
        """Rewind one completed purchase into an editable open document.

        This deliberately reverses current stock and supplier balance in the
        same transaction. Selling prices are never changed by the rewind.
        """
        with self._session_factory() as session:
            purchase = session.scalar(
                select(Purchase).where(Purchase.id == purchase_id).with_for_update()
            )
            if purchase is None:
                raise ValueError("Purchase not found")
            if purchase.status is PurchaseStatus.DRAFT:
                session.commit()
                return purchase
            if purchase.status is PurchaseStatus.CANCELLED:
                raise ValueError("Cancelled purchases cannot be edited")

            items = list(
                session.scalars(
                    select(PurchaseItem)
                    .where(PurchaseItem.purchase_id == purchase_id)
                    .order_by(PurchaseItem.product_id)
                    .with_for_update()
                )
            )
            receipt_count = session.scalar(
                select(func.count(InventoryMovement.id)).where(
                    InventoryMovement.purchase_item_id.in_([item.id for item in items]),
                    InventoryMovement.movement_type == InventoryMovementType.RECEIPT,
                )
            )
            if not receipt_count:
                purchase.status = PurchaseStatus.DRAFT
                session.commit()
                return purchase
            for item in items:
                product = session.scalar(
                    select(Product).where(Product.id == item.product_id).with_for_update()
                )
                if product is None or product.quantity_in_stock < item.quantity:
                    raise ValueError("Insufficient stock to reopen purchase")
                product.quantity_in_stock -= item.quantity

            session.query(InventoryMovement).filter(
                InventoryMovement.purchase_item_id.in_([item.id for item in items])
            ).delete(synchronize_session=False)
            session.query(SupplierPayment).filter(
                SupplierPayment.purchase_id == purchase_id
            ).delete(synchronize_session=False)
            purchase.status = PurchaseStatus.DRAFT
            session.commit()
            session.refresh(purchase)
            return purchase

    def delete_draft(self, purchase_id: uuid.UUID) -> None:
        with self._session_factory() as session:
            purchase = session.scalar(
                select(Purchase).where(Purchase.id == purchase_id).with_for_update()
            )
            if purchase is None or purchase.status is not PurchaseStatus.DRAFT:
                raise ValueError("Only draft purchases can be deleted")
            session.query(PurchaseItem).filter(
                PurchaseItem.purchase_id == purchase_id
            ).delete(synchronize_session=False)
            session.delete(purchase)
            session.commit()

    def get_detail(self, purchase_id: uuid.UUID) -> tuple[Purchase, list[PurchaseItem], list[SupplierPayment]] | None:
        with self._session_factory() as session:
            purchase = session.get(Purchase, purchase_id)
            if purchase is None:
                return None
            items = list(session.scalars(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id)))
            payments = list(session.scalars(select(SupplierPayment).where(SupplierPayment.purchase_id == purchase_id).order_by(SupplierPayment.payment_date)))
            return purchase, items, payments

    def confirm(
        self,
        purchase_id: uuid.UUID,
        initial_payment: Decimal,
        payment_method: PaymentMethod,
        price_updates: dict[uuid.UUID, Decimal],
    ) -> Purchase:
        with self._session_factory() as session:
            purchase = session.scalar(select(Purchase).where(Purchase.id == purchase_id).with_for_update())
            if purchase is None:
                raise ValueError("Purchase not found")
            if purchase.status not in {PurchaseStatus.DRAFT, PurchaseStatus.OPEN}:
                raise ValueError("Purchase is already confirmed")
            items = list(session.scalars(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id).order_by(PurchaseItem.product_id).with_for_update()))
            if not items:
                raise ValueError("Purchase must contain items")
            products = []
            for item in items:
                product = session.scalar(select(Product).where(Product.id == item.product_id).with_for_update())
                if product is None or not product.is_active:
                    raise ValueError("Purchase product is unavailable")
                products.append(product)
            if initial_payment < 0 or initial_payment > purchase.total:
                raise ValueError("Invalid initial payment")
            for item, product in zip(items, products, strict=True):
                product.quantity_in_stock += item.quantity
                product.cost_price = item.unit_cost
                if product.is_for_sale is not False and product.id in price_updates:
                    new_price = price_updates[product.id]
                    if new_price < 0:
                        raise ValueError("Selling price cannot be negative")
                    product.selling_price = new_price
                session.add(InventoryMovement(purchase_item_id=item.id, product_id=product.id, movement_type=InventoryMovementType.RECEIPT, quantity=item.quantity))
            if initial_payment:
                session.add(SupplierPayment(supplier_id=purchase.supplier_id, purchase_id=purchase.id, amount=initial_payment, payment_date=datetime.now(ARMENIA_TIMEZONE), method=payment_method))
            purchase.status = PurchaseStatus.PAID if initial_payment == purchase.total else (PurchaseStatus.PARTIALLY_PAID if initial_payment else PurchaseStatus.OPEN)
            session.commit()
            session.refresh(purchase)
            return purchase

    def add_payment(self, purchase_id: uuid.UUID, amount: Decimal, method: PaymentMethod, payment_date: datetime, notes: str | None) -> SupplierPayment:
        with self._session_factory() as session:
            purchase = session.scalar(select(Purchase).where(Purchase.id == purchase_id).with_for_update())
            if purchase is None or purchase.status in {
                PurchaseStatus.DRAFT,
                PurchaseStatus.CANCELLED,
            }:
                raise ValueError("Purchase cannot receive payment")
            paid = session.scalar(select(func.coalesce(func.sum(SupplierPayment.amount), 0)).where(SupplierPayment.purchase_id == purchase_id))
            if amount <= 0 or amount > purchase.total - Decimal(paid or 0):
                raise ValueError("Payment exceeds purchase balance")
            payment = SupplierPayment(supplier_id=purchase.supplier_id, purchase_id=purchase.id, amount=amount, payment_date=payment_date, method=method, notes=notes)
            session.add(payment)
            new_paid = Decimal(paid or 0) + amount
            purchase.status = PurchaseStatus.PAID if new_paid == purchase.total else PurchaseStatus.PARTIALLY_PAID
            session.commit()
            session.refresh(payment)
            return payment

    def pay_supplier_debt(
        self,
        supplier_id: uuid.UUID,
        amount: Decimal,
        method: PaymentMethod,
        payment_date: datetime,
        from_datetime: datetime | None,
        to_datetime: datetime | None,
    ) -> int:
        """Spread one payment over unpaid documents, oldest first.

        Only documents dated in ``[from, to)`` are paid. Everything happens in
        one transaction; returns how many documents received a payment.
        """
        with self._session_factory() as session:
            statement = (
                select(Purchase)
                .where(
                    Purchase.supplier_id == supplier_id,
                    Purchase.status.in_(
                        (PurchaseStatus.OPEN, PurchaseStatus.PARTIALLY_PAID)
                    ),
                )
                .order_by(Purchase.purchase_date, Purchase.id)
                .with_for_update()
            )
            if from_datetime is not None:
                statement = statement.where(Purchase.purchase_date >= from_datetime)
            if to_datetime is not None:
                statement = statement.where(Purchase.purchase_date < to_datetime)
            purchases = list(session.scalars(statement))
            paid_by_purchase = {
                row[0]: Decimal(row[1])
                for row in session.execute(
                    select(SupplierPayment.purchase_id, func.sum(SupplierPayment.amount))
                    .where(
                        SupplierPayment.purchase_id.in_([p.id for p in purchases])
                    )
                    .group_by(SupplierPayment.purchase_id)
                ).all()
            }
            remaining = amount
            paid_documents = 0
            for purchase in purchases:
                if remaining <= 0:
                    break
                debt = purchase.total - paid_by_purchase.get(purchase.id, Decimal("0"))
                if debt <= 0:
                    continue
                part = min(debt, remaining)
                session.add(
                    SupplierPayment(
                        supplier_id=supplier_id,
                        purchase_id=purchase.id,
                        amount=part,
                        payment_date=payment_date,
                        method=method,
                    )
                )
                purchase.status = (
                    PurchaseStatus.PAID if part == debt else PurchaseStatus.PARTIALLY_PAID
                )
                remaining -= part
                paid_documents += 1
            if remaining > 0:
                supplier = session.get(Supplier, supplier_id)
                opening_balance_available = (
                    supplier is not None
                    and from_datetime is None
                    and to_datetime is None
                )
                opening_paid = Decimal("0")
                if opening_balance_available:
                    opening_paid = Decimal(
                        session.scalar(
                            select(func.coalesce(func.sum(SupplierPayment.amount), 0))
                            .where(
                                SupplierPayment.supplier_id == supplier_id,
                                SupplierPayment.purchase_id.is_(None),
                            )
                        )
                        or 0
                    )
                opening_debt_left = (
                    Decimal(supplier.opening_debt) - opening_paid
                    if opening_balance_available and supplier is not None
                    else Decimal("0")
                )
                if remaining > opening_debt_left:
                    raise ValueError("Payment exceeds supplier debt")
                # The opening balance has no purchase document to attach a
                # payment to, so record its payment without a purchase ID.
                session.add(
                    SupplierPayment(
                        supplier_id=supplier_id,
                        purchase_id=None,
                        amount=remaining,
                        payment_date=payment_date,
                        method=method,
                        notes="Նախկին պարտքի մարում",
                    )
                )
            session.commit()
            return paid_documents

    def cancel(self, purchase_id: uuid.UUID) -> Purchase:
        with self._session_factory() as session:
            purchase = session.scalar(select(Purchase).where(Purchase.id == purchase_id).with_for_update())
            if purchase is None:
                raise ValueError("Purchase not found")
            if purchase.status is PurchaseStatus.DRAFT:
                purchase.status = PurchaseStatus.CANCELLED
                session.commit()
                return purchase
            if purchase.status is PurchaseStatus.CANCELLED:
                return purchase
            payment_count = session.scalar(select(func.count(SupplierPayment.id)).where(SupplierPayment.purchase_id == purchase_id))
            if payment_count:
                raise ValueError("Paid purchases cannot be cancelled")
            items = list(session.scalars(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id).order_by(PurchaseItem.product_id).with_for_update()))
            for item in items:
                product = session.scalar(select(Product).where(Product.id == item.product_id).with_for_update())
                if product is None or product.quantity_in_stock < item.quantity:
                    raise ValueError("Insufficient stock for cancellation")
                product.quantity_in_stock -= item.quantity
                session.add(InventoryMovement(purchase_item_id=item.id, product_id=item.product_id, movement_type=InventoryMovementType.REVERSAL, quantity=item.quantity))
            purchase.status = PurchaseStatus.CANCELLED
            session.commit()
            session.refresh(purchase)
            return purchase
