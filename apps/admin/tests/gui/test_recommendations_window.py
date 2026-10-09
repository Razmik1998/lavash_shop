from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from models import Product, Unit
from ui.components import RecommendationCard, SimpleTable
from ui.recommendations_window import RecommendationsWindow, _coverage


class _RecommendationService:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def procurement_recommendations(self) -> list[dict[str, Any]]:
        return self._records


class _FailingRecommendationService:
    def procurement_recommendations(self) -> list[dict[str, Any]]:
        raise RuntimeError("Connection unavailable")


def _record(
    *,
    stock: Decimal,
    threshold: Decimal,
    sold: Decimal,
) -> dict[str, Any]:
    product = Product(
        id=uuid.uuid4(),
        sku="SKU-001",
        name="Սուրճ",
        unit=Unit.PIECE,
        selling_price=Decimal("1200"),
        quantity_in_stock=stock,
        low_stock_threshold=threshold,
        is_active=True,
    )
    return {
        "product": product,
        "sold_30d": sold,
        "suppliers": [
            {
                "name": "Արարատ",
                "phone": "091000000",
                "active": True,
                "average_cost": Decimal("200"),
                "lowest_cost": Decimal("180"),
                "last_purchase": datetime(2026, 10, 1, tzinfo=UTC),
                "purchase_count": 3,
            },
            {
                "name": "Մասիս",
                "phone": None,
                "active": True,
                "average_cost": Decimal("230"),
                "lowest_cost": Decimal("220"),
                "last_purchase": None,
                "purchase_count": 1,
            },
        ],
    }


def test_recommendations_expand_supplier_comparison(qtbot: Any) -> None:
    window = RecommendationsWindow(
        _RecommendationService(
            [_record(stock=Decimal("2"), threshold=Decimal("5"), sold=Decimal("10"))]
        )
    )
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window._list.body.count() > 0, timeout=2000)

    assert window._urgent_card.value_label.text() == "1"
    assert window._buy_card.value_label.text() == "1"
    assert window._tracked_card.value_label.text() == "1"
    card = window._list.body.itemAt(0).widget()
    assert isinstance(card, RecommendationCard)
    assert card.details.isHidden()

    card.toggle.click()

    assert not card.details.isHidden()
    supplier_table = card.details.findChild(SimpleTable)
    assert supplier_table is not None
    assert supplier_table.rowCount() == 2
    status_item = supplier_table.item(0, 2)
    assert status_item is not None
    assert status_item.text() == "Առաջարկվում է"


def test_coverage_is_rounded_and_handles_depleted_stock() -> None:
    assert _coverage(Decimal("-2"), Decimal("9.4")) == "Պաշարը սպառված է"
    assert _coverage(Decimal("1"), Decimal("0")) == "Վաճառք չկա"
    assert _coverage(Decimal("5"), Decimal("47")) == "~3 օր"


def test_recommendations_show_clear_empty_state(qtbot: Any) -> None:
    window = RecommendationsWindow(
        _RecommendationService(
            [_record(stock=Decimal("20"), threshold=Decimal("5"), sold=Decimal("0"))]
        )
    )
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: not window._empty_state.isHidden(), timeout=2000)

    assert window._empty_state.text() == ("Հիանալի է․ այս պահին պատվիրելու ապրանք չկա։")
    assert not window._demand_chart.isVisible()


def test_recommendations_surface_load_error_and_allow_retry(qtbot: Any) -> None:
    window = RecommendationsWindow(_FailingRecommendationService())
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: not window._error.isHidden(), timeout=2000)

    assert "Connection unavailable" in window._error.text()
    assert "Չհաջողվեց բեռնել" in window._recommendation_count.text()
    assert window._refresh_button.isEnabled()
