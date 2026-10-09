"""Database-backed Armenian supplier purchase report."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from services import PurchaseFilters, SupplierReportRow, SupplierRow
from ui.components import (
    DataTable,
    DatePeriodFilter,
    FormField,
    PageHeader,
    PageSubtitle,
    Panel,
    RefreshButton,
    SearchButton,
    SearchField,
    SectionHeading,
    SelectField,
    StatCard,
    StatusBadge,
)
from ui.style import (
    configure_page_layout,
    format_currency,
    format_quantity,
)
from ui.workers import run_in_background, wait_for_pending_threads


class SupplierReportService(Protocol):
    def supplier_report(
        self, filters: PurchaseFilters | None = None
    ) -> list[SupplierReportRow]: ...


class SupplierSelectorService(Protocol):
    def list_suppliers(self) -> list[SupplierRow]: ...


class SupplierReportWindow(QWidget):
    def __init__(
        self,
        report_service: SupplierReportService,
        supplier_service: SupplierSelectorService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._report_service = report_service
        self._business_timezone = ZoneInfo("Asia/Yerevan")
        self.setObjectName("supplierReport")
        self.setStyleSheet("""
            QWidget#supplierReport QFrame#panel,
            QWidget#supplierReport QFrame#statCard {
                background: white; border: 1px solid #dfe7f1; border-radius: 14px;
            }
            QWidget#supplierReport QDateEdit {
                min-height: 36px; padding: 5px 12px;
                border: 1px solid #ccd8e8; border-radius: 8px;
                background: white;
            }
            QWidget#supplierReport QDateEdit:disabled {
                color: #87909a; background: #f5f8fd;
            }
            QWidget#supplierReport QTableView::item { padding: 0 10px; }
            QWidget#supplierReport QTableView {
                border: 0; alternate-background-color: #f5f8fd;
            }
            QWidget#supplierReport QHeaderView::section {
                background: #edf3fc; color: #344c70; padding: 14px 10px;
            }
        """)
        self._period = DatePeriodFilter(business_timezone="Asia/Yerevan")
        self._from_date = self._period._from_date
        self._to_date = self._period._to_date
        self._from_date.setDisplayFormat("dd.MM.yyyy")
        self._to_date.setDisplayFormat("dd.MM.yyyy")
        self._from_date.setAccessibleName("Սկիզբ")
        self._to_date.setAccessibleName("Վերջ")
        self._search_generation = 0
        self._loaded_period = ""
        self._supplier = SelectField([("Բոլոր մատակարարները", None)])
        for supplier in supplier_service.list_suppliers():
            self._supplier.addItem(supplier.name, supplier.id)
        self._search = SearchField("Ապրանք կամ մատակարար", on_submit=self.reload)
        self._table = DataTable(
            [
                "Մատակարար",
                "Գնումների քանակ",
                "Ապրանքների քանակ",
                "Գնման գումար",
                "Վճարված գումար",
                "Ընթացիկ պարտք",
                "Ժամանակահատված",
            ]
        )
        self._model = self._table.item_model
        self._search.setClearButtonEnabled(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setDefaultSectionSize(48)
        self._refresh_button = RefreshButton(on_click=self.reload)
        self._search_button = SearchButton(on_click=self.reload)
        filters = Panel()
        filter_layout = QGridLayout(filters)
        filter_layout.setContentsMargins(20, 18, 20, 18)
        filter_layout.setSpacing(14)
        filter_layout.addWidget(SectionHeading("Ժամանակահատված և որոնում"), 0, 0, 1, 3)
        filter_layout.addWidget(FormField("Ժամանակահատված", self._period), 1, 0, 1, 3)
        filter_layout.addWidget(FormField("Մատակարար", self._supplier), 2, 0)
        filter_layout.addWidget(FormField("Ապրանք կամ մատակարար", self._search), 2, 1)
        filter_layout.addWidget(
            self._search_button, 2, 2, alignment=Qt.AlignmentFlag.AlignBottom
        )
        filter_layout.setColumnStretch(1, 1)
        self._cards = [
            StatCard("Մատակարարներ", "—", tone="info"),
            StatCard("Գնման գումար", "—", tone="primary"),
            StatCard("Վճարված գումար", "—", tone="success"),
            StatCard("Ընթացիկ պարտք", "—", tone="danger"),
        ]
        totals = QHBoxLayout()
        totals.setSpacing(14)
        for card in self._cards:
            totals.addWidget(card, 1)
        results = Panel()
        results_layout = QVBoxLayout(results)
        results_layout.setContentsMargins(16, 16, 16, 16)
        results_heading = QHBoxLayout()
        results_heading.addWidget(SectionHeading("Մատակարարների ամփոփում"))
        results_heading.addStretch()
        self._status = StatusBadge("Բեռնվում է")
        results_heading.addWidget(self._status)
        results_layout.addLayout(results_heading)
        self._message = PageSubtitle()
        results_layout.addWidget(self._message)
        results_layout.addWidget(self._table, 1)
        heading = QHBoxLayout()
        heading.addWidget(
            PageHeader(
                "Մատակարարների հաշվետվություն",
                "Գնումներ, վճարումներ և պարտքեր՝ մեկ տեղում",
            ),
            1,
        )
        heading.addWidget(self._refresh_button)
        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.addLayout(heading)
        layout.addLayout(totals)
        layout.addWidget(filters)
        layout.addWidget(results, stretch=1)
        self.reload()

    def reload(self) -> None:
        start, end = self._period.values()
        if start is not None and end is not None and start >= end:
            self._message.setText("Սկիզբը պետք է լինի ավարտից առաջ։")
            self._status.set_status("Սխալ միջակայք", "warning")
            return
        filters = PurchaseFilters(
            from_datetime=self._date_start(),
            to_datetime=self._date_end(),
            supplier_id=self._supplier.currentData(),
            search=self._search.text().strip() or None,
        )
        period = (
            "Ամբողջ պատմություն"
            if start is None
            else (f"{start:%d.%m.%Y} – {end - timedelta(days=1):%d.%m.%Y}")
        )
        self._search_generation += 1
        generation = self._search_generation
        self._status.set_status("Բեռնվում է", "info")
        self._message.setText("Հաշվետվությունը բեռնվում է…")

        def loaded(rows: list[SupplierReportRow]) -> None:
            if generation == self._search_generation:
                self._loaded_period = period
                self._loaded(rows)

        def failed(error: Exception) -> None:
            if generation == self._search_generation:
                self._failed(error)

        run_in_background(
            self, lambda: self._report_service.supplier_report(filters), loaded, failed
        )

    def _date_start(self) -> datetime | None:
        value, _ = self._period.values()
        return (
            None
            if value is None
            else value.replace(tzinfo=self._business_timezone).astimezone(UTC)
        )

    def _date_end(self) -> datetime | None:
        _, value = self._period.values()
        # Purchase report queries use an inclusive upper bound.
        return (
            None
            if value is None
            else (
                value.replace(tzinfo=self._business_timezone).astimezone(UTC)
                - timedelta(microseconds=1)
            )
        )

    def _loaded(self, rows: list[SupplierReportRow]) -> None:
        period = self._loaded_period
        self._table.set_rows(
            [
                row.supplier_name,
                str(row.purchase_count),
                format_quantity(row.purchased_quantity),
                format_currency(row.purchase_amount),
                format_currency(row.paid_amount),
                format_currency(row.outstanding_debt),
                period,
            ]
            for row in rows
        )

        values = [str(len(rows))] + [
            format_currency(sum((getattr(row, field) for row in rows), Decimal("0")))
            for field in ("purchase_amount", "paid_amount", "outstanding_debt")
        ]
        for card, value in zip(self._cards, values, strict=True):
            card.set_value(value)
        for index, row in enumerate(rows):
            for column in range(1, 6):
                self._model.item(index, column).setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            if row.outstanding_debt > 0:
                self._model.item(index, 5).setForeground(QColor("#b43d4b"))
        self._status.set_status(f"{len(rows)} մատակարար", "success")
        self._message.setText(
            period
            if rows
            else (f"{period} · Տվյալներ չեն գտնվել։ Փոխեք ֆիլտրերը կամ որոնման բառը։")
        )

    def _failed(self, _error: Exception) -> None:
        self._table.clear_rows()
        for card in self._cards:
            card.set_value("—")
        self._status.set_status("Բեռնման սխալ", "danger")
        self._message.setText(
            "Չհաջողվեց բեռնել հաշվետվությունը։ Փորձեք կրկին թարմացնել։"
        )

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)
