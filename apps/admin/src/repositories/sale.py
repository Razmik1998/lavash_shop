"""Repository: owns Session usage for the users table."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased, sessionmaker

from exceptions import (
    InvalidSaleUnlockKeyError,
    SaleAlreadyEditingError,
    SaleNotEditableError,
)
from models import (
    CreditCustomer,
    CustomerCreditSale,
    Product,
    Sale,
    SaleAuditEvent,
    SaleInventoryAdjustment,
    SaleItem,
    SaleItemAction,
    SaleItemChange,
    SaleRevision,
    SaleRevisionOutcome,
    SaleStatus,
    SaleUnlockKey,
    User,
)
from security import hash_password, verify_password

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


class SaleRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_by_client_id(self, client_sale_id: uuid.UUID) -> Sale | None:
        with self._session_factory() as session:
            return session.scalar(
                select(Sale).where(Sale.client_sale_id == client_sale_id)
            )

    def analytics_rows(
        self, start_at: datetime, end_at: datetime
    ) -> list[tuple[Any, ...]]:
        """Return completed sale item snapshots in a half-open time window."""
        with self._session_factory() as session:
            return list(
                session.execute(
                    select(
                        Sale.id,
                        Sale.created_at,
                        Sale.total,
                        SaleItem.product_name,
                        SaleItem.product_sku,
                        SaleItem.unit,
                        SaleItem.quantity,
                        SaleItem.line_total,
                        SaleItem.cost_price,
                    )
                    .join(SaleItem, SaleItem.sale_id == Sale.id)
                    .join(Product, Product.id == SaleItem.product_id)
                    .where(
                        Sale.status == SaleStatus.COMPLETED,
                        SaleItem.is_active.is_(True),
                        Product.is_for_sale.is_(True),
                        Sale.created_at >= start_at,
                        Sale.created_at < end_at,
                    )
                    .order_by(Sale.created_at, Sale.id)
                )
            )

    def create_sale(
        self,
        session_id: uuid.UUID,
        employee_user_id: uuid.UUID,
        terminal_id: str,
        client_sale_id: uuid.UUID,
        lines: list[tuple[Product, Decimal, Decimal, Decimal]],
        credit_customer_id: uuid.UUID | None = None,
    ) -> Sale:
        with self._session_factory() as session:
            existing = session.scalar(
                select(Sale).where(Sale.client_sale_id == client_sale_id)
            )
            if existing is not None:
                return existing
            total = sum((line[3] for line in lines), Decimal("0"))
            sale = Sale(
                id=uuid.uuid4(),
                pos_session_id=session_id,
                employee_user_id=employee_user_id,
                terminal_id=terminal_id,
                client_sale_id=client_sale_id,
                status=SaleStatus.COMPLETED,
                total=total,
            )
            session.add(sale)
            session.flush()
            if credit_customer_id is not None:
                customer = session.scalar(
                    select(CreditCustomer).where(
                        CreditCustomer.id == credit_customer_id,
                        CreditCustomer.is_active,
                    )
                )
                if customer is None:
                    raise ValueError("Credit customer not found")
                session.add(
                    CustomerCreditSale(
                        customer_id=credit_customer_id,
                        sale_id=sale.id,
                        amount=total,
                    )
                )
            for product, quantity, unit_price, line_total in lines:
                parent = (
                    session.get(Product, product.parent_product_id)
                    if product.parent_product_id is not None
                    else None
                )
                session.add(
                    SaleItem(
                        sale_id=sale.id,
                        product_id=product.id,
                        product_name=product.display_name(parent),
                        product_sku=product.sku,
                        unit=product.unit.value,
                        quantity=quantity,
                        cost_price=product.cost_price,
                        unit_price=unit_price,
                        original_unit_price=product.selling_price or unit_price,
                        discount_amount=(
                            (product.selling_price or unit_price) - unit_price
                        )
                        * quantity,
                        line_total=line_total,
                    )
                )
            session.add(
                SaleRevision(
                    sale_id=sale.id,
                    revision_number=0,
                    status=SaleStatus.COMPLETED.value,
                    total=total,
                    closed_total=total,
                    outcome=SaleRevisionOutcome.CREATED.value,
                    changed_by_user_id=employee_user_id,
                    closed_at=func.now(),
                )
            )
            session.add(
                SaleAuditEvent(
                    sale_id=sale.id,
                    pos_session_id=session_id,
                    terminal_id=terminal_id,
                    employee_user_id=employee_user_id,
                    actor_user_id=employee_user_id,
                    event_type="created",
                    new_value={
                        "total": str(total),
                        **_payment_state(session, credit_customer_id),
                    },
                )
            )
            session.commit()
            session.refresh(sale)
            return sale

    def list_sales(
        self,
        filters: Any,
        cursor: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[
        tuple[Sale, str, Decimal, Decimal, Decimal | None, str | None, uuid.UUID | None]
    ]:
        with self._session_factory() as session:
            income = _sale_item_total(Sale, filters, "income")
            revenue = _sale_item_total(Sale, filters, "revenue")
            credit_amount = func.coalesce(CustomerCreditSale.amount, None)
            statement = select(
                Sale,
                User.full_name,
                income.label("income"),
                revenue.label("revenue"),
                CustomerCreditSale.customer_id,
                credit_amount.label("credit_amount"),
                (CreditCustomer.first_name + " " + CreditCustomer.last_name).label(
                    "credit_customer_name"
                ),
            ).join(User, Sale.employee_user_id == User.id)
            statement = statement.outerjoin(
                CustomerCreditSale, CustomerCreditSale.sale_id == Sale.id
            ).outerjoin(
                CreditCustomer, CreditCustomer.id == CustomerCreditSale.customer_id
            )
            statement = _apply_sale_filters(statement, filters)
            if cursor is not None:
                created_at, sale_id = cursor
                statement = statement.where(
                    (Sale.created_at < created_at)
                    | ((Sale.created_at == created_at) & (Sale.id < sale_id))
                )
            statement = statement.order_by(
                Sale.created_at.desc(), Sale.id.desc()
            ).limit(limit + 1)
            rows = []
            for (
                sale,
                full_name,
                income,
                revenue,
                customer_id,
                credit,
                customer_name,
            ) in session.execute(statement):
                rows.append(
                    (
                        sale,
                        full_name,
                        income,
                        revenue,
                        customer_id,
                        credit,
                        customer_name,
                    )
                )
            return rows

    def summarize_sales(
        self, filters: Any
    ) -> tuple[int, Decimal, Decimal, Decimal, Decimal]:
        with self._session_factory() as session:
            filtered = _apply_sale_filters(
                select(Sale.id).where(Sale.status == SaleStatus.COMPLETED), filters
            ).subquery()
            item_statement = select(
                SaleItem.sale_id,
                func.sum(SaleItem.quantity).label("quantity"),
                func.sum(
                    (SaleItem.unit_price - func.coalesce(SaleItem.cost_price, 0))
                    * SaleItem.quantity
                ).label("income"),
                func.sum(SaleItem.line_total).label("revenue"),
            ).join(Product, Product.id == SaleItem.product_id).where(
                SaleItem.is_active, Product.is_for_sale.is_(True)
            )
            if getattr(filters, "barbecue_only", False):
                item_statement = item_statement.where(
                    Product.parent_product_id.is_not(None)
                )
            item_totals = item_statement.group_by(SaleItem.sale_id).subquery()
            row = session.execute(
                select(
                    func.count(filtered.c.id),
                    func.coalesce(func.sum(item_totals.c.quantity), 0),
                    func.coalesce(func.sum(item_totals.c.revenue), 0),
                    func.coalesce(func.sum(item_totals.c.income), 0),
                    func.coalesce(func.sum(CustomerCreditSale.amount), 0),
                ).select_from(
                    filtered.outerjoin(
                        item_totals, filtered.c.id == item_totals.c.sale_id
                    ).outerjoin(
                        CustomerCreditSale, CustomerCreditSale.sale_id == filtered.c.id
                    )
                )
            ).one()
            return int(row[0]), row[1], row[2], row[3], row[4]

    def credit_totals_by_sessions(
        self, session_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Decimal]:
        if not session_ids:
            return {}
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    Sale.pos_session_id,
                    func.coalesce(func.sum(CustomerCreditSale.amount), 0),
                )
                .join(CustomerCreditSale, CustomerCreditSale.sale_id == Sale.id)
                .where(
                    Sale.pos_session_id.in_(session_ids),
                    Sale.status == SaleStatus.COMPLETED,
                )
                .group_by(Sale.pos_session_id)
            )
            return {session_id: Decimal(total) for session_id, total in rows}

    def get_credit_info(
        self, sale_id: uuid.UUID
    ) -> tuple[uuid.UUID, Decimal, str] | None:
        with self._session_factory() as session:
            row = session.execute(
                select(
                    CustomerCreditSale.customer_id,
                    CustomerCreditSale.amount,
                    CreditCustomer.first_name + " " + CreditCustomer.last_name,
                )
                .join(
                    CreditCustomer,
                    CreditCustomer.id == CustomerCreditSale.customer_id,
                )
                .where(CustomerCreditSale.sale_id == sale_id)
            ).first()
            return None if row is None else (row[0], row[1], row[2])

    def get_detail(
        self, sale_id: uuid.UUID, *, barbecue_only: bool = False
    ) -> tuple[Sale, list[SaleItem], list[SaleAuditEvent]] | None:
        with self._session_factory() as session:
            sale = session.get(Sale, sale_id)
            if sale is None:
                return None
            item_statement = select(SaleItem).where(
                SaleItem.sale_id == sale_id, SaleItem.is_active
            ).outerjoin(Product, Product.id == SaleItem.product_id).where(
                or_(SaleItem.product_id.is_(None), Product.is_for_sale.is_(True))
            )
            items = list(session.scalars(item_statement))
            if (
                sale.status in {SaleStatus.CANCELLED, SaleStatus.VOIDED}
                and not items
            ):
                latest_revision = session.scalar(
                    select(func.max(SaleItem.revision_number)).where(
                        SaleItem.sale_id == sale_id
                    )
                )
                if latest_revision is not None:
                    items = list(
                        session.scalars(
                            select(SaleItem).outerjoin(
                                Product, Product.id == SaleItem.product_id
                            ).where(
                                SaleItem.sale_id == sale_id,
                                SaleItem.revision_number == latest_revision,
                                or_(
                                    SaleItem.product_id.is_(None),
                                    Product.is_for_sale.is_(True),
                                ),
                            )
                        )
                    )
            if barbecue_only:
                item_product_ids = {
                    item.product_id for item in items if item.product_id is not None
                }
                barbecue_product_ids = set(
                    session.scalars(
                        select(Product.id).where(
                            Product.id.in_(item_product_ids),
                            Product.parent_product_id.is_not(None),
                        )
                    )
                )
                items = [
                    item for item in items if item.product_id in barbecue_product_ids
                ]
            audits = list(
                session.scalars(
                    select(SaleAuditEvent)
                    .where(SaleAuditEvent.sale_id == sale_id)
                    .order_by(SaleAuditEvent.created_at, SaleAuditEvent.id)
                )
            )
            return sale, items, audits

    def get_history(
        self, sale_id: uuid.UUID
    ) -> tuple[
        list[tuple[SaleRevision, str, str]],
        list[tuple[SaleItemChange, str]],
    ]:
        with self._session_factory() as session:
            opener = aliased(User)
            revisions = [
                (revision, closer_name or "", opener_name or "")
                for revision, closer_name, opener_name in session.execute(
                    select(SaleRevision, User.full_name, opener.full_name)
                    .outerjoin(User, User.id == SaleRevision.changed_by_user_id)
                    .outerjoin(opener, opener.id == SaleRevision.unlocked_by_user_id)
                    .where(SaleRevision.sale_id == sale_id)
                    .order_by(SaleRevision.revision_number)
                )
            ]
            changes = [
                (change, name or "")
                for change, name in session.execute(
                    select(SaleItemChange, User.full_name)
                    .outerjoin(User, User.id == SaleItemChange.changed_by_user_id)
                    .outerjoin(SaleItem, SaleItem.id == SaleItemChange.sale_item_id)
                    .outerjoin(Product, Product.id == SaleItem.product_id)
                    .where(SaleItemChange.sale_id == sale_id)
                    .where(
                        or_(SaleItem.product_id.is_(None), Product.is_for_sale.is_(True))
                    )
                    .order_by(SaleItemChange.created_at, SaleItemChange.id)
                )
            ]
            return revisions, changes

    def get_payment_history(
        self, sale_id: uuid.UUID
    ) -> list[tuple[SaleAuditEvent, str]]:
        with self._session_factory() as session:
            return [
                (event, name or "")
                for event, name in session.execute(
                    select(SaleAuditEvent, User.full_name)
                    .outerjoin(User, User.id == SaleAuditEvent.actor_user_id)
                    .where(SaleAuditEvent.sale_id == sale_id)
                    .order_by(SaleAuditEvent.created_at, SaleAuditEvent.id)
                )
            ]

    def list_key_history(
        self,
        key_id: uuid.UUID,
        from_datetime: datetime | None,
        to_datetime: datetime | None,
    ) -> list[tuple[SaleAuditEvent, Sale, str]]:
        with self._session_factory() as session:
            statement = (
                select(SaleAuditEvent, Sale, User.full_name)
                .join(Sale, Sale.id == SaleAuditEvent.sale_id)
                .join(User, User.id == SaleAuditEvent.actor_user_id)
                .where(SaleAuditEvent.authorization_key_id == key_id)
                .order_by(SaleAuditEvent.created_at, SaleAuditEvent.id)
            )
            if from_datetime is not None:
                statement = statement.where(SaleAuditEvent.created_at >= from_datetime)
            if to_datetime is not None:
                statement = statement.where(SaleAuditEvent.created_at < to_datetime)
            return list(session.execute(statement))

    def create_unlock_key(
        self, name: str, plain_key: str, created_by_user_id: uuid.UUID
    ) -> SaleUnlockKey:
        with self._session_factory() as session:
            key = SaleUnlockKey(
                name=name.strip(),
                key_hash=hash_password(plain_key),
                created_by_user_id=created_by_user_id,
            )
            session.add(key)
            session.commit()
            session.refresh(key)
            return key

    def list_unlock_keys(self) -> list[SaleUnlockKey]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(SaleUnlockKey).order_by(SaleUnlockKey.created_at.desc())
                )
            )

    def set_unlock_key_active(self, key_id: uuid.UUID, is_active: bool) -> None:
        with self._session_factory() as session:
            key = session.get(SaleUnlockKey, key_id)
            if key is None:
                raise InvalidSaleUnlockKeyError("Unlock key not found")
            key.is_active = is_active
            session.commit()

    def unlock_sale(
        self, sale_id: uuid.UUID, actor_user_id: uuid.UUID, plain_key: str
    ) -> int:
        with self._session_factory() as session:
            sale = session.scalar(
                select(Sale).where(Sale.id == sale_id).with_for_update()
            )
            if sale is None:
                raise SaleNotEditableError("Sale not found")
            if sale.status is not SaleStatus.COMPLETED:
                raise SaleAlreadyEditingError("Sale is not currently confirmed")
            keys = list(
                session.scalars(select(SaleUnlockKey).where(SaleUnlockKey.is_active))
            )
            authorized_key = next(
                (key for key in keys if verify_password(plain_key, key.key_hash)), None
            )
            if authorized_key is None:
                raise InvalidSaleUnlockKeyError("Invalid or inactive unlock key")
            items = list(
                session.scalars(
                    select(SaleItem).where(
                        SaleItem.sale_id == sale_id, SaleItem.is_active
                    )
                )
            )
            prior_revision = session.scalar(
                select(func.max(SaleRevision.revision_number)).where(
                    SaleRevision.sale_id == sale_id
                )
            )
            revision_number = int(prior_revision or 0) + 1
            snapshot = _snapshot_items(items)
            session.add(
                SaleRevision(
                    sale_id=sale.id,
                    revision_number=revision_number,
                    status=sale.status.value,
                    total=sale.total,
                    outcome=SaleRevisionOutcome.UNLOCKED.value,
                    changed_by_user_id=actor_user_id,
                    unlocked_by_user_id=actor_user_id,
                )
            )
            for item in items:
                if item.product_id is not None:
                    product = session.scalar(
                        select(Product)
                        .where(Product.id == item.product_id)
                        .with_for_update()
                    )
                    if product is not None:
                        product.quantity_in_stock = (
                            product.quantity_in_stock or Decimal("0")
                        ) + item.quantity
                        session.add(
                            SaleInventoryAdjustment(
                                sale_id=sale.id,
                                revision_number=revision_number,
                                product_id=product.id,
                                quantity=item.quantity,
                                direction="revert",
                            )
                        )
            sale.status = SaleStatus.EDITING
            sale.current_unlock_key_id = authorized_key.id
            session.add(
                _audit(
                    sale,
                    actor_user_id,
                    "DOCUMENT_UNLOCKED",
                    authorized_key.id,
                    snapshot,
                )
            )
            session.add(
                _audit(
                    sale,
                    actor_user_id,
                    "DOCUMENT_EDIT_STARTED",
                    authorized_key.id,
                    None,
                )
            )
            session.commit()
            return revision_number

    def reconfirm_sale(
        self,
        sale_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        lines: list[tuple[Product, Decimal, Decimal, Decimal]],
        credit_customer_id: uuid.UUID | None = None,
    ) -> Sale:
        with self._session_factory() as session:
            sale = session.scalar(
                select(Sale).where(Sale.id == sale_id).with_for_update()
            )
            if sale is None or sale.status is not SaleStatus.EDITING:
                raise SaleNotEditableError("Sale is not in editing state")
            revision = session.scalar(
                select(SaleRevision)
                .where(
                    SaleRevision.sale_id == sale_id,
                    SaleRevision.outcome == SaleRevisionOutcome.UNLOCKED.value,
                )
                .order_by(SaleRevision.revision_number.desc())
                .limit(1)
            )
            if revision is None:
                last = session.scalar(
                    select(func.max(SaleRevision.revision_number)).where(
                        SaleRevision.sale_id == sale_id
                    )
                )
                revision = SaleRevision(
                    sale_id=sale.id,
                    revision_number=int(last or 0) + 1,
                    status=SaleStatus.COMPLETED.value,
                    total=sale.total,
                    outcome=SaleRevisionOutcome.UNLOCKED.value,
                    changed_by_user_id=actor_user_id,
                )
                session.add(revision)
                session.flush()
            revision_number = revision.revision_number
            total = sum((line[3] for line in lines), Decimal("0"))
            existing: dict[uuid.UUID, SaleItem] = {}
            extra_active: list[SaleItem] = []
            for item in session.scalars(
                select(SaleItem).where(SaleItem.sale_id == sale_id, SaleItem.is_active)
            ):
                if item.product_id is None or item.product_id in existing:
                    extra_active.append(item)
                else:
                    existing[item.product_id] = item
            changes: list[SaleItemChange] = []

            def record(
                item: SaleItem,
                action: SaleItemAction,
                old: dict[str, object] | None,
                new: dict[str, object] | None,
            ) -> None:
                changes.append(
                    SaleItemChange(
                        sale_id=sale.id,
                        sale_item_id=item.id,
                        revision_id=revision.id,
                        action=action.value,
                        old_data=old,
                        new_data=new,
                        changed_by_user_id=actor_user_id,
                    )
                )

            for product, quantity, unit_price, line_total in lines:
                locked_product = session.scalar(
                    select(Product).where(Product.id == product.id).with_for_update()
                )
                if locked_product is None:
                    raise SaleNotEditableError("Product not found")
                locked_product.quantity_in_stock = (
                    locked_product.quantity_in_stock or Decimal("0")
                ) - quantity
                session.add(
                    SaleInventoryAdjustment(
                        sale_id=sale.id,
                        revision_number=revision_number,
                        product_id=product.id,
                        quantity=quantity,
                        direction="apply",
                    )
                )
                found = existing.pop(product.id, None)
                if found is None:
                    parent = (
                        session.get(Product, product.parent_product_id)
                        if product.parent_product_id
                        else None
                    )
                    new_item = SaleItem(
                        id=uuid.uuid4(),
                        sale_id=sale.id,
                        product_id=product.id,
                        product_name=product.display_name(parent),
                        product_sku=product.sku,
                        unit=product.unit.value,
                        quantity=quantity,
                        cost_price=product.cost_price,
                        unit_price=unit_price,
                        line_total=line_total,
                        original_unit_price=product.selling_price or unit_price,
                        discount_amount=(
                            (product.selling_price or unit_price) - unit_price
                        )
                        * quantity,
                        is_active=True,
                        revision_number=revision_number,
                    )
                    session.add(new_item)
                    session.flush()
                    record(new_item, SaleItemAction.ADDED, None, _item_data(new_item))
                    continue
                item = found
                before = _item_data(item)
                quantity_changed = item.quantity != quantity
                price_changed = item.unit_price != unit_price
                if not quantity_changed and not price_changed:
                    continue
                old_price = item.unit_price
                item.quantity = quantity
                item.unit_price = unit_price
                item.line_total = line_total
                item.discount_amount = max(
                    (item.original_unit_price - unit_price) * quantity, Decimal("0")
                )
                after = _item_data(item)
                if quantity_changed:
                    record(item, SaleItemAction.EDITED, before, after)
                if price_changed:
                    record(
                        item,
                        _price_action(item.original_unit_price, old_price, unit_price),
                        before,
                        after,
                    )
            for item in [*existing.values(), *extra_active]:
                record(item, SaleItemAction.DELETED, _item_data(item), None)
                item.is_active = False
            session.add_all(changes)
            revision.closed_at = func.now()
            revision.closed_total = total
            revision.is_changed = bool(changes)
            revision.changed_by_user_id = actor_user_id
            revision.status = SaleStatus.COMPLETED.value
            revision.outcome = (
                SaleRevisionOutcome.COMPLETED
                if changes
                else SaleRevisionOutcome.COMPLETED_UNCHANGED
            ).value
            sale.total = total
            sale.status = SaleStatus.COMPLETED
            credit_sale = session.scalar(
                select(CustomerCreditSale).where(
                    CustomerCreditSale.sale_id == sale.id
                )
            )
            previous_customer_id = (
                credit_sale.customer_id if credit_sale is not None else None
            )
            if credit_customer_id is not None:
                customer = session.scalar(
                    select(CreditCustomer).where(
                        CreditCustomer.id == credit_customer_id,
                        CreditCustomer.is_active,
                    )
                )
                if customer is None:
                    raise ValueError("Credit customer not found")
                if credit_sale is None:
                    session.add(
                        CustomerCreditSale(
                            customer_id=credit_customer_id,
                            sale_id=sale.id,
                            amount=total,
                        )
                    )
                else:
                    credit_sale.customer_id = credit_customer_id
                    credit_sale.amount = total
            elif credit_sale is not None:
                session.delete(credit_sale)
            if previous_customer_id != credit_customer_id:
                payment_event = _audit(
                    sale,
                    actor_user_id,
                    "PAYMENT_TYPE_CHANGED",
                    sale.current_unlock_key_id,
                    _payment_state(session, credit_customer_id),
                )
                payment_event.old_value = _payment_state(session, previous_customer_id)
                session.add(payment_event)
            session.add(
                _audit(
                    sale,
                    actor_user_id,
                    "DOCUMENT_RECONFIRMED",
                    sale.current_unlock_key_id,
                    {"total": str(total), "revision": revision_number},
                )
            )
            session.commit()
            session.refresh(sale)
            return sale

    def cancel_unlocked_sale(
        self, sale_id: uuid.UUID, actor_user_id: uuid.UUID, reason: str
    ) -> None:
        with self._session_factory() as session:
            sale = session.scalar(
                select(Sale).where(Sale.id == sale_id).with_for_update()
            )
            if sale is None or sale.status not in (
                SaleStatus.EDITING,
                SaleStatus.COMPLETED,
            ):
                raise SaleNotEditableError("Sale cannot be cancelled")
            if sale.status is SaleStatus.COMPLETED:
                self._restore_stock(session, sale)
            sale.status = SaleStatus.CANCELLED
            sale.cancellation_reason = reason
            revision = session.scalar(
                select(SaleRevision)
                .where(
                    SaleRevision.sale_id == sale_id,
                    SaleRevision.outcome == SaleRevisionOutcome.UNLOCKED.value,
                )
                .order_by(SaleRevision.revision_number.desc())
                .limit(1)
            )
            if revision is not None:
                revision.outcome = SaleRevisionOutcome.CANCELLED.value
                revision.status = SaleStatus.CANCELLED.value
                revision.changed_by_user_id = actor_user_id
                revision.closed_at = func.now()
            session.add(
                _audit(
                    sale,
                    actor_user_id,
                    "DOCUMENT_CANCELLED",
                    sale.current_unlock_key_id,
                    {"cancellation_reason": reason},
                )
            )
            session.commit()

    @staticmethod
    def _restore_stock(session: Session, sale: Sale) -> None:
        revision_number = int(
            session.scalar(
                select(func.max(SaleRevision.revision_number)).where(
                    SaleRevision.sale_id == sale.id
                )
            )
            or 0
        )
        items = session.scalars(
            select(SaleItem).where(SaleItem.sale_id == sale.id, SaleItem.is_active)
        )
        for item in items:
            if item.product_id is None:
                continue
            product = session.scalar(
                select(Product).where(Product.id == item.product_id).with_for_update()
            )
            if product is None:
                continue
            product.quantity_in_stock = (
                product.quantity_in_stock or Decimal("0")
            ) + item.quantity
            session.add(
                SaleInventoryAdjustment(
                    sale_id=sale.id,
                    revision_number=revision_number,
                    product_id=product.id,
                    quantity=item.quantity,
                    direction="revert",
                )
            )

    def get_employee_name(self, user_id: uuid.UUID) -> str:
        with self._session_factory() as session:
            return (
                session.scalar(select(User.full_name).where(User.id == user_id)) or ""
            )


def _apply_sale_filters(statement: Any, filters: Any) -> Any:
    statement = statement.where(
        select(SaleItem.id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(
            SaleItem.sale_id == Sale.id,
            or_(
                SaleItem.is_active.is_(True),
                Sale.status.in_((SaleStatus.CANCELLED, SaleStatus.VOIDED)),
            ),
            Product.is_for_sale.is_(True),
        )
        .exists()
    )
    if getattr(filters, "from_datetime", None) is not None:
        statement = statement.where(Sale.created_at >= filters.from_datetime)
    if getattr(filters, "to_datetime", None) is not None:
        statement = statement.where(Sale.created_at < filters.to_datetime)
    if getattr(filters, "terminal_id", None) is not None:
        statement = statement.where(Sale.terminal_id == filters.terminal_id)
    if getattr(filters, "employee_user_id", None) is not None:
        statement = statement.where(Sale.employee_user_id == filters.employee_user_id)
    if getattr(filters, "session_id", None) is not None:
        statement = statement.where(Sale.pos_session_id == filters.session_id)
    if getattr(filters, "customer_id", None) is not None:
        statement = statement.where(
            select(CustomerCreditSale.id)
            .where(
                CustomerCreditSale.sale_id == Sale.id,
                CustomerCreditSale.customer_id == filters.customer_id,
            )
            .correlate(Sale)
            .exists()
        )
    if getattr(filters, "status", None) is not None:
        statement = statement.where(Sale.status == filters.status)
    if getattr(filters, "barbecue_only", False):
        statement = statement.where(
            select(SaleItem.id)
            .join(Product, Product.id == SaleItem.product_id)
            .where(
                SaleItem.sale_id == Sale.id,
                or_(
                    SaleItem.is_active.is_(True),
                    Sale.status.in_((SaleStatus.CANCELLED, SaleStatus.VOIDED)),
                ),
                Product.is_for_sale.is_(True),
                Product.parent_product_id.is_not(None),
            )
            .exists()
        )
    return statement


def _sale_item_total(sale: Any, filters: Any, kind: str) -> Any:
    if kind == "income":
        expression = (
            SaleItem.unit_price - func.coalesce(SaleItem.cost_price, 0)
        ) * SaleItem.quantity
    else:
        expression = SaleItem.line_total
    statement = (
        select(func.coalesce(func.sum(expression), 0))
        .join(Product, Product.id == SaleItem.product_id)
        .where(
            SaleItem.sale_id == sale.id,
            SaleItem.is_active,
            Product.is_for_sale.is_(True),
        )
    )
    if getattr(filters, "barbecue_only", False):
        statement = statement.where(Product.parent_product_id.is_not(None))
    return statement.scalar_subquery()


def _item_data(item: SaleItem) -> dict[str, object]:
    return {
        "product_id": str(item.product_id) if item.product_id else None,
        "product_name": item.product_name,
        "product_sku": item.product_sku,
        "unit": item.unit,
        "quantity": str(item.quantity),
        "unit_price": str(item.unit_price),
        "line_total": str(item.line_total),
        "cost_price": None if item.cost_price is None else str(item.cost_price),
        "original_unit_price": str(item.original_unit_price),
        "discount_amount": str(item.discount_amount),
    }


def _price_action(
    original: Decimal, old_price: Decimal, new_price: Decimal
) -> SaleItemAction:
    if old_price >= original and new_price < original:
        return SaleItemAction.DISCOUNT_ADDED
    if old_price < original and new_price >= original:
        return SaleItemAction.DISCOUNT_REMOVED
    if old_price < original and new_price < original:
        return SaleItemAction.DISCOUNT_CHANGED
    return SaleItemAction.EDITED


def _snapshot_items(items: list[SaleItem]) -> list[dict[str, object]]:
    return [
        {
            "product_id": str(item.product_id) if item.product_id else None,
            "product_sku": item.product_sku,
            "product_name": item.product_name,
            "quantity": str(item.quantity),
            "unit_price": str(item.unit_price),
            "line_total": str(item.line_total),
        }
        for item in items
    ]


def _payment_state(
    session: Session, customer_id: uuid.UUID | None
) -> dict[str, object]:
    if customer_id is None:
        return {"payment": "cash"}
    customer = session.get(CreditCustomer, customer_id)
    name = f"{customer.first_name} {customer.last_name}" if customer else ""
    return {"payment": "credit", "customer": name}


def _audit(
    sale: Sale,
    actor_user_id: uuid.UUID,
    event_type: str,
    authorization_key_id: uuid.UUID | None,
    value: object,
) -> SaleAuditEvent:
    return SaleAuditEvent(
        sale_id=sale.id,
        pos_session_id=sale.pos_session_id,
        terminal_id=sale.terminal_id,
        employee_user_id=sale.employee_user_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        authorization_key_id=authorization_key_id,
        new_value=value,
    )
