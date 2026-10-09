"""Printer discovery and receipt output behind an application boundary."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QRect, QSizeF, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPageSize, QPainter, QPdfWriter
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

from printing.models import Receipt, ReceiptSettings

logger = logging.getLogger(__name__)


class PrinterService:
    def __init__(self, settings: ReceiptSettings) -> None:
        self._settings = settings

    @staticmethod
    def available_printers() -> list[str]:
        return [printer.printerName() for printer in QPrinterInfo.availablePrinters()]

    @staticmethod
    def default_printer() -> str | None:
        printer = QPrinterInfo.defaultPrinter()
        name = printer.printerName()
        return name or None

    def print_receipt(self, receipt: Receipt, printer_name: str) -> None:
        if printer_name not in self.available_printers():
            raise RuntimeError(f"Printer is unavailable: {printer_name}")
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPrinterName(printer_name)
        printer.setPageSize(
            QPageSize(
                QSizeF(float(self._settings.paper_width_mm), 220.0),
                QPageSize.Unit.Millimeter,
            )
        )
        painter = QPainter(printer)
        try:
            self._draw_receipt(painter, receipt)
        finally:
            painter.end()
        logger.info(
            "printing op=receipt printer=%s sale_id=%s outcome=sent",
            printer_name,
            receipt.sale_id,
        )

    def save_receipt_pdf(self, receipt: Receipt) -> Path:
        directory = self._settings.receipt_directory
        directory.mkdir(parents=True, exist_ok=True)
        output_path = directory / f"receipt-{receipt.sale_id}.pdf"
        writer = QPdfWriter(str(output_path))
        writer.setResolution(96)
        writer.setPageSize(
            QPageSize(QPageSize.PageSizeId.A4)
        )
        painter = QPainter(writer)
        try:
            self._draw_receipt(painter, receipt)
        finally:
            painter.end()
        logger.info(
            "printing op=receipt_pdf path=%s sale_id=%s outcome=saved",
            output_path,
            receipt.sale_id,
        )
        return output_path

    def _draw_receipt(self, painter: QPainter, receipt: Receipt) -> None:
        page_width = painter.viewport().width()
        margin = max(24, int(page_width * 0.07))
        content_width = page_width - margin * 2
        body_font = QFont("Arial", 10)
        header_font = QFont("Arial", 10, QFont.Weight.Bold)
        title_font = QFont("Arial", 20, QFont.Weight.Bold)
        painter.setFont(body_font)
        y = margin

        painter.setFont(title_font)
        painter.drawText(margin, y, content_width, 36, 0, self._settings.store_name)
        y += 48
        painter.setFont(body_font)
        if self._settings.address:
            painter.drawText(margin, y, content_width, 24, 0, self._settings.address)
            y += 24
        for phone in self._settings.phone_numbers:
            painter.drawText(margin, y, content_width, 24, 0, f"Phone: {phone}")
            y += 24
        y += 12
        painter.drawText(margin, y, content_width, 24, 0, f"Receipt: {receipt.sale_id}")
        y += 24
        painter.drawText(
            margin, y, content_width, 24, 0, f"Terminal: {receipt.terminal_id}"
        )
        y += 24
        painter.drawText(margin, y, content_width, 24, 0, f"Date: {receipt.created_at}")
        y += 42

        columns = (0.34, 0.18, 0.14, 0.17, 0.17)
        widths = [int(content_width * fraction) for fraction in columns]
        widths[-1] += content_width - sum(widths)
        headers = ("Name", "Code", "Quantity", "Unit price", "Total")
        row_height = 34
        x = margin
        painter.setFont(header_font)
        painter.setBrush(Qt.GlobalColor.lightGray)
        painter.setPen(Qt.GlobalColor.black)
        for width, header in zip(widths, headers, strict=True):
            rect = QRect(x, y, width, row_height)
            painter.drawRect(rect)
            painter.drawText(
                rect.adjusted(8, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter,
                header,
            )
            x += width
        y += row_height

        painter.setBrush(Qt.BrushStyle.NoBrush)
        metrics = QFontMetrics(body_font)
        for line in receipt.lines:
            values = (
                metrics.elidedText(
                    line.product_name,
                    Qt.TextElideMode.ElideRight,
                    widths[0] - 16,
                ),
                line.product_code,
                self._format_amount(line.quantity),
                self._format_currency(line.unit_price),
                self._format_currency(line.line_total),
            )
            x = margin
            for index, (width, value) in enumerate(
                zip(widths, values, strict=True)
            ):
                rect = QRect(x, y, width, row_height)
                painter.drawRect(rect)
                alignment = (
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    if index == 0
                    else Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                painter.drawText(rect.adjusted(8, 0, -8, 0), alignment, value)
                x += width
            y += row_height

        y += 24
        painter.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        painter.drawText(
            margin, y, content_width, 32, Qt.AlignmentFlag.AlignRight,
            f"Total: {self._format_currency(receipt.total)}",
        )

    @staticmethod
    def _format_amount(value: object) -> str:
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    @classmethod
    def _format_currency(cls, value: object) -> str:
        return f"{cls._format_amount(value)} ֏"


class PrinterCatalog:
    """Small facade for UI settings without exposing Qt printer classes."""

    def __init__(self, names: Sequence[str]) -> None:
        self.names = tuple(names)
