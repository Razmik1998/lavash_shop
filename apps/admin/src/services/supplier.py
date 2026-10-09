"""Application layer: AuthService, EmployeeService."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from exceptions import (
    InvalidFiltersError,
    InvalidPurchaseError,
    SupplierNotFoundError,
)
from models import (
    PurchaseStatus,
    Supplier,
)
from repository import (
    SupplierRepository,
)
from schemas import (
    PurchaseRow,
    SupplierAccount,
    SupplierHistory,
    SupplierPaymentRow,
    SupplierRow,
    SupplierSummary,
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
_CONFIRMED_STATUSES = {
    PurchaseStatus.OPEN.value,
    PurchaseStatus.PARTIALLY_PAID.value,
    PurchaseStatus.PAID.value,
}


class SupplierService:
    def __init__(self, repository: SupplierRepository) -> None:
        self._repository = repository

    def list_suppliers(self) -> list[SupplierRow]:
        return [self._row(supplier) for supplier in self._repository.list_all()]

    def list_summaries(self) -> list[SupplierSummary]:
        return [
            SupplierSummary(
                self._row(supplier),
                int(purchase_count),
                Decimal(purchase_total),
                Decimal(paid_total),
                Decimal(supplier.opening_debt)
                + Decimal(purchase_total)
                - Decimal(paid_total),
                last_purchase_date,
            )
            for supplier, purchase_count, purchase_total, paid_total, last_purchase_date
            in self._repository.list_with_summaries()
        ]

    def get_history(self, supplier_id: uuid.UUID) -> SupplierHistory:
        supplier = self.get_supplier(supplier_id)
        purchases, payments = self._repository.get_history(supplier_id)
        return SupplierHistory(
            supplier,
            [
                PurchaseRow(
                    purchase.id,
                    purchase.purchase_number,
                    name,
                    purchase.purchase_date,
                    purchase.total,
                    paid,
                    purchase.total - paid,
                    purchase.status.value,
                    Decimal("0"),
                )
                for purchase, name, paid in purchases
            ],
            payments,
        )

    def get_account(
        self,
        supplier_id: uuid.UUID,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
    ) -> SupplierAccount:
        if (
            from_datetime is not None
            and to_datetime is not None
            and from_datetime >= to_datetime
        ):
            raise InvalidFiltersError("Period start must be before its end")
        supplier = self.get_supplier(supplier_id)
        purchases, payments, total_debt = self._repository.get_account(
            supplier_id, from_datetime, to_datetime
        )
        rows = [
            PurchaseRow(
                purchase.id,
                purchase.purchase_number,
                supplier.name,
                purchase.purchase_date,
                purchase.total,
                paid,
                purchase.total - paid,
                purchase.status.value,
                item_quantity,
            )
            for purchase, paid, item_quantity in purchases
        ]
        confirmed = [row for row in rows if row.status in _CONFIRMED_STATUSES]
        purchased_total = sum((row.total for row in confirmed), Decimal("0"))
        paid_total = sum((row.paid for row in confirmed), Decimal("0"))
        payment_rows = [
            SupplierPaymentRow(
                payment.id,
                payment.payment_date,
                payment.amount,
                payment.method,
                purchase_number,
                payment.notes,
            )
            for payment, purchase_number in payments
        ]
        return SupplierAccount(
            supplier,
            rows,
            payment_rows,
            purchased_total,
            paid_total,
            purchased_total
            - paid_total
            + (
                Decimal(supplier.opening_debt)
                if from_datetime is None and to_datetime is None
                else Decimal("0")
            ),
            sum((row.amount for row in payment_rows), Decimal("0")),
            Decimal(supplier.opening_debt) + total_debt,
        )

    def get_supplier(self, supplier_id: uuid.UUID) -> SupplierRow:
        supplier = self._repository.get(supplier_id)
        if supplier is None:
            raise SupplierNotFoundError(f"Supplier not found: {supplier_id}")
        return self._row(supplier)

    def save_supplier(
        self,
        supplier_id: uuid.UUID | None,
        name: str,
        phone: str | None,
        description: str | None,
        is_active: bool = True,
        opening_debt: Decimal = Decimal("0"),
    ) -> SupplierRow:
        clean_name = name.strip()
        if not clean_name:
            raise InvalidPurchaseError("Supplier name is required")
        if not opening_debt.is_finite() or opening_debt < 0:
            raise InvalidPurchaseError("Opening debt must be a nonnegative amount")
        supplier = (
            self._repository.get(supplier_id) if supplier_id is not None else None
        )
        supplier = supplier or Supplier(id=uuid.uuid4(), name=clean_name)
        supplier.name = clean_name
        supplier.phone = phone.strip() if phone else None
        supplier.description = description.strip() if description else None
        supplier.is_active = is_active
        supplier.opening_debt = opening_debt
        return self._row(self._repository.save(supplier))

    @staticmethod
    def _row(supplier: Supplier) -> SupplierRow:
        return SupplierRow(
            supplier.id,
            supplier.name,
            supplier.phone,
            supplier.description,
            supplier.is_active,
            Decimal(supplier.opening_debt),
        )
