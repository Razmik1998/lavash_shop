from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from exceptions import (
    InvalidCursorError,
    InvalidFiltersError,
    InvalidSaleCancellationReasonError,
    InvalidSalePriceError,
    ProductNotFoundError,
    SessionClosedError,
    SessionNotOwnedError,
    TerminalMismatchError,
)
from models import PosSession, PosSessionStatus, Product, SaleStatus, Unit
from services import SalesFilters, SalesHistoryService, SalesService


class FakeSessionRepository:
    def __init__(self, session: PosSession | None) -> None:
        self.session = session

    def get_by_id(self, session_id: uuid.UUID) -> PosSession | None:
        if self.session is not None and self.session.id == session_id:
            return self.session
        return None


class FakeProductRepository:
    def __init__(self, product: Product) -> None:
        self.product = product

    def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        return self.product if product_id == self.product.id else None

    def update(self, product: Product) -> Product:
        self.product = product
        return product


class FakeSaleRepository:
    def __init__(self) -> None:
        self.created: tuple[object, ...] | None = None

    def create_sale(self, *args: object) -> object:
        self.created = args
        sale_id = uuid.uuid4()
        now = datetime.now(UTC)
        return type("Sale", (), {
            "id": sale_id,
            "pos_session_id": args[0],
            "employee_user_id": args[1],
            "terminal_id": args[2],
            "status": SaleStatus.COMPLETED,
            "total": Decimal("7.50"),
            "created_at": now,
        })()

    def get_detail(
        self, sale_id: uuid.UUID
    ) -> tuple[object, list[object], list[object]]:
        sale = type("Sale", (), {
            "id": sale_id,
            "pos_session_id": uuid.uuid4(),
            "employee_user_id": uuid.uuid4(),
            "terminal_id": "pos-1",
            "status": SaleStatus.COMPLETED,
            "total": Decimal("7.50"),
            "created_at": datetime.now(UTC),
            "cancellation_reason": None,
        })()
        return sale, [], []


class FakeHistoryRepository:
    def __init__(self) -> None:
        self.filters: SalesFilters | None = None
        self.cursor: tuple[datetime, uuid.UUID] | None = None
        self.limit = 0
        self.rows: list[object] = []

    def list_sales(
        self,
        filters: SalesFilters,
        cursor: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[object]:
        self.filters = filters
        self.cursor = cursor
        self.limit = limit
        return self.rows

    def summarize_sales(
        self, filters: SalesFilters
    ) -> tuple[int, Decimal, Decimal, Decimal]:
        self.filters = filters
        return 2, Decimal("3"), Decimal("15.00"), Decimal("6.00")


def _session(
    user_id: uuid.UUID, status: PosSessionStatus = PosSessionStatus.ACTIVE
) -> PosSession:
    now = datetime.now(UTC)
    return PosSession(
        id=uuid.uuid4(),
        terminal_id="pos-1",
        user_id=user_id,
        status=status,
        started_at=now,
        closed_at=now if status is PosSessionStatus.CLOSED else None,
        last_connected_at=now,
        last_activity_at=now,
        created_at=now,
        updated_at=now,
    )


def _product() -> Product:
    return Product(
        id=uuid.uuid4(),
        name="Coffee",
        sku="COF-001",
        barcode=None,
        unit=Unit.PIECE,
        cost_price=Decimal("2.00"),
        selling_price=Decimal("2.50"),
        quantity_in_stock=Decimal("10"),
        low_stock_threshold=None,
        is_active=True,
    )


def test_create_sale_uses_session_owner_and_authoritative_product_price() -> None:
    employee = uuid.uuid4()
    session = _session(employee)
    product = _product()
    sale_repository = FakeSaleRepository()
    service = SalesService(
        sale_repository,
        FakeSessionRepository(session),
        FakeProductRepository(product),
    )

    service.create_sale(
        employee,
        session.id,
        session.terminal_id,
        uuid.uuid4(),
        [(product.id, Decimal("3"))],
    )

    assert sale_repository.created is not None
    lines = sale_repository.created[-1]
    assert lines[0][1:] == (Decimal("3"), Decimal("2.50"), Decimal("7.50"))
    assert sale_repository.created[0] == session.id
    assert sale_repository.created[1] == employee


def test_create_sale_rejects_price_outside_current_product_price_range() -> None:
    employee = uuid.uuid4()
    session = _session(employee)
    product = _product()
    service = SalesService(
        FakeSaleRepository(),
        FakeSessionRepository(session),
        FakeProductRepository(product),
    )

    with pytest.raises(InvalidSalePriceError, match="requested_price=2.51"):
        service.create_sale(
            employee,
            session.id,
            session.terminal_id,
            uuid.uuid4(),
            [(product.id, Decimal("1"), Decimal("2.51"))],
        )


def test_create_sale_rejects_internal_use_product() -> None:
    employee = uuid.uuid4()
    session = _session(employee)
    product = _product()
    product.is_for_sale = False
    service = SalesService(
        FakeSaleRepository(),
        FakeSessionRepository(session),
        FakeProductRepository(product),
    )

    with pytest.raises(ProductNotFoundError):
        service.create_sale(
            employee,
            session.id,
            session.terminal_id,
            uuid.uuid4(),
            [(product.id, Decimal("1"))],
        )


def test_create_sale_combines_duplicate_product_lines_before_stock_and_total() -> None:
    employee = uuid.uuid4()
    session = _session(employee)
    product = _product()
    sale_repository = FakeSaleRepository()
    service = SalesService(
        sale_repository,
        FakeSessionRepository(session),
        FakeProductRepository(product),
    )

    service.create_sale(
        employee,
        session.id,
        session.terminal_id,
        uuid.uuid4(),
        [(product.id, Decimal("1")), (product.id, Decimal("2"))],
    )

    assert sale_repository.created is not None
    lines = sale_repository.created[-1]
    assert len(lines) == 1
    assert lines[0][1:] == (Decimal("3"), Decimal("2.50"), Decimal("7.50"))


def test_create_sale_reduces_stock_for_sold_items() -> None:
    employee = uuid.uuid4()
    session = _session(employee)
    product = _product()
    product.quantity_in_stock = Decimal("5")
    service = SalesService(
        FakeSaleRepository(),
        FakeSessionRepository(session),
        FakeProductRepository(product),
    )

    service.create_sale(
        employee,
        session.id,
        session.terminal_id,
        uuid.uuid4(),
        [(product.id, Decimal("2"))],
    )

    assert product.quantity_in_stock == Decimal("3")


@pytest.mark.parametrize(
    ("initial_stock", "expected_stock"),
    [("1", "-2"), ("0", "-3"), ("-1", "-4")],
)
def test_create_sale_allows_negative_stock_when_request_exceeds_available(
    initial_stock: str, expected_stock: str
) -> None:
    employee = uuid.uuid4()
    session = _session(employee)
    product = _product()
    product.quantity_in_stock = Decimal(initial_stock)
    service = SalesService(
        FakeSaleRepository(),
        FakeSessionRepository(session),
        FakeProductRepository(product),
    )

    service.create_sale(
        employee,
        session.id,
        session.terminal_id,
        uuid.uuid4(),
        [(product.id, Decimal("3"))],
    )

    assert product.quantity_in_stock == Decimal(expected_stock)


def test_cancel_sale_requires_a_nonblank_reason() -> None:
    employee = uuid.uuid4()
    session = _session(employee)
    service = SalesService(
        FakeSaleRepository(),
        FakeSessionRepository(session),
        FakeProductRepository(_product()),
    )

    with pytest.raises(InvalidSaleCancellationReasonError):
        service.cancel_sale(employee, session.id, uuid.uuid4(), "  \n ")


def test_create_sale_rejects_wrong_owner_and_terminal() -> None:
    employee = uuid.uuid4()
    session = _session(employee)
    product = _product()
    service = SalesService(
        FakeSaleRepository(),
        FakeSessionRepository(session),
        FakeProductRepository(product),
    )

    with pytest.raises(SessionNotOwnedError):
        service.create_sale(
            uuid.uuid4(),
            session.id,
            session.terminal_id,
            uuid.uuid4(),
            [(product.id, Decimal("1"))],
        )

    with pytest.raises(TerminalMismatchError):
        service.create_sale(
            employee, session.id, "pos-2", uuid.uuid4(), [(product.id, Decimal("1"))]
        )


def test_create_sale_rejects_closed_session() -> None:
    employee = uuid.uuid4()
    session = _session(employee, PosSessionStatus.CLOSED)
    product = _product()
    service = SalesService(
        FakeSaleRepository(),
        FakeSessionRepository(session),
        FakeProductRepository(product),
    )

    with pytest.raises(SessionClosedError):
        service.create_sale(
            employee,
            session.id,
            session.terminal_id,
            uuid.uuid4(),
            [(product.id, Decimal("1"))],
        )


def test_history_forwards_filters_and_cursor_and_keeps_page_size() -> None:
    repository = FakeHistoryRepository()
    created_at = datetime.now(UTC) - timedelta(days=1)
    repository.rows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            pos_session_id=uuid.uuid4(),
            terminal_id="pos-1",
            employee_user_id=uuid.uuid4(),
            status=SaleStatus.COMPLETED,
            total=Decimal("5.00"),
            created_at=created_at,
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            pos_session_id=uuid.uuid4(),
            terminal_id="pos-2",
            employee_user_id=uuid.uuid4(),
            status=SaleStatus.COMPLETED,
            total=Decimal("6.00"),
            created_at=created_at - timedelta(seconds=1),
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            pos_session_id=uuid.uuid4(),
            terminal_id="pos-3",
            employee_user_id=uuid.uuid4(),
            status=SaleStatus.COMPLETED,
            total=Decimal("7.00"),
            created_at=created_at - timedelta(seconds=2),
        ),
    ]
    service = SalesHistoryService(repository)
    filters = SalesFilters(terminal_id="pos-1")

    page = service.list_sales(filters, None, limit=2)

    assert repository.filters == filters
    assert repository.limit == 2
    assert len(page.items) == 2
    assert page.next_cursor is not None


def test_history_handles_tuple_rows_returned_by_repository() -> None:
    created_at = datetime.now(UTC)
    sale = SimpleNamespace(
        id=uuid.uuid4(),
        pos_session_id=uuid.uuid4(),
        terminal_id="pos-1",
        employee_user_id=uuid.uuid4(),
        status=SaleStatus.COMPLETED,
        total=Decimal("12.50"),
        created_at=created_at,
    )
    repository = FakeHistoryRepository()
    repository.rows = [
        (sale, "Jane Admin", Decimal("4.00"), Decimal("12.50")),
    ]
    service = SalesHistoryService(repository)

    page = service.list_sales(SalesFilters(), None, limit=10)

    assert len(page.items) == 1
    assert page.items[0].employee_full_name == "Jane Admin"
    assert page.items[0].total == Decimal("12.50")
    assert page.items[0].income_total == Decimal("4.00")


def test_history_summary_is_database_result_and_cursor_validation_is_strict() -> None:
    repository = FakeHistoryRepository()
    service = SalesHistoryService(repository)

    summary = service.summarize_sales(SalesFilters(session_id=uuid.uuid4()))

    assert summary.sale_count == 2
    assert summary.item_quantity_total == Decimal("3")
    assert summary.revenue_total == Decimal("15.00")
    assert summary.income_total == Decimal("6.00")

    with pytest.raises(InvalidCursorError):
        service.list_sales(SalesFilters(), "not-a-cursor")
    with pytest.raises(InvalidFiltersError):
        service.list_sales(SalesFilters(), None, limit=101)
