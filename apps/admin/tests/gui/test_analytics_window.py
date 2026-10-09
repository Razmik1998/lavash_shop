from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from PySide6.QtWidgets import QWidget

from ui.analytics_window import AnalyticsWindow


class _AnalyticsService:
    def __init__(self, report: dict[str, Any]) -> None:
        self._report = report
        self.periods: list[str] = []

    def report(self, period: str) -> dict[str, Any]:
        self.periods.append(period)
        return self._report


def _report(
    *,
    revenue: Decimal = Decimal("15000"),
    revenue_change: Decimal | None = Decimal("12.5"),
    products: bool = True,
) -> dict[str, Any]:
    return {
        "revenue": revenue,
        "orders": 6 if revenue else 0,
        "average_order": Decimal("2500") if revenue else Decimal("0"),
        "estimated_profit": Decimal("4200") if revenue else Decimal("0"),
        "cost_coverage": Decimal("12000") if revenue else Decimal("0"),
        "revenue_change": revenue_change,
        "daily": [(date(2026, 10, 6), revenue)],
        "weekdays": [
            (index, revenue if index == 1 else Decimal("0")) for index in range(7)
        ],
        "hourly": [
            (hour, Decimal("3") if hour == 14 and revenue else Decimal("0"))
            for hour in range(24)
        ],
        "top_products": (
            [
                {
                    "name": "Սուրճ",
                    "orders": 4,
                    "quantity": Decimal("6"),
                    "unit": "հատ",
                    "peak_hour": 14,
                }
            ]
            if products
            else []
        ),
        "revenue_products": [],
        "profit_products": [],
        "peak_hour": 14 if revenue else None,
        "peak_weekday": 1 if revenue else None,
    }


def test_analytics_dashboard_shows_kpis_comparison_and_product_rows(qtbot: Any) -> None:
    service = _AnalyticsService(_report())
    window = AnalyticsWindow(service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(
        lambda: window._revenue.value_label.text() == "15'000 ֏", timeout=2000
    )

    assert window._orders.value_label.text() == "6"
    assert window._average.value_label.text() == "2'500 ֏"
    assert window._profit.value_label.text() == "4'200 ֏"
    assert window._change_badge.text() == "●  ↑ 12.5%"
    assert window._top_table.item_model.item(0, 0).text() == "Սուրճ"
    assert "Ամենաակտիվ ժամը՝ 14:00–15:00" in window._insight.text()
    hour_chart = window._hour_bars.findChild(QWidget, "barChartPlot")
    assert hour_chart is not None
    assert "14:00: 3 պատվեր" in hour_chart.accessibleName()


def test_analytics_dashboard_has_clear_empty_and_no_comparison_states(
    qtbot: Any,
) -> None:
    service = _AnalyticsService(
        _report(
            revenue=Decimal("0"),
            revenue_change=None,
            products=False,
        )
    )
    window = AnalyticsWindow(service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window._empty_products.isVisible(), timeout=2000)

    assert window._revenue.value_label.text() == "0 ֏"
    assert window._change_badge.text() == "●  Համեմատություն չկա"
    daily_chart = window._daily_bars.findChild(QWidget, "barChartPlot")
    assert daily_chart is not None
    assert daily_chart.accessibleName() == "Տվյալներ չկան"
    assert window._insight.text() == (
        "Ընտրված ժամանակահատվածում ավարտված վաճառքներ չկան։"
    )
