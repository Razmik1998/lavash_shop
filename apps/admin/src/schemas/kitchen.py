from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from models import KitchenExport, KitchenExportItem, KitchenProduction, KitchenProductionItem


@dataclass(frozen=True)
class KitchenExportLineInput:
    product_id: uuid.UUID
    quantity: Decimal


@dataclass(frozen=True)
class KitchenExportRow:
    id: uuid.UUID
    document_number: str
    created_at: datetime
    created_by_name: str
    status: str
    total_quantity: Decimal
    total_cost: Decimal


@dataclass(frozen=True)
class KitchenExportDetail:
    export: KitchenExport
    created_by_name: str
    items: list[KitchenExportItem]


@dataclass(frozen=True)
class KitchenProductionLineInput:
    product_id: uuid.UUID
    quantity: Decimal


@dataclass(frozen=True)
class KitchenProductionRow:
    id: uuid.UUID
    document_number: str
    created_at: datetime
    created_by_name: str
    total_quantity: Decimal
    item_count: int


@dataclass(frozen=True)
class KitchenProductionDetail:
    production: KitchenProduction
    created_by_name: str
    items: list[KitchenProductionItem]


@dataclass(frozen=True)
class KitchenAnalyticsRow:
    document_number: str
    created_at: datetime
    product_name: str
    product_sku: str
    unit: str
    quantity: Decimal
    amount: Decimal
