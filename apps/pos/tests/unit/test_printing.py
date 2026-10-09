from __future__ import annotations

from pathlib import Path

from networking.protocol import SaleItemPayload, SalePayload
from printing import PrinterService, ReceiptFormatter
from printing.models import ReceiptSettings, receipt_from_sale


def _sale() -> SalePayload:
    return SalePayload(
        id="sale-1",
        session_id="session-1",
        terminal_id="pos-1",
        employee_user_id="employee-1",
        status="completed",
        total="1450",
        created_at="2026-09-11T12:00:00+00:00",
        items=[
            SaleItemPayload(
                product_id="product-1",
                product_name="fresh apples",
                product_sku="SKU-001",
                unit="piece",
                quantity="2",
                unit_price="400",
                line_total="800",
            ),
            SaleItemPayload(
                product_id="product-2",
                product_name="milk",
                product_sku="SKU-002",
                unit="piece",
                quantity="1",
                unit_price="650",
                line_total="650",
            ),
        ],
        audit_events=[],
    )


def test_receipt_contains_authoritative_sale_lines() -> None:
    receipt = receipt_from_sale(_sale())

    assert receipt.sale_id == "sale-1"
    assert receipt.lines[0].product_name == "Fresh Apples"
    assert receipt.lines[0].product_code == "SKU-001"
    assert receipt.lines[0].quantity == 2
    assert receipt.lines[0].line_total == 800
    assert receipt.total == 1450


def test_receipt_settings_accept_supported_paper_widths() -> None:
    assert ReceiptSettings(paper_width_mm=58).paper_width_mm == 58
    assert ReceiptSettings(paper_width_mm=80).paper_width_mm == 80


def test_thermal_receipt_uses_ascii_native_qr_and_cut_command() -> None:
    formatter = ReceiptFormatter(
        ReceiptSettings(
            chars_per_line=48,
            online_order_url="https://shop.example/order",
            cut_paper=True,
        )
    )

    payload = formatter.format(receipt_from_sale(_sale()))

    assert b"=" * 48 + b"\n" in payload
    assert b"Fresh Apples" in payload
    assert b"1,450 AMD" in payload
    assert b"https://shop.example/order" in payload
    assert b"\x1d\x28\x6b\x03\x00\x31\x51\x30" in payload
    assert payload.endswith(b"\x1d\x56\x00")
    assert not any(byte >= 0x80 for byte in payload)


def test_armenian_receipt_raster_text_is_centered_and_larger(qapp: object) -> None:
    formatter = ReceiptFormatter(
        ReceiptSettings(
            language="hy",
            store_name="ՁԿԱՆ ԽԱՆՈՒԹ",
            online_order_url="https://shop.example/order",
        )
    )

    centered_title = formatter._center("ՇՆՈՐՀԱԿԱԼՈՒԹՅՈՒՆ", font_size=34, bold=True)
    payload = formatter.format(receipt_from_sale(_sale()))
    qr_print = b"\x1d\x28\x6b\x03\x00\x31\x51\x30"

    assert centered_title.startswith(b"\x1ba\x01\x1dv0\x00")
    assert centered_title[7] == 72  # 576 printable dots at 48 columns.
    assert centered_title[9:11] == bytes((46, 0))  # Larger Armenian type.
    raster = centered_title[11 : 11 + (72 * 46)]
    occupied_columns = [
        byte_index * 8 + bit
        for byte_index in range(72)
        for bit in range(8)
        if any(raster[row * 72 + byte_index] & (0x80 >> bit) for row in range(46))
    ]
    left_margin = min(occupied_columns)
    right_margin = 575 - max(occupied_columns)
    assert abs(left_margin - right_margin) <= 2
    assert qr_print + b"\n\x1ba\x01\x1dv0\x00" in payload


def test_receipt_pdf_is_saved_as_a_nonempty_document(
    tmp_path: Path, qapp: object
) -> None:
    receipt = receipt_from_sale(_sale())
    service = PrinterService(
        ReceiptSettings(store_name="Test Store", receipt_directory=tmp_path)
    )

    output_path = service.save_receipt_pdf(receipt)

    assert output_path == tmp_path / "receipt-sale-1.pdf"
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_closeout_sections_and_withdrawals_are_complete() -> None:
    from decimal import Decimal

    from printing.models import CloseoutReport

    report = CloseoutReport(
        session_id="session-123",
        terminal_id="pos-1",
        employee_name="Andranik",
        closed_at="2026-10-09T01:24:00+04:00",
        opening_cash=Decimal("20000"),
        cash_sales=Decimal("161640"),
        credit_sales=Decimal("3468.68"),
        repayments=Decimal("0"),
        handover_total=Decimal("40428"),
        expected_cash=Decimal("60428"),
        closing_cash=Decimal("20000"),
        difference=Decimal("40428"),
        withdrawals=(
            "2026-10-09T01:24:44.149869+04:00 | Andranik | 121212 AMD | "
            "Payment for a delivery with a long description that must wrap completely",
        ),
    )
    payload = ReceiptFormatter(ReceiptSettings(chars_per_line=32)).format_closeout(
        report
    )
    for text in (
        b"SALES",
        b"CASH DRAWER",
        b"CASH TO HAND OVER",
        b"165,108.68 AMD",
        b"121,212 AMD",
        b"WITHDRAWAL HISTORY",
    ):
        assert text in payload
    assert b"wrap completely" in b" ".join(payload.split())
    assert b"149869" not in payload
    assert b"\x1ba\x00" in payload
    assert payload.endswith(b"\x1d\x56\x00")


def test_armenian_closeout_amounts_use_pixel_alignment(qapp: object) -> None:
    formatter = ReceiptFormatter(ReceiptSettings(language="hy", chars_per_line=32))
    payload = formatter._closeout_pair("Ակնկալվող դրամարկղ", "165,108.68 ֏")
    assert payload.startswith(b"\x1ba\x00\x1dv0\x00")
    # A narrow paper layout stacks long labels above the right-aligned amount.
    assert int.from_bytes(payload[7:9], "little") == 48
    assert int.from_bytes(payload[9:11], "little") == 72
