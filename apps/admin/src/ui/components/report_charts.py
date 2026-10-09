"""Compact report visualizations with exact values and signed comparisons."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from ui.style import format_currency

PALETTE = ("#6366f1", "#f59e0b", "#f43f5e", "#10b981")


class ReportChart(QWidget):
    def __init__(self, *, donut: bool = False) -> None:
        super().__init__()
        self.donut = donut
        self.items: list[tuple[str, float | None, float | None]] = []
        self.setMinimumHeight(285)
        self.setMinimumWidth(300)

    def set_items(self, items: list[tuple[str, float | None, float | None]]) -> None:
        self.items = items
        description = "\n".join(
            f"{title}: "
            + ("Անհայտ" if value is None else format_currency(Decimal(str(value))))
            + (
                f" · Նախորդ՝ {format_currency(Decimal(str(old)))}"
                if old is not None
                else ""
            )
            for title, value, old in items
        )
        self.setAccessibleName(description or "Տվյալներ չկան")
        self.setToolTip(description)
        row_height = self.fontMetrics().height() * 2 + 44
        self.setMinimumHeight(
            190 + len(items) * (self.fontMetrics().height() * 2 + 12)
            if self.donut
            else max(285, len(items) * row_height + 12)
        )
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        if self.donut:
            total = sum(max(0, value or 0) for _, value, _ in self.items)
            ring = QRectF((width - 150) / 2, 12, 150, 150)
            painter.setPen(QPen(QColor("#eef2ff"), 22))
            painter.drawEllipse(ring)
            start = 90 * 16
            for index, (_, value, _) in enumerate(self.items):
                span = round(max(0, value or 0) / total * 360 * 16) if total else 0
                painter.setPen(QPen(QColor(PALETTE[index % 4]), 22))
                painter.drawArc(ring, start, -span)
                start -= span
            painter.setPen(QColor("#475569"))
            painter.drawText(
                ring, Qt.AlignmentFlag.AlignCenter, "100%" if total else "Տվյալներ չկան"
            )
            for index, (title, value, _) in enumerate(self.items):
                row_height = self.fontMetrics().height() * 2 + 12
                y = 190 + index * row_height
                painter.setPen(QColor(PALETTE[index % 4]))
                painter.drawText(10, y, "●")
                painter.setPen(QColor("#475569"))
                percent = (value or 0) / total * 100 if total else 0
                painter.drawText(
                    QRectF(30, y - 17, width - 40, row_height),
                    Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                    f"{title} · {percent:.1f}%\n"
                    f"{format_currency(Decimal(str(value or 0)))}",
                )
        else:
            values = [
                v for _, value, old in self.items for v in (value, old) if v is not None
            ]
            low, high = min([0, *values]), max([1, *values])
            left, right = 12.0, width - 12.0
            zero = left + (right - left) * (-low) / (high - low)
            row_height = self.fontMetrics().height() * 2 + 44
            for index, (title, value, old) in enumerate(self.items):
                y = index * row_height + 8
                painter.setPen(QColor("#475569"))
                display = (
                    "Անհայտ" if value is None else format_currency(Decimal(str(value)))
                )
                painter.drawText(
                    QRectF(left, y, right - left, self.fontMetrics().height() * 2),
                    Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                    title,
                )
                bar_y = y + self.fontMetrics().height() * 2 + 4
                painter.drawText(
                    QRectF(left, bar_y, right - left, self.fontMetrics().height()),
                    Qt.AlignmentFlag.AlignRight,
                    display,
                )
                bar_y += self.fontMetrics().height()
                for offset, number, color in (
                    (4, value, PALETTE[index % 4]),
                    (17, old, "#cbd5e1"),
                ):
                    if number is None or number == 0:
                        continue
                    end = left + (right - left) * (number - low) / (high - low)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(color))
                    painter.drawRoundedRect(
                        QRectF(min(zero, end), bar_y + offset, abs(end - zero), 9),
                        4,
                        4,
                    )
                painter.setPen(QColor("#94a3b8"))
                painter.drawLine(int(zero), bar_y + 2, int(zero), bar_y + 28)
        painter.end()
