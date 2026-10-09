from __future__ import annotations

from decimal import Decimal

from pytestqt.qtbot import QtBot

from ui.components.discount_dialog import DiscountDialog


def _dialog(qtbot: QtBot, current: Decimal | None = None) -> DiscountDialog:
    dialog = DiscountDialog("Cola", Decimal("1000"), Decimal("800"), current)
    qtbot.addWidget(dialog)
    return dialog


def test_defaults_to_selling_price(qtbot: QtBot) -> None:
    assert _dialog(qtbot).price() == Decimal("1000")


def test_slider_minimum_gives_minimum_price(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)
    dialog._slider.setValue(0)
    assert dialog.price() == Decimal("800")


def test_typed_price_in_range_is_accepted(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)
    dialog._price_field.setText("900")
    assert dialog.price() == Decimal("900")


def test_typed_price_out_of_range_blocks_apply(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot)
    dialog._price_field.setText("700")
    assert not dialog._save.isEnabled()
    assert dialog.price() == Decimal("1000")
