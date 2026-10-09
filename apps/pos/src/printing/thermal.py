"""80 mm ESC/POS receipt formatting and Windows RAW printer transport."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics, QImage, QPainter

from printing.models import CloseoutReport, Receipt, ReceiptSettings

try:  # pywin32 is installed only in the Windows POS build.
    import win32print  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - exercised on non-Windows platforms
    win32print = None

logger = logging.getLogger(__name__)
_ARMENIAN_TRANSLITERATION = {
    "ա": "a",
    "բ": "b",
    "գ": "g",
    "դ": "d",
    "ե": "e",
    "զ": "z",
    "է": "e",
    "ը": "y",
    "թ": "t",
    "ժ": "zh",
    "ի": "i",
    "լ": "l",
    "խ": "kh",
    "ծ": "ts",
    "կ": "k",
    "հ": "h",
    "ձ": "dz",
    "ղ": "gh",
    "ճ": "ch",
    "մ": "m",
    "յ": "y",
    "ն": "n",
    "շ": "sh",
    "ո": "o",
    "չ": "ch",
    "պ": "p",
    "ջ": "j",
    "ռ": "rr",
    "ս": "s",
    "վ": "v",
    "տ": "t",
    "ր": "r",
    "ց": "ts",
    "ւ": "v",
    "փ": "p",
    "ք": "k",
    "օ": "o",
    "ֆ": "f",
    "և": "ev",
}


class ThermalPrinterError(RuntimeError):
    """A printer or receipt configuration error suitable for the POS UI."""


class ReceiptFormatter:
    """Create safe, width-limited ESC/POS bytes; QR stays native printer data."""

    ESC = b"\x1b"
    GS = b"\x1d"

    def __init__(self, settings: ReceiptSettings) -> None:
        if settings.paper_width_mm != 80:
            raise ValueError("Thermal receipts require 80 mm paper")
        if not 32 <= settings.chars_per_line <= 48:
            raise ValueError("Receipt characters per line must be between 32 and 48")
        self.width = settings.chars_per_line
        self.settings = settings

    def _text(self, value: str, *, font_size: int = 24) -> bytes:
        if self.settings.language == "hy" and self._contains_armenian(value):
            return self._raster_text(value, font_size=font_size)
        # Keep non-Armenian text in normal ESC/POS text mode. The active XP-80C
        # code page is not known to support Armenian, so English-mode Armenian
        # product names use a readable transliteration instead of UTF-8 bytes.
        safe = self._ascii_fallback(value)
        return safe.encode("cp437", errors="replace") + b"\n"

    @staticmethod
    def _contains_armenian(value: str) -> bool:
        return any("\u0530" <= character <= "\u058f" for character in value)

    def _raster_text(
        self,
        value: str,
        *,
        font_size: int = 26,
        centered: bool = False,
        bold: bool = False,
    ) -> bytes:
        """Render only Armenian text as a centered or left-aligned raster line."""
        width = self.width * 12
        height = font_size + 12
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        font = QFont("Arial")
        font.setPixelSize(font_size)
        font.setBold(bold)
        metrics = QFontMetrics(font)
        if metrics.horizontalAdvance(value) > width - 12:
            value = metrics.elidedText(value, Qt.TextElideMode.ElideRight, width - 12)
        painter.setFont(font)
        painter.setPen(Qt.GlobalColor.black)
        alignment = Qt.AlignmentFlag.AlignVCenter
        alignment |= (
            Qt.AlignmentFlag.AlignHCenter if centered else Qt.AlignmentFlag.AlignLeft
        )
        painter.drawText(
            0,
            0,
            width,
            height,
            alignment,
            value,
        )
        painter.end()

        return self._image_bytes(image)

    @staticmethod
    def _image_bytes(image: QImage) -> bytes:
        width, height = image.width(), image.height()
        row_bytes = (width + 7) // 8
        raster = bytearray()
        for y in range(height):
            for byte_index in range(row_bytes):
                bits = 0
                for bit in range(8):
                    x = byte_index * 8 + bit
                    if x < width and (image.pixel(x, y) & 0xFF) < 160:
                        bits |= 0x80 >> bit
                raster.append(bits)
        return (
            b"\x1dv0\x00"
            + bytes((row_bytes & 0xFF, row_bytes >> 8, height & 0xFF, height >> 8))
            + bytes(raster)
            + b"\n"
        )

    @staticmethod
    def _ascii_fallback(value: str) -> str:
        transliterated: list[str] = []
        index = 0
        while index < len(value):
            character = value[index]
            if value[index : index + 2].lower() == "ու":
                transliterated.append("U" if value[index].isupper() else "u")
                index += 2
                continue
            replacement = _ARMENIAN_TRANSLITERATION.get(character.lower())
            if replacement is not None:
                transliterated.append(
                    replacement.capitalize() if character.isupper() else replacement
                )
            else:
                transliterated.append(character)
            index += 1
        return "".join(transliterated).encode("ascii", errors="replace").decode("ascii")

    def _center(
        self,
        value: str,
        *,
        font_size: int = 26,
        bold: bool = False,
    ) -> bytes:
        # Set printer alignment here as well as centering inside Armenian
        # raster lines. Callers may follow left-aligned product rows.
        alignment = b"\x1ba\x01"
        if self.settings.language == "hy" and self._contains_armenian(value):
            return alignment + self._raster_text(
                value.strip(), font_size=font_size, centered=True, bold=bold
            )
        return alignment + self._text(value[: self.width].strip())

    def _pair(self, left: str, right: str) -> bytes:
        if len(right) >= self.width:
            raise ThermalPrinterError("A receipt amount exceeds the printable width.")
        left = left[: max(0, self.width - len(right) - 1)]
        return self._text(f"{left:<{self.width - len(right)}}{right}")

    def _product_details(self, left: str, right: str) -> bytes:
        if len(right) >= self.width:
            raise ThermalPrinterError("A product amount exceeds the printable width.")
        available_left = self.width - len(right) - 1
        if len(left) > available_left:
            return self._wrap_name(left) + self._text(right.rjust(self.width))
        return self._pair(left, right)

    def _unit_label(self, unit: str) -> str:
        labels = {
            "en": {
                "piece": "pcs",
                "kg": "kg",
                "g": "g",
                "l": "L",
                "barbecue": "portion",
            },
            "hy": {
                "piece": "pcs",
                "kg": "kg",
                "g": "g",
                "l": "L",
                "barbecue": "portion",
            },
        }
        return labels[self.settings.language].get(unit, unit)

    def _append_phone_numbers(self, output: bytearray) -> None:
        if not self.settings.phone_numbers:
            return
        prefix = "Հեռախոս՝ " if self.settings.language == "hy" else "Phone: "
        for phone in self.settings.phone_numbers:
            output.extend(self._center(f"{prefix}{phone}", font_size=24))

    def _separator(self) -> bytes:
        return self._text("=" * self.width)

    @staticmethod
    def _amount(value: Decimal) -> str:
        normalized = format(value, ",f")
        return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized

    def _wrap_name(self, name: str) -> bytes:
        safe = (
            name.strip()
            if self.settings.language == "hy"
            else self._ascii_fallback(name).strip()
        )
        words = safe.split() or ["Product"]
        lines: list[str] = []
        current = ""
        font = QFont("Arial")
        font.setPixelSize(24)
        metrics = QFontMetrics(font)

        def fits(value: str) -> bool:
            if self.settings.language == "hy" and self._contains_armenian(value):
                return metrics.horizontalAdvance(value) <= self.width * 12 - 12
            return len(value) <= self.width

        for word in words:
            while not fits(word):
                chunk = ""
                for character in word:
                    if chunk and not fits(chunk + character):
                        break
                    chunk += character
                if not chunk:
                    chunk = word[0]
                if current:
                    lines.append(current)
                    current = ""
                lines.append(chunk)
                word = word[len(chunk) :]
            candidate = f"{current} {word}".strip()
            if current and not fits(candidate):
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return b"".join(self._text(line) for line in lines)

    def format(self, receipt: Receipt) -> bytes:
        armenian = self.settings.language == "hy"
        currency = "֏" if armenian else "AMD"
        detail_currency = "AMD" if armenian else currency
        store_name = (
            "ՍԵՎԱՆԻ ՁԿՆԱՇԽԱՐՀ" if armenian else self.settings.store_name or "FISH SHOP"
        )
        output = bytearray(b"\x1b@\x1bt\x00")  # initialize, CP437
        output.extend(b"\x1ba\x01\x1bE\x01\x1d!\x11")
        output.extend(self._center(store_name, font_size=42, bold=True))
        output.extend(b"\x1d!\x00\x1bE\x00")
        output.extend(
            self._center("ԹԱՐՄ ՁՈՒԿ" if armenian else "FRESH FISH", font_size=28)
        )
        order = "Պատվեր" if armenian else "ORDER"
        output.extend(self._center(f"{order} #{receipt.sale_id}", font_size=24))
        output.extend(self._center(self._format_datetime(receipt.created_at)))
        output.extend(self._separator())
        output.extend(
            self._center("ՎԱՃԱՌՔԻ ԿՏՐՈՆ" if armenian else "FISH ORDER", font_size=30)
        )
        output.extend(b"\x1ba\x00")

        for line in receipt.lines:
            output.extend(self._wrap_name(line.product_name))
            quantity = self._amount(line.quantity)
            unit_price = self._amount(line.unit_price)
            line_total = self._amount(line.line_total)
            output.extend(
                self._product_details(
                    f"{quantity} {self._unit_label(line.unit)} x "
                    f"{unit_price} {detail_currency}",
                    f"{line_total} {detail_currency}",
                )
            )

        item_count = sum((line.quantity for line in receipt.lines), Decimal("0"))
        output.extend(self._separator())
        item_label = "ԱՊՐԱՆՔ" if armenian else "ITEMS"
        total_label = "ԸՆԴԱՄԵՆԸ" if armenian else "TOTAL"
        if armenian:
            output.extend(
                self._center(f"{self._amount(item_count)} {item_label}", font_size=24)
            )
            output.extend(b"\x1bE\x01")
            output.extend(
                self._center(
                    f"{total_label} {self._amount(receipt.total)} {currency}",
                    font_size=30,
                    bold=True,
                )
            )
        else:
            output.extend(self._pair(f"{self._amount(item_count)} {item_label}", ""))
            output.extend(b"\x1bE\x01\x1d!\x01")
            output.extend(
                self._pair(total_label, f"{self._amount(receipt.total)} {currency}")
            )
        output.extend(b"\x1d!\x00\x1bE\x00")
        output.extend(self._separator())

        if self.settings.online_order_url:
            url = self.settings.online_order_url.strip()
            try:
                qr_data = url.encode("ascii")
            except UnicodeEncodeError as exc:
                raise ThermalPrinterError(
                    "Online order URL must contain only ASCII characters."
                ) from exc
            if len(qr_data) > 120:
                raise ThermalPrinterError(
                    "Online order URL is too long for a centered receipt QR code."
                )
            output.extend(b"\x1ba\x01")
            order_online = "ՊԱՏՎԻՐԵԼ ԱՌՑԱՆՑ" if armenian else "ORDER ONLINE"
            output.extend(self._center(order_online, font_size=28))
            output.extend(self._qr(qr_data))
            # Keep a full blank row between the native QR and its caption.
            output.extend(b"\n")
            scan_to_order = (
                "Սկանավորեք և պատվիրեք" if armenian else "Scan & Order Online"
            )
            output.extend(self._center(scan_to_order, font_size=25))
        if self.settings.phone_numbers:
            output.extend(self._separator())
            self._append_phone_numbers(output)
        thank_you = "ՇՆՈՐՀԱԿԱԼՈՒԹՅՈՒՆ" if armenian else "THANK YOU!"
        output.extend(self._center(thank_you, font_size=34, bold=True))
        output.extend(b"\n\n\n\n")
        output.extend(b"\x1b@")
        if self.settings.cut_paper:
            output.extend(b"\x1d\x56\x00")
        return bytes(output)

    def _closeout_pair(self, label: str, value: str, *, bold: bool = False) -> bytes:
        """Align Armenian amounts by pixels, preserving the entire amount."""
        if self.settings.language != "hy":
            emphasis = b"\x1bE\x01" if bold else b"\x1bE\x00"
            return emphasis + self._product_details(label, value) + b"\x1bE\x00"
        width = self.width * 12
        font = QFont("Arial")
        font.setPixelSize(24)
        font.setBold(bold)
        metrics = QFontMetrics(font)
        if metrics.horizontalAdvance(value) > width - 16:
            raise ThermalPrinterError("A closeout amount exceeds the printable width.")
        stacked = (
            metrics.horizontalAdvance(label) + metrics.horizontalAdvance(value) + 32
            > width - 16
        )
        height = 72 if stacked else 40
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        painter.setFont(font)
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(
            8,
            0,
            width - 16,
            36,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            label,
        )
        painter.drawText(
            8,
            36 if stacked else 0,
            width - 16,
            36,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            value,
        )
        painter.end()
        return b"\x1ba\x00" + self._image_bytes(image)

    def format_closeout(self, report: CloseoutReport) -> bytes:
        labels = {
            "en": {
                "title": "SESSION CLOSEOUT",
                "date": "Date",
                "employee": "Employee",
                "session": "Session",
                "terminal": "Terminal",
                "opening": "Opening cash",
                "cash_sales": "Cash sales",
                "credit_sales": "Credit sales",
                "repayments": "Credit repayments",
                "sales_total": "Total sales",
                "handover": "Cash to hand over",
                "expected": "Expected drawer",
                "closing": "Counted drawer",
                "difference": "Difference",
                "footer": "SESSION CLOSED",
            },
            "hy": {
                "title": "ՍԵՍԻԱՅԻ ԱՄՓՈՓՈՒՄ",
                "date": "Ամսաթիվ",
                "employee": "Աշխատակից",
                "session": "Սեսիա",
                "terminal": "Տերմինալ",
                "opening": "Սկզբնական դրամարկղ",
                "cash_sales": "Կանխիկ վաճառք",
                "credit_sales": "Պարտքով վաճառք",
                "repayments": "Պարտքերի մարում",
                "sales_total": "Ընդհանուր վաճառք",
                "handover": "Հանձնման ենթակա գումար",
                "expected": "Ակնկալվող դրամարկղ",
                "closing": "Հաշված դրամարկղ",
                "difference": "Տարբերություն",
                "footer": "ՍԵՍԻԱՆ ԱՎԱՐՏՎԱԾ Է",
            },
        }[self.settings.language]
        armenian = self.settings.language == "hy"
        currency = "֏" if armenian else "AMD"
        output = bytearray(b"\x1b@\x1bt\x00")
        if self.settings.store_name:
            output.extend(
                self._center(self.settings.store_name, font_size=32, bold=True)
            )
        output.extend(b"\x1bE\x01")
        output.extend(self._center(labels["title"], font_size=30, bold=True))
        output.extend(b"\x1bE\x00")
        output.extend(self._center(self._format_datetime(report.closed_at)))
        output.extend(self._separator())
        output.extend(b"\x1ba\x00")
        for key, value in (
            ("employee", report.employee_name),
            ("terminal", report.terminal_id),
            ("session", report.session_id[:12]),
        ):
            output.extend(self._wrap_name(f"{labels[key]}: {value}"))

        def section(title: str) -> None:
            output.extend(self._separator())
            output.extend(b"\x1bE\x01")
            output.extend(self._center(title, font_size=26, bold=True))
            output.extend(b"\x1bE\x00\x1ba\x00")

        def money(label: str, value: Decimal, *, bold: bool = False) -> None:
            output.extend(
                self._closeout_pair(
                    label, f"{self._amount(value)} {currency}", bold=bold
                )
            )

        section("ՎԱՃԱՌՔՆԵՐ" if armenian else "SALES")
        money(labels["cash_sales"], report.cash_sales)
        money(labels["credit_sales"], report.credit_sales)
        money(labels["sales_total"], report.cash_sales + report.credit_sales, bold=True)
        section("ԴՐԱՄԱՐԿՂ" if armenian else "CASH DRAWER")
        money(labels["opening"], report.opening_cash)
        money(labels["repayments"], report.repayments)
        withdrawals_total = (
            report.cash_sales + report.repayments - report.handover_total
        )
        withdrawal_label = "Դուրսբերումներ" if armenian else "Withdrawals"
        money(withdrawal_label, withdrawals_total)
        money(labels["expected"], report.expected_cash)
        money(labels["closing"], report.closing_cash)
        money(labels["difference"], report.difference, bold=True)
        section("ՀԱՆՁՆՎՈՂ ԳՈՒՄԱՐ" if armenian else "CASH TO HAND OVER")
        output.extend(b"\x1bE\x01")
        if not armenian:
            output.extend(b"\x1d!\x11")
        output.extend(
            self._center(
                f"{self._amount(report.handover_total)} {currency}",
                font_size=40,
                bold=True,
            )
        )
        output.extend(b"\x1d!\x00\x1bE\x00")
        if report.withdrawals:
            section("ԴՈՒՐՍԲԵՐՈՒՄՆԵՐ" if armenian else "WITHDRAWAL HISTORY")
            for index, withdrawal in enumerate(report.withdrawals, 1):
                # Existing reports store date | recipient | amount | reason.
                parts = withdrawal.split(" | ", 3)
                if len(parts) == 4:
                    date, recipient, value, reason = parts
                    output.extend(
                        self._wrap_name(f"{index}. {self._format_datetime(date)}")
                    )
                    output.extend(self._wrap_name(recipient))
                    output.extend(self._closeout_pair("", value, bold=True))
                    output.extend(self._wrap_name(reason))
                else:
                    output.extend(self._wrap_name(withdrawal))
                output.extend(self._text("-" * self.width))
        output.extend(self._separator())
        output.extend(self._center(labels["footer"], font_size=26, bold=True))
        output.extend(b"\n\n\n\n\x1b@")
        if self.settings.cut_paper:
            output.extend(b"\x1d\x56\x00")
        return bytes(output)

    def _qr(self, data: bytes) -> bytes:
        # Epson ESC/POS QR: model 2, size 6, error correction M, store, print.
        length = len(data) + 3
        return b"".join(
            (
                b"\x1d\x28\x6b\x04\x00\x31\x41\x32\x00",
                b"\x1d\x28\x6b\x03\x00\x31\x43\x06",
                b"\x1d\x28\x6b\x03\x00\x31\x45\x31",
                bytes(
                    (
                        0x1D,
                        0x28,
                        0x6B,
                        length & 0xFF,
                        length >> 8,
                        0x31,
                        0x50,
                        0x30,
                    )
                ),
                data,
                b"\x1d\x28\x6b\x03\x00\x31\x51\x30",
            )
        )

    @staticmethod
    def _format_datetime(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone()
            return parsed.strftime("%d.%m.%Y | %H:%M")
        except ValueError:
            return value[:20]


class ThermalPrinterService:
    """Windows RAW transport for receipt bytes generated by ReceiptFormatter."""

    def __init__(
        self,
        settings: ReceiptSettings,
        printer_name: str,
        enabled: bool = True,
    ) -> None:
        self._settings = settings
        self._printer_name = printer_name.strip()
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def print_receipt(self, receipt: Receipt) -> bool:
        try:
            payload = ReceiptFormatter(self._settings).format(receipt)
        except (ValueError, ThermalPrinterError) as exc:
            raise ThermalPrinterError(
                f"Receipt configuration is invalid: {exc}"
            ) from exc
        return self._print_payload(
            payload, f"FishShop receipt {receipt.sale_id}", receipt.sale_id
        )

    def print_closeout_report(self, report: CloseoutReport) -> bool:
        try:
            payload = ReceiptFormatter(self._settings).format_closeout(report)
        except (ValueError, ThermalPrinterError) as exc:
            raise ThermalPrinterError(
                f"Closeout report configuration is invalid: {exc}"
            ) from exc
        return self._print_payload(
            payload, f"FishShop closeout {report.session_id}", report.session_id
        )

    def _print_payload(self, payload: bytes, document: str, record_id: str) -> bool:
        if not self._enabled:
            logger.info("printing op=receipt outcome=disabled")
            return False
        if not self._printer_name:
            raise ThermalPrinterError("No receipt printer is configured.")
        if sys.platform != "win32" or win32print is None:
            raise ThermalPrinterError(
                "Windows RAW printing is available only in the Windows POS app."
            )
        handle = None
        document_started = False
        page_started = False
        cleanup_error: Exception | None = None
        try:
            handle = win32print.OpenPrinter(self._printer_name)
            job_id = win32print.StartDocPrinter(handle, 1, (document, None, "RAW"))
            if not job_id:
                raise ThermalPrinterError("The printer did not accept the print job.")
            document_started = True
            win32print.StartPagePrinter(handle)
            page_started = True
            written = win32print.WritePrinter(handle, payload)
            if written != len(payload):
                raise ThermalPrinterError("The printer received an incomplete receipt.")
        except ThermalPrinterError:
            raise
        except Exception as exc:
            logger.warning(
                "printing op=receipt printer=%s sale_id=%s outcome=failed",
                self._printer_name,
                record_id,
                exc_info=True,
            )
            raise ThermalPrinterError(
                f"Could not print receipt. Check that '{self._printer_name}' is online."
            ) from exc
        finally:
            if handle is not None:
                if page_started:
                    try:
                        win32print.EndPagePrinter(handle)
                    except Exception as exc:
                        cleanup_error = exc
                        logger.warning(
                            "printing op=end_page outcome=failed", exc_info=True
                        )
                if document_started:
                    try:
                        win32print.EndDocPrinter(handle)
                    except Exception as exc:
                        cleanup_error = cleanup_error or exc
                        logger.warning(
                            "printing op=end_document outcome=failed", exc_info=True
                        )
                try:
                    win32print.ClosePrinter(handle)
                except Exception as exc:
                    cleanup_error = cleanup_error or exc
                    logger.warning("printing op=close outcome=failed", exc_info=True)

        if cleanup_error is not None:
            raise ThermalPrinterError(
                "Windows could not finish or release the receipt print job."
            ) from cleanup_error

        logger.info(
            "printing op=receipt printer=%s sale_id=%s outcome=sent",
            self._printer_name,
            record_id,
        )
        return True
