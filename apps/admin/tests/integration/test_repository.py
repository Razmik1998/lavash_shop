"""Integration tests against real PostgreSQL."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from exceptions import (
    BarcodeAlreadyExistsError,
    SessionAlreadyActiveError,
    SkuAlreadyExistsError,
    UsernameAlreadyExistsError,
)
from models import (
    CreditCustomer,
    PosSession,
    PosSessionStatus,
    Product,
    Role,
    Sale,
    SaleItem,
    SaleStatus,
    Unit,
    User,
)
from repository import (
    CustomerRepository,
    PosSessionRepository,
    ProductRepository,
    SaleRepository,
    UserRepository,
)


def _make_user(
    username: str, role: Role = Role.EMPLOYEE, full_name: str = "Test User"
) -> User:
    return User(
        id=uuid.uuid4(),
        username=username,
        full_name=full_name,
        hashed_password="hash",
        role=role,
        is_active=True,
    )


def _make_product(
    name: str, sku: str, barcode: str | None = None
) -> Product:
    return Product(
        id=uuid.uuid4(),
        name=name,
        sku=sku,
        barcode=barcode,
        unit=Unit.PIECE,
        cost_price=Decimal("2.00"),
        selling_price=Decimal("3.00"),
        quantity_in_stock=Decimal("5"),
    )


def test_add_and_get_by_username(user_repository: UserRepository) -> None:
    user_repository.add(_make_user("alice"))

    found = user_repository.get_by_username("alice")

    assert found is not None
    assert found.username == "alice"


def test_get_by_username_returns_none_when_missing(
    user_repository: UserRepository,
) -> None:
    assert user_repository.get_by_username("nobody") is None


def test_duplicate_username_raises_domain_exception(
    user_repository: UserRepository,
) -> None:
    user_repository.add(_make_user("bob"))

    with pytest.raises(UsernameAlreadyExistsError):
        user_repository.add(_make_user("bob"))


def test_list_by_role_filters_correctly(user_repository: UserRepository) -> None:
    user_repository.add(_make_user("admin1", role=Role.ADMIN))
    user_repository.add(_make_user("employee1", role=Role.EMPLOYEE))
    user_repository.add(_make_user("employee2", role=Role.EMPLOYEE))

    employees = user_repository.list_by_role(Role.EMPLOYEE)

    assert {u.username for u in employees} == {"employee1", "employee2"}


@pytest.mark.parametrize(
    ("term", "expected_sku"),
    [("salmon", "SAL-001"), ("SAL-002", "SAL-002"), ("99002", "SAL-002")],
)
def test_product_search_matches_name_sku_or_barcode(
    product_repository: ProductRepository, term: str, expected_sku: str
) -> None:
    product_repository.add(_make_product("Fresh Salmon", "SAL-001", "99001"))
    product_repository.add(_make_product("Frozen Tuna", "SAL-002", "99002"))

    products = product_repository.search(term)

    assert [product.sku for product in products] == [expected_sku]


def test_duplicate_product_sku_maps_to_domain_exception(
    product_repository: ProductRepository,
) -> None:
    product_repository.add(_make_product("First", "DUP-001"))

    with pytest.raises(SkuAlreadyExistsError):
        product_repository.add(_make_product("Second", "DUP-001"))


def test_duplicate_product_barcode_maps_to_domain_exception(
    product_repository: ProductRepository,
) -> None:
    product_repository.add(_make_product("First", "SKU-001", "12345"))

    with pytest.raises(BarcodeAlreadyExistsError):
        product_repository.add(_make_product("Second", "SKU-002", "12345"))


class TestPosSessionRepository:
    def test_create_starts_an_active_session(
        self,
        user_repository: UserRepository,
        pos_session_repository: PosSessionRepository,
    ) -> None:
        user = user_repository.add(_make_user("cashier1"))

        session = pos_session_repository.create(user.id, "pos-1")

        assert session.status is PosSessionStatus.ACTIVE
        assert session.terminal_id == "pos-1"
        assert session.user_id == user.id
        assert session.closed_at is None

    def test_create_rejects_duplicate_active_session_for_same_terminal(
        self,
        user_repository: UserRepository,
        pos_session_repository: PosSessionRepository,
    ) -> None:
        user1 = user_repository.add(_make_user("cashier1"))
        user2 = user_repository.add(_make_user("cashier2"))
        pos_session_repository.create(user1.id, "pos-1")

        with pytest.raises(SessionAlreadyActiveError):
            pos_session_repository.create(user2.id, "pos-1")

    def test_create_allows_new_active_session_after_terminal_closed(
        self,
        user_repository: UserRepository,
        pos_session_repository: PosSessionRepository,
    ) -> None:
        user1 = user_repository.add(_make_user("cashier1"))
        user2 = user_repository.add(_make_user("cashier2"))
        first = pos_session_repository.create(user1.id, "pos-1")
        pos_session_repository.close(first.id)

        second = pos_session_repository.create(user2.id, "pos-1")

        assert second.status is PosSessionStatus.ACTIVE

    def test_close_persists_closed_at_and_status(
        self,
        user_repository: UserRepository,
        pos_session_repository: PosSessionRepository,
    ) -> None:
        user = user_repository.add(_make_user("cashier1"))
        session = pos_session_repository.create(user.id, "pos-1")

        closed = pos_session_repository.close(session.id)

        assert closed is not None
        assert closed.status is PosSessionStatus.CLOSED
        assert closed.closed_at is not None

        reloaded = pos_session_repository.get_by_id(session.id)
        assert reloaded is not None
        assert reloaded.status is PosSessionStatus.CLOSED
        assert reloaded.closed_at is not None

    def test_close_is_idempotent(
        self,
        user_repository: UserRepository,
        pos_session_repository: PosSessionRepository,
    ) -> None:
        user = user_repository.add(_make_user("cashier1"))
        session = pos_session_repository.create(user.id, "pos-1")

        first_close = pos_session_repository.close(session.id)
        second_close = pos_session_repository.close(session.id)

        assert first_close is not None
        assert second_close is not None
        assert first_close.closed_at == second_close.closed_at

    def test_close_returns_none_for_unknown_session(
        self, pos_session_repository: PosSessionRepository
    ) -> None:
        assert pos_session_repository.close(uuid.uuid4()) is None

    def test_get_active_by_terminal_returns_none_after_close(
        self,
        user_repository: UserRepository,
        pos_session_repository: PosSessionRepository,
    ) -> None:
        user = user_repository.add(_make_user("cashier1"))
        session = pos_session_repository.create(user.id, "pos-1")
        pos_session_repository.close(session.id)

        assert pos_session_repository.get_active_by_terminal("pos-1") is None

    def test_get_active_by_terminal_returns_active_session(
        self,
        user_repository: UserRepository,
        pos_session_repository: PosSessionRepository,
    ) -> None:
        user = user_repository.add(_make_user("cashier1"))
        session = pos_session_repository.create(user.id, "pos-1")

        active = pos_session_repository.get_active_by_terminal("pos-1")

        assert active is not None
        assert active.id == session.id

    def test_update_heartbeat_refreshes_connection_timestamps(
        self,
        user_repository: UserRepository,
        pos_session_repository: PosSessionRepository,
    ) -> None:
        user = user_repository.add(_make_user("cashier1"))
        session = pos_session_repository.create(user.id, "pos-1")

        updated = pos_session_repository.update_heartbeat(session.id)

        assert updated is not None
        assert updated.last_connected_at >= session.last_connected_at
        assert updated.last_activity_at >= session.last_activity_at

    def test_disconnect_sets_last_connected_at_in_past_while_status_stays_active(
        self,
        user_repository: UserRepository,
        pos_session_repository: PosSessionRepository,
    ) -> None:
        user = user_repository.add(_make_user("cashier1"))
        session = pos_session_repository.create(user.id, "pos-1")

        disconnected = pos_session_repository.disconnect(session.id)

        assert disconnected is not None
        assert disconnected.status is PosSessionStatus.ACTIVE
        assert disconnected.last_connected_at == datetime.fromtimestamp(0, UTC)

        active = pos_session_repository.get_active_by_terminal("pos-1")
        assert active is not None
        assert active.id == session.id

    def test_disconnect_returns_none_for_unknown_session(
        self, pos_session_repository: PosSessionRepository
    ) -> None:
        assert pos_session_repository.disconnect(uuid.uuid4()) is None

    def test_list_all_with_user_names_returns_joined_full_name(
        self,
        user_repository: UserRepository,
        pos_session_repository: PosSessionRepository,
    ) -> None:
        user = user_repository.add(_make_user("cashier1", full_name="Cashier One"))
        pos_session_repository.create(user.id, "pos-1")

        rows = pos_session_repository.list_all_with_user_names()

        assert len(rows) == 1
        session, full_name = rows[0]
        assert session.terminal_id == "pos-1"
        assert full_name == "Cashier One"


class TestPosSessionRepositoryConcurrency:
    def test_concurrent_start_session_for_same_terminal_allows_only_one_winner(
        self,
        user_repository: UserRepository,
        pos_session_repository: PosSessionRepository,
    ) -> None:
        """Two near-simultaneous start_session calls for the same
        terminal_id (matching the backend enforcement rule in
        models.py's partial unique index) must let exactly one succeed
        and force the other to observe SessionAlreadyActiveError,
        regardless of thread scheduling."""
        user1 = user_repository.add(_make_user("cashier1"))
        user2 = user_repository.add(_make_user("cashier2"))

        results: list[object] = []
        start_barrier = threading.Barrier(2)

        def _attempt(user_id: uuid.UUID) -> None:
            start_barrier.wait()
            try:
                results.append(pos_session_repository.create(user_id, "pos-1"))
            except SessionAlreadyActiveError as exc:
                results.append(exc)

        threads = [
            threading.Thread(target=_attempt, args=(user1.id,)),
            threading.Thread(target=_attempt, args=(user2.id,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        successes = [r for r in results if isinstance(r, PosSession)]
        failures = [r for r in results if isinstance(r, SessionAlreadyActiveError)]
        assert len(successes) == 1
        assert len(failures) == 1


def test_create_sale_preserves_transaction_snapshot_and_creation_audit(
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pos_session_repository: PosSessionRepository,
    sale_repository: SaleRepository,
) -> None:
    employee = user_repository.add(_make_user("cashier-sale"))
    product = product_repository.add(_make_product("Coffee", "COF-001"))
    session = pos_session_repository.create(employee.id, "pos-1")

    sale = sale_repository.create_sale(
        session.id,
        employee.id,
        session.terminal_id,
        uuid.uuid4(),
        [(product, Decimal("2"), Decimal("3.00"), Decimal("6.00"))],
    )

    product.name = "Renamed Coffee"
    detail = sale_repository.get_detail(sale.id)

    assert detail is not None
    stored_sale, items, audits = detail
    assert stored_sale.pos_session_id == session.id
    assert items[0].product_name == "Coffee"
    assert items[0].unit_price == Decimal("3.00")
    assert items[0].line_total == Decimal("6.00")
    assert len(audits) == 1
    assert audits[0].event_type == "created"
    assert audits[0].new_value == {"total": "6.00"}


def test_cancelled_sale_keeps_reason_and_shows_latest_saved_items(
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pos_session_repository: PosSessionRepository,
    sale_repository: SaleRepository,
    session_factory: sessionmaker[Session],
) -> None:
    sale_id, user_id, _, _ = _completed_sale(
        user_repository, product_repository, pos_session_repository, sale_repository
    )
    sale_repository.unlock_sale(sale_id, user_id, "secret")
    sale_repository.cancel_unlocked_sale(
        sale_id, user_id, "Duplicate order entered at the terminal"
    )

    with session_factory() as session:
        sale = session.get(Sale, sale_id)
        assert sale is not None
        for item in session.scalars(
            select(SaleItem).where(SaleItem.sale_id == sale_id)
        ):
            item.is_active = False
        session.commit()

    result = sale_repository.get_detail(sale_id)

    assert result is not None
    cancelled_sale, items, audits = result
    assert cancelled_sale.status is SaleStatus.CANCELLED
    assert (
        cancelled_sale.cancellation_reason
        == "Duplicate order entered at the terminal"
    )
    assert {item.product_name for item in items} == {"Tea", "Milk"}
    assert audits[-1].new_value == {
        "cancellation_reason": "Duplicate order entered at the terminal"
    }


def _completed_sale(
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pos_session_repository: PosSessionRepository,
    sale_repository: SaleRepository,
) -> tuple[uuid.UUID, uuid.UUID, Product, Product]:
    employee = user_repository.add(_make_user("cashier-edit"))
    first = product_repository.add(_make_product("Tea", "TEA-001"))
    second = product_repository.add(_make_product("Milk", "MLK-001"))
    session = pos_session_repository.create(employee.id, "pos-1")
    sale = sale_repository.create_sale(
        session.id,
        employee.id,
        session.terminal_id,
        uuid.uuid4(),
        [
            (first, Decimal("2"), Decimal("3.00"), Decimal("6.00")),
            (second, Decimal("1"), Decimal("3.00"), Decimal("3.00")),
        ],
    )
    sale_repository.create_unlock_key("k", "secret", employee.id)
    return sale.id, employee.id, first, second


def test_edit_without_changes_keeps_items_and_logs_unchanged(
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pos_session_repository: PosSessionRepository,
    sale_repository: SaleRepository,
) -> None:
    sale_id, user_id, first, second = _completed_sale(
        user_repository, product_repository, pos_session_repository, sale_repository
    )
    sale_repository.unlock_sale(sale_id, user_id, "secret")
    sale_repository.reconfirm_sale(
        sale_id,
        user_id,
        [
            (first, Decimal("2"), Decimal("3.00"), Decimal("6.00")),
            (second, Decimal("1"), Decimal("3.00"), Decimal("3.00")),
        ],
    )
    _, items, _ = sale_repository.get_detail(sale_id)  # type: ignore[misc]
    revisions, changes = sale_repository.get_history(sale_id)
    assert len(items) == 2
    assert changes == []
    assert revisions[-1][0].outcome == "completed_unchanged"


def test_edit_updates_in_place_and_soft_deletes_removed_lines(
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pos_session_repository: PosSessionRepository,
    sale_repository: SaleRepository,
) -> None:
    sale_id, user_id, first, _second = _completed_sale(
        user_repository, product_repository, pos_session_repository, sale_repository
    )
    sale_repository.unlock_sale(sale_id, user_id, "secret")
    sale_repository.reconfirm_sale(
        sale_id,
        user_id,
        [(first, Decimal("4"), Decimal("3.00"), Decimal("12.00"))],
    )
    sale, items, _ = sale_repository.get_detail(sale_id)  # type: ignore[misc]
    _, changes = sale_repository.get_history(sale_id)
    assert [i.quantity for i in items] == [Decimal("4")]
    assert sale.total == Decimal("12.00")
    assert sorted(c.action for c, _ in changes) == ["deleted", "edited"]


def _credit_customer(
    session_factory: sessionmaker[Session], first_name: str, phone: str
) -> uuid.UUID:
    customer = CreditCustomer(first_name=first_name, last_name="Test", phone=phone)
    with session_factory() as session:
        session.add(customer)
        session.commit()
        return customer.id


def test_edit_logs_payment_type_and_customer_changes(
    session_factory: sessionmaker[Session],
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pos_session_repository: PosSessionRepository,
    sale_repository: SaleRepository,
) -> None:
    sale_id, user_id, first, _second = _completed_sale(
        user_repository, product_repository, pos_session_repository, sale_repository
    )
    anna = _credit_customer(session_factory, "Anna", "111")
    boris = _credit_customer(session_factory, "Boris", "222")
    lines = [(first, Decimal("2"), Decimal("3.00"), Decimal("6.00"))]

    for customer_id in (anna, boris, None):
        sale_repository.unlock_sale(sale_id, user_id, "secret")
        sale_repository.reconfirm_sale(sale_id, user_id, lines, customer_id)

    _, _, audits = sale_repository.get_detail(sale_id)  # type: ignore[misc]
    payment = [a for a in audits if a.event_type == "PAYMENT_TYPE_CHANGED"]
    assert [(a.old_value, a.new_value) for a in payment] == [
        ({"payment": "cash"}, {"payment": "credit", "customer": "Anna Test"}),
        (
            {"payment": "credit", "customer": "Anna Test"},
            {"payment": "credit", "customer": "Boris Test"},
        ),
        ({"payment": "credit", "customer": "Boris Test"}, {"payment": "cash"}),
    ]


def test_cancelling_completed_credit_sale_restores_stock_and_debt(
    session_factory: sessionmaker[Session],
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pos_session_repository: PosSessionRepository,
    sale_repository: SaleRepository,
) -> None:
    employee = user_repository.add(_make_user("cashier-cancel"))
    product = product_repository.add(_make_product("Tea", "TEA-777"))
    session = pos_session_repository.create(employee.id, "pos-1")
    customer_id = _credit_customer(session_factory, "Ann", "+37400000001")
    sale = sale_repository.create_sale(
        session.id,
        employee.id,
        session.terminal_id,
        uuid.uuid4(),
        [(product, Decimal("2"), Decimal("3.00"), Decimal("6.00"))],
        customer_id,
    )
    with session_factory() as db:
        db_product = db.get(Product, product.id)
        assert db_product is not None
        db_product.quantity_in_stock = Decimal("3")
        db.commit()
    customers = CustomerRepository(session_factory)
    assert _debt_of(customers, customer_id) == Decimal("6.00")

    sale_repository.cancel_unlocked_sale(sale.id, employee.id, "Mistake")

    with session_factory() as db:
        db_product = db.get(Product, product.id)
        assert db_product is not None
        assert db_product.quantity_in_stock == Decimal("5")
        assert db.get(Sale, sale.id).status is SaleStatus.CANCELLED  # type: ignore[union-attr]
    assert _debt_of(customers, customer_id) == Decimal("0")


def _debt_of(customers: CustomerRepository, customer_id: uuid.UUID) -> Decimal:
    return customers.get(customer_id).current_debt


def test_unlocking_credit_sale_removes_debt_until_reconfirmed(
    session_factory: sessionmaker[Session],
    user_repository: UserRepository,
    product_repository: ProductRepository,
    pos_session_repository: PosSessionRepository,
    sale_repository: SaleRepository,
) -> None:
    employee = user_repository.add(_make_user("cashier-unlock"))
    product = product_repository.add(_make_product("Tea", "TEA-888"))
    session = pos_session_repository.create(employee.id, "pos-1")
    customer_id = _credit_customer(session_factory, "Bob", "+37400000002")
    sale = sale_repository.create_sale(
        session.id,
        employee.id,
        session.terminal_id,
        uuid.uuid4(),
        [(product, Decimal("2"), Decimal("3.00"), Decimal("6.00"))],
        customer_id,
    )
    sale_repository.create_unlock_key("k", "secret", employee.id)
    customers = CustomerRepository(session_factory)
    assert _debt_of(customers, customer_id) == Decimal("6.00")

    sale_repository.unlock_sale(sale.id, employee.id, "secret")
    assert _debt_of(customers, customer_id) == Decimal("0")

    sale_repository.reconfirm_sale(
        sale.id,
        employee.id,
        [(product, Decimal("3"), Decimal("3.00"), Decimal("9.00"))],
        customer_id,
    )
    assert _debt_of(customers, customer_id) == Decimal("9.00")
