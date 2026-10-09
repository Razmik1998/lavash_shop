"""Supplier list filters, totals, and selection actions."""

from decimal import Decimal
from uuid import uuid4

from services import SupplierRow, SupplierSummary
from ui.suppliers_window import SuppliersWindow


class Service:
    def list_summaries(self):
        return [
            SupplierSummary(
                SupplierRow(uuid4(), "Արև", "091123456", None, True),
                2,
                Decimal(1000),
                Decimal(400),
                Decimal(600),
                None,
            ),
            SupplierSummary(
                SupplierRow(uuid4(), "Արարատ", None, None, False),
                1,
                Decimal(500),
                Decimal(500),
                Decimal(0),
                None,
            ),
        ]


def test_supplier_filters_update_totals_and_clear_hidden_selection(qtbot):
    window = SuppliersWindow(Service())
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window._model.rowCount() == 2)
    assert window._summary_cards[1].value_label.text() == "1'500 ֏"
    window._table.selectRow(1)
    assert window._supplier_actions[4].isEnabled()
    assert not window._supplier_actions[3].isEnabled()
    window._status_filter.setCurrentIndex(window._status_filter.findData("active"))
    assert window._table.isRowHidden(1)
    assert window._summary_cards[1].value_label.text() == "1'000 ֏"
    assert not window._supplier_actions[2].isEnabled()
    window._table.selectRow(0)
    assert window._supplier_actions[3].isEnabled()
    assert not window._supplier_actions[4].isEnabled()
    window._filter.setText("091")
    assert not window._table.isRowHidden(0)
    window._filter.setText("missing")
    assert window._summary_cards[0].value_label.text() == "0"
    assert not window._supplier_actions[2].isEnabled()
    assert "չեն գտնվել" in window._list_message.text()
