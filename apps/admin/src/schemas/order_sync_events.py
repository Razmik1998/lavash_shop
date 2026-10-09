"""Service-facing dataclasses for the Django order-sync wire contract.

These are the shapes `networking/order_sync_client.py` decodes inbound
JSON into (and encodes outbound calls from) and that
`services/sync.py`'s `SyncService` consumes. No UI or repository
imports, per the schemas/ convention in CLAUDE.md.

Kept separate from `schemas/online_orders.py` (the local `OnlineOrder`/
`OnlineOrderItem` DB-mirroring shapes the Online Selling UI reads via
`OnlineOrderService`) -- these dataclasses instead mirror Django's wire
format one-to-one and are consumed only by `SyncService`, never by the
UI directly.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


class OrderEventType(enum.Enum):
    """Mirrors Django's `OrderEvent.event_type` values broadcast over
    `/ws/admin/orders/` and returned by the HTTP recovery endpoint."""

    ORDER_CREATED = "order.created"
    ORDER_CONFIRMED = "order.confirmed"
    ORDER_REJECTED = "order.rejected"


@dataclass(frozen=True)
class OrderSyncEvent:
    """One entry from the WebSocket event stream or the HTTP recovery
    (`GET /api/admin/orders/sync/`) response. Carries only identity --
    callers fetch the full order snapshot via `fetch_order_detail`
    when they need it."""

    event_id: int
    order_id: uuid.UUID
    event_type: OrderEventType
    created_at: datetime


@dataclass(frozen=True)
class OrderSyncItemDetail:
    product_id: uuid.UUID | None
    product_name: str
    unit: str
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal


@dataclass(frozen=True)
class OrderSyncDetail:
    """Full order snapshot from `GET /api/admin/orders/<id>/`, as
    Django serves it -- the wire shape, not the local `OnlineOrder`
    mirror `OnlineOrderDetail` (`schemas/online_orders.py`) built from
    it."""

    order_id: uuid.UUID
    order_number: str
    status: str
    customer_name: str
    customer_phone: str
    customer_address: str
    order_date: datetime
    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    total: Decimal
    items: list[OrderSyncItemDetail]


@dataclass(frozen=True)
class OrderSyncActionResult:
    """Result of a confirm/reject call, e.g.
    `{"order_id": 1, "status": "CONFIRMED"}`."""

    order_id: uuid.UUID
    status: str
