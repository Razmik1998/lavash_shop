"""Reusable layout containers so screens never hand-roll toolbars."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import partial

from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.components.buttons import TabButton


class ActionBar(QWidget):
    """A left-aligned row of action buttons with trailing stretch."""

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


class FilterBar(QGroupBox):
    """A titled grid of filter inputs; the last column stretches."""

    def __init__(
        self,
        fields: Sequence[tuple[str | None, QWidget]] = (),
        *,
        title: str = "Ֆիլտրեր",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)
        self.setObjectName("filterBar")
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(12, 12, 12, 12)
        self._grid.setHorizontalSpacing(10)
        self._column = 0
        for label, widget in fields:
            self.add_field(label, widget)

    def add_field(self, label: str | None, widget: QWidget, stretch: int = 0) -> None:
        if label:
            self._grid.addWidget(QLabel(label), 0, self._column)
            self._column += 1
        self._grid.addWidget(widget, 0, self._column)
        if stretch:
            self._grid.setColumnStretch(self._column, stretch)
        self._column += 1


class DialogButtonBar(QWidget):
    """Right-aligned dialog footer; the confirming button goes last."""

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


class TabBar(QWidget):
    """A row of ``TabButton``s that switch an in-page section (e.g. a
    ``QStackedWidget`` of tab contents owned by the caller). Distinct from
    the app-level sidebar navigation (``NavButton``, wired in
    ``main_window.py``) — this is a reusable in-screen tab strip, e.g. for
    the Online Selling page's Pending/History split."""

    def __init__(
        self,
        labels: Sequence[str],
        *,
        on_change: Callable[[int], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._on_change = on_change
        self._buttons: list[TabButton] = []
        for index, label in enumerate(labels):
            button = TabButton(label, on_click=partial(self._select, index))
            button.set_active(index == 0)
            row.addWidget(button)
            self._buttons.append(button)
        row.addStretch()

    def _select(self, index: int) -> None:
        self.set_active(index)
        if self._on_change is not None:
            self._on_change(index)

    def set_active(self, index: int) -> None:
        for button_index, button in enumerate(self._buttons):
            button.set_active(button_index == index)


class Toolbar(QWidget):
    """Stacks a filter bar above an action bar."""

    def __init__(
        self,
        *sections: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        for section in sections:
            column.addWidget(section)
