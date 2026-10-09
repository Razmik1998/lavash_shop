from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Date, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.elements import Cast

from models import Base
from models.customer import CustomerCreditPayment, CustomerCreditSale
from models.enums import PaymentMethod, PurchaseStatus, SaleStatus, Unit
from models.product import Product
from models.purchase import Purchase
from models.sale import Sale, SaleItem
from models.supplier import Supplier, SupplierPayment
from models.waste import WasteDocument
from repositories.reports import ReportsRepository
from services.reports import ReportsService


@compiles(Cast, "sqlite")
def sqlite_date_cast(element, compiler, **kwargs):
    # SQLite CAST(... AS DATE) yields an integer; emulate PostgreSQL's date cast.
    if isinstance(element.type, Date):
        return "date(" + compiler.process(element.clause, **kwargs) + ")"
    return compiler.visit_cast(element, **kwargs)


def test_financial_aggregates_do_not_multiply_joins_and_use_local_dates():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def timezone_function(connection, record):
        connection.create_function(
            "timezone",
            2,
            lambda zone, raw: (
                datetime.fromisoformat(raw)
                .replace(tzinfo=UTC)
                .astimezone(ZoneInfo(zone))
                .replace(tzinfo=None)
                .isoformat(" ")
            ),
        )

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    sale_id, supplier_id, product_id = uuid4(), uuid4(), uuid4()
    at = datetime(2026, 1, 1, 21)  # January 2 in Armenia.
    with factory.begin() as session:
        session.add(
            Sale(
                id=sale_id,
                pos_session_id=uuid4(),
                employee_user_id=uuid4(),
                terminal_id="test",
                client_sale_id=uuid4(),
                total=100,
                status=SaleStatus.COMPLETED,
                created_at=at,
            )
        )
        session.add(
            Sale(
                pos_session_id=uuid4(),
                employee_user_id=uuid4(),
                terminal_id="test",
                client_sale_id=uuid4(),
                total=999,
                status=SaleStatus.CANCELLED,
                created_at=at,
            )
        )
        for cost, active in ((10, True), (20, True), (999, False)):
            session.add(
                SaleItem(
                    sale_id=sale_id,
                    product_name="test",
                    product_sku="x",
                    unit="piece",
                    quantity=2,
                    cost_price=cost,
                    unit_price=25,
                    original_unit_price=25,
                    line_total=50,
                    is_active=active,
                )
            )
        session.add(CustomerCreditSale(customer_id=uuid4(), sale_id=sale_id, amount=40))
        session.add(
            CustomerCreditPayment(
                customer_id=uuid4(),
                amount=15,
                pos_session_id=uuid4(),
                pos_user_id=uuid4(),
                paid_at=at,
            )
        )
        session.add(Supplier(id=supplier_id, name="test", opening_debt=10))
        session.add(
            Purchase(
                supplier_id=supplier_id,
                purchase_number="1",
                purchase_date=at,
                total=200,
                status=PurchaseStatus.OPEN,
            )
        )
        session.add(
            Purchase(
                supplier_id=supplier_id,
                purchase_number="2",
                purchase_date=at,
                total=999,
                status=PurchaseStatus.DRAFT,
            )
        )
        session.add(
            SupplierPayment(
                supplier_id=supplier_id,
                amount=30,
                payment_date=at,
                method=PaymentMethod.CASH,
            )
        )
        session.add(
            WasteDocument(
                document_number="1",
                created_by=uuid4(),
                status="locked",
                total_cost=5,
                created_at=datetime(2025, 12, 1),
                locked_at=at,
            )
        )
        session.add(
            WasteDocument(
                document_number="2",
                created_by=uuid4(),
                status="draft",
                total_cost=999,
                created_at=at,
            )
        )
        session.add(
            Product(
                id=product_id,
                sku="1",
                name="test",
                unit=Unit.PIECE,
                quantity_in_stock=3,
                cost_price=10,
                selling_price=25,
            )
        )
    statements = []
    event.listen(
        engine, "before_cursor_execute", lambda *args: statements.append(args[2])
    )
    report = ReportsService(ReportsRepository(factory)).report(
        date(2026, 1, 2), date(2026, 1, 2)
    )
    current = report["current"]
    assert current["revenue"] == 100
    assert current["orders"] == 1
    assert current["cost"] == 60
    assert current["received"] == 75
    assert current["cash_flow"] == 45
    assert current["profit"] == 35
    assert current["purchases"] == 200
    assert report["balances"]["stock_cost"] == 30
    assert report["balances"]["customer_debt"] == 25
    assert report["balances"]["supplier_debt"] == 180
    assert len(statements) == 2
    assert report["previous"]["revenue"] == 0


class MissingCosts:
    def daily(self, start, end, timezone):
        return [{"day": date(2026, 1, 1), "metric": "missing_cost", "amount": 1}]

    def balances(self):
        return {}


def test_missing_costs_suppress_profit_and_chart():
    service = ReportsService(MissingCosts())
    report = service.report(date(2026, 1, 1), date(2026, 1, 3))
    assert report["current"]["profit"] is None
    assert len(report["daily"]) == 3
    assert service.chart(report, "profit", False) == ([], [])
    labels, series = service.chart(report, "revenue", True)
    assert labels == ["01.2026"]
    assert series[0][1] == [0]


@pytest.mark.parametrize(
    "start,end",
    [
        (date(2026, 2, 2), date(2026, 2, 1)),
        (date(2024, 1, 1), date(2026, 1, 1)),
        (date(2099, 1, 1), date(2099, 1, 2)),
    ],
)
def test_invalid_date_ranges(start, end):
    with pytest.raises(ValueError):
        ReportsService(MissingCosts()).report(start, end)
