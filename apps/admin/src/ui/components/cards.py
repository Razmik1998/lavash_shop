"""Scrolling card list and the replenishment recommendation card."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.components.buttons import GhostButton
from ui.components.panels import Panel, StatusBadge


class CardScrollArea(QScrollArea):
    """Vertically scrolling list of cards; never scrolls horizontally."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cardScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("cardScrollBody")
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(0, 0, 8, 0)
        self.body.setSpacing(12)
        self.setWidget(inner)

    def clear(self) -> None:
        while self.body.count():
            item = self.body.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

    def add_card(self, card: QWidget) -> None:
        self.body.addWidget(card)


class CardList(QWidget):
    """Plain vertical stack of cards, meant to live inside a scrolling page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(12)

    def clear(self) -> None:
        while self.body.count():
            item = self.body.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

    def add_card(self, card: QWidget) -> None:
        self.body.addWidget(card)


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    return label


class _Metric(QWidget):
    def __init__(self, caption: str, value: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(_label(caption, "metricCaption"))
        layout.addWidget(_label(value, "metricValue"))


class RecommendationCard(Panel):
    """One product to reorder: urgency, key metrics, best supplier, details."""

    def __init__(
        self,
        *,
        name: str,
        urgent: bool,
        suggested: str,
        metrics: list[tuple[str, str]],
        supplier: str,
        supplier_note: str,
        details: QWidget,
    ) -> None:
        super().__init__()
        self.setProperty("urgent", urgent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.badge = StatusBadge(
            "Շտապ" if urgent else "Պատվիրել", "danger" if urgent else "warning"
        )
        top.addWidget(self.badge)
        top.addWidget(_label(name, "cardTitle"), 1)
        order = QVBoxLayout()
        order.setSpacing(0)
        caption = _label("Առաջարկվող քանակ", "metricCaption")
        caption.setAlignment(Qt.AlignmentFlag.AlignRight)
        value = _label(suggested, "cardHighlight")
        value.setAlignment(Qt.AlignmentFlag.AlignRight)
        order.addWidget(caption)
        order.addWidget(value)
        top.addLayout(order)
        root.addLayout(top)

        row = QHBoxLayout()
        row.setSpacing(32)
        for caption_text, value_text in metrics:
            row.addWidget(_Metric(caption_text, value_text))
        row.addStretch(1)
        root.addLayout(row)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        info = QVBoxLayout()
        info.setSpacing(2)
        info.addWidget(_label("Լավագույն մատակարար", "metricCaption"))
        info.addWidget(_label(supplier, "metricValue"))
        if supplier_note:
            info.addWidget(_label(supplier_note, "cardNote"))
        footer.addLayout(info, 1)
        self.toggle = GhostButton(
            "Համեմատել մատակարարներին",
            tooltip="Բացել մատակարարների գների համեմատությունը",
        )
        self.toggle.clicked.connect(self._toggle)
        footer.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(footer)

        self.details = details
        self.details.hide()
        root.addWidget(self.details)

    def _toggle(self) -> None:
        expanded = self.details.isHidden()
        self.details.setVisible(expanded)
        self.toggle.setText(
            "Թաքցնել մատակարարներին" if expanded else "Համեմատել մատակարարներին"
        )
