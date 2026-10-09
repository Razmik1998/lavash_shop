import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from models import Purchase, PurchaseItem, SupplierPayment


@dataclass(frozen=True)
class PurchaseLineInput:
    product_id: uuid.UUID
    quantity: Decimal
    unit_cost: Decimal
    selling_price: Decimal | None
    markup_percentage: Decimal | None = None


@dataclass(frozen=True)
class PurchaseRow:
    id: uuid.UUID
    purchase_number: str
    supplier_name: str
    purchase_date: datetime
    total: Decimal
    paid: Decimal
    debt: Decimal
    status: str
    item_quantity: Decimal = Decimal("0")


@dataclass(frozen=True)
class PurchasePage:
    items: list[PurchaseRow]
    has_more: bool


@dataclass(frozen=True)
class PurchaseSummary:
    purchase_count: int
    total_amount: Decimal
    item_quantity: Decimal
    draft_count: int


@dataclass(frozen=True)
class PurchaseDetail:
    purchase: Purchase
    items: list[PurchaseItem]
    payments: list[SupplierPayment]
