"""Report filter boundaries and asynchronous result consistency."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from PySide6.QtCore import QDate

from services import SupplierReportRow
from ui.components import DatePeriodFilter, RefreshButton, SearchButton
from ui.supplier_report_window import SupplierReportWindow


class Suppliers:
    def list_suppliers(self):
        return []


class Reports:
    def supplier_report(self, filters):
        return []


def test_quick_periods_cover_one_business_day(qtbot):
    period = DatePeriodFilter(business_timezone="Asia/Yerevan")
    qtbot.addWidget(period)
    period.set_period("today")
    today, today_end = period.values()
    period.set_period("tomorrow")
    tomorrow, tomorrow_end = period.values()
    assert tomorrow == today_end
    assert tomorrow_end - tomorrow == timedelta(days=1)
    period.set_period("yesterday")
    yesterday, yesterday_end = period.values()
    assert yesterday_end == today
    assert yesterday_end - yesterday == timedelta(days=1)
    period.set_period("all")
    assert period.values() == (None, None)


def test_report_snapshots_filters_and_discards_old_results(qtbot, monkeypatch):
    pending = []
    monkeypatch.setattr(
        "ui.supplier_report_window.run_in_background",
        lambda owner, fn, success, failure: pending.append((fn, success, failure)),
    )
    window = SupplierReportWindow(Reports(), Suppliers())
    qtbot.addWidget(window)
    assert window._date_start() is None
    assert window._date_end() is None
    window._period.set_period("custom")
    window._from_date.setDate(QDate(2026, 10, 8))
    window._to_date.setDate(QDate(2026, 10, 8))
    assert window._date_start() == datetime(2026, 10, 7, 20, tzinfo=UTC)
    assert window._date_end() == datetime(2026, 10, 8, 20, tzinfo=UTC) - timedelta(
        microseconds=1
    )
    window.reload()
    row = SupplierReportRow(
        uuid4(), "Արև", 2, Decimal(5), Decimal(1250), Decimal(250), Decimal(1000)
    )
    pending[-1][1]([row])
    pending[0][1]([])
    assert window._model.rowCount() == 1
    assert window._cards[1].value_label.text() == "1'250 ֏"
    assert window._model.item(0, 6).text() == "08.10.2026 – 08.10.2026"
    window._from_date.setDate(QDate(2026, 10, 9))
    window.reload()
    assert len(pending) == 2
    assert "Սխալ" in window._status.text()


def test_shared_action_buttons_have_icons(qtbot):
    for button in (RefreshButton(), SearchButton()):
        qtbot.addWidget(button)
        assert not button.icon().isNull()
