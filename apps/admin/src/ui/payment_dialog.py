"""Shared "record a payment" dialog used by every purchase screen."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from models import PaymentMethod
from ui.components import (
    CancelButton,
    DialogButtonBar,
    MoneyField,
    PageTitle,
    SaveButton,
    SelectField,
    warn,
)
from ui.style import format_currency

PAYMENT_METHOD_OPTIONS: tuple[tuple[str, PaymentMethod], ...] = (
    ("Կանխիկ", PaymentMethod.CASH),
    ("Քարտ", PaymentMethod.CARD),
    ("Փոխանցում", PaymentMethod.TRANSFER),
    ("Այլ", PaymentMethod.OTHER),
)


def payment_method_label(method: PaymentMethod) -> str:
    return dict((value, label) for label, value in PAYMENT_METHOD_OPTIONS).get(
        method, method.value
    )


class PaymentDialog(QDialog):
    """Collects an amount and a payment method; ``result_value`` holds them."""

    def __init__(
        self, outstanding: Decimal | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Գրանցել վճարում")
        self._amount = MoneyField()
        self._method = SelectField(
            [(label, value) for label, value in PAYMENT_METHOD_OPTIONS]
        )
        layout = QVBoxLayout(self)
        layout.addWidget(PageTitle("Գրանցել վճարում"))
        if outstanding is not None:
            layout.addWidget(QLabel(f"Մնացած պարտք՝ {format_currency(outstanding)}"))
        layout.addWidget(self._amount)
        layout.addWidget(self._method)
        layout.addWidget(
            DialogButtonBar(
                [
                    CancelButton(on_click=self.reject),
                    SaveButton(on_click=self.accept),
                ]
            )
        )

    def result_value(self) -> tuple[Decimal, PaymentMethod] | None:
        amount = self._amount.decimal_value()
        if amount is None:
            warn(self, "Գումարը պետք է լինի թիվ։")
            return None
        return amount, self._method.currentData()
