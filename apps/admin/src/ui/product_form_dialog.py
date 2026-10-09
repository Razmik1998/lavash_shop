"""Shared add/edit form for products."""

from __future__ import annotations

import random
import uuid
from decimal import Decimal, InvalidOperation
from typing import cast

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models import Product, Unit
from ui.style import format_quantity

_UNIT_LABELS = {
    Unit.PIECE: "Հատ",
    Unit.KG: "Կգ",
    Unit.GRAM: "Գրամ",
    Unit.LITER: "Լիտր",
    Unit.BARBECUE: "Խորոված",
}


class ProductFormDialog(QDialog):
    def __init__(
        self,
        product: Product | None = None,
        parent: QWidget | None = None,
        next_sku: str | None = None,
        parent_products: list[Product] | None = None,
    ) -> None:
        super().__init__(parent)
        self._product = product
        self.setWindowTitle("Խմբագրել ապրանք" if product else "Ավելացնել ապրանք")

        self.name_edit = QLineEdit()
        self.sku_edit = QLineEdit()
        self.barcode_edit = QLineEdit()
        self.unit_combo = QComboBox()
        for unit, label in _UNIT_LABELS.items():
            self.unit_combo.addItem(label, unit)
        self.parent_combo = QComboBox()
        self.parent_combo.addItem("Չկա", None)
        for parent_product in parent_products or []:
            if parent_product.unit is Unit.BARBECUE and parent_product.is_active:
                self.parent_combo.addItem(
                    f"{parent_product.name} ({parent_product.sku})",
                    parent_product.id,
                )
        self.cost_edit = QLineEdit()
        self.selling_edit = QLineEdit()
        self.minimum_price_edit = QLineEdit()
        self.stock_edit = QLineEdit("0")
        self.threshold_edit = QLineEdit()
        self.active_checkbox = QCheckBox()
        self.active_checkbox.setChecked(True)
        self.for_sale_checkbox = QCheckBox()
        self.for_sale_checkbox.setChecked(
            product is None or product.is_for_sale is not False
        )
        self._price_fields = (
            self.cost_edit,
            self.selling_edit,
            self.minimum_price_edit,
            self.stock_edit,
            self.threshold_edit,
        )
        self._minimum_price_manually_changed = False
        self.selling_edit.textChanged.connect(self._selling_price_changed)
        self.minimum_price_edit.textChanged.connect(self._minimum_price_changed)
        self.for_sale_checkbox.toggled.connect(self._sync_sale_fields)

        self.unit_combo.currentIndexChanged.connect(self._sync_bundle_fields)
        self.parent_combo.currentIndexChanged.connect(self._parent_selection_changed)

        generate_button = QPushButton("Ստեղծել ինքնաշխատ")
        generate_button.clicked.connect(self._generate_sku)
        sku_widget = QWidget()
        sku_layout = QVBoxLayout(sku_widget)
        sku_layout.setContentsMargins(0, 0, 0, 0)
        sku_layout.addWidget(self.sku_edit)
        sku_layout.addWidget(generate_button)

        form = QFormLayout()
        form.addRow("Անուն:", self.name_edit)
        form.addRow("Կոդ (SKU):", sku_widget)
        form.addRow("Շտրիխ:", self.barcode_edit)
        form.addRow("Միավոր:", self.unit_combo)
        form.addRow("Խորովածի ծնող:", self.parent_combo)
        form.addRow("Ինքնարժեք:", self.cost_edit)
        form.addRow("Վաճառքի գին:", self.selling_edit)
        form.addRow("Նվազագույն գին:", self.minimum_price_edit)
        form.addRow("Պաշարի քանակ:", self.stock_edit)
        form.addRow("Նվազագույն պաշար:", self.threshold_edit)
        form.addRow("Հասանելի է վաճառքի համար:", self.for_sale_checkbox)
        form.addRow("Ակտիվ է:", self.active_checkbox)
        self._selling_label = form.labelForField(self.selling_edit)
        self._minimum_price_label = form.labelForField(self.minimum_price_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

        if product is not None:
            self._populate(product)
        elif next_sku is not None:
            self.sku_edit.setText(next_sku)
        self._sync_sale_fields()

    def _populate(self, product: Product) -> None:
        self.name_edit.setText(product.name)
        self.sku_edit.setText(product.sku)
        self.barcode_edit.setText(product.barcode or "")
        unit_index = self.unit_combo.findData(product.unit)
        if unit_index >= 0:
            self.unit_combo.setCurrentIndex(unit_index)
        self.cost_edit.setText(self._decimal_text(product.cost_price))
        self.selling_edit.setText(self._decimal_text(product.selling_price))
        self.minimum_price_edit.setText(self._decimal_text(product.minimum_price))
        self._minimum_price_manually_changed = True
        self.stock_edit.setText(self._decimal_text(product.quantity_in_stock))
        self.threshold_edit.setText(self._decimal_text(product.low_stock_threshold))
        self.active_checkbox.setChecked(product.is_active)
        self.for_sale_checkbox.setChecked(product.is_for_sale is not False)
        parent_index = self.parent_combo.findData(product.parent_product_id)
        if parent_index >= 0:
            self.parent_combo.setCurrentIndex(parent_index)
        self._sync_bundle_fields()

    def _sync_sale_fields(self) -> None:
        visible = self.for_sale_checkbox.isChecked()
        self.selling_edit.setVisible(visible)
        self.minimum_price_edit.setVisible(visible)
        if self._selling_label is not None:
            self._selling_label.setVisible(visible)
        if self._minimum_price_label is not None:
            self._minimum_price_label.setVisible(visible)

    def _sync_bundle_fields(self) -> None:
        is_bundle = self.unit_combo.currentData() is Unit.BARBECUE
        editing_parent = (
            self._product is not None
            and self._product.parent_product_id is None
            and is_bundle
        )
        self.parent_combo.setEnabled(not editing_parent)
        if editing_parent:
            self.parent_combo.setCurrentIndex(0)
        for field in self._price_fields:
            field.setEnabled(not is_bundle)
            if is_bundle:
                field.clear()

    def _selling_price_changed(self, value: str) -> None:
        if not self._minimum_price_manually_changed:
            self.minimum_price_edit.setText(value)

    def _minimum_price_changed(self, _value: str) -> None:
        if self.minimum_price_edit.hasFocus():
            self._minimum_price_manually_changed = True

    def _parent_selection_changed(self) -> None:
        if (
            self.parent_combo.currentData() is not None
            and self.unit_combo.currentData() is Unit.BARBECUE
        ):
            child_unit_index = self.unit_combo.findData(Unit.KG)
            if child_unit_index >= 0:
                self.unit_combo.setCurrentIndex(child_unit_index)

    @staticmethod
    def _decimal_text(value: Decimal | None) -> str:
        return format_quantity(value)

    def _generate_sku(self) -> None:
        current = self.sku_edit.text().strip()
        digits = "".join(ch for ch in current if ch.isdigit())
        if digits:
            next_number = int(digits) + 1
        else:
            next_number = random.randint(1, 999999)
        self.sku_edit.setText(str(next_number))

    @staticmethod
    def next_sku_from_last(last_sku: str | None) -> str | None:
        if last_sku is None or not last_sku.strip():
            return "1"
        digits = "".join(ch for ch in last_sku if ch.isdigit())
        if not digits:
            return "1"
        return str(int(digits) + 1)

    def _parse_decimal(
        self, edit: QLineEdit, label: str, optional: bool
    ) -> Decimal | None:
        value = edit.text().strip()
        if not value and optional:
            return None
        try:
            decimal_value = Decimal(value)
        except InvalidOperation:
            raise ValueError(f"{label} դաշտը պետք է լինի թիվ։") from None
        if not decimal_value.is_finite() or decimal_value < 0:
            raise ValueError(f"{label} դաշտը պետք է լինի ոչ բացասական թիվ։")
        return decimal_value

    def _validate_and_accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Սխալ", "Անունը պարտադիր է։")
            return
        if not self.sku_edit.text().strip():
            QMessageBox.warning(self, "Սխալ", "Կոդը պարտադիր է։")
            return

        unit = cast(Unit, self.unit_combo.currentData())
        if unit is Unit.BARBECUE:
            self.accept()
            return

        try:
            self._parse_decimal(self.cost_edit, "Ինքնարժեքը", True)
            if not self.for_sale_checkbox.isChecked():
                self._parse_decimal(self.stock_edit, "Պաշարի քանակը", False)
                self._parse_decimal(self.threshold_edit, "Նվազագույն պաշարը", True)
                self.accept()
                return
            selling_price = self._parse_decimal(
                self.selling_edit, "Վաճառքի գինը", False
            )
            minimum_price = self._parse_decimal(
                self.minimum_price_edit, "Նվազագույն գինը", False
            )
            if (
                selling_price is not None
                and minimum_price is not None
                and minimum_price > selling_price
            ):
                raise ValueError("Նվազագույն գինը չի կարող գերազանցել վաճառքի գինը։")
            self._parse_decimal(self.stock_edit, "Պաշարի քանակը", False)
            self._parse_decimal(self.threshold_edit, "Նվազขั้นต่ำ պաշարը", True)
        except ValueError as error:
            QMessageBox.warning(self, "Սխալ", str(error))
            return
        self.accept()

    def values(
        self,
    ) -> tuple[
        str,
        str,
        str | None,
        Unit,
        Decimal | None,
        Decimal | None,
        Decimal | None,
        Decimal | None,
        Decimal | None,
        bool,
        uuid.UUID | None,
        bool,
    ]:
        unit = cast(Unit, self.unit_combo.currentData())
        if unit is Unit.BARBECUE:
            return (
                self.name_edit.text().strip(),
                self.sku_edit.text().strip(),
                self.barcode_edit.text().strip() or None,
                unit,
                None,
                None,
                None,
                None,
                None,
                self.active_checkbox.isChecked(),
                None,
                self.for_sale_checkbox.isChecked(),
            )

        is_for_sale = self.for_sale_checkbox.isChecked()
        selling_price = (
            self._parse_decimal(self.selling_edit, "Վաճառքի գինը", False)
            if is_for_sale
            else None
        )
        minimum_price = (
            self._parse_decimal(self.minimum_price_edit, "Նվազագույն գինը", False)
            if is_for_sale
            else None
        )
        quantity_in_stock = self._parse_decimal(self.stock_edit, "Պաշարի քանակը", False)
        if is_for_sale and (selling_price is None or minimum_price is None):
            raise ValueError("Վաճառքի գինը պարտադիր է վաճառվող ապրանքի համար։")
        if (
            is_for_sale
            and minimum_price is not None
            and selling_price is not None
            and minimum_price > selling_price
        ):
            raise ValueError("Նվազագույն գինը չի կարող գերազանցել վաճառքի գինը։")
        assert quantity_in_stock is not None
        return (
            self.name_edit.text().strip(),
            self.sku_edit.text().strip(),
            self.barcode_edit.text().strip() or None,
            unit,
            self._parse_decimal(self.cost_edit, "Ինքնարժեքը", True),
            selling_price,
            minimum_price,
            quantity_in_stock,
            self._parse_decimal(self.threshold_edit, "Նվազագույն պաշարը", True),
            self.active_checkbox.isChecked(),
            cast(uuid.UUID | None, self.parent_combo.currentData()),
            is_for_sale,
        )


def unit_label(unit: Unit) -> str:
    return _UNIT_LABELS.get(unit, unit.value)
