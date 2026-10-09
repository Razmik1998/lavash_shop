from __future__ import annotations

import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from services import SalesFilters, SalesHistoryService, SalesPage, SalesSummary
from ui.components import DataTable, PageTitle
from ui.sale_detail_dialog import SaleDetailDialog
from ui.style import (
    configure_page_layout,
    format_currency,
    format_quantity,
)
from ui.workers import run_in_background, wait_for_pending_threads


class PosSessionDetailWindow(QWidget):
    def __init__(self, session_id: uuid.UUID, service: SalesHistoryService) -> None:
        super().__init__()
        self._session_id = session_id
        self._service = service
        self._cursor: str | None = None
        self._loading = False
        self._filters = SalesFilters(session_id=session_id)
        self._summary = QLabel("Loading...")
        self._table = DataTable(
            [
                "Ստեղծված",
                "Տերմինալ",
                "Աշխատակից",
                "Կարգավիճակ",
                "Վճարման ձև",
                "Պարտք / հաճախորդ",
                "Ընդհանուր",
            ],
            on_double_click=self._open_detail,
        )
        self._model = self._table.item_model
        layout = QVBoxLayout()
        configure_page_layout(layout)
        layout.addWidget(PageTitle(f"POS session {session_id}"))
        layout.addWidget(self._summary)
        layout.addWidget(self._table, 1)
        self.setLayout(layout)
        self._load()

    def _load(self) -> None:
        run_in_background(
            self,
            lambda: self._service.summarize_sales(self._filters),
            self._summary_loaded,
            self._failed,
        )
        self._load_page()

    def _load_page(self) -> None:
        if self._loading:
            return
        self._loading = True
        run_in_background(
            self,
            lambda: self._service.list_sales(self._filters, self._cursor),
            self._page_loaded,
            self._failed,
        )

    def _summary_loaded(self, summary: SalesSummary) -> None:
        self._summary.setText(
            f"Վաճառքներ՝ {summary.sale_count} | Ապրանքներ՝ "
            f"{format_quantity(summary.item_quantity_total)} | "
            f"Ընդհանուր՝ {format_currency(summary.revenue_total)} | "
            f"Եկամուտ՝ {format_currency(summary.income_total)} | "
            f"Պարտքով՝ {format_currency(summary.credit_total)}"
        )

    def _page_loaded(self, page: SalesPage) -> None:
        self._loading = False
        for row in page.items:
            payment_type = "Պարտքով" if row.credit_amount is not None else "Կանխիկ"
            credit_info = (
                f"{format_currency(row.credit_amount)} / {row.credit_customer_name}"
                if row.credit_amount is not None
                else "-"
            )
            values = [
                row.created_at.isoformat(),
                row.terminal_id,
                str(row.employee_user_id),
                row.status,
                payment_type,
                credit_info,
                format_currency(row.total),
            ]
            items = [QStandardItem(value) for value in values]
            items[0].setData(row.id, Qt.ItemDataRole.UserRole)
            self._model.appendRow(items)
        self._cursor = page.next_cursor

    def _open_detail(self) -> None:
        row = self._table.selected_row()
        item = None if row < 0 else self._model.item(row, 0)
        sale_id = None if item is None else item.data(Qt.ItemDataRole.UserRole)
        if isinstance(sale_id, uuid.UUID):
            SaleDetailDialog(sale_id, self._service).exec()

    def _failed(self, error: Exception) -> None:
        self._loading = False
        self._summary.setText("Unable to load session sales")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)
