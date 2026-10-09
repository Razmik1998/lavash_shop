from datetime import date
from decimal import Decimal

from services.reports import ReportsService
from ui.reports_window import ReportsWindow


class EmptyReports:
    def daily(self, start, end, timezone):
        return []

    def balances(self):
        return {
            key: Decimal(0)
            for key in (
                "stock_cost",
                "stock_retail",
                "stock_missing_cost",
                "negative_stock",
                "customer_debt",
                "supplier_debt",
            )
        }


class FixedService(ReportsService):
    def today(self):
        return date(2026, 1, 31)


def test_reports_load_switch_categories_and_draw_chart(qtbot):
    window = ReportsWindow(FixedService(EmptyReports()))
    qtbot.addWidget(window)
    window.resize(1200, 900)
    window.show()
    qtbot.waitUntil(lambda: window._report is not None)
    assert window._metrics.item_model.rowCount() == 4
    assert window._balances.item_model.rowCount() == 4
    window._category.setCurrentIndex(1)
    window._grouping.setCurrentIndex(1)
    assert len(window._chart._labels) == 1
    window._chart.grab()
    window._start.setDate(window._end.date().addDays(1))
    window.refresh()
    qtbot.waitUntil(lambda: "Չհաջողվեց" in window._status.text())
    assert window._metrics.item_model.rowCount() == 0


def test_visualizations_handle_signed_values_unknown_profit_and_failure(qtbot):
    window = ReportsWindow(FixedService(EmptyReports()))
    qtbot.addWidget(window)
    window.resize(1200, 900)
    window.show()
    qtbot.waitUntil(lambda: window._report is not None)
    report = window._report
    report["current"].update(
        revenue=Decimal(100), cost=Decimal(60), waste=Decimal(5), profit=Decimal(35)
    )
    report["balances"]["customer_debt"] = Decimal(-20)
    window._render()
    assert len(window._composition.items) == 3
    assert window._balance_chart.items[2][1] == -20
    for chart in (window._composition, window._comparison, window._balance_chart):
        assert not chart.grab().isNull()
    report["current"]["profit"] = None
    window._render()
    assert window._composition.items == []
    assert window._comparison.items[3][1] is None
    window._failed(window._generation, ValueError("Invalid range"))
    assert all(
        not chart.items
        for chart in (window._composition, window._comparison, window._balance_chart)
    )


def test_trend_axis_legend_and_hover_stay_readable(qtbot):
    from PySide6.QtCore import QPoint

    from ui.components.line_chart import LineChart

    chart = LineChart()
    qtbot.addWidget(chart)
    chart.resize(650, 420)
    chart.show()
    labels = [f"{i:02d}.09 / {i:02d}.08" for i in range(1, 31)]
    chart.set_series(
        labels,
        [
            ("Ընտրված ժամանակահատված", [0] * 29 + [159130]),
            ("Նախորդ նույն տևողությունը", [-5000] * 30),
        ],
    )
    qtbot.waitUntil(lambda: chart._legend.height() > 0)
    assert chart._legend.isVisible()
    assert chart._plot().top() > chart._legend.geometry().bottom()
    low, high, step = chart._scale()
    assert low <= -5000 and high >= 159130
    assert step == 50000
    indices = chart._tick_indices()
    assert indices[0] == 0 and indices[-1] == 29
    assert len(indices) < 10
    point = chart._point(29, 159130).toPoint()
    qtbot.mouseMove(chart, point)
    assert chart._hover == 29
    qtbot.mouseMove(chart, QPoint(2, 2))
    assert chart._hover is None
    assert not chart.grab().isNull()
    chart.set_series(["01.09"], [("Ընտրված", [0])])
    assert chart._point(0, 0).x() == chart._plot().center().x()
    assert chart._tick(0.25, 0.25) == "0.25"
    assert not chart.grab().isNull()
