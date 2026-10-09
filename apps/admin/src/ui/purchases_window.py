"""Armenian purchase list and auditable workflow actions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from models import PaymentMethod
from services import (
    PurchaseDetail,
    PurchaseFilters,
    PurchaseLineInput,
    PurchaseRow,
    SupplierReportRow,
    SupplierRow,
)
from ui.components import (
    ActionBar,
    AddButton,
    CancelButton,
    DataTable,
    DateField,
    DeleteButton,
    DialogButtonBar,
    FilterBar,
    PageSubtitle,
    PageTitle,
    PaymentButton,
    PrimaryButton,
    SearchButton,
    SearchField,
    SelectField,
    Toolbar,
    confirm,
    warn,
)
from ui.payment_dialog import PaymentDialog
from ui.purchase_document import PurchaseDocumentFlow
from ui.style import (
    configure_page_layout,
    format_currency,
    format_quantity,
)
from ui.suppliers_window import ProductService, PurchaseDialog
from ui.workers import run_in_background, wait_for_pending_threads


class PurchaseService(Protocol):
    def list_purchases(
        self, filters: PurchaseFilters | None = None
    ) -> list[PurchaseRow]: ...

    def create_draft(
        self,
        supplier_id: uuid.UUID,
        purchase_date: datetime,
        notes: str | None,
        lines: list[PurchaseLineInput],
    ) -> object: ...

    def get_detail(self, purchase_id: uuid.UUID) -> PurchaseDetail: ...
    def confirm(
        self,
        purchase_id: uuid.UUID,
        initial_payment: Decimal = Decimal("0"),
        payment_method: PaymentMethod = PaymentMethod.CASH,
        price_updates: dict[uuid.UUID, Decimal] | None = None,
    ) -> object: ...
    def cancel(self, purchase_id: uuid.UUID) -> object: ...
    def summarize_purchases(self, filters: PurchaseFilters | None = None) -> object: ...
    def add_payment(
        self,
        purchase_id: uuid.UUID,
        amount: Decimal,
        method: PaymentMethod,
        payment_date: datetime,
        notes: str | None = None,
    ) -> object: ...
    def delete_draft(self, purchase_id: uuid.UUID) -> None: ...
    def supplier_report(
        self, filters: PurchaseFilters | None = None
    ) -> list[SupplierReportRow]: ...

    def update_draft(
        self,
        purchase_id: uuid.UUID,
        supplier_id: uuid.UUID,
        purchase_date: datetime,
        notes: str | None,
        lines: list[PurchaseLineInput],
    ) -> object: ...

    def reopen_for_edit(self, purchase_id: uuid.UUID) -> object: ...


class SupplierService(Protocol):
    def list_suppliers(self) -> list[SupplierRow]: ...


class PurchasesWindow(QWidget):
    def __init__(
        self,
        service: PurchaseService,
        supplier_service: SupplierService | None = None,
        product_service: ProductService | None = None,
        business_timezone: str = "Asia/Yerevan",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._supplier_service = supplier_service
        self._product_service = product_service
        self._business_timezone = ZoneInfo(business_timezone)
        self._rows: list[PurchaseRow] = []
        self._reload_generation = 0
        self._documents = PurchaseDocumentFlow(
            self,
            service,
            self._open_editor if product_service is not None else None,
            self.reload,
        )
        self._search = SearchField("Համար, մատակարար կամ ապրանք", on_submit=self.reload)
        self._supplier = SelectField(
            [("Բոլոր մատակարարները", None)],
            on_change=self._mark_filters_changed,
        )
        if supplier_service is not None:
            for supplier in supplier_service.list_suppliers():
                self._supplier.addItem(supplier.name, supplier.id)
        self._from_date = DateField(on_change=self._mark_filters_changed)
        self._to_date = DateField(on_change=self._mark_filters_changed)
        self._table = DataTable(
            [
                "Համար",
                "Մատակարար",
                "Ամսաթիվ",
                "Ընդամենը",
                "Վճարված",
                "Պարտք",
                "Կարգավիճակ",
                "Քանակ",
            ],
            on_double_click=self._show_detail,
        )
        self._model = self._table.item_model
        title = PageTitle("Գնումներ")
        filter_group = FilterBar(
            [
                ("Սկիզբ", self._from_date),
                ("Վերջ", self._to_date),
                (None, self._supplier),
            ]
        )
        filter_group.add_field(None, self._search, stretch=1)
        filter_group.add_field(None, SearchButton(on_click=self.reload))

        action_group = ActionBar(
            [
                AddButton("Նոր գնում", on_click=self._new_purchase),
                PaymentButton(on_click=self._add_payment),
                CancelButton("Չեղարկել գնումը", on_click=self._cancel),
                DeleteButton("Ջնջել սևագիրը", on_click=self._delete_draft),
            ],
            title="Գործողություններ",
        )

        toolbar = Toolbar(filter_group, action_group)
        layout = QVBoxLayout()
        configure_page_layout(layout)
        layout.addWidget(title)
        layout.addWidget(toolbar)
        self._summary = PageSubtitle()
        layout.addWidget(self._summary)
        layout.addWidget(self._table, stretch=1)
        self.setLayout(layout)
        self.reload()

    def _mark_filters_changed(self) -> None:
        self._summary.setText("Ֆիլտրերը փոխվել են․ սեղմեք «Որոնել»։")

    def reload(self) -> None:
        if self._from_date.date() > self._to_date.date():
            self._summary.setText(
                "Սխալ․ սկզբի ամսաթիվը չի կարող ուշ լինել վերջի ամսաթվից։"
            )
            return
        self._reload_generation += 1
        generation = self._reload_generation
        filters = PurchaseFilters(
            from_datetime=self._date_start(),
            to_datetime=self._date_end(),
            supplier_id=self._supplier.currentData(),
            search=self._search.text().strip() or None,
        )
        run_in_background(
            self,
            lambda: self._service.list_purchases(filters),
            lambda rows: self._loaded_if_current(generation, rows),
            self._failed,
        )
        if hasattr(self._service, "summarize_purchases"):
            run_in_background(
                self,
                lambda: self._service.summarize_purchases(filters),
                lambda summary: self._summary_loaded_if_current(generation, summary),
                self._failed,
            )

    def _loaded_if_current(self, generation: int, rows: list[PurchaseRow]) -> None:
        if generation == self._reload_generation:
            self._loaded(rows)

    def _summary_loaded_if_current(self, generation: int, summary: object) -> None:
        if generation == self._reload_generation:
            self._summary_loaded(summary)

    def _date_start(self) -> datetime:
        return datetime.combine(
            self._from_date.date_value(), time.min, tzinfo=self._business_timezone
        ).astimezone(UTC)

    def _date_end(self) -> datetime:
        return datetime.combine(
            self._to_date.date_value(), time.max, tzinfo=self._business_timezone
        ).astimezone(UTC)

    def _loaded(self, rows: list[PurchaseRow]) -> None:
        self._rows = rows
        self._table.set_rows(
            [
                row.purchase_number,
                row.supplier_name,
                row.purchase_date.date().isoformat(),
                format_currency(row.total),
                format_currency(row.paid),
                format_currency(row.debt),
                self._status(row.status),
                format_quantity(row.item_quantity),
            ]
            for row in rows
        )
        for index, row in enumerate(rows):
            if row.status == "draft":
                self._table.highlight_row(index)

    def _summary_loaded(self, summary: object) -> None:
        self._summary.setText(
            f"Փաստաթղթեր՝ {getattr(summary, 'purchase_count', 0)} | "
            f"Գումար՝ {format_currency(getattr(summary, 'total_amount', Decimal('0')))} | "
            f"Քանակ՝ {format_quantity(getattr(summary, 'item_quantity', Decimal('0')))} | "
            f"Սևագրեր՝ {getattr(summary, 'draft_count', 0)}"
        )

    def _selected(self) -> PurchaseRow | None:
        row = self._table.selected_row()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _new_purchase(self) -> None:
        if self._supplier_service is None or self._product_service is None:
            warn(self, "Գնումների ծառայությունը հասանելի չէ։")
            return
        suppliers = self._supplier_service.list_suppliers()
        active_suppliers = [supplier for supplier in suppliers if supplier.is_active]
        if not active_suppliers:
            warn(self, "Ստեղծեք ակտիվ մատակարար։")
            return
        selector = QDialog(self)
        selector.setWindowTitle("Ընտրել մատակարար")
        combo = SelectField(
            [(supplier.name, supplier) for supplier in active_suppliers],
            parent=selector,
        )
        layout = QVBoxLayout(selector)
        layout.addWidget(QLabel("Մատակարար"))
        layout.addWidget(combo)
        layout.addWidget(
            DialogButtonBar(
                [
                    CancelButton(on_click=selector.reject),
                    PrimaryButton("Շարունակել", on_click=selector.accept),
                ]
            )
        )
        if selector.exec() != QDialog.DialogCode.Accepted:
            return
        dialog = PurchaseDialog(
            combo.currentData(),
            self._service,
            self._product_service,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _show_detail(self) -> None:
        row = self._selected()
        if row is not None:
            self._documents.open(row)

    def _open_editor(
        self,
        supplier: SupplierRow,
        detail: PurchaseDetail,
        finalize_on_save: bool,
        initial_payment: Decimal,
    ) -> bool:
        if self._product_service is None:
            return False
        dialog = PurchaseDialog(
            supplier=supplier,
            purchase_service=self._service,
            product_service=self._product_service,
            detail=detail,
            finalize_on_save=finalize_on_save,
            initial_payment=initial_payment,
            parent=self,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _cancel(self) -> None:
        row = self._selected()
        if row is None:
            return
        if not confirm(self, "Հաստատել", "Չեղարկե՞լ այս գնումը։"):
            return
        run_in_background(
            self,
            lambda: self._service.cancel(row.id),
            lambda _: self.reload(),
            self._failed,
        )

    def _delete_draft(self) -> None:
        row = self._selected()
        if row is None or row.status != "draft":
            warn(self, "Ընտրեք բաց գնում։")
            return
        if not confirm(self, "Հաստատել", "Ջնջե՞լ փաստաթուղթը։"):
            return
        run_in_background(
            self,
            lambda: self._service.delete_draft(row.id),
            lambda _: self.reload(),
            self._failed,
        )

    def _add_payment(self) -> None:
        row = self._selected()
        if row is None:
            return
        dialog = PaymentDialog(row.debt, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payment = dialog.result_value()
        if payment is None:
            return
        amount_value, method = payment
        run_in_background(
            self,
            lambda: self._service.add_payment(
                row.id,
                amount_value,
                method,
                datetime.now(self._business_timezone),
            ),
            lambda _: self.reload(),
            self._failed,
        )

    @staticmethod
    def _status(status: str) -> str:
        # Only two working states are exposed: an editable open document and a
        # completed one whose stock/supplier balance has been applied.
        return {
            "draft": "Բաց",
            "open": "Ավարտված",
            "partially_paid": "Ավարտված",
            "paid": "Ավարտված",
            "cancelled": "Չեղարկված",
        }.get(status, status)

    def _failed(self, _error: Exception) -> None:
        warn(self, "Գործողությունը չհաջողվեց կատարել։")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)
