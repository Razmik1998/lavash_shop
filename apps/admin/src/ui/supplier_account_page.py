"""In-page supplier account: purchase documents and payment history."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from models import PaymentMethod
from services import PurchaseRow, SupplierAccount, SupplierRow
from ui.components import (
    ActionBar,
    BackButton,
    DataTable,
    DatePeriodFilter,
    DetailsButton,
    EditButton,
    NavCard,
    PageSubtitle,
    PageTitle,
    PaymentButton,
    ProfileHeader,
    RefreshButton,
    SectionHeading,
    StatCard,
    inform,
    warn,
)
from ui.payment_dialog import PaymentDialog, payment_method_label
from ui.purchase_document import (
    EditorOpener,
    PurchaseDocumentFlow,
    PurchaseDocumentService,
    purchase_status_label,
)
from ui.style import configure_page_layout, format_currency, format_quantity
from ui.workers import run_in_background, wait_for_pending_threads

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


class SupplierAccountService(Protocol):
    def get_account(
        self,
        supplier_id: uuid.UUID,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
    ) -> SupplierAccount: ...


class SupplierPaymentService(PurchaseDocumentService, Protocol):
    def add_payment(
        self,
        purchase_id: uuid.UUID,
        amount: Decimal,
        method: PaymentMethod,
        payment_date: datetime,
        notes: str | None = None,
    ) -> object: ...

    def pay_supplier_debt(
        self,
        supplier_id: uuid.UUID,
        amount: Decimal,
        method: PaymentMethod,
        payment_date: datetime,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
    ) -> int: ...


class _AccountView(QWidget):
    """One period-filtered account table with totals and payment actions.

    Shared by the documents page and the payment-history page, which differ
    only in their table and in whether a single document can be paid.
    """

    def __init__(
        self,
        title: str,
        headers: Sequence[str],
        account_service: SupplierAccountService,
        payment_service: SupplierPaymentService,
        *,
        on_back: Callable[[], object],
        on_changed: Callable[[], object],
        documents: bool,
        open_editor: EditorOpener | None = None,
    ) -> None:
        super().__init__()
        self._title_text = title
        self._account_service = account_service
        self._payment_service = payment_service
        self._on_changed = on_changed
        self._documents = documents
        self._supplier: SupplierRow | None = None
        self._account: SupplierAccount | None = None
        self._generation = 0
        self._flow = PurchaseDocumentFlow(
            self, payment_service, open_editor, self._document_changed
        )

        self._title = PageTitle(title)
        self._period = DatePeriodFilter(on_change=self.reload)
        self._message = PageSubtitle()
        self._purchased = StatCard("Գնումների գումար", "0 ֏", tone="primary")
        self._paid = StatCard("Վճարված", "0 ֏", tone="success")
        self._debt = StatCard("Վճարման ենթակա պարտք", "0 ֏", tone="danger")
        self._total_debt = StatCard(
            "Ընդհանուր պարտք", "0 ֏", "Ամբողջ պատմությամբ", tone="danger"
        )
        self._table = DataTable(
            headers, on_double_click=self._open_document if documents else None
        )

        header = QHBoxLayout()
        header.addWidget(BackButton(on_click=on_back))
        header.addWidget(self._title)
        header.addStretch()
        header.addWidget(RefreshButton(on_click=self.reload))

        stats = QHBoxLayout()
        for card in (self._purchased, self._paid, self._debt, self._total_debt):
            stats.addWidget(card, stretch=1)

        actions: list[QWidget] = [
            PaymentButton("Վճարել պարտքը", on_click=self._pay_debt)
        ]
        if documents:
            actions = [
                DetailsButton("Բացել փաստաթուղթը", on_click=self._open_document),
                EditButton(on_click=self._edit_document, enabled=self._flow.can_edit),
                PaymentButton("Վճարել փաստաթուղթը", on_click=self._pay_document),
                *actions,
            ]

        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.addLayout(header)
        layout.addWidget(self._period)
        layout.addLayout(stats)
        layout.addWidget(ActionBar(actions))
        layout.addWidget(self._message)
        layout.addWidget(self._table, stretch=1)

    def open(self, supplier: SupplierRow) -> None:
        self._supplier = supplier
        self._title.setText(f"{self._title_text}՝ {supplier.name}")
        self.reload()

    def _period_range(self) -> tuple[datetime | None, datetime | None]:
        from_value, to_value = self._period.values()
        return (
            from_value.replace(tzinfo=ARMENIA_TIMEZONE) if from_value else None,
            to_value.replace(tzinfo=ARMENIA_TIMEZONE) if to_value else None,
        )

    def reload(self) -> None:
        supplier = self._supplier
        if supplier is None:
            return
        from_datetime, to_datetime = self._period_range()
        if (
            from_datetime is not None
            and to_datetime is not None
            and (from_datetime >= to_datetime)
        ):
            self._message.setText("Սկզբի ամսաթիվը չի կարող ուշ լինել վերջից։")
            return
        self._generation += 1
        generation = self._generation
        self._message.setText("Բեռնվում է...")
        run_in_background(
            self,
            lambda: self._account_service.get_account(
                supplier.id, from_datetime, to_datetime
            ),
            lambda account: self._loaded(generation, account),
            lambda error: self._load_failed(generation, error),
        )

    def _loaded(self, generation: int, account: SupplierAccount) -> None:
        if generation != self._generation:
            return
        self._account = account
        self._purchased.set_value(format_currency(account.purchased_total))
        self._paid.set_value(format_currency(account.paid_total))
        self._debt.set_value(format_currency(account.debt))
        self._total_debt.set_value(format_currency(account.total_debt))
        if self._documents:
            self._show_documents(account.purchases)
        else:
            self._show_payments(account)

    def _show_documents(self, purchases: list[PurchaseRow]) -> None:
        self._table.set_rows(
            [
                row.purchase_number,
                row.purchase_date.astimezone(ARMENIA_TIMEZONE).date().isoformat(),
                format_currency(row.total),
                format_currency(row.paid),
                format_currency(row.debt),
                purchase_status_label(row.status),
                format_quantity(row.item_quantity),
            ]
            for row in purchases
        )
        for index, row in enumerate(purchases):
            if row.status == "draft":
                self._table.highlight_row(index)
        self._message.setText(
            "" if purchases else "Այս ժամանակահատվածում փաստաթղթեր չկան։"
        )

    def _show_payments(self, account: SupplierAccount) -> None:
        self._table.set_rows(
            [
                payment.payment_date.astimezone(ARMENIA_TIMEZONE).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                payment.purchase_number or "-",
                format_currency(payment.amount),
                payment_method_label(payment.method),
                payment.notes or "",
            ]
            for payment in account.payments
        )
        self._message.setText(
            f"Վճարումներ ժամանակահատվածում՝ {len(account.payments)} | "
            f"Գումար՝ {format_currency(account.payments_total)}"
            if account.payments
            else "Այս ժամանակահատվածում վճարումներ չկան։"
        )

    def _load_failed(self, generation: int, _error: Exception) -> None:
        if generation != self._generation:
            return
        self._message.setText("Չհաջողվեց բեռնել մատակարարի տվյալները։")

    def _ask_payment(
        self, outstanding: Decimal
    ) -> tuple[Decimal, PaymentMethod] | None:
        dialog = PaymentDialog(outstanding, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        payment = dialog.result_value()
        if payment is None:
            return None
        if payment[0] <= 0 or payment[0] > outstanding:
            warn(self, "Գումարը պետք է լինի դրական և չգերազանցի պարտքը։")
            return None
        return payment

    def _pay_debt(self) -> None:
        supplier = self._supplier
        account = self._account
        if supplier is None or account is None:
            return
        if account.debt <= 0:
            inform(self, "Այս ժամանակահատվածում պարտք չկա։")
            return
        payment = self._ask_payment(account.debt)
        if payment is None:
            return
        amount, method = payment
        from_datetime, to_datetime = self._period_range()
        run_in_background(
            self,
            lambda: self._payment_service.pay_supplier_debt(
                supplier.id,
                amount,
                method,
                datetime.now(ARMENIA_TIMEZONE),
                from_datetime,
                to_datetime,
            ),
            self._payment_saved,
            self._payment_failed,
        )

    def _pay_document(self) -> None:
        purchase = self._selected_purchase()
        if purchase is None:
            return
        if purchase.status not in {"open", "partially_paid"}:
            warn(self, "Այս փաստաթուղթը վճարման ենթակա չէ։")
            return
        payment = self._ask_payment(purchase.debt)
        if payment is None:
            return
        amount, method = payment
        run_in_background(
            self,
            lambda: self._payment_service.add_payment(
                purchase.id, amount, method, datetime.now(ARMENIA_TIMEZONE)
            ),
            self._payment_saved,
            self._payment_failed,
        )

    def _payment_saved(self, _result: object) -> None:
        self._on_changed()
        self.reload()

    def _payment_failed(self, _error: Exception) -> None:
        warn(self, "Չհաջողվեց գրանցել վճարումը։")

    def _selected_purchase(self) -> PurchaseRow | None:
        account = self._account
        row = self._table.selected_row()
        if account is None or not 0 <= row < len(account.purchases):
            warn(self, "Ընտրեք գնման փաստաթուղթ։")
            return None
        return account.purchases[row]

    def _open_document(self) -> None:
        purchase = self._selected_purchase()
        if purchase is not None:
            self._flow.open(purchase)

    def _edit_document(self) -> None:
        purchase = self._selected_purchase()
        if purchase is not None:
            self._flow.edit(purchase)

    def _document_changed(self) -> None:
        self._on_changed()
        self.reload()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._generation += 1
        wait_for_pending_threads(self)
        super().closeEvent(event)


class SupplierAccountPage(QWidget):
    """Supplier landing page with documents and payment-history subpages."""

    def __init__(
        self,
        account_service: SupplierAccountService,
        payment_service: SupplierPaymentService,
        *,
        on_back: Callable[[], object],
        on_changed: Callable[[], object],
        open_editor: EditorOpener | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._account_service = account_service
        self._supplier: SupplierRow | None = None
        self._generation = 0
        self._stack = QStackedWidget()
        self._menu_page = self._build_menu_page(on_back)
        self.documents_view = _AccountView(
            "Գնման փաստաթղթեր",
            ["Համար", "Ամսաթիվ", "Ընդամենը", "Վճարված", "Պարտք", "Կարգավիճակ", "Քանակ"],
            account_service,
            payment_service,
            on_back=self.show_menu,
            on_changed=on_changed,
            documents=True,
            open_editor=open_editor,
        )
        self.payments_view = _AccountView(
            "Վճարումների պատմություն",
            ["Ամսաթիվ", "Փաստաթուղթ", "Գումար", "Վճարման ձև", "Նշումներ"],
            account_service,
            payment_service,
            on_back=self.show_menu,
            on_changed=on_changed,
            documents=False,
        )
        self._stack.addWidget(self._menu_page)
        self._stack.addWidget(self.documents_view)
        self._stack.addWidget(self.payments_view)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

    def _build_menu_page(self, on_back: Callable[[], object]) -> QWidget:
        page = QWidget()
        self._profile = ProfileHeader()
        self._purchased = StatCard("Գնումների գումար", "—", tone="primary")
        self._paid = StatCard("Վճարված", "—", tone="success")
        self._debt = StatCard("Ընդհանուր պարտք", "—", tone="danger")
        self._documents = StatCard("Փաստաթղթեր", "—", tone="info")
        self._menu_message = PageSubtitle()

        header = QHBoxLayout()
        header.addWidget(BackButton(on_click=on_back))
        header.addStretch()
        header.addWidget(RefreshButton(on_click=self._load_overview))

        stats = QHBoxLayout()
        stats.setSpacing(12)
        for card in (self._purchased, self._paid, self._debt, self._documents):
            stats.addWidget(card, stretch=1)

        sections = QHBoxLayout()
        sections.setSpacing(16)
        sections.addWidget(
            NavCard(
                "Գնման փաստաթղթեր",
                "Բոլոր գնումները՝ բացել, խմբագրել և վճարել ըստ ժամանակահատվածի։",
                icon="📄",
                on_click=self.show_documents,
            ),
            stretch=1,
        )
        sections.addWidget(
            NavCard(
                "Վճարումների պատմություն",
                "Բոլոր վճարումները մատակարարին, ամսաթվերով և փաստաթղթերով։",
                icon="💳",
                tone="success",
                on_click=self.show_payments,
            ),
            stretch=1,
        )

        layout = QVBoxLayout(page)
        configure_page_layout(layout)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addWidget(self._profile)
        layout.addLayout(stats)
        layout.addWidget(self._menu_message)
        layout.addWidget(SectionHeading("Բաժիններ"))
        layout.addLayout(sections)
        layout.addStretch()
        return page

    def open(self, supplier: SupplierRow) -> None:
        self._supplier = supplier
        details = " · ".join(
            part for part in (supplier.phone, supplier.description) if part
        )
        self._profile.set_profile(
            supplier.name,
            details or "Կոնտակտային տվյալներ չկան",
            "Ակտիվ" if supplier.is_active else "Արխիվացված",
            "info" if supplier.is_active else "warning",
        )
        self.show_menu()

    def show_menu(self) -> None:
        self._stack.setCurrentWidget(self._menu_page)
        self._load_overview()

    def _load_overview(self) -> None:
        supplier = self._supplier
        if supplier is None:
            return
        self._generation += 1
        generation = self._generation
        run_in_background(
            self,
            lambda: self._account_service.get_account(supplier.id),
            lambda account: self._overview_loaded(generation, account),
            lambda _error: self._overview_failed(generation),
        )

    def _overview_loaded(self, generation: int, account: SupplierAccount) -> None:
        if generation != self._generation:
            return
        confirmed = [
            row for row in account.purchases if row.status not in {"draft", "cancelled"}
        ]
        drafts = sum(1 for row in account.purchases if row.status == "draft")
        last_purchase = max((row.purchase_date for row in confirmed), default=None)
        self._purchased.set_value(format_currency(account.purchased_total))
        self._paid.set_value(format_currency(account.paid_total))
        self._debt.set_value(format_currency(account.total_debt))
        self._documents.set_value(
            str(len(confirmed)),
            f"Վերջին գնում՝ {last_purchase.astimezone(ARMENIA_TIMEZONE):%d.%m.%Y}"
            if last_purchase
            else "Գնումներ դեռ չկան",
        )
        self._menu_message.setText(
            f"Ուշադրություն․ {drafts} բաց (չհաստատված) փաստաթուղթ։" if drafts else ""
        )

    def _overview_failed(self, generation: int) -> None:
        if generation == self._generation:
            self._menu_message.setText("Չհաջողվեց բեռնել մատակարարի ամփոփումը։")

    def show_documents(self) -> None:
        if self._supplier is not None:
            self._stack.setCurrentWidget(self.documents_view)
            self.documents_view.open(self._supplier)

    def show_payments(self) -> None:
        if self._supplier is not None:
            self._stack.setCurrentWidget(self.payments_view)
            self.payments_view.open(self._supplier)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._generation += 1
        wait_for_pending_threads(self)
        super().closeEvent(event)
