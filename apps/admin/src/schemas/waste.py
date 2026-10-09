from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from models.waste import WasteDocument, WasteDocumentItem


@dataclass(frozen=True)
class WasteLineInput:
    product_id: uuid.UUID
    quantity: Decimal
    reason: str = "spoiled"
    reason_note: str | None = None


@dataclass(frozen=True)
class WasteRow:
    id: uuid.UUID
    document_number: str
    created_at: datetime
    created_by_name: str
    status: str
    total_quantity: Decimal
    total_cost: Decimal


@dataclass(frozen=True)
class WasteDetail:
    document: WasteDocument
    created_by_name: str
    items: list[WasteDocumentItem]


WASTE_REASONS = {
    "spoiled": "Փչացած",
    "expired": "Ժամկետանց",
    "damaged": "Վնասված",
    "inedible": "Սննդի համար ոչ պիտանի",
    "custom": "Այլ պատճառ",
}
