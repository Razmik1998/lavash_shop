from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from schemas import (
    CustomerPaymentHistoryRow,
    CustomerRow,
    SaleDetail,
    SalesFilters,
    SalesPage,
    SalesSummary,
)
from ui.components import (
    DataTable,
    DatePeriodFilter,
    GhostButton,
    PageTitle,
    PrimaryButton,
    RefreshButton,
    SecondaryButton,
)
from ui.sale_unlock_keys_window import _audit_label, _format_change
from ui.style import configure_page_layout, format_currency, format_quantity
from ui.workers import run_in_background, wait_for_pending_threads

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


class CreditCustomerService(Protocol):
    def list_credit_customers(self) -> list[CustomerRow]: ...

    def list_payment_history(
        self,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
        customer_id: uuid.UUID | None = None,
    ) -> list[CustomerPaymentHistoryRow]: ...

    def list_sales(
        self, filters: SalesFilters, cursor: str | None, limit: int = 50
    ) -> SalesPage: ...

    def summarize_sales(self, filters: SalesFilters) -> SalesSummary: ...

    def get_sale_detail(
        self, sale_id: uuid.UUID, *, barbecue_only: bool = False
    ) -> SaleDetail: ...


class CreditCustomersWindow(QWidget):
    def __init__(self, service: CreditCustomerService) -> None:
        super().__init__()
        self._service = service
        self._customer_id: uuid.UUID | None = None
        self._stack = QStackedWidget()
        self._customers_page = self._build_customers_page()
        self._customer_actions_page = self._build_customer_actions_page()
        self._purchases_page = self._build_purchases_page()
        self._payments_page = self._build_payments_page()
        self._purchase_detail_page = self._build_purchase_detail_page()
        self._stack.addWidget(self._customers_page)
        self._stack.addWidget(self._customer_actions_page)
        self._stack.addWidget(self._purchases_page)
        self._stack.addWidget(self._payments_page)
        self._stack.addWidget(self._purchase_detail_page)
        layout = QVBoxLayout()
        configure_page_layout(layout)
        layout.addWidget(self._stack)
        self.setLayout(layout)
        self._load_customers()

    def _build_customers_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(PageTitle("Պարտքով հաճախորդներ"))
        actions = QHBoxLayout()
        actions.addWidget(RefreshButton(on_click=self._load_customers))
        actions.addStretch()
        actions.addWidget(
            SecondaryButton("Բացել հաճախորդին", on_click=self._open_customer_actions)
        )
        layout.addLayout(actions)
        self._customers = DataTable(
            ["Անուն", "Հեռախոս", "Ընթացիկ պարտք"],
            on_double_click=self._open_customer_actions,
        )
        layout.addWidget(self._customers, 1)
        return page

    def _build_customer_actions_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        header.addWidget(GhostButton("← Վերադառնալ", on_click=self._show_customers))
        self._customer_actions_title = PageTitle("Հաճախորդ")
        header.addWidget(self._customer_actions_title)
        header.addStretch()
        layout.addLayout(header)
        layout.addWidget(
            PrimaryButton("Պարտքով վերցրած ապրանքներ", on_click=self._show_purchases)
        )
        layout.addWidget(
            SecondaryButton("Վճարումների պատմություն", on_click=self._show_payments)
        )
        layout.addStretch()
        return page

    def _build_purchases_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        header.addWidget(
            GhostButton("← Վերադառնալ", on_click=self._show_customer_actions)
        )
        self._purchases_title = PageTitle("Պարտքով վերցրած ապրանքներ")
        header.addWidget(self._purchases_title)
        header.addStretch()
        layout.addLayout(header)
        self._purchases_period = DatePeriodFilter(on_change=self._load_purchases)
        layout.addWidget(self._purchases_period)
        self._purchases_total = QLabel()
        layout.addWidget(self._purchases_total)
        self._purchases_status = QLabel()
        layout.addWidget(self._purchases_status)
        layout.addWidget(RefreshButton(on_click=self._load_purchases))
        self._purchases = DataTable(
            ["Ամսաթիվ", "Գումար", "Հաճախորդ", "Կարգավիճակ"],
            on_double_click=self._open_purchase_detail,
        )
        layout.addWidget(self._purchases, 1)
        return page

    def _build_purchase_detail_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        header.addWidget(GhostButton("← Վերադառնալ", on_click=self._show_purchases))
        self._purchase_detail_title = PageTitle("Վաճառքի մանրամասներ")
        header.addWidget(self._purchase_detail_title)
        header.addStretch()
        layout.addLayout(header)
        self._purchase_detail_meta = QLabel()
        self._purchase_detail_meta.setWordWrap(True)
        layout.addWidget(self._purchase_detail_meta)
        self._purchase_detail_items = DataTable(
            [
                "Ապրանք",
                "Կոդ",
                "Քանակ",
                "Ինքնարժեք",
                "Գին",
                "Զեղչ",
                "Եկամուտ",
                "Ընդհանուր",
            ]
        )
        layout.addWidget(self._purchase_detail_items, 1)
        self._purchase_detail_audit = DataTable(
            ["Ամսաթիվ", "Գործողություն", "Նախորդ արժեք", "Նոր արժեք"]
        )
        layout.addWidget(self._purchase_detail_audit, 1)
        return page

    def _build_payments_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        header.addWidget(GhostButton("← Վերադառնալ", on_click=self._show_customers))
        self._payments_title = PageTitle("Վճարումների պատմություն")
        header.addWidget(self._payments_title)
        header.addStretch()
        layout.addLayout(header)
        self._period = DatePeriodFilter(on_change=self._load_payments)
        layout.addWidget(self._period)
        layout.addWidget(RefreshButton(on_click=self._load_payments))
        self._payments = DataTable(
            ["Ամսաթիվ", "Հաճախորդ", "Հեռախոս", "Գումար", "POS սեսիա", "Աշխատակից"]
        )
        layout.addWidget(self._payments, 1)
        return page

    def _load_customers(self) -> None:
        run_in_background(
            self,
            self._service.list_credit_customers,
            self._customers_loaded,
            self._failed,
        )

    def _customers_loaded(self, customers: list[CustomerRow]) -> None:
        self._customers.set_rows(
            [
                customer.first_name + " " + customer.last_name,
                customer.phone,
                format_currency(customer.current_debt),
            ]
            for customer in customers
        )
        self._customer_rows = customers

    def _open_customer_actions(self) -> None:
        row = self._customers.selected_row()
        if row < 0 or row >= len(self._customer_rows):
            return
        self._customer_id = self._customer_rows[row].id
        customer = self._customer_rows[row]
        title = f"{customer.first_name} {customer.last_name}"
        self._customer_actions_title.setText(title)
        self._purchases_title.setText(f"Պարտքով վերցրած ապրանքներ՝ {title}")
        self._payments_title.setText(f"Վճարումների պատմություն՝ {title}")
        self._stack.setCurrentWidget(self._customer_actions_page)

    def _show_purchases(self) -> None:
        self._stack.setCurrentWidget(self._purchases_page)
        self._load_purchases()

    def _show_payments(self) -> None:
        self._stack.setCurrentWidget(self._payments_page)
        self._load_payments()

    def _load_purchases(self) -> None:
        if self._customer_id is None:
            return
        from_value, to_value = self._purchases_period.values()
        filters = SalesFilters(
            from_datetime=from_value.replace(tzinfo=ARMENIA_TIMEZONE)
            if from_value
            else None,
            to_datetime=to_value.replace(tzinfo=ARMENIA_TIMEZONE) if to_value else None,
            customer_id=self._customer_id,
        )
        run_in_background(
            self,
            lambda: self._service.list_sales(filters, None),
            self._purchases_loaded,
            self._failed,
        )
        run_in_background(
            self,
            lambda: self._service.summarize_sales(filters),
            lambda summary: self._purchases_total.setText(
                f"Ընդհանուր պարտքով վաճառք՝ {format_currency(summary.credit_total)}"
            ),
            self._failed,
        )

    def _purchases_loaded(self, page: SalesPage) -> None:
        self._purchase_rows = page.items
        self._purchases_status.setText(
            "Այս ժամանակահատվածում պարտքով վաճառք չկա։" if not page.items else ""
        )
        self._purchases.set_rows(
            [
                row.created_at.astimezone(ARMENIA_TIMEZONE).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                format_currency(row.credit_amount or row.total),
                row.credit_customer_name or "-",
                row.status,
            ]
            for row in page.items
        )

    def _open_purchase_detail(self) -> None:
        row = self._purchases.selected_row()
        if 0 <= row < len(self._purchase_rows):
            run_in_background(
                self,
                lambda: self._service.get_sale_detail(self._purchase_rows[row].id),
                self._purchase_detail_loaded,
                self._failed,
            )

    def _purchase_detail_loaded(self, detail: SaleDetail) -> None:
        payment_type = "Պարտքով" if detail.credit_amount is not None else "Կանխիկ"
        timestamp = detail.created_at.astimezone(ARMENIA_TIMEZONE).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self._purchase_detail_title.setText(
            f"Վաճառքի մանրամասներ՝ {detail.terminal_id}"
        )
        self._purchase_detail_meta.setText(
            f"Վճարման ձև՝ {payment_type} | "
            f"Գումար՝ {format_currency(detail.total)} | "
            f"Պարտք՝ {format_currency(detail.credit_amount or 0)} | "
            f"Հաճախորդ՝ {detail.credit_customer_name or '-'} | "
            f"Ամսաթիվ՝ {timestamp}"
        )
        self._purchase_detail_items.set_rows(
            [
                item.product_name,
                item.product_sku,
                format_quantity(item.quantity),
                format_currency(item.cost_price or 0),
                format_currency(item.unit_price),
                format_currency(item.discount_amount) if item.discount_amount else "-",
                format_currency(
                    (item.unit_price - (item.cost_price or 0)) * item.quantity
                ),
                format_currency(item.line_total),
            ]
            for item in detail.items
        )
        self._purchase_detail_audit.set_rows(
            [
                event.created_at.astimezone(ARMENIA_TIMEZONE).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                _audit_label(event.event_type),
                _format_change(event.old_value),
                _format_change(event.new_value),
            ]
            for event in detail.audit_events
        )
        self._stack.setCurrentWidget(self._purchase_detail_page)

    def _load_payments(self) -> None:
        if self._customer_id is None:
            return
        from_value, to_value = self._period.values()
        from_datetime = (
            from_value.replace(tzinfo=ARMENIA_TIMEZONE) if from_value else None
        )
        to_datetime = to_value.replace(tzinfo=ARMENIA_TIMEZONE) if to_value else None
        run_in_background(
            self,
            lambda: self._service.list_payment_history(
                from_datetime, to_datetime, self._customer_id
            ),
            self._payments_loaded,
            self._failed,
        )

    def _payments_loaded(self, payments: list[CustomerPaymentHistoryRow]) -> None:
        self._payments.set_rows(
            [
                payment.paid_at.astimezone(ARMENIA_TIMEZONE).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                payment.customer_name,
                payment.phone,
                format_currency(payment.amount),
                str(payment.pos_session_id),
                str(payment.pos_user_id),
            ]
            for payment in payments
        )

    def _show_customers(self) -> None:
        self._stack.setCurrentWidget(self._customers_page)
        self._load_customers()

    def _show_customer_actions(self) -> None:
        self._stack.setCurrentWidget(self._customer_actions_page)

    def _failed(self, error: Exception) -> None:
        message = f"Չհաջողվեց բեռնել տվյալները։ {error}"
        self._payments.set_rows([[message, "", "", "", "", ""]])
        self._purchases_status.setText(message)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)
