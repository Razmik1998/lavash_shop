"""Service-facing shapes for the Online Selling screen.

Mirrors the ``OnlineOrder``/``OnlineOrderItem`` models
(``models/online_order.py``) the way ``schemas/sales.py`` mirrors
``Sale``/``SaleItem`` -- these dataclasses are what
``OnlineOrderService`` (``services/online_orders.py``) returns to the UI;
the UI never touches the ORM models directly.

Distinct from ``schemas/order_sync_events.py``, which holds the
wire-level shapes Django's HTTP/WebSocket contract speaks (integer
``order_id``, raw status strings) for ``networking/order_sync_client.py``
and ``SyncService`` -- those never reach the UI directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from models import (
    OnlineOrderBusinessStatus,
    OnlineOrderConversionStatus,
    OnlineOrderSyncStatus,
)


@dataclass(frozen=True)
class OnlineOrderItemRow:
    product_id: uuid.UUID | None
    product_name: str
    unit: str
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal


@dataclass(frozen=True)
class OnlineOrderRow:
    """One row of the Pending Orders / History list."""

    id: uuid.UUID
    web_order_id: uuid.UUID
    order_number: str
    customer_name: str
    total: Decimal
    business_status: OnlineOrderBusinessStatus
    sync_status: OnlineOrderSyncStatus
    conversion_status: OnlineOrderConversionStatus
    order_date: datetime
    received_at: datetime


@dataclass(frozen=True)
class OnlineOrdersPage:
    items: list[OnlineOrderRow]
    next_cursor: str | None


@dataclass(frozen=True)
class OnlineOrderDetail:
    """Full order detail: customer info, item table, financial breakdown --
    per spec task-9 §4/§6."""

    id: uuid.UUID
    web_order_id: uuid.UUID
    order_number: str
    customer_name: str
    customer_phone: str
    customer_address: str
    order_date: datetime
    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    total: Decimal
    business_status: OnlineOrderBusinessStatus
    sync_status: OnlineOrderSyncStatus
    conversion_status: OnlineOrderConversionStatus
    conversion_error: str | None
    rejection_reason: str | None
    sale_id: uuid.UUID | None
    items: list[OnlineOrderItemRow]
