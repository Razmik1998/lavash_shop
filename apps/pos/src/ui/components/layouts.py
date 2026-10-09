"""Reusable layout containers so screens never hand-roll toolbars."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class ActionBar(QWidget):
    """A row of action buttons with stretch on the free side."""

    def __init__(
        self,
        widgets: Sequence[QWidget] = (),
        *,
        align_right: bool = False,
        title: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(8)
        if title:
            self._row.addWidget(QLabel(title))
        if align_right:
            self._row.addStretch()
        for widget in widgets:
            self._row.addWidget(widget)
        if not align_right:
            self._row.addStretch()

    def add(self, widget: QWidget) -> None:
        self._row.insertWidget(self._row.count() - 1, widget)


class DialogButtonBar(QWidget):
    """Right-aligned footer; the confirming button goes last."""

    def __init__(
        self, widgets: Sequence[QWidget] = (), parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 8, 0, 0)
        row.setSpacing(8)
        row.addStretch()
        for widget in widgets:
            row.addWidget(widget)
