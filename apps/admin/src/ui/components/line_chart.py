"""Readable financial trends with signed scales and date-aware hover details."""

from __future__ import annotations

import math
from decimal import Decimal

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import QLabel, QToolTip, QVBoxLayout, QWidget

from ui.style import format_currency


class LineChart(QWidget):
    COLORS = ("#6366f1", "#0d9488", "#f43f5e", "#f59e0b")

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(380)
        self.setMouseTracking(True)
        self._labels: list[str] = []
        self._series: list[tuple[str, list[float]]] = []
        self._hover: int | None = None
        self._empty_message = "Գծապատկերի տվյալները հասանելի չեն։"
        self._legend = QWidget(self)
        self._legend_layout = QVBoxLayout(self._legend)
        self._legend_layout.setContentsMargins(0, 0, 0, 0)
        self._legend_layout.setSpacing(8)
        self.setAccessibleName("Ֆինանսական միտումներ․ գումար՝ դրամով, ըստ ամսաթվի")

    def set_series(
        self,
        labels: list[str],
        series: list[tuple[str, list[float]]],
        *,
        empty_message: str = "Գծապատկերի տվյալները հասանելի չեն։",
    ) -> None:
        if any(len(values) != len(labels) for _, values in series):
            raise ValueError("Each chart series must match its date labels")
        if any(not math.isfinite(v) for _, values in series for v in values):
            raise ValueError("Chart values must be finite")
        self._labels, self._series = labels, series
        self._empty_message = empty_message
        self._hover = None
        QToolTip.hideText()
        while self._legend_layout.count():
            item = self._legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, (title, _) in enumerate(series):
            mark = "━━" if index == 0 else "┄┄"
            label = QLabel(f"{mark}  {title}")
            label.setWordWrap(True)
            label.setStyleSheet(
                f"color: {self.COLORS[index % 4]}; background: transparent;"
            )
            self._legend_layout.addWidget(label)
            label.show()
        self._layout_legend()
        self.update()

    def _layout_legend(self) -> None:
        width = max(1, self.width() - 24)
        height = max(
            0,
            self._legend_layout.sizeHint().height(),
            self._legend_layout.heightForWidth(width),
        )
        self._legend.setGeometry(12, 4, width, height)
        self._legend.setVisible(bool(self._series))
        self.setMinimumHeight(max(380, height + 260))

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._layout_legend()
        super().resizeEvent(event)

    def _scale(self) -> tuple[float, float, float]:
        values = [v for _, data in self._series for v in data]
        low, high = min([0.0, *values]), max([0.0, *values])
        if low == high:
            return 0, 1, 0.25
        raw = (high - low) / 4
        magnitude = 10 ** math.floor(math.log10(raw))
        step = next(n * magnitude for n in (1, 2, 2.5, 5, 10) if n * magnitude >= raw)
        return math.floor(low / step) * step, math.ceil(high / step) * step, step

    @staticmethod
    def _tick(value: float, step: float) -> str:
        decimals = max(0, -Decimal(str(step)).normalize().as_tuple().exponent)
        return f"{value:,.{decimals}f}".replace(",", " ")

    def _plot(self) -> QRectF:
        low, high, step = self._scale()
        fm = self.fontMetrics()
        gutter = (
            max(fm.horizontalAdvance(self._tick(v, step)) for v in (low, high)) + 20
        )
        return QRectF(
            gutter,
            self._legend.geometry().bottom() + fm.height() + 24,
            max(1, self.width() - gutter - 18),
            max(1, self.height() - self._legend.height() - fm.height() - 95),
        )

    def _point(self, index: int, value: float) -> QPointF:
        plot = self._plot()
        low, high, _ = self._scale()
        x = (
            plot.center().x()
            if len(self._labels) == 1
            else plot.left() + plot.width() * index / max(1, len(self._labels) - 1)
        )
        return QPointF(x, plot.bottom() - (value - low) / (high - low) * plot.height())

    def _tick_indices(self) -> list[int]:
        count = len(self._labels)
        if count <= 1:
            return list(range(count))
        label_width = (
            max(
                self.fontMetrics().horizontalAdvance(s.split(" / ")[0])
                for s in self._labels
            )
            + 36
        )
        slots = min(count, max(2, int(self._plot().width() / label_width)))
        return sorted({round(i * (count - 1) / (slots - 1)) for i in range(slots)})

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self._plot()
        low, high, step = self._scale()
        fm = painter.fontMetrics()
        painter.setPen(QColor("#64748b"))
        painter.drawText(int(plot.left()), int(plot.top() - 10), "Գումար · ֏")
        if not self._labels or not self._series:
            painter.drawText(
                plot,
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self._empty_message,
            )
            return
        for i in range(round((high - low) / step) + 1):
            value = low + step * i
            y = plot.bottom() - (value - low) / (high - low) * plot.height()
            painter.setPen(QPen(QColor("#cbd5e1" if value == 0 else "#edf0f7"), 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor("#64748b"))
            painter.drawText(
                QRectF(0, y - fm.height() / 2, plot.left() - 12, fm.height()),
                Qt.AlignmentFlag.AlignRight,
                self._tick(value, step),
            )
        for i in self._tick_indices():
            label = self._labels[i].split(" / ")[0]
            width = fm.horizontalAdvance(label) + 12
            x = max(
                plot.left(),
                min(self._point(i, 0).x() - width / 2, plot.right() - width),
            )
            painter.drawText(
                QRectF(x, plot.bottom() + 12, width, fm.height() + 4),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )
        painter.drawText(
            QRectF(
                plot.left(), self.height() - fm.height() - 4, plot.width(), fm.height()
            ),
            Qt.AlignmentFlag.AlignRight,
            "Ամսաթիվ · մանրամասները՝ մկնիկով",
        )
        painter.save()
        painter.setClipRect(plot.adjusted(-4, -4, 4, 4))
        for index, (_, values) in enumerate(self._series):
            color = QColor(self.COLORS[index % 4])
            path = QPainterPath()
            for i, value in enumerate(values):
                point = self._point(i, value)
                if i == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            if values and index == 0:
                area = QPainterPath(path)
                area.lineTo(self._point(len(values) - 1, 0))
                area.lineTo(self._point(0, 0))
                area.closeSubpath()
                shade = QColor(color)
                shade.setAlpha(22)
                painter.fillPath(area, shade)
            pen = QPen(color, 2.8)
            if index:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawPath(path)
            painter.setBrush(color)
            if len(values) <= 12:
                for i, value in enumerate(values):
                    painter.drawEllipse(self._point(i, value), 3, 3)
        if self._hover is not None:
            x = self._point(self._hover, 0).x()
            painter.setPen(QPen(QColor("#94a3b8"), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            for index, (_, values) in enumerate(self._series):
                painter.setPen(QPen(QColor("white"), 2))
                painter.setBrush(QColor(self.COLORS[index % 4]))
                painter.drawEllipse(self._point(self._hover, values[self._hover]), 5, 5)
        painter.restore()
        if not any(v for _, data in self._series for v in data):
            painter.setPen(QColor("#64748b"))
            painter.drawText(
                plot,
                Qt.AlignmentFlag.AlignCenter,
                "Այս ժամանակահատվածներում գումարներ չեն գրանցվել։",
            )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        plot = self._plot()
        if not self._labels or not self._series or not plot.contains(event.position()):
            self._hover = None
            QToolTip.hideText()
            self.update()
            return
        index = round(
            (event.position().x() - plot.left())
            / plot.width()
            * (len(self._labels) - 1)
        )
        self._hover = max(0, min(len(self._labels) - 1, index))
        dates = self._labels[self._hover].split(" / ")
        text = []
        for i, (title, values) in enumerate(self._series):
            day = dates[min(i, len(dates) - 1)]
            if i > 0 and len(dates) == 1:
                day = "Ընտրված ամսվա համապատասխան օրերը"
            text.append(
                f"{title}\n{day} · {format_currency(Decimal(str(values[self._hover])))}"
            )
        QToolTip.showText(event.globalPosition().toPoint(), "\n\n".join(text), self)
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = None
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)
