import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from models import SaleStatus


@dataclass(frozen=True)
class SalesFilters:
    from_datetime: datetime | None = None
    to_datetime: datetime | None = None
    terminal_id: str | None = None
    employee_user_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    status: SaleStatus | None = None
    barbecue_only: bool = False
    customer_id: uuid.UUID | None = None


@dataclass(frozen=True)
class SaleRow:
    id: uuid.UUID
    session_id: uuid.UUID
    terminal_id: str
    employee_user_id: uuid.UUID
    employee_full_name: str
    status: str
    total: Decimal
    created_at: datetime
    income_total: Decimal
    credit_amount: Decimal | None = None
    credit_customer_name: str | None = None
    credit_customer_id: uuid.UUID | None = None


@dataclass(frozen=True)
class SalesPage:
    items: list[SaleRow]
    next_cursor: str | None


@dataclass(frozen=True)
class SalesSummary:
    sale_count: int
    item_quantity_total: Decimal
    revenue_total: Decimal
    income_total: Decimal
    credit_total: Decimal = Decimal("0")


@dataclass(frozen=True)
class SaleItemSnapshot:
    product_id: uuid.UUID | None
    product_name: str
    product_sku: str
    unit: str
    quantity: Decimal
    cost_price: Decimal | None
    original_unit_price: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class SaleAudit:
    event_type: str
    field_name: str | None
    old_value: dict[str, object] | None
    new_value: dict[str, object] | None
    actor_user_id: uuid.UUID
    created_at: datetime
    authorization_key_id: uuid.UUID | None = None


@dataclass(frozen=True)
class SaleKeyHistoryRow:
    sale_id: uuid.UUID
    terminal_id: str
    session_id: uuid.UUID
    event_type: str
    old_value: dict[str, object] | None
    new_value: dict[str, object] | None
    actor_user_id: uuid.UUID
    actor_name: str
    created_at: datetime


@dataclass(frozen=True)
class SaleRevisionRow:
    revision_number: int
    outcome: str | None
    is_changed: bool
    opened_at: datetime
    closed_at: datetime | None
    duration_seconds: int | None
    closed_total: Decimal | None
    user_full_name: str
    opened_by_user_full_name: str | None = None


@dataclass(frozen=True)
class SaleItemChangeRow:
    action: str
    product_name: str
    old_data: dict[str, object] | None
    new_data: dict[str, object] | None
    user_full_name: str
    created_at: datetime


@dataclass(frozen=True)
class SaleAuditHistoryRow:
    event_type: str
    old_value: dict[str, object] | None
    new_value: dict[str, object] | None
    user_full_name: str
    created_at: datetime


@dataclass(frozen=True)
class SaleDetail:
    id: uuid.UUID
    session_id: uuid.UUID
    terminal_id: str
    employee_user_id: uuid.UUID
    employee_full_name: str
    status: str
    total: Decimal
    created_at: datetime
    items: list[SaleItemSnapshot]
    audit_events: list[SaleAudit]
    credit_amount: Decimal | None = None
    credit_customer_name: str | None = None
    credit_customer_id: uuid.UUID | None = None
    revisions: list[SaleRevisionRow] = field(default_factory=list)
    item_changes: list[SaleItemChangeRow] = field(default_factory=list)
    cancellation_reason: str | None = None
