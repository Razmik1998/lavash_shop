from __future__ import annotations

import uuid
from decimal import Decimal

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from services import SaleDetail, SalesHistoryService
from ui.sale_unlock_keys_window import _audit_label, _format_change
from ui.style import configure_table_view, format_currency, format_quantity
from ui.workers import run_in_background, wait_for_pending_threads


class SaleDetailDialog(QDialog):
    def __init__(self, sale_id: uuid.UUID, service: SalesHistoryService) -> None:
        super().__init__()
        self._service = service
        self._sale_id = sale_id
        self.setWindowTitle("Sale detail")
        self._summary = QLabel("Loading...")
        self._items = QTableWidget(0, 9)
        configure_table_view(self._items)
        self._items.setHorizontalHeaderLabels(
            [
                "Product",
                "SKU",
                "Unit",
                "Quantity",
                "Cost",
                "Price",
                "Discount",
                "Income",
                "Line total",
            ]
        )
        self._audit = QLabel()
        layout = QVBoxLayout(self)
        layout.addWidget(self._summary)
        layout.addWidget(self._items)
        layout.addWidget(self._audit)
        run_in_background(
            self, lambda: service.get_sale_detail(sale_id), self._loaded, self._failed
        )

    def _loaded(self, detail: SaleDetail) -> None:
        self._summary.setText(
            f"{detail.created_at} | {detail.status} | "
            f"Վճարման ձև՝ "
            f"{'Պարտքով' if detail.credit_amount is not None else 'Կանխիկ'} | "
            f"{format_currency(detail.total)}"
        )
        if detail.credit_amount is not None:
            self._summary.setText(
                f"{self._summary.text()} | Պարտք՝ "
                f"{format_currency(detail.credit_amount)} | "
                f"Հաճախորդ՝ {detail.credit_customer_name}"
            )
        self._items.setRowCount(len(detail.items))
        for row, item in enumerate(detail.items):
            values = [
                item.product_name,
                item.product_sku,
                item.unit,
                format_quantity(item.quantity),
                format_currency(item.cost_price or Decimal("0")),
                format_currency(item.unit_price),
                format_currency(item.discount_amount) if item.discount_amount else "",
                format_currency(
                    (item.unit_price - (item.cost_price or Decimal("0")))
                    * item.quantity
                ),
                format_currency(item.line_total),
            ]
            for column, value in enumerate(values):
                self._items.setItem(row, column, QTableWidgetItem(value))
        audit_lines = [
            f"{event.created_at} | {_audit_label(event.event_type)} | "
            f"{_format_change(event.old_value)} -> {_format_change(event.new_value)}"
            for event in detail.audit_events
        ]
        self._audit.setText("\n".join(audit_lines) if audit_lines else "Audit: none")

    def _failed(self, error: Exception) -> None:
        self._summary.setText("Unable to load sale detail")
        self._audit.setText(str(error))

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)
