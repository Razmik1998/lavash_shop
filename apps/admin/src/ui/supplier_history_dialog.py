"""Supplier purchase history dialog with incremental loading."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from models import PaymentMethod
from services import PurchaseFilters, PurchasePage, PurchaseRow, SupplierRow
from ui.components import (
    ActionBar,
    CloseButton,
    DataTable,
    PageSubtitle,
    PageTitle,
    PaymentButton,
    warn,
)
from ui.payment_dialog import PaymentDialog
from ui.style import (
    configure_page_layout,
    format_currency,
    format_quantity,
)
from ui.workers import run_in_background, wait_for_pending_threads

_ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


class PurchaseService(Protocol):
    def list_purchase_page(
        self,
        filters: PurchaseFilters,
        offset: int = 0,
        limit: int = 50,
    ) -> PurchasePage: ...

    def add_payment(
        self,
        purchase_id: uuid.UUID,
        amount: Decimal,
        method: PaymentMethod,
        payment_date: datetime,
        notes: str | None = None,
    ) -> object: ...


class SupplierPurchaseHistoryDialog(QDialog):
    _PAGE_SIZE = 50

    def __init__(
        self,
        supplier: SupplierRow,
        purchase_service: PurchaseService,
        on_history_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._supplier = supplier
        self._purchase_service = purchase_service
        self._on_history_changed = on_history_changed
        self._rows: list[PurchaseRow] = []
        self._offset = 0
        self._generation = 0
        self._loading = False
        self._has_more = True
        self.setWindowTitle("Մատակարարի գնումներ")

        heading = PageTitle(f"Գնման փաստաթղթեր՝ {supplier.name}")
        self._message = PageSubtitle()
        self._table = DataTable(
            [
                "Համար",
                "Ամսաթիվ",
                "Ընդամենը",
                "Վճարված",
                "Պարտք",
                "Կարգավիճակ",
                "Քանակ",
            ]
        )
        self._model = self._table.item_model
        self._table.verticalScrollBar().valueChanged.connect(self._scroll_changed)
        buttons = ActionBar(
            [PaymentButton(on_click=self._add_payment)],
        )
        buttons.add(CloseButton(on_click=self.reject))
        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.addWidget(heading)
        layout.addWidget(self._message)
        layout.addWidget(self._table, stretch=1)
        layout.addWidget(buttons)
        self.resize(880, 560)
        self._reload()

    def _reload(self) -> None:
        if self._loading:
            return
        self._generation += 1
        self._offset = 0
        self._has_more = True
        self._rows.clear()
        self._model.removeRows(0, self._model.rowCount())
        self._message.setText("Բեռնվում է...")
        self._load_next_page()

    def _load_next_page(self) -> None:
        if self._loading or not self._has_more:
            return
        self._loading = True
        generation = self._generation
        offset = self._offset
        run_in_background(
            self,
            lambda: self._purchase_service.list_purchase_page(
                PurchaseFilters(supplier_id=self._supplier.id),
                offset,
                self._PAGE_SIZE,
            ),
            lambda page: self._page_loaded(generation, offset, page),
            lambda error: self._page_failed(generation, error),
        )

    def _page_loaded(self, generation: int, offset: int, page: PurchasePage) -> None:
        if generation != self._generation:
            return
        self._loading = False
        self._offset = offset + len(page.items)
        self._has_more = page.has_more
        self._rows.extend(page.items)
        for row in page.items:
            self._table.append_row(
                [
                    row.purchase_number,
                    row.purchase_date.date().isoformat(),
                    format_currency(row.total),
                    format_currency(row.paid),
                    format_currency(row.debt),
                    self._status(row.status),
                    format_quantity(row.item_quantity),
                ]
            )
        self._message.setText("" if self._rows else "Գնումների փաստաթղթեր չկան։")

    def _page_failed(self, generation: int, _error: Exception) -> None:
        if generation != self._generation:
            return
        self._loading = False
        self._message.setText("Չհաջողվեց բեռնել մատակարարի գնումները։")

    def _scroll_changed(self, value: int) -> None:
        scrollbar = self._table.verticalScrollBar()
        if scrollbar.maximum() and value >= scrollbar.maximum() - 2:
            self._load_next_page()

    def _selected_purchase(self) -> PurchaseRow | None:
        row = self._table.selected_row()
        if row < 0 or row >= len(self._rows):
            warn(self, "Ընտրեք գնման փաստաթուղթ։")
            return None
        return self._rows[row]

    def _add_payment(self) -> None:
        purchase = self._selected_purchase()
        if purchase is None:
            return
        if purchase.status not in {"open", "partially_paid"}:
            warn(self, "Այս փաստաթուղթը վճարման ենթակա չէ։")
            return
        dialog = PaymentDialog(purchase.debt, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payment = dialog.result_value()
        if payment is None:
            return
        payment_amount, method = payment
        run_in_background(
            self,
            lambda: self._purchase_service.add_payment(
                purchase.id,
                payment_amount,
                method,
                datetime.now(_ARMENIA_TIMEZONE),
            ),
            self._payment_saved,
            self._payment_failed,
        )

    def _payment_saved(self, _payment: object) -> None:
        self._on_history_changed()
        self._reload()

    def _payment_failed(self, _error: Exception) -> None:
        warn(self, "Չհաջողվեց գրանցել վճարումը։")

    @staticmethod
    def _status(status: str) -> str:
        return {
            "draft": "Բաց",
            "open": "Ավարտված",
            "partially_paid": "Ավարտված",
            "paid": "Ավարտված",
            "cancelled": "Չեղարկված",
        }.get(status, status)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._generation += 1
        wait_for_pending_threads(self)
        super().closeEvent(event)
