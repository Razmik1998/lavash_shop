"""Inventory replenishment and supplier cost recommendations."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from ui.components import (
    BarChart,
    CardList,
    CardScrollArea,
    ErrorLabel,
    PageHeader,
    PageSubtitle,
    Panel,
    RecommendationCard,
    RefreshButton,
    SectionHeading,
    SimpleTable,
    StatCard,
    StatusBadge,
)
from ui.style import configure_page_layout, format_currency, format_quantity
from ui.workers import run_in_background, wait_for_pending_threads


def _money(value: Decimal | None) -> str:
    return "—" if value is None else format_currency(value)


def _quantity(value: Decimal | None, unit: str) -> str:
    if value is None:
        return "Չնշված"
    return f"{format_quantity(value.quantize(Decimal('0.001')))} {unit}"


def _coverage(stock: Decimal, sold: Decimal) -> str:
    if stock <= 0:
        return "Պաշարը սպառված է"
    if sold <= 0:
        return "Վաճառք չկա"
    days = int((stock * Decimal("30") / sold).to_integral_value())
    return f"~{format_quantity(days)} օր"


class RecommendationsWindow(QWidget):
    def __init__(self, purchase_service: Any) -> None:
        super().__init__()
        self._service = purchase_service
        self._page = CardScrollArea()
        layout = self._page.body
        configure_page_layout(layout)
        heading = QHBoxLayout()
        heading.addWidget(
            PageHeader(
                "Պաշարների համալրում",
                "Վաճառքի տեմպով հաշվարկված առաջարկներ և հաստատված գնումներից "
                "վերցված մատակարարների գներ։",
            ),
            1,
        )
        self._refresh_button = RefreshButton("Թարմացնել", on_click=self.refresh)
        heading.addWidget(self._refresh_button)
        layout.addLayout(heading)

        self._stats = QHBoxLayout()
        self._urgent_card = StatCard(
            "Շտապ համալրել", "—", "Պաշարը հասել է նվազագույն շեմին", tone="danger"
        )
        self._buy_card = StatCard(
            "Պատվիրելու ապրանքներ", "—", "Առաջարկվող քանակները՝ ստորև", tone="warning"
        )
        self._tracked_card = StatCard(
            "Դիտարկվող ապրանքներ", "—", "Ակտիվ տեսականուց", tone="info"
        )
        self._stats.addWidget(self._urgent_card)
        self._stats.addWidget(self._buy_card)
        self._stats.addWidget(self._tracked_card)
        layout.addLayout(self._stats)

        self._demand_chart = BarChart("Ամենաշատ վաճառված ապրանքներ · 30 օր")
        self._demand_chart.hide()
        layout.addWidget(self._demand_chart)

        section = QHBoxLayout()
        section.addWidget(SectionHeading("Առաջարկվող պատվերներ"))
        self._recommendation_count = StatusBadge("Բեռնվում է…", "info")
        section.addWidget(self._recommendation_count)
        section.addStretch()
        layout.addLayout(section)

        self._list = CardList()
        self._list.hide()
        layout.addWidget(self._list)
        self._status_panel = Panel()
        status_layout = QVBoxLayout(self._status_panel)
        status_layout.setContentsMargins(12, 12, 12, 12)
        self._empty_state = PageSubtitle()
        self._empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_state.setMinimumHeight(100)
        self._empty_state.hide()
        status_layout.addWidget(self._empty_state)
        self._error = ErrorLabel()
        self._error.hide()
        status_layout.addWidget(self._error)
        self._loading = PageSubtitle("Տվյալները բեռնվում են…")
        status_layout.addWidget(self._loading)
        layout.addWidget(self._status_panel)

        note = PageSubtitle(
            "Առաջարկվող քանակը հաշվի է առնում վերջին 30 օրվա վաճառքը, "
            "նվազագույն պաշարի շեմը և առկա մնացորդը։ Պաշարի ծածկույթը "
            "մոտավոր է՝ հաշվարկված վաճառքի վերջին տեմպով։"
        )
        layout.addWidget(note)
        layout.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._page)
        self.refresh()

    def refresh(self) -> None:
        self._refresh_button.setEnabled(False)
        self._recommendation_count.set_status("Բեռնվում է…", "info")
        self._loading.setText("Տվյալները բեռնվում են…")
        self._loading.show()
        self._status_panel.show()
        self._empty_state.hide()
        self._error.hide()
        run_in_background(
            self,
            self._service.procurement_recommendations,
            self._render,
            self._show_error,
        )

    def _render(self, records: list[dict[str, Any]]) -> None:
        self._refresh_button.setEnabled(True)
        self._loading.hide()
        self._error.hide()
        recommendations = []
        urgent = 0
        for record in records:
            product = record["product"]
            sold = Decimal(record["sold_30d"])
            stock = product.quantity_in_stock
            threshold = product.low_stock_threshold
            target = sold + (threshold or Decimal("0"))
            if stock is None:
                continue
            suggested = max(Decimal("0"), target - stock)
            if suggested <= 0:
                continue
            is_urgent = stock <= (threshold or Decimal("0"))
            urgent += int(is_urgent)
            suppliers = sorted(
                record["suppliers"],
                key=lambda supplier: (
                    not supplier["active"],
                    supplier["average_cost"],
                ),
            )
            recommendations.append(
                (is_urgent, suggested, sold, stock, product, suppliers)
            )

        recommendations.sort(key=lambda row: (not row[0], -(row[1])))
        demand_rows = sorted(
            ((Decimal(record["sold_30d"]), record["product"]) for record in records),
            key=lambda entry: entry[0],
            reverse=True,
        )[:5]
        self._demand_chart.set_items(
            [
                (
                    product.name,
                    amount,
                    f"{format_quantity(amount)} {product.unit.value}",
                )
                for amount, product in demand_rows
                if amount > 0
            ]
        )
        self._demand_chart.setVisible(
            any(amount > 0 for amount, _product in demand_rows)
        )
        self._urgent_card.set_value(format_quantity(urgent))
        self._buy_card.set_value(format_quantity(len(recommendations)))
        self._tracked_card.set_value(format_quantity(len(records)))
        self._recommendation_count.set_status(
            format_quantity(len(recommendations)),
            "warning" if recommendations else "success",
        )
        self._list.clear()
        if not recommendations:
            self._list.hide()
            self._status_panel.show()
            self._empty_state.setText(
                "Ակտիվ ապրանքներ դեռ չկան։"
                if not records
                else "Հիանալի է․ այս պահին պատվիրելու ապրանք չկա։"
            )
            self._empty_state.show()
            return

        self._list.show()
        self._status_panel.hide()
        for is_urgent, suggested, sold, stock, product, suppliers in recommendations:
            active = [supplier for supplier in suppliers if supplier["active"]]
            best = active[0] if active else None
            next_best = active[1] if len(active) > 1 else None
            saving = (
                next_best["average_cost"] - best["average_cost"]
                if best and next_best
                else None
            )
            note = ""
            if best and saving is not None and saving > 0:
                note = f"Խնայողություն՝ {_money(saving)} / միավոր"
            unit = product.unit.value
            if best:
                supplier_text = f"{best['name']} · {best['phone'] or 'հեռախոս չկա'}"
                supplier_text += f" · {_money(best['average_cost'])}"
            else:
                supplier_text = "Ակտիվ մատակարար չկա"
            self._list.add_card(
                RecommendationCard(
                    name=product.name,
                    urgent=is_urgent,
                    suggested=_quantity(suggested, unit),
                    metrics=[
                        ("Առկա պաշար", _quantity(max(stock, Decimal("0")), unit)),
                        ("Վաճառք · 30 օր", _quantity(sold, unit)),
                        ("Պաշարի ծածկույթ", _coverage(stock, sold)),
                    ],
                    supplier=supplier_text,
                    supplier_note=note,
                    details=self._supplier_table(suppliers),
                )
            )

    def _show_error(self, error: Exception) -> None:
        self._refresh_button.setEnabled(True)
        self._loading.hide()
        self._recommendation_count.set_status("Չհաջողվեց բեռնել", "danger")
        self._error.setText(f"Չհաջողվեց բեռնել առաջարկները․ {error}")
        self._error.show()

    def closeEvent(self, event: QCloseEvent) -> None:
        wait_for_pending_threads(self)
        super().closeEvent(event)

    @staticmethod
    def _supplier_table(suppliers: list[dict[str, Any]]) -> Panel:
        panel = Panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        layout.addWidget(SectionHeading("Մատակարարների գների համեմատություն"))
        if not suppliers:
            layout.addWidget(PageSubtitle("Այս ապրանքի համար գնման պատմություն չկա։"))
            return panel
        table = SimpleTable(
            [
                "Մատակարար",
                "Հեռախոս",
                "Կարգավիճակ",
                "Միջին գին",
                "Նվազագույն գին",
                "Վերջին գնում",
                "Փաստաթղթեր",
            ]
        )
        for index, supplier in enumerate(suppliers):
            last = supplier["last_purchase"]
            values = [
                str(supplier["name"]),
                str(supplier["phone"] or "—"),
                (
                    "Առաջարկվում է"
                    if supplier["active"] and index == 0
                    else "Ակտիվ"
                    if supplier["active"]
                    else "Ապաակտիվ"
                ),
                _money(supplier["average_cost"]),
                _money(supplier["lowest_cost"]),
                (last.strftime("%d.%m.%Y") if last else "—"),
                format_quantity(supplier["purchase_count"]),
            ]
            row = table.append_row(values)
            for column in (3, 4, 6):
                item = table.item(row, column)
                if item is not None:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
        row_height = table.verticalHeader().defaultSectionSize()
        table.setFixedHeight(
            table.horizontalHeader().height() + 24 + row_height * len(suppliers) + 8
        )
        layout.addWidget(table)
        return panel
