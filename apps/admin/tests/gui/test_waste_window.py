import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from PySide6.QtWidgets import QLabel

from models import Product, Unit, User
from schemas.waste import WasteDetail, WasteLineInput, WasteRow
from ui.waste_window import WasteEditorPage, WasteWindow


def test_editor_restores_reasons_and_historical_cost(qtbot):
    product = Product(
        id=uuid.uuid4(),
        name="Milk",
        sku="milk",
        unit=Unit.LITER,
        cost_price=Decimal("100"),
        quantity_in_stock=Decimal("10"),
        is_active=True,
    )
    item = SimpleNamespace(
        product_id=product.id,
        product_name="Old Milk",
        quantity=Decimal("2"),
        unit_cost=Decimal("25"),
        reason="custom",
        reason_note="Fridge failed",
        unit="l",
    )
    detail = WasteDetail(SimpleNamespace(notes="Note"), "Admin", [item])
    saved = []
    editor = WasteEditorPage(lambda: None, lambda *args: saved.append(args))
    qtbot.addWidget(editor)
    editor.set_document([product], detail)
    assert editor._items.item_model.item(0, 0).text() == "Old Milk"
    assert "Fridge failed" in editor._items.item_model.item(0, 5).text()
    editor._save_document(lock=True)
    assert saved[0][2] == [
        WasteLineInput(product.id, Decimal("2"), "custom", "Fridge failed")
    ]


def test_report_excludes_drafts_and_groups_units(qtbot):
    window = WasteWindow(None, None, User(full_name="Admin"))
    qtbot.addWidget(window)
    rows = [
        WasteRow(
            uuid.uuid4(),
            "WST-1",
            datetime.now(UTC),
            "Admin",
            "locked",
            Decimal("2"),
            Decimal("50"),
        ),
        WasteRow(
            uuid.uuid4(),
            "WST-2",
            datetime.now(UTC),
            "Admin",
            "draft",
            Decimal("8"),
            Decimal("200"),
        ),
    ]
    details = [
        WasteDetail(
            SimpleNamespace(total_cost=Decimal("50")),
            "Admin",
            [SimpleNamespace(unit="kg", quantity=Decimal("2"))],
        )
    ]
    window._loaded((rows, details))
    assert window._table.row_count() == 2
    assert "50" in window._cost_card.findChild(QLabel, "statValue").text()
    assert "2" in window._quantity_card.findChild(QLabel, "statValue").text()
    for period in (
        "today",
        "7_days",
        "1_month",
        "3_months",
        "6_months",
        "12_months",
        "custom",
    ):
        window._period.set_period(period, notify=False)
        start, end = window._bounds()
        assert start < end
        assert start.tzinfo == UTC
    window._period.set_period("7_days", notify=False)
    start, end = window._bounds()
    assert end - start == timedelta(days=7)


def test_range_honors_timestamp_offsets(qtbot):
    from datetime import timezone

    row = WasteRow(
        uuid.uuid4(),
        "WST-1",
        datetime(2026, 10, 8, 1, tzinfo=timezone(timedelta(hours=4))),
        "Admin",
        "draft",
        Decimal("1"),
        Decimal("1"),
    )
    service = SimpleNamespace(list_documents=lambda: [row])
    window = WasteWindow(service, None, User())
    qtbot.addWidget(window)
    # Oct 8 at 01:00 in Yerevan belongs to Oct 7 in UTC.
    result, _ = window._load_report(
        datetime(2026, 10, 7, tzinfo=UTC), datetime(2026, 10, 8, tzinfo=UTC)
    )
    assert result == [row]
