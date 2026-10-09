from __future__ import annotations

import uuid
from decimal import Decimal

from models import Product, Unit
from ui.product_form_dialog import ProductFormDialog


def test_product_form_values_parse_numbers_as_decimals(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = ProductFormDialog()
    qtbot.addWidget(dialog)

    dialog.name_edit.setText("Fresh Salmon")
    dialog.sku_edit.setText("SAL-001")
    dialog.barcode_edit.setText("99001")
    dialog.cost_edit.setText("7.25")
    dialog.selling_edit.setText("10.50")
    dialog.stock_edit.setText("1.250")
    dialog.threshold_edit.setText("0.500")

    values = dialog.values()

    assert values == (
        "Fresh Salmon",
        "SAL-001",
        "99001",
        Unit.PIECE,
        Decimal("7.25"),
        Decimal("10.50"),
        Decimal("10.50"),
        Decimal("1.250"),
        Decimal("0.500"),
        True,
        None,
        True,
    )
    assert isinstance(values[4], Decimal)
    assert isinstance(values[5], Decimal)
    assert isinstance(values[6], Decimal)
    assert isinstance(values[7], Decimal)
    assert isinstance(values[8], Decimal)


def test_internal_product_form_hides_sale_fields() -> None:
    dialog = ProductFormDialog()
    dialog.name_edit.setText("Cooking Oil")
    dialog.sku_edit.setText("OIL-001")
    dialog.cost_edit.setText("4.25")
    dialog.stock_edit.setText("3")
    dialog.for_sale_checkbox.setChecked(False)

    values = dialog.values()

    assert dialog.selling_edit.isHidden()
    assert dialog.minimum_price_edit.isHidden()
    assert values[4] == Decimal("4.25")
    assert values[5] is None
    assert values[6] is None
    assert values[7] == Decimal("3")
    assert values[-1] is False

    dialog.for_sale_checkbox.setChecked(True)
    assert not dialog.selling_edit.isHidden()
    assert not dialog.minimum_price_edit.isHidden()


def test_product_form_defaults_next_sku_from_latest_item() -> None:
    next_sku = ProductFormDialog.next_sku_from_last("SAL-010")
    assert next_sku == "11"

    dialog = ProductFormDialog(next_sku=next_sku)

    assert dialog.sku_edit.text() == "11"


def test_selecting_barbecue_parent_switches_new_item_to_child_unit(qtbot) -> None:  # type: ignore[no-untyped-def]
    barbecue_parent = Product(
        id=uuid.uuid4(),
        sku="BBQ-001",
        barcode=None,
        name="Sterlec",
        unit=Unit.BARBECUE,
        parent_product_id=None,
        cost_price=None,
        selling_price=None,
        quantity_in_stock=None,
        low_stock_threshold=None,
        is_active=True,
    )
    dialog = ProductFormDialog(parent_products=[barbecue_parent])
    qtbot.addWidget(dialog)

    barbecue_index = dialog.unit_combo.findData(Unit.BARBECUE)
    dialog.unit_combo.setCurrentIndex(barbecue_index)
    dialog.parent_combo.setCurrentIndex(1)
    dialog.selling_edit.setText("1000")
    dialog.stock_edit.setText("1")

    assert dialog.parent_combo.currentData() == barbecue_parent.id
    assert dialog.unit_combo.currentData() is Unit.KG
    assert dialog.values()[-2] == barbecue_parent.id
