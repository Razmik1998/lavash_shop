"""Persistence for online orders and their local sale conversion."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from models import (
    ONLINE_SYSTEM_USER_ID,
    ONLINE_TERMINAL_ID,
    OnlineOrder,
    OnlineOrderBusinessStatus,
    OnlineOrderConversionStatus,
    OnlineOrderItem,
    OnlineOrderSyncStatus,
    OrderSyncState,
    PosSession,
    PosSessionStatus,
    Product,
    Sale,
    SaleAuditEvent,
    SaleItem,
    SaleStatus,
)
from schemas.order_sync_events import OrderSyncDetail


class OnlineOrderRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_orders(
        self,
        statuses: set[OnlineOrderBusinessStatus],
        cursor: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[OnlineOrder]:
        with self._session_factory() as session:
            statement = select(OnlineOrder).where(
                OnlineOrder.business_status.in_(statuses)
            )
            if cursor is not None:
                order_date, order_id = cursor
                statement = statement.where(
                    (OnlineOrder.order_date < order_date)
                    | (
                        (OnlineOrder.order_date == order_date)
                        & (OnlineOrder.id < order_id)
                    )
                )
            return list(
                session.scalars(
                    statement.order_by(
                        OnlineOrder.order_date.desc(), OnlineOrder.id.desc()
                    ).limit(limit + 1)
                )
            )

    def get_detail(
        self, order_id: uuid.UUID
    ) -> tuple[OnlineOrder, list[OnlineOrderItem]] | None:
        with self._session_factory() as session:
            order = session.get(OnlineOrder, order_id)
            if order is None:
                return None
            items = list(
                session.scalars(
                    select(OnlineOrderItem).where(
                        OnlineOrderItem.online_order_id == order_id
                    )
                )
            )
            return order, items

    def get_by_web_id(self, web_order_id: uuid.UUID) -> OnlineOrder | None:
        with self._session_factory() as session:
            return session.scalar(
                select(OnlineOrder).where(OnlineOrder.web_order_id == web_order_id)
            )

    def save_snapshot(self, detail: OrderSyncDetail) -> OnlineOrder:
        with self._session_factory() as session:
            order = session.scalar(
                select(OnlineOrder).where(OnlineOrder.web_order_id == detail.order_id)
            )
            if order is None:
                order = OnlineOrder(
                    web_order_id=detail.order_id,
                    order_number=detail.order_number,
                    customer_name=detail.customer_name,
                    customer_phone=detail.customer_phone,
                    customer_address=detail.customer_address,
                    order_date=detail.order_date,
                    subtotal=detail.subtotal,
                    delivery_fee=detail.delivery_fee,
                    discount=detail.discount,
                    total=detail.total,
                )
                session.add(order)
                session.flush()
            order.order_number = detail.order_number
            order.customer_name = detail.customer_name
            order.customer_phone = detail.customer_phone
            order.customer_address = detail.customer_address
            order.order_date = detail.order_date
            order.subtotal = detail.subtotal
            order.delivery_fee = detail.delivery_fee
            order.discount = detail.discount
            order.total = detail.total
            order.business_status = _business_status(detail.status)
            order.sync_status = OnlineOrderSyncStatus.RECEIVED
            session.query(OnlineOrderItem).filter(
                OnlineOrderItem.online_order_id == order.id
            ).delete()
            for item in detail.items:
                session.add(
                    OnlineOrderItem(
                        online_order_id=order.id,
                        product_id=_uuid_or_none(item.product_id),
                        product_name=item.product_name,
                        unit=item.unit,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                        subtotal=item.subtotal,
                    )
                )
            session.commit()
            session.refresh(order)
            return order

    def set_business_status(
        self,
        order_id: uuid.UUID,
        status: OnlineOrderBusinessStatus,
        reason: str | None = None,
    ) -> OnlineOrder | None:
        with self._session_factory() as session:
            order = session.scalar(
                select(OnlineOrder).where(OnlineOrder.id == order_id).with_for_update()
            )
            if order is None:
                return None
            order.business_status = status
            order.rejection_reason = reason
            session.commit()
            session.refresh(order)
            return order

    def mark_conversion_failed(self, order_id: uuid.UUID, message: str) -> None:
        with self._session_factory() as session:
            order = session.get(OnlineOrder, order_id)
            if order is not None:
                order.conversion_status = OnlineOrderConversionStatus.FAILED
                order.conversion_error = message[:1000]
                session.commit()

    def convert_to_sale(self, order_id: uuid.UUID) -> uuid.UUID:
        """Create the linked sale and inventory changes in one transaction."""
        with self._session_factory() as session:
            order = session.scalar(
                select(OnlineOrder).where(OnlineOrder.id == order_id).with_for_update()
            )
            if order is None:
                raise LookupError("Online order not found")
            if order.sale_id is not None:
                return order.sale_id
            existing = session.scalar(
                select(Sale).where(Sale.web_order_id == order.web_order_id)
            )
            if existing is not None:
                order.sale_id = existing.id
                order.conversion_status = OnlineOrderConversionStatus.CREATED
                order.conversion_error = None
                session.commit()
                return existing.id
            if order.business_status is not OnlineOrderBusinessStatus.CONFIRMED:
                raise ValueError("Only confirmed orders can be converted")
            pos_session = session.scalar(
                select(PosSession).where(
                    PosSession.terminal_id == ONLINE_TERMINAL_ID,
                    PosSession.status == PosSessionStatus.ACTIVE,
                )
            )
            if pos_session is None:
                raise LookupError("ONLINE session is not available")
            items = list(
                session.scalars(
                    select(OnlineOrderItem).where(
                        OnlineOrderItem.online_order_id == order.id
                    )
                )
            )
            if not items:
                raise ValueError("Online order has no items")
            sale = Sale(
                pos_session_id=pos_session.id,
                employee_user_id=ONLINE_SYSTEM_USER_ID,
                terminal_id=ONLINE_TERMINAL_ID,
                client_sale_id=uuid.uuid4(),
                web_order_id=order.web_order_id,
                status=SaleStatus.COMPLETED,
                total=order.total,
            )
            session.add(sale)
            session.flush()
            for item in items:
                if item.product_id is None:
                    raise ValueError(
                        f"No local product mapping for item {item.product_name}"
                    )
                product = session.scalar(
                    select(Product)
                    .where(Product.id == item.product_id)
                    .with_for_update()
                )
                if product is None or not product.is_active or product.is_for_sale is False:
                    raise ValueError(f"Product is unavailable: {item.product_name}")
                product.quantity_in_stock = (
                    product.quantity_in_stock or Decimal("0")
                ) - item.quantity
                session.add(
                    SaleItem(
                        sale_id=sale.id,
                        product_id=product.id,
                        product_name=item.product_name,
                        product_sku=product.sku,
                        unit=item.unit,
                        quantity=item.quantity,
                        cost_price=product.cost_price,
                        unit_price=item.unit_price,
                        line_total=item.subtotal,
                    )
                )
            session.add(
                SaleAuditEvent(
                    sale_id=sale.id,
                    pos_session_id=pos_session.id,
                    terminal_id=ONLINE_TERMINAL_ID,
                    employee_user_id=ONLINE_SYSTEM_USER_ID,
                    actor_user_id=ONLINE_SYSTEM_USER_ID,
                    event_type="created",
                    new_value={
                        "total": str(order.total),
                        "web_order_id": str(order.web_order_id),
                    },
                )
            )
            order.sale_id = sale.id
            order.conversion_status = OnlineOrderConversionStatus.CREATED
            order.conversion_error = None
            session.commit()
            return sale.id

    def get_sync_state(self, device_id: str) -> OrderSyncState | None:
        with self._session_factory() as session:
            return session.scalar(
                select(OrderSyncState).where(OrderSyncState.device_id == device_id)
            )

    def save_sync_state(self, device_id: str, event_id: int) -> None:
        with self._session_factory() as session:
            state = session.scalar(
                select(OrderSyncState)
                .where(OrderSyncState.device_id == device_id)
                .with_for_update()
            )
            if state is None:
                state = OrderSyncState(device_id=device_id, last_event_id=event_id)
                session.add(state)
            elif state.last_event_id is None or event_id > state.last_event_id:
                state.last_event_id = event_id
            state.last_synced_at = datetime.now(UTC)
            session.commit()

    def mark_acknowledged(self, web_order_id: uuid.UUID) -> None:
        with self._session_factory() as session:
            order = session.scalar(
                select(OnlineOrder).where(OnlineOrder.web_order_id == web_order_id)
            )
            if order is not None:
                order.sync_status = OnlineOrderSyncStatus.ACKNOWLEDGED
                session.commit()


def _business_status(value: str) -> OnlineOrderBusinessStatus:
    normalized = value.lower()
    return OnlineOrderBusinessStatus(normalized)


def _uuid_or_none(value: uuid.UUID | None) -> uuid.UUID | None:
    return value


def encode_cursor(order_date: datetime, order_id: uuid.UUID) -> str:
    payload = json.dumps([order_date.isoformat(), str(order_id)]).encode()
    return base64.urlsafe_b64encode(payload).decode()


def decode_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        date_value, id_value = json.loads(base64.urlsafe_b64decode(value.encode()))
        return datetime.fromisoformat(date_value), uuid.UUID(id_value)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid online-order cursor") from exc
