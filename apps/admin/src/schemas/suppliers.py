import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from models import PaymentMethod, PurchaseStatus, SupplierPayment
from schemas.purchases import PurchaseRow


@dataclass(frozen=True)
class SupplierRow:
    id: uuid.UUID
    name: str
    phone: str | None
    description: str | None
    is_active: bool
    opening_debt: Decimal = Decimal("0")


@dataclass(frozen=True)
class SupplierSummary:
    supplier: SupplierRow
    purchase_count: int
    purchase_total: Decimal
    paid_total: Decimal
    debt: Decimal
    last_purchase_date: datetime | None


@dataclass(frozen=True)
class SupplierHistory:
    supplier: SupplierRow
    purchases: list[PurchaseRow]
    payments: list[SupplierPayment]


@dataclass(frozen=True)
class SupplierPaymentRow:
    id: uuid.UUID
    payment_date: datetime
    amount: Decimal
    method: PaymentMethod
    purchase_number: str | None
    notes: str | None


@dataclass(frozen=True)
class SupplierAccount:
    """A supplier's documents and payments for one period, with totals.

    ``purchased_total``/``paid_total``/``debt`` cover confirmed documents
    dated in the period; ``total_debt`` is the all-time outstanding balance.
    """

    supplier: SupplierRow
    purchases: list[PurchaseRow]
    payments: list[SupplierPaymentRow]
    purchased_total: Decimal
    paid_total: Decimal
    debt: Decimal
    payments_total: Decimal
    total_debt: Decimal


@dataclass(frozen=True)
class PurchaseFilters:
    from_datetime: datetime | None = None
    to_datetime: datetime | None = None
    supplier_id: uuid.UUID | None = None
    status: PurchaseStatus | None = None
    search: str | None = None


@dataclass(frozen=True)
class SupplierReportRow:
    supplier_id: uuid.UUID
    supplier_name: str
    purchase_count: int
    purchased_quantity: Decimal
    purchase_amount: Decimal
    paid_amount: Decimal
    outstanding_debt: Decimal
