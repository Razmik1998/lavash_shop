"""Application-service interface for the Online Selling screen.

The UI calls only these methods and never touches
SQL/repositories/`SyncService`'s transport directly,
per `.claude/rules/desktop.md` and `.claude/rules/architecture.md`.

See `.claude/specs/9/admin-architecture.md` for the binding design this
stub must match once implemented:
  - §4: `OnlineOrder`/`OnlineOrderItem` fields and the three independent
    status dimensions (business/sync/conversion).
  - §7: the order -> `Sale` conversion transaction (reuses
    `SalesService.create_sale`, extended with `web_order_id`; runs under
    the bootstrapped `ONLINE` `PosSession`).
  - §8: the retry-after-failure model -- `retry_conversion` below is
    deliberately *not* a separate code path, it just re-invokes the same
    conversion entry point `confirm_order` uses internally, which must
    already be safe to call repeatedly (idempotent on
    `Sale.web_order_id`).

`OnlineOrderService` owns confirm/reject/list/conversion. It never talks
to sockets/WebSocket -- receiving events from Django and deciding when to
call `confirm_order`/persist an incoming order is `SyncService`'s job
(services/sync.py), which calls into this service, not the other way
around.
"""

from __future__ import annotations

import uuid

from exceptions import (
    OnlineOrderNotConfirmedError,
    OnlineOrderNotFoundError,
    OnlineOrderNotPendingError,
)
from models import (
    OnlineOrder,
    OnlineOrderBusinessStatus,
    OnlineOrderConversionStatus,
    OnlineOrderItem,
)
from repositories.online_order import (
    OnlineOrderRepository,
    decode_cursor,
    encode_cursor,
)
from schemas.online_orders import (
    OnlineOrderDetail,
    OnlineOrderItemRow,
    OnlineOrderRow,
    OnlineOrdersPage,
)


class OnlineOrderService:
    """Confirm/reject/list operations over `OnlineOrder`, plus the
    order -> `Sale` conversion `confirm_order`/`retry_conversion` trigger
    (the conversion itself composes `SalesService.create_sale` rather
    than reimplementing stock deduction/sale-row construction, per
    admin-architecture.md §7).

    The repository owns SQL and transactions. This service owns status
    transitions and converts ORM rows into UI-safe schemas.
    """

    def __init__(self, repository: OnlineOrderRepository, page_size: int = 50) -> None:
        self._repository = repository
        self._page_size = page_size

    def list_pending_orders(self, cursor: str | None = None) -> OnlineOrdersPage:
        """Orders with `business_status == PENDING`, newest first.

        `cursor`/`OnlineOrdersPage.next_cursor` follow the same
        opaque-cursor pagination convention as
        `SalesHistoryService.list_sales` (schemas/sales.py`'s
        `SalesPage`) -- `None` cursor means "first page".
        """
        return self._list({OnlineOrderBusinessStatus.PENDING}, cursor)

    def list_history(self, cursor: str | None = None) -> OnlineOrdersPage:
        """Orders with `business_status in {CONFIRMED, REJECTED}`, newest
        first. A confirmed row's eventual `Sale` is always under
        `terminal_id="ONLINE"` (admin-architecture.md §3) -- the UI reads
        that off the linked `Sale`/`OnlineOrder.sale_id`, this method does
        not need to embed the terminal id itself."""
        return self._list(
            {OnlineOrderBusinessStatus.CONFIRMED, OnlineOrderBusinessStatus.REJECTED},
            cursor,
        )

    def get_order_detail(self, online_order_id: uuid.UUID) -> OnlineOrderDetail:
        """Raises:
        OnlineOrderNotFoundError: no such `online_order_id`.
        """
        result = self._repository.get_detail(online_order_id)
        if result is None:
            raise OnlineOrderNotFoundError(f"Online order not found: {online_order_id}")
        return _detail(*result)

    def get_order_row(self, online_order_id: uuid.UUID) -> OnlineOrderRow:
        result = self._repository.get_detail(online_order_id)
        if result is None:
            raise OnlineOrderNotFoundError(f"Online order not found: {online_order_id}")
        return _row(result[0])

    def confirm_order(self, online_order_id: uuid.UUID) -> OnlineOrderDetail:
        """Sets `business_status=CONFIRMED`, then converts the order to a
        `Sale` under the `ONLINE` terminal in the same unit of work
        (admin-architecture.md §7). Idempotent: calling again once
        already `CONFIRMED`/`conversion_status=CREATED` returns the
        existing detail unchanged rather than erroring.

        Raises:
            OnlineOrderNotFoundError: no such `online_order_id`.
            OnlineOrderNotPendingError: `business_status` is not
                `PENDING` (and the order isn't already confirmed -- see
                the idempotent case above).
        """
        result = self._repository.get_detail(online_order_id)
        if result is None:
            raise OnlineOrderNotFoundError(f"Online order not found: {online_order_id}")
        order, _items = result
        if order.business_status is OnlineOrderBusinessStatus.CONFIRMED:
            if order.conversion_status is OnlineOrderConversionStatus.CREATED:
                return _detail(*result)
        elif order.business_status is not OnlineOrderBusinessStatus.PENDING:
            raise OnlineOrderNotPendingError("Only pending orders can be confirmed")
        self._repository.set_business_status(
            online_order_id, OnlineOrderBusinessStatus.CONFIRMED
        )
        try:
            self._repository.convert_to_sale(online_order_id)
        except Exception as exc:
            self._repository.mark_conversion_failed(online_order_id, str(exc))
        return self.get_order_detail(online_order_id)

    def reject_order(
        self, online_order_id: uuid.UUID, reason: str
    ) -> OnlineOrderDetail:
        """Sets `business_status=REJECTED` + `rejection_reason=reason`.
        Never creates a `Sale` -- a rejected order must not reach
        conversion.

        Raises:
            OnlineOrderNotFoundError: no such `online_order_id`.
            OnlineOrderNotPendingError: `business_status` is not
                `PENDING`.
            ValueError: `reason` is empty/blank (validate at the service
                boundary, don't trust the UI dialog alone).
        """
        if not reason.strip():
            raise ValueError("Rejection reason is required")
        result = self._repository.get_detail(online_order_id)
        if result is None:
            raise OnlineOrderNotFoundError(f"Online order not found: {online_order_id}")
        if result[0].business_status is not OnlineOrderBusinessStatus.PENDING:
            raise OnlineOrderNotPendingError("Only pending orders can be rejected")
        self._repository.set_business_status(
            online_order_id, OnlineOrderBusinessStatus.REJECTED, reason.strip()
        )
        return self.get_order_detail(online_order_id)

    def retry_conversion(self, online_order_id: uuid.UUID) -> OnlineOrderDetail:
        """Re-invokes the same conversion entry point `confirm_order`
        uses internally, for a `CONFIRMED` order stuck at
        `conversion_status=FAILED` (admin-architecture.md §8). Safe to
        call repeatedly -- the `Sale.web_order_id` unique constraint is
        the actual idempotency guarantee, this method does not add a
        second one.

        Raises:
            OnlineOrderNotFoundError: no such `online_order_id`.
            OnlineOrderNotConfirmedError: `business_status` is not
                `CONFIRMED` (e.g. called against a still-pending or
                rejected order).
        """
        result = self._repository.get_detail(online_order_id)
        if result is None:
            raise OnlineOrderNotFoundError(f"Online order not found: {online_order_id}")
        if result[0].business_status is not OnlineOrderBusinessStatus.CONFIRMED:
            raise OnlineOrderNotConfirmedError("Only confirmed orders can be retried")
        try:
            self._repository.convert_to_sale(online_order_id)
        except Exception as exc:
            self._repository.mark_conversion_failed(online_order_id, str(exc))
        return self.get_order_detail(online_order_id)

    def _list(
        self, statuses: set[OnlineOrderBusinessStatus], cursor: str | None
    ) -> OnlineOrdersPage:
        decoded = decode_cursor(cursor) if cursor else None
        rows = self._repository.list_orders(statuses, decoded, self._page_size)
        has_more = len(rows) > self._page_size
        rows = rows[: self._page_size]
        next_cursor = (
            encode_cursor(rows[-1].order_date, rows[-1].id) if has_more else None
        )
        return OnlineOrdersPage([_row(row) for row in rows], next_cursor)


def _row(order: OnlineOrder) -> OnlineOrderRow:
    return OnlineOrderRow(
        id=order.id,
        web_order_id=order.web_order_id,
        order_number=order.order_number,
        customer_name=order.customer_name,
        total=order.total,
        business_status=order.business_status,
        sync_status=order.sync_status,
        conversion_status=order.conversion_status,
        order_date=order.order_date,
        received_at=order.received_at,
    )


def _detail(order: OnlineOrder, items: list[OnlineOrderItem]) -> OnlineOrderDetail:
    return OnlineOrderDetail(
        id=order.id,
        web_order_id=order.web_order_id,
        order_number=order.order_number,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        customer_address=order.customer_address,
        order_date=order.order_date,
        subtotal=order.subtotal,
        delivery_fee=order.delivery_fee,
        discount=order.discount,
        total=order.total,
        business_status=order.business_status,
        sync_status=order.sync_status,
        conversion_status=order.conversion_status,
        conversion_error=order.conversion_error,
        rejection_reason=order.rejection_reason,
        sale_id=order.sale_id,
        items=[
            OnlineOrderItemRow(
                item.product_id,
                item.product_name,
                item.unit,
                item.quantity,
                item.unit_price,
                item.subtotal,
            )
            for item in items
        ],
    )
