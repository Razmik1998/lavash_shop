"""Table components for the POS UI.

Screens must not build ``QTableView``/``QTableWidget`` by hand: use
``DataTable`` for model-backed lists and ``SimpleTable`` for small fixed
grids. Both apply the shared table styling, copy shortcut and context menu.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QTableView, QTableWidget, QTableWidgetItem, QWidget

from ui.style import configure_table_view

CellValue = str | QStandardItem


class DataTable(QTableView):
    """A styled table backed by a ``QStandardItemModel``."""

    def __init__(
        self,
        headers: Sequence[str],
        *,
        on_double_click: Callable[[], object] | None = None,
        min_height: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.item_model = QStandardItemModel(0, len(headers))
        self.item_model.setHorizontalHeaderLabels(list(headers))
        self.setModel(self.item_model)
        configure_table_view(self)
        if min_height is not None:
            self.setMinimumHeight(min_height)
        if on_double_click is not None:
            self.doubleClicked.connect(lambda _index: on_double_click())

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
