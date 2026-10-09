import uuid
from decimal import Decimal

from models import Product, Unit
from ui.kitchen_window import KitchenProductionPage


def product(name, sku, unit=Unit.PIECE, barcode=None):
    return Product(
        id=uuid.uuid4(),
        name=name,
        sku=sku,
        barcode=barcode,
        unit=unit,
        is_active=True,
        quantity_in_stock=Decimal("10"),
    )


def test_search_ranks_exact_codes_and_clears_stale_selection(qtbot):
    page = KitchenProductionPage(lambda: None, lambda *_: None)
    qtbot.addWidget(page)
    exact = product("Z soup", "100", barcode="998877")
    page.set_products([product("A soup", "1001"), exact])
    page._product_search.setText("100")
    assert page._catalog_table.item_model.item(0, 0).text() == exact.name
    page._product_search.setText("998877")
    assert page._selected_product().id == exact.id
    assert page._add_button.isEnabled()
    page._product_search.setText("missing")
    assert page._selected_product() is None
    assert not page._add_button.isEnabled()


def test_repeated_add_updates_balance_and_saves_correct_quantities(qtbot):
    saved = []
    page = KitchenProductionPage(lambda: None, lambda *args: saved.append(args))
    qtbot.addWidget(page)
    item = product("Soup", "100", Unit.KG)
    page.set_products([item])
    page._quantity.setText("2.5")
    page._add_button.click()
    page._add_button.click()
    assert page._lines[item.id] == Decimal("5")
    assert "15" in page._table.item_model.item(0, 3).text()
    assert "17.5" in page._balance_preview.text()
    page._save.click()
    assert saved[0][1][0].quantity == Decimal("5")
    page._table.selectRow(0)
    page._remove.click()
    assert not page._lines
    assert not page._save.isEnabled()


def test_barbecue_parent_prefix_is_displayed_and_searchable(qtbot):
    page = KitchenProductionPage(lambda: None, lambda *_: None)
    qtbot.addWidget(page)
    parent = product("Barbecue", "BBQ", Unit.BARBECUE)
    child = product("Siga", "7")
    child.parent_product_id = parent.id
    plain = product("Soup", "8")
    orphan = product("Salad", "9")
    orphan.parent_product_id = uuid.uuid4()
    page.set_products([parent, child, plain, orphan])
    assert page._catalog_table.row_count() == 3
    assert page._product_names[plain.id] == "Soup"
    assert page._product_names[orphan.id] == "Salad"
    page._product_search.setText("barbecue siga")
    assert page._catalog_table.row_count() == 1
    assert page._catalog_table.item_model.item(0, 0).text() == "Barbecue -> Siga"
    assert page._selection_title.text() == "Barbecue -> Siga"
    page._add_button.click()
    assert page._table.item_model.item(0, 0).text() == "Barbecue -> Siga"
