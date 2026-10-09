"""Sales analytics dashboard."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ui.components import (
    BarChart,
    CardScrollArea,
    DataTable,
    FormField,
    PageHeader,
    PageSubtitle,
    Panel,
    RefreshButton,
    SectionHeading,
    SelectField,
    StatCard,
    StatusBadge,
)
from ui.style import configure_page_layout, format_currency, format_quantity
from ui.workers import run_in_background, wait_for_pending_threads


class AnalyticsReportService(Protocol):
    def report(self, period: str) -> dict[str, Any]: ...


class AnalyticsWindow(QWidget):
    _WEEKDAY_NAMES = ("Երկ", "Երք", "Չրք", "Հնգ", "Ուրբ", "Շբթ", "Կիր")

    def __init__(self, analytics_service: AnalyticsReportService) -> None:
        super().__init__()
        self._service = analytics_service
        self._request_generation = 0
        self._period = SelectField(
            [
                ("Այսօր", "daily"),
                ("Վերջին 7 օրը", "weekly"),
                ("Վերջին 30 օրը", "monthly"),
            ],
            on_change=self.refresh,
        )
        self._page = CardScrollArea()
        layout = self._page.body
        configure_page_layout(layout)
        heading = QHBoxLayout()
        heading.addWidget(
            PageHeader(
                "Վաճառքի վերլուծություն",
                "Հասույթ, պատվերներ և ապրանքների արդյունավետություն՝ "
                "ըստ ընտրված ժամանակահատվածի։",
            ),
            1,
        )
        heading.addWidget(FormField("Ժամանակահատված", self._period))
        heading.addWidget(RefreshButton("Թարմացնել", on_click=self.refresh))
        layout.addLayout(heading)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self._revenue = StatCard(
            "Ընդհանուր հասույթ", "—", "Ավարտված վաճառքներից", tone="primary"
        )
        self._orders = StatCard(
            "Ավարտված պատվերներ", "—", "Ընտրված ժամանակահատվածում", tone="info"
        )
        self._average = StatCard(
            "Միջին պատվեր", "—", "Մեկ պատվերի հաշվով", tone="success"
        )
        self._profit = StatCard(
            "Մոտավոր շահույթ", "—", "Հաշվարկվում է հայտնի ինքնարժեքով", tone="warning"
        )
        for card in (self._revenue, self._orders, self._average, self._profit):
            cards.addWidget(card)
        layout.addLayout(cards)

        comparison = Panel()
        comparison.setObjectName("analyticsComparison")
        comparison_layout = QHBoxLayout(comparison)
        comparison_layout.setContentsMargins(16, 10, 16, 10)
        comparison_layout.setSpacing(12)
        comparison_text = QVBoxLayout()
        comparison_text.setSpacing(2)
        comparison_text.addWidget(SectionHeading("Հասույթի փոփոխություն"))
        self._change = PageSubtitle("Նախորդ նույն ժամանակահատվածի համեմատ")
        comparison_text.addWidget(self._change)
        comparison_layout.addLayout(comparison_text, stretch=1)
        self._change_badge = StatusBadge("Հաշվարկվում է", tone="info")
        comparison_layout.addWidget(self._change_badge)
        layout.addWidget(comparison)

        layout.addWidget(SectionHeading("Վաճառքի դինամիկա"))
        self._daily_bars = BarChart("Հասույթ ըստ օրվա")
        self._weekday_bars = BarChart("Հասույթ ըստ շաբաթվա օրվա")
        self._hour_bars = BarChart("Պատվերներ ըստ ժամի")
        layout.addWidget(self._daily_bars)
        charts = QHBoxLayout()
        charts.setSpacing(12)
        charts.addWidget(self._weekday_bars, stretch=1)
        charts.addWidget(self._hour_bars, stretch=1)
        layout.addLayout(charts)

        layout.addWidget(SectionHeading("Հիմնական եզրակացություններ"))
        insights = QHBoxLayout()
        insights.setSpacing(12)
        self._peak_hour_card = StatCard("Ամենաակտիվ ժամ", "—", "", tone="info")
        self._peak_day_card = StatCard("Լավագույն օր", "—", "", tone="success")
        self._margin_card = StatCard("Շահույթի մարժա", "—", "", tone="warning")
        self._previous_card = StatCard("Նախորդ ժամանակահատված", "—", "", tone="primary")
        for card in (
            self._peak_hour_card,
            self._peak_day_card,
            self._margin_card,
            self._previous_card,
        ):
            insights.addWidget(card)
        layout.addLayout(insights)

        layout.addWidget(SectionHeading("Ապրանքների արդյունավետություն"))
        self._top_table = DataTable(["Ապրանք", "Պատվերներ", "Քանակ", "Ակտիվ ժամ"])
        self._revenue_table = DataTable(["Ապրանք", "Քանակ", "Հասույթ", "Ակտիվ ժամ"])
        self._profit_table = DataTable(
            ["Ապրանք", "Հասույթ", "Մոտավոր շահույթ", "Ակտիվ ժամ"]
        )
        layout.addWidget(self._table_panel("Ամենապահանջված ապրանքներ", self._top_table))
        layout.addWidget(self._table_panel("Հասույթի առաջատարներ", self._revenue_table))
        layout.addWidget(self._table_panel("Շահույթի առաջատարներ", self._profit_table))

        self._empty_products = PageSubtitle(
            "Այս ժամանակահատվածում ապրանքների տվյալներ չկան։"
        )
        self._empty_products.setObjectName("analyticsEmptyState")
        self._empty_products.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_products.hide()
        layout.addWidget(self._empty_products)

        self._insight = PageSubtitle()
        self._insight.setObjectName("analyticsInsight")
        layout.addWidget(self._insight)
        layout.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._page)
        self.refresh()

    @staticmethod
    def _table_panel(title: str, table: DataTable) -> Panel:
        panel = Panel()
        panel.setObjectName("analyticsTablePanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 14, 14, 14)
        panel_layout.setSpacing(10)
        panel_layout.addWidget(SectionHeading(title))
        panel_layout.addWidget(table)
        return panel

    @staticmethod
    def _fit_height(table: DataTable) -> None:
        rows = max(table.item_model.rowCount(), 1)
        table.setFixedHeight(
            table.horizontalHeader().height()
            + table.verticalHeader().defaultSectionSize() * rows
            + 8
        )

    def refresh(self) -> None:
        period = self._period.currentData()
        self._request_generation += 1
        generation = self._request_generation
        self._change.setText("Նախորդ նույն ժամանակահատվածի համեմատ")
        self._change_badge.set_status("Թարմացվում է", tone="info")
        run_in_background(
            self,
            lambda: self._service.report(str(period)),
            lambda report: self._render_if_current(generation, report),
            lambda exc: self._failed_if_current(generation, exc),
        )

    def _render_if_current(self, generation: int, report: dict[str, Any]) -> None:
        if generation == self._request_generation:
            self._render(report)

    def _failed_if_current(self, generation: int, error: Exception) -> None:
        if generation != self._request_generation:
            return
        self._change.setText(f"Չհաջողվեց թարմացնել վերլուծությունը․ {error}")
        self._change_badge.set_status("Սխալ", tone="danger")

    def _render(self, report: dict[str, Any]) -> None:
        revenue = Decimal(report["revenue"])
        orders = int(report["orders"])
        self._revenue.set_value(format_currency(revenue))
        self._orders.set_value(format_quantity(orders))
        self._average.set_value(format_currency(Decimal(report["average_order"])))
        self._profit.set_value(
            format_currency(Decimal(report["estimated_profit"])),
            (
                "Հասանելի ինքնարժեքով վաճառքների գնահատում"
                if Decimal(report["cost_coverage"]) < revenue
                else "Հաշվարկված է ապրանքների ինքնարժեքով"
            ),
        )
        change = report["revenue_change"]
        self._set_comparison(change)
        self._daily_bars.set_items(
            [
                (day.strftime("%d.%m"), amount, format_currency(amount))
                for day, amount in report["daily"]
            ]
        )
        self._weekday_bars.set_items(
            [
                (self._WEEKDAY_NAMES[index], amount, format_currency(amount))
                for index, amount in report["weekdays"]
            ]
        )
        self._hour_bars.set_items(
            [
                (f"{hour:02d}:00", amount, f"{int(amount)} պատվեր")
                for hour, amount in report["hourly"]
            ]
        )
        self._top_table.clear_rows()
        for product in report["top_products"]:
            self._top_table.append_row(
                [
                    str(product["name"]),
                    str(product["orders"]),
                    f"{format_quantity(Decimal(product['quantity']))} "
                    f"{product['unit']}",
                    self._peak_hour_text(product["peak_hour"]),
                ]
            )
        self._fill_table(self._revenue_table, report["revenue_products"])
        self._profit_table.clear_rows()
        for product in report["profit_products"]:
            self._profit_table.append_row(
                [
                    str(product["name"]),
                    format_currency(Decimal(product["revenue"])),
                    format_currency(Decimal(product["profit"])),
                    self._peak_hour_text(product["peak_hour"]),
                ]
            )
        for table in (self._top_table, self._revenue_table, self._profit_table):
            self._fit_height(table)
        self._render_insights(report, revenue)
        has_products = any(
            report[key]
            for key in ("top_products", "revenue_products", "profit_products")
        )
        self._empty_products.setVisible(not has_products)
        peak_hour = report["peak_hour"]
        peak_weekday = report["peak_weekday"]
        parts = []
        if peak_hour is not None:
            parts.append(
                f"Ամենաակտիվ ժամը՝ {int(peak_hour):02d}:00–{int(peak_hour) + 1:02d}:00"
            )
        if peak_weekday is not None:
            parts.append(
                f"Շաբաթվա ամենաբարձր հասույթը՝ {self._WEEKDAY_NAMES[int(peak_weekday)]}"
            )
        if Decimal(report["cost_coverage"]) < revenue:
            parts.append(
                "Շահույթի գնահատումը ներառում է միայն ինքնարժեք ունեցող վաճառքի տողերը։"
            )
        self._insight.setText(
            " · ".join(parts)
            if parts
            else "Ընտրված ժամանակահատվածում ավարտված վաճառքներ չկան։"
        )

    def _render_insights(self, report: dict[str, Any], revenue: Decimal) -> None:
        peak_hour = report["peak_hour"]
        peak_weekday = report["peak_weekday"]
        self._peak_hour_card.set_value(
            "—" if peak_hour is None else self._peak_hour_text(int(peak_hour)),
            "Ամենաշատ պատվերները",
        )
        self._peak_day_card.set_value(
            "—" if peak_weekday is None else self._WEEKDAY_NAMES[int(peak_weekday)],
            "Շաբաթվա ամենաբարձր հասույթը",
        )
        coverage = Decimal(report["cost_coverage"])
        profit = Decimal(report["estimated_profit"])
        self._margin_card.set_value(
            f"{profit / coverage * 100:.1f}%" if coverage > 0 else "—",
            "Հայտնի ինքնարժեքով վաճառքների մեջ",
        )
        previous = report.get("previous_revenue")
        self._previous_card.set_value(
            "—" if previous is None else format_currency(Decimal(previous)),
            "Նախորդ նույն ժամանակահատվածի հասույթ",
        )

    def _set_comparison(self, change: Decimal | None) -> None:
        if change is None:
            self._change.setText(
                "Համեմատության համար նախորդ ժամանակահատվածի տվյալներ չկան։"
            )
            self._change_badge.set_status("Համեմատություն չկա", tone="info")
            return
        if change > 0:
            self._change_badge.set_status(f"↑ {change:.1f}%", tone="success")
        elif change < 0:
            self._change_badge.set_status(f"↓ {abs(change):.1f}%", tone="warning")
        else:
            self._change_badge.set_status("— 0.0%", tone="info")
        self._change.setText("Հասույթը՝ նախորդ նույն ժամանակահատվածի համեմատ")

    def _fill_table(self, table: DataTable, products: list[dict[str, Any]]) -> None:
        table.clear_rows()
        for product in products:
            table.append_row(
                [
                    str(product["name"]),
                    f"{format_quantity(Decimal(product['quantity']))} "
                    f"{product['unit']}",
                    format_currency(Decimal(product["revenue"])),
                    self._peak_hour_text(product["peak_hour"]),
                ]
            )

    @staticmethod
    def _peak_hour_text(hour: int | None) -> str:
        return "—" if hour is None else f"{hour:02d}:00–{hour + 1:02d}:00"

    def closeEvent(self, event: Any) -> None:
        wait_for_pending_threads(self)
        super().closeEvent(event)
