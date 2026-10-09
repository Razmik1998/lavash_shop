"""Receipt data models independent from Qt printing APIs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from networking.protocol import SalePayload


@dataclass(frozen=True)
class ReceiptLine:
    product_name: str
    product_code: str
    unit: str
    unit_price: Decimal
    quantity: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class Receipt:
    sale_id: str
    created_at: str
    terminal_id: str
    lines: tuple[ReceiptLine, ...]
    total: Decimal


@dataclass(frozen=True)
class CloseoutReport:
    session_id: str
    terminal_id: str
    employee_name: str
    closed_at: str
    opening_cash: Decimal
    cash_sales: Decimal
    credit_sales: Decimal
    repayments: Decimal
    handover_total: Decimal
    expected_cash: Decimal
    closing_cash: Decimal
    difference: Decimal
    withdrawals: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReceiptSettings:
    store_name: str = ""
    phone_numbers: tuple[str, ...] = ()
    address: str = ""
    paper_width_mm: int = 80
    receipt_directory: Path = Path("receipts")
    chars_per_line: int = 48
    cut_paper: bool = True
    online_order_url: str = ""
    language: str = "en"

    def __post_init__(self) -> None:
        if self.paper_width_mm not in (58, 80):
            raise ValueError("Receipt paper width must be 58 or 80 millimeters")
        if self.language not in {"en", "hy"}:
            raise ValueError("Receipt language must be 'en' or 'hy'")


def receipt_from_sale(sale: SalePayload) -> Receipt:
    """Build a receipt from a confirmed sale response."""
    lines = tuple(
        ReceiptLine(
            product_name=str(item.product_name).title(),
            product_code=str(item.product_sku),
            unit=str(item.unit),
            unit_price=Decimal(item.unit_price),
            quantity=Decimal(item.quantity),
            line_total=Decimal(item.line_total),
        )
        for item in sale.items
    )
    return Receipt(
        sale_id=str(sale.id),
        created_at=str(sale.created_at),
        terminal_id=str(sale.terminal_id),
        lines=lines,
        total=Decimal(sale.total),
    )
