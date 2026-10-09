from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models import Product, Role, Unit, User
from models.waste import WasteDocument, WasteDocumentItem
from repositories.waste import WasteRepository
from schemas.waste import WasteLineInput


@pytest.fixture
def waste():
    engine = create_engine("sqlite://")
    for model in (User, Product, WasteDocument, WasteDocumentItem):
        model.__table__.create(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        user = User(
            username="admin", full_name="Admin", hashed_password="test", role=Role.ADMIN
        )
        product = Product(
            sku="milk",
            name="Milk",
            unit=Unit.LITER,
            cost_price=Decimal("25.50"),
            quantity_in_stock=Decimal("10"),
            is_active=True,
        )
        session.add_all([user, product])
        session.commit()
    yield WasteRepository(factory), factory, user.id, product.id
    engine.dispose()


def stock(factory, product_id):
    with factory() as session:
        return session.get(Product, product_id).quantity_in_stock


def test_complete_reopen_and_recomplete(waste):
    repo, factory, user_id, product_id = waste
    doc = repo.create_draft(
        user_id, None, [WasteLineInput(product_id, Decimal("2"), "expired")]
    )
    assert stock(factory, product_id) == 10
    assert doc.total_cost == Decimal("51.00")
    repo.lock(doc.id)
    assert stock(factory, product_id) == 8
    with pytest.raises(ValueError):
        repo.lock(doc.id)
    assert stock(factory, product_id) == 8
    repo.reopen_for_edit(doc.id)
    repo.reopen_for_edit(doc.id)
    assert stock(factory, product_id) == 10
    repo.update_draft(
        doc.id,
        "Updated",
        [WasteLineInput(product_id, Decimal("3"), "damaged")],
        complete=True,
    )
    assert stock(factory, product_id) == 7
    assert repo.get_detail(doc.id)[0].total_cost == Decimal("76.50")


def test_historical_cost_and_name_survive_edit(waste):
    repo, factory, user_id, product_id = waste
    doc = repo.create_draft(
        user_id, None, [WasteLineInput(product_id, Decimal("2"))], complete=True
    )
    with factory() as session:
        product = session.get(Product, product_id)
        product.cost_price = Decimal("100")
        product.name = "New name"
        session.commit()
    repo.reopen_for_edit(doc.id)
    repo.update_draft(
        doc.id, None, [WasteLineInput(product_id, Decimal("3"))], complete=True
    )
    item = repo.get_detail(doc.id)[2][0]
    assert item.product_name == "Milk"
    assert item.unit_cost == Decimal("25.50")
    assert item.line_total == Decimal("76.50")


@pytest.mark.parametrize(
    "quantity, reason, note",
    [
        ("0", "spoiled", None),
        ("-1", "spoiled", None),
        ("NaN", "spoiled", None),
        ("1.0001", "spoiled", None),
        ("1", "unknown", None),
        ("1", "custom", "  "),
    ],
)
def test_invalid_lines_leave_no_document(waste, quantity, reason, note):
    repo, factory, user_id, product_id = waste
    with pytest.raises(ValueError):
        repo.create_draft(
            user_id, None, [WasteLineInput(product_id, Decimal(quantity), reason, note)]
        )
    with factory() as session:
        assert session.scalar(select(WasteDocument)) is None
    assert stock(factory, product_id) == 10


def test_failed_completion_is_atomic(waste):
    repo, factory, user_id, product_id = waste
    with pytest.raises(ValueError):
        repo.create_draft(
            user_id, None, [WasteLineInput(product_id, Decimal("11"))], complete=True
        )
    with factory() as session:
        assert session.scalar(select(WasteDocument)) is None
    doc = repo.create_draft(user_id, None, [WasteLineInput(product_id, Decimal("1"))])
    with pytest.raises(ValueError):
        repo.update_draft(
            doc.id,
            "Must roll back",
            [WasteLineInput(product_id, Decimal("11"))],
            complete=True,
        )
    detail, _, items = repo.get_detail(doc.id)
    assert detail.notes is None
    assert items[0].quantity == 1
    assert stock(factory, product_id) == 10


def test_custom_reason_and_duplicate_quantity(waste):
    repo, factory, user_id, product_id = waste
    line = WasteLineInput(product_id, Decimal("1.125"), "custom", "Refrigerator failed")
    doc = repo.create_draft(user_id, None, [line, line], complete=True)
    items = repo.get_detail(doc.id)[2]
    assert len(items) == 1
    assert items[0].quantity == Decimal("2.250")
    assert items[0].reason_note == "Refrigerator failed"
    assert stock(factory, product_id) == Decimal("7.750")
