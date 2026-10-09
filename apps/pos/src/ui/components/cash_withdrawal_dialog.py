"""Collect a cash withdrawal in one validated form."""

from decimal import Decimal

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.components.buttons import PrimaryButton, SecondaryButton
from ui.components.icons import pos_icon
from ui.components.inputs import AmountField, SelectField, TextArea


class CashWithdrawalDialog(QDialog):
    def __init__(self, recipients: list[dict[str, str]], parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("cashWithdrawalDialog")
        self.setWindowTitle("Գումար վերցնել")
        self.setModal(True)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        title = QLabel("Գումար վերցնել")
        title.setObjectName("screenTitle")
        layout.addWidget(title)
        subtitle = QLabel("Լրացրեք բոլոր դաշտերը և հաստատեք մեկ քայլով։")
        subtitle.setObjectName("screenSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        self.recipient = SelectField([(r["name"], r["id"]) for r in recipients])
        self.amount = AmountField("0.00")
        self.reason = TextArea("Նշեք գումարը վերցնելու պատճառը")
        self.reason.setMaximumHeight(130)
        for caption, field in (
            ("Անձ", self.recipient),
            ("Գումար (֏)", self.amount),
            ("Պատճառ", self.reason),
        ):
            label = QLabel(caption)
            label.setBuddy(field)
            layout.addWidget(label)
            layout.addWidget(field)
        self.error = QLabel()
        self.error.setObjectName("errorLabel")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(
            SecondaryButton("Չեղարկել", icon=pos_icon("close"), on_click=self.reject)
        )
        self.submit = PrimaryButton(
            "OK · Գրանցել",
            icon=pos_icon("check", "#0c3a33"),
            on_click=self._validate,
        )
        self.submit.setDefault(True)
        buttons.addWidget(self.submit)
        layout.addLayout(buttons)
        self.amount.setFocus()

    def _validate(self) -> None:
        value = self.amount.decimal_value()
        if (
            value is None
            or not value.is_finite()
            or value <= 0
            or value.as_tuple().exponent < -2
        ):
            self.error.setText(
                "Մուտքագրեք դրական գումար՝ առավելագույնը 2 տասնորդական նիշով։"
            )
            self.amount.setFocus()
            return
        if not self.reason.value():
            self.error.setText("Նշեք գումարը վերցնելու պատճառը։")
            self.reason.setFocus()
            return
        if self.recipient.currentData() is None:
            self.error.setText("Ընտրեք գումար վերցնող անձին։")
            return
        self.accept()

    def values(self) -> tuple[str, Decimal, str]:
        value = self.amount.decimal_value()
        assert value is not None
        return self.recipient.currentData(), value, self.reason.value()
