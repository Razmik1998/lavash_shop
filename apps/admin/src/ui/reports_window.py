"""Armenian business reports composed from the desktop component library."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from services.reports import ReportsService
from ui.components import (
    CardScrollArea,
    DataTable,
    DateField,
    FormField,
    PageHeader,
    PageSubtitle,
    RefreshButton,
    SectionHeading,
    SelectField,
    StatCard,
)
from ui.components.line_chart import LineChart
from ui.components.report_charts import PALETTE, ReportChart
from ui.style import configure_page_layout, format_currency
from ui.workers import run_in_background, wait_for_pending_threads

CATEGORIES = {
    "overview": [
        ("revenue", "Վաճառքի հասույթ"),
        ("cost", "Վաճառվածի ինքնարժեք"),
        ("waste", "Դուրսգրման կորուստ"),
        ("profit", "Շահույթ՝ դուրսգրումից հետո"),
    ],
    "cash": [
        ("received", "Ստացված գումար"),
        ("payments", "Մատակարարներին վճարված"),
        ("cash_flow", "Գրանցված դրամական հոսք"),
        ("repayments", "Հաճախորդների պարտքի մարում"),
    ],
    "purchases": [
        ("purchases", "Գնումների արժեք"),
        ("payments", "Մատակարարներին վճարված"),
        ("waste", "Դուրսգրման կորուստ"),
        ("free_sales", "Անվճար տրվածի հայտնի ինքնարժեք"),
    ],
    "credit": [
        ("credit", "Պարտքով վաճառք"),
        ("repayments", "Հաճախորդների պարտքի մարում"),
        ("revenue", "Վաճառքի հասույթ"),
        ("average_order", "Միջին վաճառք"),
    ],
}


class ReportsWindow(QWidget):
    def __init__(self, service: ReportsService) -> None:
        super().__init__()
        self._service = service
        self._generation = 0
        self._report: dict[str, Any] | None = None
        self.setObjectName("reportsDashboard")
        self.setStyleSheet("""
            QWidget#cardScrollBody { background: #f4f5fb; }
            QWidget#pageHeader {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #312e81, stop:0.6 #4f46e5, stop:1 #7c3aed);
                border-radius: 20px;
            }
            QWidget#pageHeader QLabel#pageTitle { color: white; font-size: 28px; }
            QWidget#pageHeader QLabel#pageSubtitle { color: #ddd6fe; }
            QFrame#reportPanel { background: white; border: 1px solid #e2e5f1;
                border-radius: 18px; }
            QLabel#sectionHeading { color: #312e81; font-size: 17px; }
            QLabel#pageSubtitle { color: #64748b; }
            QDateEdit { background: white; border: 1px solid #cbd5e1;
                border-radius: 9px; padding: 8px 12px; color: #1e293b; }
            QDateEdit::drop-down { width: 28px; border: none; }
            QComboBox { background: white; border: 1px solid #cbd5e1;
                border-radius: 9px; padding: 8px 12px; color: #1e293b; }
            QTableView { border: 1px solid #e2e5f1; border-radius: 14px;
                background: white; alternate-background-color: #f5f3ff; }
            QHeaderView::section { background: #eef2ff; color: #4338ca;
                border: none; padding: 12px; }
        """)
        arrow = (Path(__file__).parent / "assets" / "chevron-down.svg").as_posix()
        self.setStyleSheet(
            self.styleSheet()
            + f"""
            QDateEdit::down-arrow, QComboBox::down-arrow {{
                image: url("{arrow}"); width: 16px; height: 16px;
            }}
            QComboBox::drop-down {{ width: 28px; border: none; }}
        """
        )
        page = CardScrollArea()
        layout = page.body
        configure_page_layout(layout)
        header = PageHeader(
            "Հաշվետվություններ",
            "Բիզնեսի հասույթ, վճարումներ, պաշարներ և կորուստներ։",
        )
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header.layout().setContentsMargins(28, 22, 28, 24)
        for label in header.findChildren(PageSubtitle):
            label.setWordWrap(True)
        layout.addWidget(header)
        filters = QGridLayout()
        filters.setHorizontalSpacing(20)
        filters.setVerticalSpacing(16)
        self._period = SelectField(
            [
                ("Վերջին 30 օրը", 30),
                ("Այսօր", 1),
                ("Վերջին 7 օրը", 7),
                ("Վերջին 3 ամիսը", 90),
                ("Վերջին տարին", 365),
                ("Ընտրված օրեր", 0),
            ]
        )
        self._start, self._end = DateField(), DateField()
        for field in (self._start, self._end):
            field.setDisplayFormat("dd.MM.yyyy")
            field.setMinimumHeight(46)
        self._category = SelectField(
            [
                ("Ընդհանուր արդյունք", "overview"),
                ("Դրամական հոսքեր", "cash"),
                ("Գնումներ և կորուստներ", "purchases"),
                ("Վաճառք և պարտքեր", "credit"),
            ]
        )
        for index, (title, widget) in enumerate(
            (
                ("Բաժին", self._category),
                ("Ժամանակահատված", self._period),
                ("Սկիզբ", self._start),
                ("Ավարտ", self._end),
            )
        ):
            widget.setMinimumHeight(46)
            filters.addWidget(FormField(title, widget), index // 2, index % 2)
        refresh = RefreshButton("Հաշվարկել", on_click=self.refresh)
        refresh.setMinimumHeight(46)
        filters.addWidget(refresh, 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
        filters.setColumnStretch(0, 1)
        filters.setColumnStretch(1, 1)
        layout.addWidget(self._panel("Ժամանակահատված և բաժին", filters))
        self._status = PageSubtitle()
        layout.addWidget(self._status)
        cards = QGridLayout()
        self._cards = [StatCard("", "—", "") for _ in range(4)]
        for index, card in enumerate(self._cards):
            color = PALETTE[index]
            background = ("#eef2ff", "#fffbeb", "#fff1f2", "#ecfdf5")[index]
            card.setStyleSheet(
                f"QFrame#statCard {{ background: {background}; "
                f"border: 1px solid {color}; border-left: 5px solid {color}; "
                "border-radius: 16px; }"
                f"QLabel#statValue {{ color: {color}; font-size: 27px; }}"
                "QLabel#statDetail { color: #475569; font-size: 13px; }"
            )
            card.detail_label.setWordWrap(True)
            cards.addWidget(card, index // 2, index % 2)
        layout.addLayout(cards)
        self._metrics = DataTable(
            [
                "Ցուցանիշ",
                "Ընտրված ժամանակահատված",
                "Նախորդ նույն տևողությունը",
                "Փոփոխություն",
            ]
        )
        self._metrics.setMinimumHeight(220)

        chart_filters = QHBoxLayout()
        self._chart_metric = SelectField(
            [
                (title, key)
                for key, title in dict(
                    pair for entries in CATEGORIES.values() for pair in entries
                ).items()
                if key != "average_order"
            ]
        )
        self._grouping = SelectField([("Ըստ օրվա", "day"), ("Ըստ ամսվա", "month")])
        chart_filters.addWidget(FormField("Գծապատկերի ցուցանիշ", self._chart_metric))
        chart_filters.addWidget(FormField("Խմբավորում", self._grouping))

        self._chart_metric.currentIndexChanged.connect(self._render)
        self._grouping.currentIndexChanged.connect(self._render)

        self._chart = LineChart()
        trend = QVBoxLayout()
        trend.addLayout(chart_filters)
        self._trend_summary = PageSubtitle()
        trend.addWidget(self._trend_summary)
        trend.addWidget(self._chart)
        layout.addWidget(self._panel("Հասույթի և ցուցանիշների դինամիկա", trend))
        visuals = QGridLayout()
        self._comparison = ReportChart()
        self._composition = ReportChart(donut=True)
        visuals.addWidget(
            self._panel("Ընտրված / նախորդ՝ մոխրագույն", self._comparison), 0, 0
        )
        visuals.addWidget(
            self._panel("Հասույթի կառուցվածք · ընդհանուր արդյունք", self._composition),
            0,
            1,
        )
        layout.addLayout(visuals)
        layout.addWidget(SectionHeading("Մանրամասն համեմատություն"))
        layout.addWidget(self._metrics)
        layout.addWidget(SectionHeading("Ընթացիկ պաշարներ և պարտքեր"))
        self._balances = DataTable(["Ցուցանիշ", "Գումար"])
        self._balances.setMinimumHeight(220)
        self._balance_chart = ReportChart()
        balance_row = QHBoxLayout()
        balance_row.addWidget(self._balances, 1)
        balance_row.addWidget(self._balance_chart, 1)
        layout.addWidget(self._panel("Պաշարների և պարտքերի պատկերը", balance_row))
        layout.addWidget(
            PageSubtitle(
                "Շահույթ = հասույթ − վաճառվածի ինքնարժեք − "
                "դուրսգրում։ Գնումները կրկին չեն հանվում շահույթից։ "
                "Դրամական հոսք = վճարված վաճառք + "
                "պարտքի մարում − մատակարարներին վճարումներ։ "
                "Պաշարներն ու պարտքերը ընթացիկ են՝ անկախ ընտրված օրերից։ "
                "Աշխատավարձը, վարձակալությունը, հարկերն ու այլ "
                "չգրանցված ծախսերը ներառված չեն։ "
                "Սա ամբողջական զուտ շահույթը կամ դրամարկղի մնացորդը չէ։"
            )
        )
        outer = QVBoxLayout(self)
        outer.addWidget(page)
        self._period.currentIndexChanged.connect(self._preset)
        self._category.currentIndexChanged.connect(self._render)
        self._preset()

    @staticmethod
    def _panel(title: str, content: Any) -> QFrame:
        panel = QFrame()
        panel.setObjectName("reportPanel")
        body = QVBoxLayout(panel)
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(16)
        heading = SectionHeading(title)
        heading.setWordWrap(True)
        body.addWidget(heading)
        if isinstance(content, QWidget):
            body.addWidget(content)
        else:
            body.addLayout(content)
        return panel

    def _preset(self) -> None:
        days = int(self._period.currentData())
        if days:
            today = self._service.today()
            first = today - timedelta(days=days - 1)
            self._start.setDate(QDate(first.year, first.month, first.day))
            self._end.setDate(QDate(today.year, today.month, today.day))
        self.refresh()

    def refresh(self) -> None:
        self._generation += 1
        generation = self._generation
        start, end = self._start.date_value(), self._end.date_value()
        self._status.setText("Հաշվարկվում է…")
        run_in_background(
            self,
            lambda: self._service.report(start, end),
            lambda report: self._loaded(generation, report),
            lambda error: self._failed(generation, error),
        )

    def _loaded(self, generation: int, report: dict[str, Any]) -> None:
        if generation != self._generation:
            return
        self._report = report
        self._render()

    def _failed(self, generation: int, error: Exception) -> None:
        if generation == self._generation:
            self._report = None
            self._metrics.clear_rows()
            self._balances.clear_rows()
            self._chart.set_series([], [])
            self._trend_summary.setText("")
            for chart in (self._comparison, self._composition, self._balance_chart):
                chart.set_items([])
            for card in self._cards:
                card.set_value("—")
            self._status.setText(
                f"Չհաջողվեց հաշվարկել․ {error}"
                if isinstance(error, ValueError)
                else "Չհաջողվեց հաշվարկել։ Մանրամասները գրանցված են error.log ֆայլում։"
            )

    def _render(self) -> None:
        if self._report is None:
            return
        report = self._report
        current, previous = report["current"], report["previous"]
        self._status.setText(
            f"{report['start']:%d.%m.%Y} – {report['end']:%d.%m.%Y} · "
            f"Վաճառքներ՝ {int(current['orders'])} · "
            f"Անհայտ ինքնարժեքով տողեր՝ {int(current['missing_cost'])}"
        )
        metrics = CATEGORIES[str(self._category.currentData())]
        self._metrics.clear_rows()
        for card, (key, title) in zip(self._cards, metrics, strict=True):
            value, old = current[key], previous[key]
            display = "Անհայտ" if value is None else format_currency(value)
            # The subtitle identifies the selected metric.
            card.set_value(display, title)
            change = (
                "—" if value is None or old is None else format_currency(value - old)
            )
            self._metrics.append_row(
                [
                    title,
                    display,
                    "Անհայտ" if old is None else format_currency(old),
                    change,
                ]
            )
        self._comparison.set_items(
            [
                (
                    title,
                    None if current[key] is None else float(current[key]),
                    None if previous[key] is None else float(previous[key]),
                )
                for key, title in metrics
            ]
        )
        composition = [
            ("Ինքնարժեք", float(current["cost"]), None),
            ("Դուրսգրում", float(current["waste"]), None),
            ("Շահույթ", float(current["profit"] or 0), None),
        ]
        # A part-to-whole chart is valid only for known, nonnegative components.
        self._composition.set_items(
            composition
            if current["profit"] is not None
            and current["revenue"] > 0
            and all(value >= 0 for _, value, _ in composition)
            else []
        )
        chart_key = str(self._chart_metric.currentData())
        labels, series = self._service.chart(
            report, chart_key, self._grouping.currentData() == "month"
        )
        previous_end = report["start"] - timedelta(days=1)
        previous_start = (
            report["start"] - (report["end"] - report["start"]) - timedelta(days=1)
        )
        titles = [
            f"Ընտրված · {report['start']:%d.%m.%Y} – {report['end']:%d.%m.%Y}",
            f"Նախորդ · {previous_start:%d.%m.%Y} – {previous_end:%d.%m.%Y}",
        ]
        series = [(titles[i], values) for i, (_, values) in enumerate(series)]
        metric_title = self._chart_metric.currentText()
        value = current[chart_key]
        total = "Անհայտ" if value is None else format_currency(value)
        self._trend_summary.setText(
            f"{metric_title} · Ընդամենը՝ {total}\n"
            "Համեմատվում են նույն տևողության ժամանակահատվածները։ "
            "Գծի յուրաքանչյուր կետը օրվա կամ ամսվա գումարն է։"
            + (
                " Ամսական համեմատությունը ներառում է նախորդ շրջանի "
                "համապատասխան օրերը՝ առանց ամբողջ ամսվա վերահաշվարկի։"
                if self._grouping.currentData() == "month"
                else ""
            )
        )
        self._chart.set_series(
            labels,
            series,
            empty_message="Շահույթի գծապատկերը հասանելի չէ․ "
            "առկա են անհայտ ինքնարժեքով վաճառքներ։"
            if chart_key == "profit"
            else "Գծապատկերի տվյալները հասանելի չեն։",
        )
        self._balances.clear_rows()
        balances = report["balances"]
        balance_items = []
        for key, title in (
            ("stock_cost", "Պաշարների հայտնի ինքնարժեք"),
            ("stock_retail", "Պաշարների վաճառքի արժեք"),
            ("customer_debt", "Հաճախորդների պարտք / կանխավճար"),
            ("supplier_debt", "Մատակարարների պարտք / կանխավճար"),
        ):
            self._balances.append_row([title, format_currency(Decimal(balances[key]))])
            balance_items.append((title, float(balances[key]), None))
        self._balance_chart.set_items(balance_items)
        if balances["stock_missing_cost"] or balances["negative_stock"]:
            self._status.setText(
                self._status.text()
                + " · Պաշարներում առկա են անհայտ ինքնարժեք կամ բացասական մնացորդներ։"
            )

    def closeEvent(self, event: Any) -> None:
        wait_for_pending_threads(self)
        super().closeEvent(event)
