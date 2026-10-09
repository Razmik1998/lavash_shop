from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class CustomerRow:
    id: uuid.UUID
    first_name: str
    last_name: str
    phone: str
    address: str | None
    notes: str | None
    is_active: bool
    current_debt: Decimal


@dataclass(frozen=True)
class CustomerPaymentRow:
    id: uuid.UUID
    customer_id: uuid.UUID
    amount: Decimal
    pos_session_id: uuid.UUID
    pos_user_id: uuid.UUID
    paid_at: datetime


@dataclass(frozen=True)
class CustomerPaymentHistoryRow:
    payment_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    phone: str
    amount: Decimal
    pos_session_id: uuid.UUID
    pos_user_id: uuid.UUID
    paid_at: datetime
