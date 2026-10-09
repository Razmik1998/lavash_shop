"""Input components: every field a screen needs, already styled."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from networking.protocol import ProductPayload


class TextField(QLineEdit):
    def __init__(
        self,
        placeholder: str = "",
        *,
        text: str = "",
        password: bool = False,
        on_submit: Callable[[], object] | None = None,
        on_changed: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        if password:
            self.setEchoMode(QLineEdit.EchoMode.Password)
        if on_submit is not None:
            self.returnPressed.connect(lambda: on_submit())
        if on_changed is not None:
            self.textChanged.connect(lambda _text: on_changed())

    def value(self) -> str:
        return self.text().strip()


class SearchField(TextField):
    def __init__(
        self,
        placeholder: str = "Որոնել",
        *,
        on_submit: Callable[[], object] | None = None,
        on_changed: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            placeholder, on_submit=on_submit, on_changed=on_changed, parent=parent
        )


class TextArea(QPlainTextEdit):
    """A multi-line text field for required reasons and free-form notes."""

    def __init__(
        self,
        placeholder: str = "",
        *,
        text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setMinimumHeight(90)

    def value(self) -> str:
        return self.toPlainText().strip()


class AmountField(TextField):
    """A numeric field that parses to ``Decimal`` or ``None``."""

    def decimal_value(self) -> Decimal | None:
        raw = self.text().strip()
        if not raw:
            return None
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None


class MoneyField(AmountField):
    """A prominent cash field accepting digits and thousands separators."""

    def __init__(
        self,
        placeholder: str = "Գումար",
        *,
        text: str = "",
        on_changed: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            placeholder, text=text, on_changed=on_changed, parent=parent
        )
        self.setObjectName("moneyField")
        self.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"[0-9, ]*"), self)
        )
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setMinimumHeight(42)

    def decimal_value(self) -> Decimal | None:
        raw = self.text().strip().replace(",", "").replace(" ", "")
        if not raw:
            return None
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None


class QuantityDialog(QDialog):
    """Ask for a sale quantity while showing the product's unit."""

    def __init__(
        self,
        unit_label: str,
        *,
        product_name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Մուտքագրել քանակ")
        self._quantity = AmountField(text="1")
        product_field = QLineEdit(product_name)
        product_field.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Ապրանք", product_field)
        form.addRow(f"Քանակ ({unit_label})", self._quantity)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        QTimer.singleShot(0, self._focus_quantity)

    def _focus_quantity(self) -> None:
        self._quantity.setFocus()
        self._quantity.selectAll()

    def _accept_if_valid(self) -> None:
        quantity = self._quantity.decimal_value()
        if quantity is not None and quantity > 0:
            self.accept()

    def quantity(self) -> Decimal | None:
        return self._quantity.decimal_value()


class ChildProductSelectionDialog(QDialog):
    """Collect integer quantities for the active children of a parent product."""

    _STYLE = """
        QDialog#barbecueSelectionDialog {
            background-color: #0c3a33;
            color: #ffffff;
            border: 1px solid #2a766a;
        }
        QFrame#headerFrame, QFrame#footerFrame {
            background-color: #0c3a33;
            border: none;
        }
        QFrame#headerFrame {
            border-bottom: 1px solid #2a766a;
        }
        QFrame#footerFrame {
            border-top: 1px solid #2a766a;
        }
        QLabel#productIcon {
            color: #ffcc00;
            font-size: 24px;
        }
        QLabel#dialogTitle, QLabel#dialogSubtitle, QLabel#productName,
        QLabel#quantityLabel, QLabel#emptyState {
            color: #ffffff;
        }
        QLabel#dialogTitle {
            font-size: 22px;
            font-weight: 700;
        }
        QLabel#dialogSubtitle {
            color: #c5ded9;
            font-size: 13px;
        }
        QLabel#productName {
            font-size: 16px;
            font-weight: 600;
        }
        QLabel#quantityLabel {
            font-size: 18px;
            font-weight: 700;
        }
        QLabel#emptyState {
            font-size: 16px;
        }
        QFrame#productRow {
            background-color: #114e45;
            border: 1px solid #1f6c61;
            border-radius: 10px;
        }
        QFrame#productRow[selected="true"] {
            background-color: #176357;
            border: 1px solid #ffcc00;
        }
        QFrame#quantityControls {
            background-color: #0f493f;
            border: 1px solid #216d62;
            border-radius: 9px;
        }
        QPushButton#quantityButton, QPushButton#closeButton,
        QPushButton#cancelButton, QPushButton#okButton {
            color: #ffffff;
            border-radius: 8px;
            font-weight: 700;
        }
        QPushButton#quantityButton {
            background-color: #186055;
            border: 1px solid #2a766a;
            font-size: 19px;
        }
        QPushButton#quantityButton:hover {
            background-color: #23786b;
        }
        QPushButton#quantityButton:pressed {
            background-color: #2d8d7d;
        }
        QPushButton#quantityButton:disabled {
            background-color: #123f38;
            color: #678b84;
            border-color: #1b5149;
        }
        QPushButton#closeButton {
            background-color: transparent;
            border: none;
            font-size: 24px;
            font-weight: 400;
        }
        QPushButton#closeButton:hover {
            background-color: #1b5a50;
        }
        QPushButton#cancelButton {
            background-color: #155047;
            border: 1px solid #2a766a;
            padding: 9px 20px;
        }
        QPushButton#cancelButton:hover {
            background-color: #216d62;
        }
        QPushButton#okButton {
            background-color: #ffcc00;
            color: #0c3a33;
            border: 1px solid #ffcc00;
            padding: 9px 28px;
        }
        QPushButton#okButton:hover {
            background-color: #e6b800;
        }
        QPushButton#okButton:pressed {
            background-color: #cca300;
        }
        QScrollArea#productsScrollArea {
            background-color: #0c3a33;
            border: none;
        }
        QWidget#productsContainer {
            background-color: #0c3a33;
        }
    """

    def __init__(
        self,
        parent_product_name: str,
        children: Sequence[ProductPayload],
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("barbecueSelectionDialog")
        self.setWindowTitle("Խորոված")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )
        self.setModal(True)
        self.setMinimumSize(520, 420)
        self.resize(560, 480)
        self.setStyleSheet(self._STYLE)
        self._quantities = {child.id: 0 for child in children}
        self._quantity_labels: dict[str, QLabel] = {}
        self._decrement_buttons: dict[str, QPushButton] = {}
        self._rows: dict[str, QFrame] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 18, 16)
        header_layout.setSpacing(12)
        icon = QLabel("🔥")
        icon.setObjectName("productIcon")
        header_layout.addWidget(icon)
        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        title = QLabel(parent_product_name)
        title.setObjectName("dialogTitle")
        subtitle = QLabel("Ընտրեք ապրանքներն ու քանակները")
        subtitle.setObjectName("dialogSubtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        close_button = QPushButton("×")
        close_button.setObjectName("closeButton")
        close_button.setFixedSize(40, 40)
        close_button.setToolTip("Close")
        close_button.clicked.connect(self.reject)
        header_layout.addWidget(close_button)
        layout.addWidget(header)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("productsScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        container.setObjectName("productsContainer")
        products_layout = QVBoxLayout(container)
        products_layout.setContentsMargins(22, 20, 22, 20)
        products_layout.setSpacing(12)

        for child in children:
            row = QFrame()
            row.setObjectName("productRow")
            row.setMinimumHeight(64)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(16, 10, 14, 10)
            row_layout.setSpacing(12)
            child_name = f"{parent_product_name} -> {child.name}"
            name = QLabel(child_name)
            name.setObjectName("productName")
            name.setWordWrap(True)
            name.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            row_layout.addWidget(name, 1)

            controls = QFrame()
            controls.setObjectName("quantityControls")
            controls_layout = QHBoxLayout(controls)
            controls_layout.setContentsMargins(4, 4, 4, 4)
            controls_layout.setSpacing(6)
            decrement = QPushButton("−")
            decrement.setObjectName("quantityButton")
            decrement.setFixedSize(42, 42)
            decrement.setEnabled(False)
            decrement.clicked.connect(
                lambda _checked=False, child_id=child.id: self._change_quantity(
                    child_id, -1
                )
            )
            quantity = QLabel("0")
            quantity.setObjectName("quantityLabel")
            quantity.setMinimumWidth(36)
            quantity.setAlignment(Qt.AlignmentFlag.AlignCenter)
            increment = QPushButton("+")
            increment.setObjectName("quantityButton")
            increment.setFixedSize(42, 42)
            increment.clicked.connect(
                lambda _checked=False, child_id=child.id: self._change_quantity(
                    child_id, 1
                )
            )
            controls_layout.addWidget(decrement)
            controls_layout.addWidget(quantity)
            controls_layout.addWidget(increment)
            row_layout.addWidget(controls)
            products_layout.addWidget(row)
            self._quantity_labels[child.id] = quantity
            self._decrement_buttons[child.id] = decrement
            self._rows[child.id] = row

        if not children:
            empty_state = QLabel("No products available")
            empty_state.setObjectName("emptyState")
            empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
            products_layout.addStretch()
            products_layout.addWidget(empty_state)
            products_layout.addStretch()
        else:
            products_layout.addStretch()
        scroll_area.setWidget(container)
        layout.addWidget(scroll_area, 1)

        footer = QFrame()
        footer.setObjectName("footerFrame")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(22, 14, 22, 16)
        footer_layout.addStretch()
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("cancelButton")
        cancel_button.setMinimumSize(110, 44)
        cancel_button.clicked.connect(self.reject)
        ok_button = QPushButton("OK")
        ok_button.setObjectName("okButton")
        ok_button.setMinimumSize(120, 44)
        ok_button.setDefault(True)
        ok_button.clicked.connect(self.accept)
        footer_layout.addWidget(cancel_button)
        footer_layout.addWidget(ok_button)
        layout.addWidget(footer)

        self._cancel_button = cancel_button
        self._ok_button = ok_button
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self) -> None:
        if self.parentWidget() is None:
            return
        parent_center = self.parentWidget().mapToGlobal(
            self.parentWidget().rect().center()
        )
        self.move(parent_center - self.rect().center())

    def _change_quantity(self, child_id: str, delta: int) -> None:
        quantity = max(0, self._quantities[child_id] + delta)
        self._quantities[child_id] = quantity
        self._quantity_labels[child_id].setText(str(quantity))
        self._decrement_buttons[child_id].setEnabled(quantity > 0)
        row = self._rows[child_id]
        row.setProperty("selected", quantity > 0)
        style = row.style()
        style.unpolish(row)
        style.polish(row)

    def selected_children(
        self, children: Sequence[ProductPayload]
    ) -> list[tuple[ProductPayload, Decimal]]:
        return [
            (child, Decimal(quantity))
            for child in children
            if (quantity := self._quantities[child.id]) >= 1
        ]


class SelectField(QComboBox):
    def __init__(
        self,
        options: Sequence[tuple[str, object]] = (),
        *,
        on_change: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        for label, value in options:
            self.addItem(label, value)
        if on_change is not None:
            self.currentIndexChanged.connect(lambda _index: on_change())

    def set_options(self, options: Sequence[tuple[str, object]]) -> None:
        self.clear()
        for label, value in options:
            self.addItem(label, value)
