from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from exceptions import CustomerPhoneAlreadyExistsError
from networking.protocol import CustomerPayload
from services import CustomerService
from ui.components.buttons import PaymentButton, SaveButton, SecondaryButton
from ui.components.inputs import AmountField, SearchField, TextField
from ui.workers import run_in_background


@dataclass(frozen=True)
class CustomerSelection:
    customer_id: str | None = None
    name: str = ""


class CreditCustomerDialog(QDialog):
    payment_recorded = Signal(object)

    def __init__(
        self,
        customers: list[CustomerPayload],
        customer_service: CustomerService | None = None,
        parent: QWidget | None = None,
        session_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Վաճառք պարտքով")
        self.setMinimumSize(620, 560)
        self.resize(700, 620)
        self.setStyleSheet(
            """
            QDialog { background: #0c3a33; color: #ffffff; }
            QLabel#dialogTitle { color: #ffffff; font-size: 22px; font-weight: 700; }
            QLabel#dialogHint, QLabel#dialogStatus { color: #a0c4be; font-size: 13px; }
            QLabel#dialogSection { color: #ffffff; font-size: 15px; font-weight: 700; }
            QTableWidget {
                background: #114e45; color: #ffffff; border: 1px solid #1b6b5e;
                border-radius: 8px; gridline-color: #1b6b5e; font-size: 14px;
            }
            QTableWidget::item { color: #ffffff; padding: 10px 8px; }
            QTableWidget::item:hover { background: #186055; }
            QTableWidget::item:selected { color: #0c3a33; background: #ffcc00; }
            QHeaderView::section {
                background: #186055; color: #ffffff; padding: 10px 8px;
                border: 0; font-weight: 700;
            }
            QLineEdit {
                background: #186055; color: #ffffff; border: 1px solid #1b6b5e;
                border-radius: 7px; padding: 9px 11px; min-height: 38px;
            }
            QLineEdit::placeholder { color: #a0c4be; }
            QLineEdit:focus { border: 2px solid #ffcc00; }
            """
        )
        self._customers = list(customers)
        self._customer_service = customer_service
        self._session_id = session_id
        self._stack = QStackedWidget()
        self._status = QLabel()
        self._status.setObjectName("dialogStatus")
        self._search = SearchField(
            "Որոնել անունով, ազգանունով կամ հեռախոսով",
            on_changed=self._render_customers,
        )
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Անուն", "Հեռախոս", "Պարտք"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.cellDoubleClicked.connect(lambda _row, _column: self.accept())
        self._first_name = TextField("Անուն")
        self._last_name = TextField("Ազգանուն")
        self._phone = TextField("Հեռախոս")
        self._address = TextField("Հասցե (ըստ ցանկության)")
        self._notes = TextField("Նշումներ (ըստ ցանկության)")
        self._stack.addWidget(self._build_list_page())
        self._stack.addWidget(self._build_create_page())

        title = QLabel("Վաճառք պարտքով")
        title.setObjectName("dialogTitle")
        hint = QLabel("Ընտրեք հաճախորդին կամ ստեղծեք նոր հաճախորդ։")
        hint.setObjectName("dialogHint")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self._stack, 1)
        self._render_customers()

    def _build_list_page(self) -> QWidget:
        page = QWidget()
        section = QLabel("Գրանցված հաճախորդներ")
        section.setObjectName("dialogSection")
        create = SecondaryButton("Ստեղծել հաճախորդ", on_click=self._show_create_page)
        payment = PaymentButton("Վճարել", on_click=self._record_payment)
        cancel = SecondaryButton("Չեղարկել", on_click=self.reject)
        confirm = SaveButton("Հաստատել", on_click=self._accept_selection)
        actions = QHBoxLayout()
        actions.addWidget(create)
        actions.addWidget(payment)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(confirm)
        layout = QVBoxLayout(page)
        layout.addWidget(section)
        layout.addWidget(self._search)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._status)
        layout.addLayout(actions)
        return page

    def _build_create_page(self) -> QWidget:
        page = QWidget()
        section = QLabel("Նոր հաճախորդ")
        section.setObjectName("dialogSection")
        back = SecondaryButton("Վերադառնալ", on_click=self._show_list_page)
        save = SaveButton("Պահպանել", on_click=self._create_customer)
        actions = QHBoxLayout()
        actions.addWidget(back)
        actions.addStretch()
        actions.addWidget(save)
        layout = QVBoxLayout(page)
        layout.addWidget(section)
        layout.addWidget(self._first_name)
        layout.addWidget(self._last_name)
        layout.addWidget(self._phone)
        layout.addWidget(self._address)
        layout.addWidget(self._notes)
        layout.addWidget(self._status)
        layout.addStretch()
        layout.addLayout(actions)
        return page

    def _render_customers(self) -> None:
        query = self._search.text().strip().casefold()
        visible = [
            customer
            for customer in self._customers
            if not query
            or query in customer.first_name.casefold()
            or query in customer.last_name.casefold()
            or query in customer.phone.casefold()
        ]
        self._table.setRowCount(0)
        for customer in visible:
            row = self._table.rowCount()
            self._table.insertRow(row)
            name = QTableWidgetItem(f"{customer.first_name} {customer.last_name}")
            name.setData(Qt.ItemDataRole.UserRole, customer.id)
            self._table.setItem(row, 0, name)
            self._table.setItem(row, 1, QTableWidgetItem(customer.phone))
            self._table.setItem(row, 2, QTableWidgetItem(f"{customer.current_debt} ֏"))
        if not visible:
            self._status.setText("Համապատասխան հաճախորդ չի գտնվել։")
        elif self._status.text() == "Համապատասխան հաճախորդ չի գտնվել։":
            self._status.clear()

    def _show_create_page(self) -> None:
        self._status.clear()
        self._stack.setCurrentIndex(1)

    def _show_list_page(self) -> None:
        self._stack.setCurrentIndex(0)
        self._render_customers()

    def _create_customer(self) -> None:
        if self._customer_service is None:
            self._status.setText("Հաճախորդների ծառայությունը հասանելի չէ։")
            return
        first_name = self._first_name.value()
        last_name = self._last_name.value()
        phone = self._phone.value()
        if not first_name or not last_name or not phone:
            self._status.setText("Անունը, ազգանունը և հեռախոսը պարտադիր են։")
            return
        self._set_create_enabled(False)
        run_in_background(
            self,
            lambda: self._customer_service.create_customer(
                first_name,
                last_name,
                phone,
                self._address.value() or None,
                self._notes.value() or None,
            ),
            self._on_customer_created,
            self._on_customer_create_failed,
        )

    def _record_payment(self) -> None:
        selection = self.selection()
        if (
            selection is None
            or self._customer_service is None
            or self._session_id is None
        ):
            self._status.setText("Ընտրեք հաճախորդ և համոզվեք, որ սեսիան ակտիվ է։")
            return
        customer = next(
            (item for item in self._customers if item.id == selection.customer_id),
            None,
        )
        if customer is None:
            return
        amount_field = AmountField(f"Գումար (պարտք՝ {customer.current_debt} ֏)")
        amount_field.setParent(self)
        amount_field.resize(320, 48)
        payment_dialog = QDialog(self)
        payment_dialog.setWindowTitle("Վճարել պարտքը")
        payment_layout = QVBoxLayout(payment_dialog)
        payment_layout.addWidget(
            QLabel(f"Հաճախորդ՝ {customer.first_name} {customer.last_name}")
        )
        payment_layout.addWidget(amount_field)
        pay = PaymentButton("Վճարել", on_click=payment_dialog.accept)
        cancel = SecondaryButton("Չեղարկել", on_click=payment_dialog.reject)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(pay)
        payment_layout.addLayout(actions)
        if payment_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        amount = amount_field.decimal_value()
        if amount is None or amount <= 0:
            self._status.setText("Մուտքագրեք դրական գումար։")
            return
        run_in_background(
            self,
            lambda: self._customer_service.record_payment(
                customer.id, amount, self._session_id
            ),
            lambda _payment: self._payment_recorded(customer.id, amount),
            self._payment_failed,
        )

    def _payment_recorded(self, customer_id: str, amount: object) -> None:
        for index, customer in enumerate(self._customers):
            if customer.id == customer_id:
                remaining = max(
                    Decimal(customer.current_debt) - Decimal(str(amount)),
                    Decimal("0"),
                )
                self._customers[index] = CustomerPayload(
                    customer.id,
                    customer.first_name,
                    customer.last_name,
                    customer.phone,
                    str(remaining),
                )
                break
        self._render_customers()
        self._status.setText("Վճարումը պահպանվեց։")
        self.payment_recorded.emit(amount)

    def _payment_failed(self, error: Exception) -> None:
        self._status.setText(f"Չհաջողվեց պահպանել վճարումը։ {error}")

    def _on_customer_created(self, customer: CustomerPayload) -> None:
        self._set_create_enabled(True)
        self._customers.insert(0, customer)
        self._clear_create_fields()
        self._show_list_page()
        self._table.selectRow(0)
        self._status.setText("Հաճախորդը պահպանվեց և ընտրվեց։")

    def _on_customer_create_failed(self, error: Exception) -> None:
        self._set_create_enabled(True)
        if isinstance(error, CustomerPhoneAlreadyExistsError):
            phone = self._phone.value()
            existing = next(
                (
                    index
                    for index, customer in enumerate(self._customers)
                    if customer.phone == phone
                ),
                None,
            )
            self._show_list_page()
            if existing is not None:
                self._table.selectRow(existing)
            self._status.setText(
                "Այս հեռախոսահամարով հաճախորդ արդեն կա։ Օգտագործեք նրա տվյալները։"
            )
            return
        self._status.setText(f"Չհաջողվեց պահպանել հաճախորդին։ {error}")

    def _set_create_enabled(self, enabled: bool) -> None:
        for field in (
            self._first_name,
            self._last_name,
            self._phone,
            self._address,
            self._notes,
        ):
            field.setEnabled(enabled)

    def _clear_create_fields(self) -> None:
        for field in (
            self._first_name,
            self._last_name,
            self._phone,
            self._address,
            self._notes,
        ):
            field.clear()

    def selection(self) -> CustomerSelection | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        return CustomerSelection(
            customer_id=str(item.data(Qt.ItemDataRole.UserRole)),
            name=item.text(),
        )

    def _accept_selection(self) -> None:
        if self.selection() is not None:
            self.accept()