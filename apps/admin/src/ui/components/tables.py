"""Table components for the Admin UI.

Screens must not build ``QTableView``/``QTableWidget`` by hand: use
``DataTable`` for model-backed lists and ``SimpleTable`` for small fixed
grids. Both apply the shared table styling, copy shortcut and context menu.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QWidget,
)

from ui.style import ATTENTION_ROW_BACKGROUND, configure_table_view

CellValue = str | QStandardItem


class DataTable(QTableView):
    """A styled table backed by a ``QStandardItemModel``."""

    def __init__(
        self,
        headers: Sequence[str],
        *,
        on_click: Callable[[], object] | None = None,
        on_double_click: Callable[[], object] | None = None,
        on_selection_changed: Callable[[], object] | None = None,
        min_height: int | None = None,
        min_width: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.item_model = QStandardItemModel(0, len(headers))
        self.item_model.setHorizontalHeaderLabels(list(headers))
        self.setModel(self.item_model)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)
        configure_table_view(self)
        if min_height is not None:
            self.setMinimumHeight(min_height)
        if min_width is not None:
            self.setMinimumWidth(min_width)
        if on_click is not None:
            self.clicked.connect(lambda _index: on_click())
        if on_double_click is not None:
            self.doubleClicked.connect(lambda _index: on_double_click())
        if on_selection_changed is not None:
            selection = self.selectionModel()
            if selection is not None:
                selection.selectionChanged.connect(
                    lambda *_args: on_selection_changed()
                )

    def clear_rows(self) -> None:
        self.item_model.removeRows(0, self.item_model.rowCount())

    def append_row(self, values: Sequence[CellValue]) -> list[QStandardItem]:
        items = [
            value if isinstance(value, QStandardItem) else QStandardItem(value)
            for value in values
        ]
        self.item_model.appendRow(items)
        return items

    def set_rows(self, rows: Iterable[Sequence[CellValue]]) -> None:
        self.clear_rows()
        for row in rows:
            self.append_row(row)

    def selected_row(self) -> int:
        index = self.currentIndex()
        return index.row() if index.isValid() else -1

    def row_count(self) -> int:
        return self.item_model.rowCount()

    def highlight_row(self, row: int) -> None:
        """Paint a row red to flag a record that still needs attention."""
        brush = QBrush(QColor(ATTENTION_ROW_BACKGROUND))
        for column in range(self.item_model.columnCount()):
            item = self.item_model.item(row, column)
            if item is not None:
                item.setBackground(brush)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.viewport():
            if event.type() == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
                index = self.indexAt(event.position().toPoint())
                tooltip = (
                    index.data(Qt.ItemDataRole.ToolTipRole) if index.isValid() else None
                )
                if tooltip:
                    QToolTip.showText(
                        self.viewport().mapToGlobal(event.position().toPoint()),
                        str(tooltip),
                        self.viewport(),
                    )
                else:
                    QToolTip.hideText()
            elif event.type() == QEvent.Type.Leave:
                QToolTip.hideText()
        return super().eventFilter(watched, event)


class SimpleTable(QTableWidget):
    """A styled fixed-column table for small, non-model content."""

    def __init__(
        self,
        headers: Sequence[str],
        *,
        min_height: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(list(headers))
        configure_table_view(self)
        if min_height is not None:
            self.setMinimumHeight(min_height)

    def set_rows(self, rows: Iterable[Sequence[str]]) -> None:
        materialized = [list(row) for row in rows]
        self.setRowCount(len(materialized))
        for row_index, row in enumerate(materialized):
            for column, value in enumerate(row):
                self.setItem(row_index, column, QTableWidgetItem(value))

    def append_row(self, values: Sequence[str]) -> int:
        row = self.rowCount()
        self.insertRow(row)
        for column, value in enumerate(values):
            self.setItem(row, column, QTableWidgetItem(value))
        return row

    def row_payload(self, row: int, column: int = 0) -> object:
        item = self.item(row, column)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)
