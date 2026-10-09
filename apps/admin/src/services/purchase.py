"""Application layer: AuthService, EmployeeService."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from exceptions import (
    InvalidFiltersError,
    InvalidPurchaseError,
    PaymentError,
    PurchaseCancellationError,
    PurchaseNotFoundError,
)
from models import (
    PaymentMethod,
    Product,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    SupplierPayment,
)
from repository import (
    ProductRepository,
    PurchaseRepository,
)
from schemas import (
    PurchaseDetail,
    PurchaseFilters,
    PurchaseLineInput,
    PurchasePage,
    PurchaseRow,
    PurchaseSummary,
    SupplierReportRow,
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


class PurchaseService:
    def __init__(self, repository: PurchaseRepository, product_repository: ProductRepository) -> None:
        self._repository = repository
        self._product_repository = product_repository

    def procurement_recommendations(self) -> list[dict[str, object]]:
        return self._repository.procurement_recommendations()

    def create_draft(
        self,
        supplier_id: uuid.UUID,
        purchase_date: datetime,
        notes: str | None,
        lines: list[PurchaseLineInput],
    ) -> Purchase:
        if not lines:
            raise InvalidPurchaseError("Purchase must contain at least one item")
        items: list[PurchaseItem] = []
        total = Decimal("0")
        for line in lines:
            if (
                not line.quantity.is_finite()
                or not line.unit_cost.is_finite()
                or line.quantity <= 0
                or line.quantity.as_tuple().exponent < -3
                or line.unit_cost < 0
                or line.unit_cost.as_tuple().exponent < -2
            ):
                raise InvalidPurchaseError("Purchase values are invalid")
            product = self._product_repository.get_by_id(line.product_id)
            if product is None or not product.is_active:
                raise InvalidPurchaseError("Purchase product is unavailable")
            selling_price, markup = _purchase_sale_pricing(product, line)
            line_total = (line.quantity * line.unit_cost).quantize(Decimal("0.01"))
            total += line_total
            parent = (
                self._product_repository.get_by_id(product.parent_product_id)
                if product.parent_product_id is not None
                else None
            )
            items.append(
                PurchaseItem(
                    product_id=product.id,
                    product_name=product.display_name(parent),
                    product_sku=product.sku,
                    unit=product.unit.value,
                    quantity=line.quantity,
                    unit_cost=line.unit_cost,
                    line_total=line_total,
                    selling_price=selling_price,
                    markup_percentage=markup,
                )
            )
        purchase = Purchase(id=uuid.uuid4(), purchase_number=f"PUR-{uuid.uuid4().hex[:10].upper()}", supplier_id=supplier_id, purchase_date=purchase_date, total=total, status=PurchaseStatus.DRAFT, notes=notes)
        try:
            return self._repository.create_draft(purchase, items)
        except ValueError as exc:
            raise InvalidPurchaseError(str(exc)) from exc

    def list_purchases(
        self, filters: PurchaseFilters | None = None
    ) -> list[PurchaseRow]:
        filters = filters or PurchaseFilters()
        return self._purchase_rows(self._repository.list_purchases(filters))

    def list_purchase_page(
        self,
        filters: PurchaseFilters,
        offset: int = 0,
        limit: int = 50,
    ) -> PurchasePage:
        if offset < 0 or not 1 <= limit <= 100:
            raise InvalidFiltersError("offset or limit is invalid")
        rows = self._repository.list_purchase_page(filters, offset, limit + 1)
        has_more = len(rows) > limit
        return PurchasePage(self._purchase_rows(rows[:limit]), has_more)

    @staticmethod
    def _purchase_rows(
        rows: list[tuple[Purchase, str, Decimal, Decimal]],
    ) -> list[PurchaseRow]:
        return [
            PurchaseRow(
                p.id,
                p.purchase_number,
                name,
                p.purchase_date,
                p.total,
                paid,
                p.total - paid,
                p.status.value,
                item_quantity,
            )
            for p, name, paid, item_quantity in rows
        ]

    def summarize_purchases(self, filters: PurchaseFilters | None = None) -> PurchaseSummary:
        count, amount, quantity, drafts = self._repository.summarize_purchases(
            filters or PurchaseFilters()
        )
        return PurchaseSummary(count, amount, quantity, drafts)

    def supplier_report(
        self, filters: PurchaseFilters | None = None
    ) -> list[SupplierReportRow]:
        return [
            SupplierReportRow(
                supplier_id,
                supplier_name,
                purchase_count,
                purchased_quantity,
                purchase_amount,
                paid_amount,
                purchase_amount - paid_amount,
            )
            for (
                supplier_id,
                supplier_name,
                purchase_count,
                purchased_quantity,
                purchase_amount,
                paid_amount,
            ) in self._repository.supplier_report(filters or PurchaseFilters())
        ]

    def update_draft(
        self,
        purchase_id: uuid.UUID,
        supplier_id: uuid.UUID,
        purchase_date: datetime,
        notes: str | None,
        lines: list[PurchaseLineInput],
    ) -> Purchase:
        purchase, items = self._build_purchase_items(supplier_id, purchase_date, notes, lines)
        try:
            return self._repository.update_draft(purchase_id, purchase, items)
        except ValueError as exc:
            raise InvalidPurchaseError(str(exc)) from exc

    def reopen_for_edit(self, purchase_id: uuid.UUID) -> Purchase:
        try:
            return self._repository.reopen_for_edit(purchase_id)
        except ValueError as exc:
            raise InvalidPurchaseError(str(exc)) from exc

    def delete_draft(self, purchase_id: uuid.UUID) -> None:
        try:
            self._repository.delete_draft(purchase_id)
        except ValueError as exc:
            raise InvalidPurchaseError(str(exc)) from exc

    def get_detail(self, purchase_id: uuid.UUID) -> PurchaseDetail:
        result = self._repository.get_detail(purchase_id)
        if result is None:
            raise PurchaseNotFoundError(f"Purchase not found: {purchase_id}")
        return PurchaseDetail(*result)

    def confirm(
        self,
        purchase_id: uuid.UUID,
        initial_payment: Decimal = Decimal("0"),
        payment_method: PaymentMethod = PaymentMethod.CASH,
        price_updates: dict[uuid.UUID, Decimal] | None = None,
    ) -> Purchase:
        try:
            return self._repository.confirm(purchase_id, initial_payment, payment_method, price_updates or {})
        except ValueError as exc:
            raise InvalidPurchaseError(str(exc)) from exc

    def add_payment(
        self,
        purchase_id: uuid.UUID,
        amount: Decimal,
        method: PaymentMethod,
        payment_date: datetime,
        notes: str | None = None,
    ) -> SupplierPayment:
        try:
            return self._repository.add_payment(purchase_id, amount, method, payment_date, notes)
        except ValueError as exc:
            raise PaymentError(str(exc)) from exc

    def pay_supplier_debt(
        self,
        supplier_id: uuid.UUID,
        amount: Decimal,
        method: PaymentMethod,
        payment_date: datetime,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
    ) -> int:
        if (
            not amount.is_finite()
            or amount <= 0
            or amount != amount.quantize(Decimal("0.01"))
        ):
            raise PaymentError("Payment amount is invalid")
        try:
            return self._repository.pay_supplier_debt(
                supplier_id, amount, method, payment_date, from_datetime, to_datetime
            )
        except ValueError as exc:
            raise PaymentError(str(exc)) from exc

    def cancel(self, purchase_id: uuid.UUID) -> Purchase:
        try:
            return self._repository.cancel(purchase_id)
        except ValueError as exc:
            raise PurchaseCancellationError(str(exc)) from exc

    def _build_purchase_items(
        self,
        supplier_id: uuid.UUID,
        purchase_date: datetime,
        notes: str | None,
        lines: list[PurchaseLineInput],
    ) -> tuple[Purchase, list[PurchaseItem]]:
        if not lines:
            raise InvalidPurchaseError("Purchase must contain at least one item")
        items: list[PurchaseItem] = []
        total = Decimal("0")
        for line in lines:
            if line.quantity <= 0 or line.unit_cost < 0:
                raise InvalidPurchaseError("Purchase values are invalid")
            product = self._product_repository.get_by_id(line.product_id)
            if product is None or not product.is_active:
                raise InvalidPurchaseError("Purchase product is unavailable")
            selling_price, markup = _purchase_sale_pricing(product, line)
            line_total = (line.quantity * line.unit_cost).quantize(Decimal("0.01"))
            total += line_total
            items.append(
                PurchaseItem(
                    product_id=product.id,
                    product_name=product.name,
                    product_sku=product.sku,
                    unit=product.unit.value,
                    quantity=line.quantity,
                    unit_cost=line.unit_cost,
                    line_total=line_total,
                    selling_price=selling_price,
                    markup_percentage=markup,
                )
            )
        purchase = Purchase(
            id=uuid.uuid4(),
            purchase_number=f"PUR-{uuid.uuid4().hex[:10].upper()}",
            supplier_id=supplier_id,
            purchase_date=purchase_date,
            total=total,
            status=PurchaseStatus.DRAFT,
            notes=notes,
        )
        return purchase, items


def _purchase_sale_pricing(
    product: Product, line: PurchaseLineInput
) -> tuple[Decimal | None, Decimal]:
    if product.is_for_sale is False:
        return None, Decimal("0")
    selling_price = line.selling_price
    if selling_price is None or not selling_price.is_finite() or selling_price < 0:
        raise InvalidPurchaseError("Selling price is required for sellable products")
    if selling_price.as_tuple().exponent < -2:
        raise InvalidPurchaseError("Selling price has too many decimal places")
    markup = line.markup_percentage
    calculated = (
        (selling_price - line.unit_cost) / line.unit_cost * Decimal("100")
        if line.unit_cost
        else Decimal("0")
    )
    if markup is None:
        markup = calculated
    if not markup.is_finite() or markup < 0:
        raise InvalidPurchaseError("Markup must be non-negative")
    if abs(markup - calculated) > Decimal("0.001"):
        raise InvalidPurchaseError("Markup does not match prices")
    return selling_price, markup.quantize(Decimal("0.001"))
