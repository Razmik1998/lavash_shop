"""Application layer: AuthService, EmployeeService."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from exceptions import (
    InvalidCursorError,
    InvalidFiltersError,
    InvalidQuantityError,
    InvalidSaleCancellationReasonError,
    InvalidSalePriceError,
    ProductNotFoundError,
    SaleNotFoundError,
    SessionClosedError,
    SessionNotFoundError,
    SessionNotOwnedError,
    TerminalMismatchError,
)
from models import (
    PosSessionStatus,
    Product,
    SaleUnlockKey,
)
from repository import (
    CustomerRepository,
    PosSessionRepository,
    ProductRepository,
    SaleRepository,
)
from schemas import (
    CustomerPaymentHistoryRow,
    CustomerPaymentRow,
    CustomerRow,
    SaleAudit,
    SaleAuditHistoryRow,
    SaleDetail,
    SaleItemChangeRow,
    SaleItemSnapshot,
    SaleKeyHistoryRow,
    SaleRevisionRow,
    SaleRow,
    SalesFilters,
    SalesPage,
    SalesSummary,
)

# How long a POS terminal may go without a heartbeat before the admin
# panel/UI shows its connection as DISCONNECTED. Kept a small multiple
# (3x) of `HEARTBEAT_INTERVAL_MS` (15s) in
# apps/pos/src/ui/session_status.py, per that module's docstring
# ("the backend's connected/disconnected threshold must be kept a
# small multiple of this, e.g. 2-3x, so a single missed beat doesn't
# flip the indicator") and the networking/server.py PosSessionService
# Protocol docstring assuming this exact computation.
HEARTBEAT_TIMEOUT_SECONDS = 45
ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


class SalesHistoryService:
    def __init__(self, sale_repository: SaleRepository, timezone: str = "UTC") -> None:
        self._sale_repository = sale_repository
        self._timezone = timezone

    def list_sales(
        self, filters: SalesFilters, cursor: str | None, limit: int = 50
    ) -> SalesPage:
        self._validate_filters(filters, limit)
        decoded = _decode_cursor(cursor) if cursor else None
        rows: list[Any] = self._sale_repository.list_sales(filters, decoded, limit)
        if not rows:
            return SalesPage([], None)
        has_more = len(rows) > limit
        rows = rows[:limit]
        last_result = rows[-1]
        last_row = (
            last_result[0]
            if hasattr(last_result, "_mapping") or isinstance(last_result, tuple)
            else last_result
        )
        next_cursor = (
            _encode_cursor(last_row.created_at, last_row.id) if has_more else None
        )
        sales: list[SaleRow] = []
        for result in rows:
            if hasattr(result, "_mapping"):
                row: Any = result[0]
                employee_full_name = result[1]
                income_total = result[2]
                revenue_total = result[3] if len(result) > 3 else row.total
                credit_customer_id = result[4] if len(result) > 4 else None
                credit_amount = result[5] if len(result) > 5 else None
                credit_customer_name = result[6] if len(result) > 6 else None
            elif isinstance(result, tuple):
                row = result[0]
                employee_full_name = result[1]
                income_total = result[2] if len(result) > 2 else Decimal("0")
                revenue_total = result[3] if len(result) > 3 else row.total
                credit_customer_id = result[4] if len(result) > 4 else None
                credit_amount = result[5] if len(result) > 5 else None
                credit_customer_name = result[6] if len(result) > 6 else None
            else:
                row = result
                employee_full_name = getattr(row, "employee_full_name", "")
                income_total = getattr(row, "income_total", Decimal("0"))
                revenue_total = getattr(row, "revenue_total", row.total)
                credit_amount = getattr(row, "credit_amount", None)
                credit_customer_name = getattr(row, "credit_customer_name", None)
                credit_customer_id = getattr(row, "credit_customer_id", None)
            sales.append(
                SaleRow(
                    row.id,
                    row.pos_session_id,
                    row.terminal_id,
                    row.employee_user_id,
                    employee_full_name,
                    row.status.value,
                    Decimal(revenue_total),
                    row.created_at,
                    Decimal(income_total),
                    Decimal(credit_amount) if credit_amount is not None else None,
                    credit_customer_name,
                    credit_customer_id,
                )
            )
        return SalesPage(
            sales,
            next_cursor,
        )

    def summarize_sales(self, filters: SalesFilters) -> SalesSummary:
        self._validate_filters(filters, 50)
        summary = self._sale_repository.summarize_sales(filters)
        count, quantity, revenue, income = summary[:4]
        credit_total = summary[4] if len(summary) > 4 else Decimal("0")
        return SalesSummary(
            int(count),
            Decimal(quantity),
            Decimal(revenue),
            Decimal(income),
            Decimal(credit_total),
        )

    def cancel_sale(
        self, sale_id: uuid.UUID, actor_user_id: uuid.UUID, reason: str
    ) -> SaleDetail:
        cancellation_reason = reason.strip()
        if not cancellation_reason:
            raise InvalidSaleCancellationReasonError(
                "A cancellation reason is required"
            )
        self._sale_repository.cancel_unlocked_sale(
            sale_id, actor_user_id, cancellation_reason
        )
        return self.get_sale_detail(sale_id, include_history=False)

    def get_sale_detail(
        self,
        sale_id: uuid.UUID,
        *,
        barbecue_only: bool = False,
        include_history: bool = True,
    ) -> SaleDetail:
        result = (
            self._sale_repository.get_detail(sale_id, barbecue_only=True)
            if barbecue_only
            else self._sale_repository.get_detail(sale_id)
        )
        if result is None:
            raise SaleNotFoundError(f"Sale not found: {sale_id}")
        sale, items, audits = result
        get_credit_info = getattr(self._sale_repository, "get_credit_info", None)
        credit_info = get_credit_info(sale_id) if get_credit_info else None
        get_employee_name = getattr(self._sale_repository, "get_employee_name", None)
        employee_full_name = (
            get_employee_name(sale.employee_user_id) if get_employee_name else ""
        )
        total = sum((item.line_total for item in items), Decimal("0"))
        revisions, item_changes, _audit_history = (
            self._load_history(sale_id) if include_history else ([], [], [])
        )
        return SaleDetail(
            sale.id,
            sale.pos_session_id,
            sale.terminal_id,
            sale.employee_user_id,
            employee_full_name,
            sale.status.value,
            total,
            sale.created_at,
            [
                SaleItemSnapshot(
                    item.product_id,
                    item.product_name,
                    item.product_sku,
                    item.unit,
                    item.quantity,
                    item.cost_price,
                    item.original_unit_price,
                    item.unit_price,
                    getattr(item, "discount_amount", Decimal("0")),
                    item.line_total,
                )
                for item in items
            ],
            [
                SaleAudit(
                    a.event_type,
                    a.field_name,
                    a.old_value,
                    a.new_value,
                    a.actor_user_id,
                    a.created_at,
                    a.authorization_key_id,
                )
                for a in audits
            ],
            credit_info[1] if credit_info else None,
            credit_info[2] if credit_info else None,
            credit_info[0] if credit_info else None,
            revisions,
            item_changes,
            cancellation_reason=sale.cancellation_reason,
        )

    def get_sale_history(
        self, sale_id: uuid.UUID
    ) -> tuple[list[SaleRevisionRow], list[SaleItemChangeRow], list[SaleAuditHistoryRow]]:
        return self._load_history(sale_id)

    def _load_history(
        self, sale_id: uuid.UUID
    ) -> tuple[list[SaleRevisionRow], list[SaleItemChangeRow], list[SaleAuditHistoryRow]]:
        get_history = getattr(self._sale_repository, "get_history", None)
        if get_history is None:
            return [], [], []
        revisions, changes = get_history(sale_id)
        get_payment_history = getattr(self._sale_repository, "get_payment_history", None)
        audit_events = get_payment_history(sale_id) if get_payment_history else []
        return (
            [
                SaleRevisionRow(
                    revision.revision_number,
                    revision.outcome,
                    revision.is_changed,
                    revision.created_at,
                    revision.closed_at,
                    (
                        int((revision.closed_at - revision.created_at).total_seconds())
                        if revision.closed_at is not None
                        else None
                    ),
                    revision.closed_total,
                    name,
                    opened_by_name or None,
                )
                for revision, name, opened_by_name in revisions
            ],
            [
                SaleItemChangeRow(
                    change.action,
                    str(
                        (change.new_data or change.old_data or {}).get(
                            "product_name", ""
                        )
                    ),
                    change.old_data,
                    change.new_data,
                    name,
                    change.created_at,
                )
                for change, name in changes
            ],
            [
                SaleAuditHistoryRow(
                    event.event_type,
                    event.old_value,
                    event.new_value,
                    name,
                    event.created_at,
                )
                for event, name in audit_events
                if event.event_type in {"PAYMENT_TYPE_CHANGED", "created"}
            ],
        )

    def list_key_history(
        self,
        key_id: uuid.UUID,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
    ) -> list[SaleKeyHistoryRow]:
        return [
            SaleKeyHistoryRow(
                event.sale_id,
                sale.terminal_id,
                sale.pos_session_id,
                event.event_type,
                event.old_value,
                event.new_value,
                event.actor_user_id,
                actor_name,
                event.created_at,
            )
            for event, sale, actor_name in self._sale_repository.list_key_history(
                key_id, from_datetime, to_datetime
            )
        ]

    @staticmethod
    def _validate_filters(filters: SalesFilters, limit: int) -> None:
        if not 1 <= limit <= 100:
            raise InvalidFiltersError("limit must be between 1 and 100")
        if (
            filters.from_datetime
            and filters.to_datetime
            and filters.from_datetime >= filters.to_datetime
        ):
            raise InvalidFiltersError("from_datetime must be before to_datetime")
        if filters.terminal_id is not None and not 0 < len(filters.terminal_id) <= 128:
            raise InvalidFiltersError("terminal_id is invalid")


class SalesService(SalesHistoryService):
    def __init__(
        self,
        sale_repository: SaleRepository,
        pos_session_repository: PosSessionRepository,
        product_repository: ProductRepository,
        timezone: str = "UTC",
        customer_repository: CustomerRepository | None = None,
    ) -> None:
        super().__init__(sale_repository, timezone)
        self._pos_session_repository = pos_session_repository
        self._product_repository = product_repository
        self._customer_repository = customer_repository

    def search_customers(self, query: str) -> list[CustomerRow]:
        if self._customer_repository is None:
            raise RuntimeError("Customer repository is not configured")
        return self._customer_repository.search(query)

    def list_credit_customers(self) -> list[CustomerRow]:
        if self._customer_repository is None:
            raise RuntimeError("Customer repository is not configured")
        return self._customer_repository.search("")

    def list_payment_history(
        self,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
        customer_id: uuid.UUID | None = None,
    ) -> list[CustomerPaymentHistoryRow]:
        if self._customer_repository is None:
            raise RuntimeError("Customer repository is not configured")
        return self._customer_repository.list_payment_history(
            from_datetime, to_datetime, customer_id
        )

    def create_customer(
        self,
        first_name: str,
        last_name: str,
        phone: str,
        address: str | None = None,
        notes: str | None = None,
    ) -> CustomerRow:
        if self._customer_repository is None:
            raise RuntimeError("Customer repository is not configured")
        return self._customer_repository.create(
            first_name, last_name, phone, address, notes
        )

    def record_payment(
        self,
        authenticated_user_id: uuid.UUID,
        customer_id: uuid.UUID,
        amount: Decimal,
        session_id: uuid.UUID,
    ) -> CustomerPaymentRow:
        if self._customer_repository is None:
            raise RuntimeError("Customer repository is not configured")
        self._validate_session_access(authenticated_user_id, session_id)
        return self._customer_repository.record_full_payment(
            customer_id, session_id, authenticated_user_id, amount
        )

    def record_full_payment(
        self,
        authenticated_user_id: uuid.UUID,
        customer_id: uuid.UUID,
        amount: Decimal,
        session_id: uuid.UUID,
    ) -> CustomerPaymentRow:
        return self.record_payment(
            authenticated_user_id, customer_id, amount, session_id
        )

    def create_unlock_key(
        self, name: str, plain_key: str, created_by_user_id: uuid.UUID
    ) -> SaleUnlockKey:
        if not name.strip() or not plain_key:
            raise ValueError("Key name and value are required")
        return self._sale_repository.create_unlock_key(
            name, plain_key, created_by_user_id
        )

    def list_unlock_keys(self) -> list[SaleUnlockKey]:
        return self._sale_repository.list_unlock_keys()

    def set_unlock_key_active(self, key_id: uuid.UUID, is_active: bool) -> None:
        self._sale_repository.set_unlock_key_active(key_id, is_active)

    def create_sale(
        self,
        authenticated_user_id: uuid.UUID,
        session_id: uuid.UUID,
        terminal_id: str,
        client_sale_id: uuid.UUID,
        requested_items: list[tuple[uuid.UUID, Decimal, Decimal | None]],
        credit_customer_id: uuid.UUID | None = None,
    ) -> Any:
        session = self._pos_session_repository.get_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        if session.status is PosSessionStatus.CLOSED:
            raise SessionClosedError(f"Session already closed: {session_id}")
        if session.user_id != authenticated_user_id:
            raise SessionNotOwnedError("Session is owned by another employee")
        if session.terminal_id != terminal_id:
            raise TerminalMismatchError("Terminal does not match session")
        if not requested_items:
            raise InvalidQuantityError("Sale must contain items")
        if credit_customer_id is not None:
            if self._customer_repository is None:
                raise RuntimeError("Customer repository is not configured")
            self._customer_repository.get(credit_customer_id)
        lines = self._prepare_lines(requested_items)
        for product, quantity, _unit_price, _line_total in lines:
            product.quantity_in_stock -= quantity
            self._product_repository.update(product)
        if credit_customer_id is None:
            sale = self._sale_repository.create_sale(
                session_id, authenticated_user_id, terminal_id, client_sale_id, lines
            )
        else:
            sale = self._sale_repository.create_sale(
                session_id,
                authenticated_user_id,
                terminal_id,
                client_sale_id,
                lines,
                credit_customer_id,
            )
        return self.get_sale_detail(sale.id)

    def list_session_sales(
        self, authenticated_user_id: uuid.UUID, session_id: uuid.UUID
    ) -> SalesPage:
        self._validate_session_access(authenticated_user_id, session_id)
        return self.list_sales(SalesFilters(session_id=session_id), None)

    def get_session_sale_detail(
        self,
        authenticated_user_id: uuid.UUID,
        session_id: uuid.UUID,
        sale_id: uuid.UUID,
    ) -> SaleDetail:
        self._validate_session_access(authenticated_user_id, session_id)
        detail = self.get_sale_detail(sale_id)
        if detail.session_id != session_id:
            raise SaleNotFoundError(f"Sale not found: {sale_id}")
        return detail

    def unlock_sale(
        self,
        authenticated_user_id: uuid.UUID,
        session_id: uuid.UUID,
        sale_id: uuid.UUID,
        secret_key: str,
    ) -> SaleDetail:
        self._validate_session_access(authenticated_user_id, session_id)
        self._sale_repository.unlock_sale(sale_id, authenticated_user_id, secret_key)
        return self.get_session_sale_detail(authenticated_user_id, session_id, sale_id)

    def update_sale(
        self,
        authenticated_user_id: uuid.UUID,
        session_id: uuid.UUID,
        sale_id: uuid.UUID,
        requested_items: list[tuple[uuid.UUID, Decimal, Decimal | None]],
        credit_customer_id: uuid.UUID | None = None,
    ) -> SaleDetail:
        self._validate_session_access(authenticated_user_id, session_id)
        if not requested_items:
            raise InvalidQuantityError("Sale must contain items")
        lines = self._prepare_lines(requested_items)
        if credit_customer_id is None:
            self._sale_repository.reconfirm_sale(sale_id, authenticated_user_id, lines)
        else:
            self._sale_repository.reconfirm_sale(
                sale_id, authenticated_user_id, lines, credit_customer_id
            )
        return self.get_session_sale_detail(authenticated_user_id, session_id, sale_id)

    def _prepare_lines(
        self, requested_items: list[tuple[uuid.UUID, Decimal, Decimal | None]]
    ) -> list[tuple[Product, Decimal, Decimal, Decimal]]:
        quantities: dict[uuid.UUID, Decimal] = {}
        requested_prices: dict[uuid.UUID, Decimal | None] = {}
        for item in requested_items:
            product_id, quantity = item[:2]
            requested_price = item[2] if len(item) > 2 else None
            if quantity <= 0 or quantity.as_tuple().exponent < -3:
                raise InvalidQuantityError(
                    f"quantity={quantity} must be positive with at most "
                    "3 decimal places"
                )
            quantities[product_id] = quantities.get(product_id, Decimal("0")) + quantity
            requested_prices[product_id] = requested_price

        lines: list[tuple[Product, Decimal, Decimal, Decimal]] = []
        for product_id, quantity in quantities.items():
            product = self._product_repository.get_by_id(product_id)
            if product is None or not product.is_active or product.is_for_sale is False:
                raise ProductNotFoundError(f"Product not found: {product_id}")
            unit_price = requested_prices[product_id]
            if unit_price is None:
                unit_price = product.selling_price or Decimal("0")
            minimum_price = product.minimum_price or Decimal("0")
            selling_price = product.selling_price or Decimal("0")
            if unit_price < minimum_price or unit_price > selling_price:
                raise InvalidSalePriceError(
                    f"product_id={product_id} requested_price={unit_price} "
                    f"allowed_minimum={minimum_price} "
                    f"allowed_maximum={selling_price}"
                )
            line_total = (unit_price * quantity).quantize(Decimal("0.01"))
            lines.append((product, quantity, unit_price, line_total))
        return lines

    def cancel_sale(
        self,
        authenticated_user_id: uuid.UUID,
        session_id: uuid.UUID,
        sale_id: uuid.UUID,
        reason: str,
    ) -> SaleDetail:
        self._validate_session_access(authenticated_user_id, session_id)
        cancellation_reason = reason.strip()
        if not cancellation_reason:
            raise InvalidSaleCancellationReasonError(
                "A cancellation reason is required"
            )
        self._sale_repository.cancel_unlocked_sale(
            sale_id, authenticated_user_id, cancellation_reason
        )
        return self.get_session_sale_detail(authenticated_user_id, session_id, sale_id)

    def _validate_session_access(
        self, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> None:
        session = self._pos_session_repository.get_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        if session.status is PosSessionStatus.CLOSED:
            raise SessionClosedError(f"Session already closed: {session_id}")
        if session.user_id != user_id:
            raise SessionNotOwnedError("Session is owned by another employee")


def _encode_cursor(created_at: datetime, sale_id: uuid.UUID) -> str:
    payload = {
        "v": 1,
        "created_at": created_at.astimezone(UTC).isoformat(),
        "id": str(sale_id),
    }
    return (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )


def _decode_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if set(payload) != {"v", "created_at", "id"} or payload["v"] != 1:
            raise ValueError
        timestamp = datetime.fromisoformat(payload["created_at"])
        if timestamp.tzinfo is None:
            raise ValueError
        return timestamp.astimezone(UTC), uuid.UUID(payload["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise InvalidCursorError("invalid_cursor") from exc
