from decimal import Decimal

import pytest
from PySide6.QtWidgets import QDialog, QWidget

from ui.components.cash_withdrawal_dialog import CashWithdrawalDialog


@pytest.mark.parametrize("amount", ["", "0", "-1", "NaN", "Infinity", "1.001", "abc"])
def test_invalid_amount_stays_in_form(qtbot, amount):
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = CashWithdrawalDialog([{"name": "Andranik", "id": "recipient-1"}], parent)
    qtbot.addWidget(dialog)
    dialog.amount.setText(amount)
    dialog.reason.setPlainText("Office expenses")
    dialog._validate()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error.text()


def test_requires_reason_then_accepts_all_fields(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = CashWithdrawalDialog(
        [{"name": "Same name", "id": "one"}, {"name": "Same name", "id": "two"}],
        parent,
    )
    qtbot.addWidget(dialog)
    dialog.recipient.setCurrentIndex(1)
    dialog.amount.setText("1500.50")
    dialog._validate()
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.reason.setPlainText("  Office expenses  ")
    dialog._validate()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.values() == ("two", Decimal("1500.50"), "Office expenses")
