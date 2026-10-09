"""Surfaces, headings and status widgets shared by the Admin UI."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.components.buttons import GhostButton


class Panel(QFrame):
    """A neutral surface that groups related controls or data."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")


class NavScrollArea(QScrollArea):
    """Scrolling container for sidebar navigation buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        inner = QWidget()
        inner.setObjectName("navScrollBody")
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(0, 0, 0, 8)
        self.body.setSpacing(6)
        self.setWidget(inner)

    def reveal(self, widget: QWidget) -> None:
        """Reveal ``widget`` vertically without changing horizontal position."""
        widget_top = widget.mapTo(self.viewport(), widget.rect().topLeft()).y()
        widget_bottom = widget_top + widget.height()
        vertical_bar = self.verticalScrollBar()
        if widget_top < 0:
            vertical_bar.setValue(vertical_bar.value() + widget_top)
        elif widget_bottom > self.viewport().height():
            vertical_bar.setValue(
                vertical_bar.value() + widget_bottom - self.viewport().height()
            )


class FormCard(Panel):
    """A width-capped card for a create/edit form; add rows to ``body``."""

    def __init__(self, *, max_width: int = 760, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMaximumWidth(max_width)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(28, 24, 28, 24)
        self.body.setSpacing(18)


class SectionHeading(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("sectionHeading")


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("divider")
        self.setFixedHeight(1)


class FormField(QWidget):
    """A caption above an input, with an optional required mark and hint."""

    def __init__(
        self,
        label: str,
        field: QWidget,
        *,
        required: bool = False,
        hint: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formField")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        caption = QLabel(
            f"{label} <span style='color:#c24145'>*</span>" if required else label
        )
        caption.setObjectName("fieldLabel")
        caption.setBuddy(field)
        layout.addWidget(caption)
        layout.addWidget(field)
        if hint:
            supporting = QLabel(hint)
            supporting.setObjectName("fieldHint")
            supporting.setWordWrap(True)
            layout.addWidget(supporting)


class PageTitle(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("pageTitle")


class PageSubtitle(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("pageSubtitle")
        self.setWordWrap(True)


class PageHeader(QWidget):
    def __init__(
        self, title: str, subtitle: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageHeader")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(2)
        layout.addWidget(PageTitle(title))
        if subtitle:
            layout.addWidget(PageSubtitle(subtitle))


class ErrorLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("errorLabel")
        self.setWordWrap(True)


class StatusBadge(QLabel):
    """Displays caller-provided status text with a non-color marker."""

    def __init__(
        self, text: str, tone: str = "info", parent: QWidget | None = None
    ) -> None:
        super().__init__(f"●  {text}", parent)
        self.setObjectName("statusBadge")
        self.setProperty("tone", tone)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_status(self, text: str, tone: str = "info") -> None:
        self.setText(f"●  {text}")
        self.setProperty("tone", tone)
        style = self.style()
        style.unpolish(self)
        style.polish(self)


class NotificationBanner(QFrame):
    """A dismissible in-page banner for a background event the user should
    notice but not be blocked by (e.g. a new online order arriving over
    ``SyncService``). Hidden until ``show_message`` is called; never a
    modal dialog, so it never interrupts whatever the user is doing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("notificationBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        self._label = QLabel("")
        self._label.setWordWrap(True)
        layout.addWidget(self._label, 1)
        layout.addWidget(GhostButton("Փակել", on_click=self.hide))
        self.hide()

    def show_message(self, text: str, tone: str = "info") -> None:
        self._label.setText(text)
        self.setProperty("tone", tone)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.show()


class SummaryBanner(QFrame):
    """A compact highlighted summary strip for one important total."""

    def __init__(
        self,
        title: str,
        value: str,
        *,
        icon: str = "֏",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("summaryBanner")
        self._title = title
        self._value = QLabel(value)
        self._value.setObjectName("summaryBannerValue")
        self._value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._value.setAccessibleName(title)

        mark = QLabel(icon)
        mark.setObjectName("summaryBannerIcon")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption = QLabel(title)
        caption.setObjectName("summaryBannerTitle")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 18, 12)
        layout.setSpacing(12)
        layout.addWidget(mark)
        layout.addWidget(caption)
        layout.addStretch()
        layout.addWidget(self._value)
        self.setAccessibleName(f"{title}: {value}")

    def set_value(self, value: str) -> None:
        self._value.setText(value)
        self.setAccessibleName(f"{self._title}: {value}")


class StatCard(Panel):
    def __init__(
        self,
        label: str,
        value: str,
        detail: str = "",
        *,
        tone: str = "default",
        on_click: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setProperty("tone", tone)
        self._on_click = on_click
        if on_click is not None:
            self.setProperty("clickable", True)
            self.setAccessibleName(label)
            self.setAccessibleDescription("Բացել ապրանքների մանրամասները")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 16, 14)
        layout.setSpacing(2)
        caption = QLabel(label)
        caption.setObjectName("statLabel")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")
        self.value_label.setProperty("tone", tone)
        layout.addWidget(caption)
        layout.addWidget(self.value_label)
        self.detail_label = QLabel(detail)
        self.detail_label.setObjectName("statDetail")
        self.detail_label.setVisible(bool(detail))
        if on_click is not None:
            for label_widget in (caption, self.value_label, self.detail_label):
                label_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.detail_label)

    def set_value(self, value: str, detail: str | None = None) -> None:
        self.value_label.setText(value)
        if detail is not None:
            self.detail_label.setText(detail)
            self.detail_label.setVisible(bool(detail))

    def mousePressEvent(self, event) -> None:
        if self._on_click is not None and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._on_click is not None and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self._on_click()
            event.accept()
            return
        super().keyPressEvent(event)


class NavCard(QFrame):
    """A large clickable card that leads to a subpage."""

    def __init__(
        self,
        title: str,
        description: str,
        *,
        icon: str = "→",
        tone: str = "primary",
        on_click: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("navCard")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(120)
        self._on_click = on_click

        badge = QLabel(icon)
        badge.setObjectName("navCardIcon")
        badge.setProperty("tone", tone)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading = QLabel(title)
        heading.setObjectName("navCardTitle")
        text = QLabel(description)
        text.setObjectName("navCardText")
        text.setWordWrap(True)
        arrow = QLabel("›")
        arrow.setObjectName("navCardArrow")

        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(heading)
        texts.addWidget(text)
        texts.addStretch()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(16)
        layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(texts, stretch=1)
        layout.addWidget(arrow, alignment=Qt.AlignmentFlag.AlignVCenter)

    def click(self) -> None:
        if self._on_click is not None:
            self._on_click()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.click()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.click()
            return
        super().keyPressEvent(event)


class ProfileHeader(QFrame):
    """A banner introducing one record: initials avatar, name, details, status."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("profileHeader")
        self._avatar = QLabel()
        self._avatar.setObjectName("profileAvatar")
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name = QLabel()
        self._name.setObjectName("profileName")
        self._detail = QLabel()
        self._detail.setObjectName("profileDetail")
        self._detail.setWordWrap(True)
        self._badge = StatusBadge("")
        texts = QVBoxLayout()
        texts.setSpacing(4)
        name_row = QHBoxLayout()
        name_row.setSpacing(12)
        name_row.addWidget(self._name)
        name_row.addWidget(self._badge)
        name_row.addStretch()
        texts.addLayout(name_row)
        texts.addWidget(self._detail)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)
        layout.addWidget(self._avatar)
        layout.addLayout(texts, stretch=1)

    def set_profile(
        self, name: str, detail: str = "", status: str = "", tone: str = "info"
    ) -> None:
        self._avatar.setText(name.strip()[:1].upper() or "?")
        self._name.setText(name)
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))
        self._badge.set_status(status, tone)
        self._badge.setVisible(bool(status))


class BarChart(Panel):
    """A compact, responsive column chart for small dashboard series."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("barChart")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 12)
        self._layout.setSpacing(8)
        heading = SectionHeading(title)
        self._layout.addWidget(heading)
        self._plot = _BarChartPlot()
        self._layout.addWidget(self._plot, stretch=1)

    def set_items(self, items: list[tuple[str, Decimal, str]]) -> None:
        self._plot.set_items(items)


class _BarChartPlot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("barChartPlot")
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._items: list[tuple[str, Decimal, str]] = []

    def set_items(self, items: list[tuple[str, Decimal, str]]) -> None:
        self._items = items
        has_values = any(value > 0 for _label, value, _display in items)
        self.setAccessibleName(
            "\n".join(f"{label}: {display}" for label, _value, display in items)
            if has_values
            else "Տվյալներ չկան"
        )
        self.setToolTip(
            "\n".join(f"{label}: {display}" for label, _value, display in items)
        )
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = QRectF(self.rect()).adjusted(8, 8, -8, -30)
        maximum = max(
            (value for _label, value, _display in self._items), default=Decimal("0")
        )

        if not self._items or maximum <= 0:
            painter.setPen(QColor("#7a8794"))
            painter.drawText(
                plot,
                Qt.AlignmentFlag.AlignCenter,
                "Տվյալներ չկան ընտրված ժամանակահատվածի համար",
            )
            return

        for grid_step in range(1, 4):
            y = plot.top() + plot.height() * grid_step / 4
            painter.setPen(QPen(QColor("#e8edf2"), 1))
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))

        slot_width = plot.width() / len(self._items)
        bar_width = min(28.0, slot_width * 0.62)
        label_stride = max(1, (len(self._items) + 5) // 6)

        for index, (label, value, _display) in enumerate(self._items):
            height = plot.height() * float(value / maximum)
            x = plot.left() + index * slot_width + (slot_width - bar_width) / 2
            y = plot.bottom() - height
            bar = QRectF(x, y, bar_width, height)
            gradient = QLinearGradient(bar.topLeft(), bar.bottomLeft())
            gradient.setColorAt(0, QColor("#5b91f5"))
            gradient.setColorAt(1, QColor("#2563eb"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            radius = min(4.0, bar_width / 3)
            painter.drawRoundedRect(bar, radius, radius)

            if index % label_stride == 0 or index == len(self._items) - 1:
                painter.setPen(QColor("#687789"))
                label_rect = QRectF(
                    plot.left() + index * slot_width,
                    plot.bottom() + 8,
                    slot_width,
                    18,
                )
                painter.drawText(
                    label_rect,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    label,
                )

        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawLine(
            int(plot.left()), int(plot.bottom()), int(plot.right()), int(plot.bottom())
        )
        painter.end()
