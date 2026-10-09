"""Purchase document detail dialog and its reopen-for-edit workflow.

Shared by the purchases list and the supplier account so both open and edit
documents the same way. The editor itself is injected (``EditorOpener``)
because ``PurchaseDialog`` lives in ``ui.suppliers_window``, which imports
this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from services import PurchaseDetail, PurchaseRow, SupplierRow
from ui.components import (
    CloseButton,
    DataTable,
    DialogButtonBar,
    EditButton,
    PageSubtitle,
    PageTitle,
    SectionHeading,
    StatCard,
    StatusBadge,
    confirm,
    warn,
)
from ui.payment_dialog import payment_method_label
from ui.style import configure_page_layout, format_currency, format_quantity
from ui.workers import run_in_background

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")

_STATUS: dict[str, tuple[str, str]] = {
    "draft": ("Բաց", "danger"),
    "open": ("Չվճարված", "warning"),
    "partially_paid": ("Մասնակի վճարված", "info"),
    "paid": ("Վճարված", "success"),
    "cancelled": ("Չեղարկված", "danger"),
}

# (supplier, detail, finalize_on_save, initial_payment) -> editor accepted
EditorOpener = Callable[[SupplierRow, PurchaseDetail, bool, Decimal], bool]


def purchase_status_label(status: str) -> str:
    return _STATUS.get(status, (status, "info"))[0]


class PurchaseDocumentService(Protocol):
    def get_detail(self, purchase_id: uuid.UUID) -> PurchaseDetail: ...

    def reopen_for_edit(self, purchase_id: uuid.UUID) -> object: ...


class PurchaseDetailDialog(QDialog):
    def __init__(
        self,
        row: PurchaseRow,
        detail: PurchaseDetail,
        *,
        editable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Գնման փաստաթուղթ {row.purchase_number}")
        self.edit_button = EditButton(enabled=editable and row.status != "cancelled")
        # Never setVisible(True) here: a parentless widget would open as its own window.
        if not editable:
            self.edit_button.hide()

        label, tone = _STATUS.get(row.status, (row.status, "info"))
        heading = QHBoxLayout()
        heading.addWidget(PageTitle(f"Փաստաթուղթ {row.purchase_number}"))
        heading.addWidget(StatusBadge(label, tone))
        heading.addStretch()
        purchase_date = row.purchase_date.astimezone(ARMENIA_TIMEZONE)
        subtitle = PageSubtitle(
            f"Մատակարար՝ {row.supplier_name} · Ամսաթիվ՝ {purchase_date:%d.%m.%Y %H:%M}"
        )

        stats = QHBoxLayout()
        stats.addWidget(
            StatCard("Ընդհանուր", format_currency(row.total), tone="primary")
        )
        stats.addWidget(StatCard("Վճարված", format_currency(row.paid), tone="success"))
        stats.addWidget(StatCard("Պարտք", format_currency(row.debt), tone="danger"))

        items_table = DataTable(
            ["Ապրանք", "Կոդ", "Քանակ", "Գնման գին", "Գումար", "Վաճառքի գին", "Մարժա"],
            min_height=200,
        )
        items_table.set_rows(
            [
                item.product_name,
                item.product_sku,
                format_quantity(item.quantity),
                format_currency(item.unit_cost),
                format_currency(item.line_total),
                (
                    format_currency(item.selling_price)
                    if item.selling_price is not None
                    else "—"
                ),
                (
                    f"{format_quantity(item.markup_percentage)}%"
                    if item.selling_price is not None
                    else "—"
                ),
            ]
            for item in detail.items
        )
        payments_table = DataTable(["Ամսաթիվ", "Գումար", "Վճարման ձև"], min_height=120)
        payments_table.set_rows(
            [
                payment.payment_date.astimezone(ARMENIA_TIMEZONE).strftime(
                    "%d.%m.%Y %H:%M"
                ),
                format_currency(payment.amount),
                payment_method_label(payment.method),
            ]
            for payment in detail.payments
        )

        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.addLayout(heading)
        layout.addWidget(subtitle)
        layout.addLayout(stats)
        layout.addWidget(SectionHeading("Ապրանքներ"))
        layout.addWidget(items_table, stretch=2)
        layout.addWidget(SectionHeading("Վճարումներ"))
        layout.addWidget(payments_table, stretch=1)
        layout.addWidget(
            DialogButtonBar([self.edit_button, CloseButton(on_click=self.reject)])
        )
        self.resize(960, 680)


class PurchaseDocumentFlow:
    """Opens a document's detail and walks it through reopen-for-edit."""

    def __init__(
        self,
        owner: QWidget,
        service: PurchaseDocumentService,
        open_editor: EditorOpener | None,
        on_changed: Callable[[], object],
    ) -> None:
        self._owner = owner
        self._service = service
        self._open_editor = open_editor
        self._on_changed = on_changed

    @property
    def can_edit(self) -> bool:
        return self._open_editor is not None

    def open(self, row: PurchaseRow) -> None:
        run_in_background(
            self._owner,
            lambda: self._service.get_detail(row.id),
            lambda detail: self._show(row, detail),
            self._failed,
        )

    def edit(self, row: PurchaseRow) -> None:
        if row.status == "cancelled":
            warn(self._owner, "Չեղարկված փաստաթուղթը հնարավոր չէ խմբագրել։")
            return
        run_in_background(
            self._owner,
            lambda: self._service.get_detail(row.id),
            lambda detail: self._begin_edit(self._owner, row, detail),
            self._failed,
        )

    def _show(self, row: PurchaseRow, detail: PurchaseDetail) -> None:
        dialog = PurchaseDetailDialog(
            row, detail, editable=self.can_edit, parent=self._owner
        )
        dialog.edit_button.clicked.connect(
            lambda: self._begin_edit(dialog, row, detail)
        )
        dialog.exec()

    def _begin_edit(
        self, parent: QWidget, row: PurchaseRow, detail: PurchaseDetail
    ) -> None:
        if not confirm(
            parent,
            "Հաստատել խմբագրումը",
            "Փաստաթուղթը կվերադառնա «Բաց» վիճակի․ պահեստի քանակները և "
            "մատակարարի հաշվարկը կչեղարկվեն մինչև կրկին պահպանելը։ Շարունակե՞լ։",
        ):
            return
        if isinstance(parent, QDialog):
            parent.accept()
        supplier = SupplierRow(
            detail.purchase.supplier_id, row.supplier_name, None, None, True
        )
        if row.status == "draft":
            self._edit_detail(supplier, detail, False, Decimal("0"))
            return
        paid = row.paid
        purchase_id = detail.purchase.id
        run_in_background(
            self._owner,
            lambda: self._reopen(purchase_id),
            lambda reopened: self._edit_detail(supplier, reopened, True, paid),
            self._failed,
        )

    def _reopen(self, purchase_id: uuid.UUID) -> PurchaseDetail:
        self._service.reopen_for_edit(purchase_id)
        return self._service.get_detail(purchase_id)

    def _edit_detail(
        self,
        supplier: SupplierRow,
        detail: PurchaseDetail,
        finalize_on_save: bool,
        initial_payment: Decimal,
    ) -> None:
        if self._open_editor is not None:
            self._open_editor(supplier, detail, finalize_on_save, initial_payment)
        # A reopened document changed state even if the editor was cancelled.
        self._on_changed()

    def _failed(self, _error: Exception) -> None:
        self._on_changed()
        warn(self._owner, "Չհաջողվեց բացել կամ խմբագրել փաստաթուղթը։")
