from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from exceptions import (
    AuthenticationError,
    SessionAlreadyActiveError,
    SessionClosedError,
    SessionNotFoundError,
)
from models import PosSession, PosSessionStatus, Product, Role, Unit, User
from security import hash_password
from services import (
    HEARTBEAT_TIMEOUT_SECONDS,
    AuthService,
    EmployeeService,
    PosSessionService,
    PurchaseLineInput,
    PurchaseService,
    ProductService,
)


class FakeUserRepository:
    def __init__(self) -> None:
        self._users_by_username: dict[str, User] = {}

    def seed(self, user: User) -> None:
        self._users_by_username[user.username] = user

    def get_by_username(self, username: str) -> User | None:
        return self._users_by_username.get(username)

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        for user in self._users_by_username.values():
            if user.id == user_id:
                return user
        return None

    def list_by_role(self, role: Role) -> list[User]:
        return [u for u in self._users_by_username.values() if u.role is role]

    def add(self, user: User) -> User:
        self._users_by_username[user.username] = user
        return user


class FakePosSessionRepository:
    """In-memory fake for `PosSessionRepository`, mirroring its
    create/close/heartbeat idempotency and one-active-per-terminal rule
    so `PosSessionService` can be unit-tested without a real database."""

    def __init__(self) -> None:
        self._sessions: dict[uuid.UUID, PosSession] = {}

    def get_active_by_terminal(self, terminal_id: str) -> PosSession | None:
        for session in self._sessions.values():
            if (
                session.terminal_id == terminal_id
                and session.status is PosSessionStatus.ACTIVE
            ):
                return session
        return None

    def get_by_id(self, session_id: uuid.UUID) -> PosSession | None:
        return self._sessions.get(session_id)

    def create(
        self,
        user_id: uuid.UUID,
        terminal_id: str,
        opening_cash: Decimal = Decimal("0"),
    ) -> PosSession:
        if self.get_active_by_terminal(terminal_id) is not None:
            raise SessionAlreadyActiveError(terminal_id)
        now = datetime.now(UTC)
        session = PosSession(
            id=uuid.uuid4(),
            terminal_id=terminal_id,
            user_id=user_id,
            status=PosSessionStatus.ACTIVE,
            started_at=now,
            closed_at=None,
            last_connected_at=now,
            last_activity_at=now,
            opening_cash=opening_cash,
            created_at=now,
            updated_at=now,
        )
        self._sessions[session.id] = session
        return session

    def close(
        self,
        session_id: uuid.UUID,
        closing_cash: Decimal | None = None,
        cash_difference: Decimal | None = None,
    ) -> PosSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.status is PosSessionStatus.CLOSED:
            return session
        session.closing_cash = closing_cash
        session.cash_difference = cash_difference
        session.status = PosSessionStatus.CLOSED
        session.closed_at = datetime.now(UTC)
        return session

    def disconnect(self, session_id: uuid.UUID) -> PosSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.status is PosSessionStatus.CLOSED:
            return session
        session.last_connected_at = datetime.fromtimestamp(0, UTC)
        return session

    def update_heartbeat(self, session_id: uuid.UUID) -> PosSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        now = datetime.now(UTC)
        session.last_connected_at = now
        session.last_activity_at = now
        return session

    def list_all(self) -> list[PosSession]:
        return list(self._sessions.values())

    def list_all_with_user_names(self) -> list[tuple[PosSession, str]]:
        raise NotImplementedError


class FakeProductRepository:
    def __init__(self, products: list[Product] | None = None) -> None:
        self._products = list(products or [])

    def add(self, product: Product) -> Product:
        self._products.append(product)
        return product

    def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        for product in self._products:
            if product.id == product_id:
                return product
        return None

    def list_all(self) -> list[Product]:
        return list(self._products)

    def list_by_unit(self, unit: Unit) -> list[Product]:
        return [product for product in self._products if product.unit is unit]

    def list_active(self) -> list[Product]:
        return [product for product in self._products if product.is_active]

    def search(self, term: str) -> list[Product]:
        return [product for product in self._products if term in product.name]

    def update(self, product: Product) -> Product:
        for index, existing in enumerate(self._products):
            if existing.id == product.id:
                self._products[index] = product
                return product
        self._products.append(product)
        return product

    def get_latest_sku(self) -> str | None:
        if not self._products:
            return None
        return max((product.sku for product in self._products), key=lambda sku: sku)


def _make_user(
    username: str, password: str, role: Role, is_active: bool = True
) -> User:
    return User(
        id=uuid.uuid4(),
        username=username,
        full_name="Someone",
        hashed_password=hash_password(password),
        role=role,
        is_active=is_active,
    )


class TestAuthService:
    def test_login_succeeds_with_correct_credentials_and_role(self) -> None:
        repo = FakeUserRepository()
        repo.seed(_make_user("admin", "secret", Role.ADMIN))
        auth_service = AuthService(repo)

        user = auth_service.login("admin", "secret", Role.ADMIN)

        assert user.username == "admin"

    def test_login_rejects_wrong_password(self) -> None:
        repo = FakeUserRepository()
        repo.seed(_make_user("admin", "secret", Role.ADMIN))
        auth_service = AuthService(repo)

        with pytest.raises(AuthenticationError):
            auth_service.login("admin", "wrong", Role.ADMIN)

    def test_login_rejects_unknown_username(self) -> None:
        auth_service = AuthService(FakeUserRepository())

        with pytest.raises(AuthenticationError):
            auth_service.login("ghost", "secret", Role.ADMIN)

    def test_login_rejects_wrong_role(self) -> None:
        repo = FakeUserRepository()
        repo.seed(_make_user("employee1", "secret", Role.EMPLOYEE))
        auth_service = AuthService(repo)

        with pytest.raises(AuthenticationError):
            auth_service.login("employee1", "secret", Role.ADMIN)

    def test_login_rejects_inactive_user(self) -> None:
        repo = FakeUserRepository()
        repo.seed(_make_user("admin", "secret", Role.ADMIN, is_active=False))
        auth_service = AuthService(repo)

        with pytest.raises(AuthenticationError):
            auth_service.login("admin", "secret", Role.ADMIN)


class TestEmployeeService:
    def test_create_employee_stores_hashed_password(self) -> None:
        repo = FakeUserRepository()
        service = EmployeeService(repo)

        employee = service.create_employee("newhire", "New Hire", "temp-pass")

        assert employee.role is Role.EMPLOYEE
        assert employee.hashed_password != "temp-pass"

    def test_list_employees_excludes_admins(self) -> None:
        repo = FakeUserRepository()
        repo.seed(_make_user("admin", "secret", Role.ADMIN))
        service = EmployeeService(repo)
        service.create_employee("emp1", "Employee One", "pw")

        employees = service.list_employees()

        assert [e.username for e in employees] == ["emp1"]


def _make_product(
    quantity: str, threshold: str | None, cost: str, selling: str
) -> Product:
    return Product(
        id=uuid.uuid4(),
        name="Salmon",
        sku="SAL-001",
        unit=Unit.KG,
        cost_price=Decimal(cost),
        selling_price=Decimal(selling),
        quantity_in_stock=Decimal(quantity),
        low_stock_threshold=(
            None if threshold is None else Decimal(threshold)
        ),
    )


@pytest.mark.parametrize(
    ("quantity", "threshold", "expected"),
    [
        ("0", "2", "out_of_stock"),
        ("2", "2", "low_stock"),
        ("3", "2", "in_stock"),
    ],
)
def test_product_service_computes_stock_status(
    quantity: str, threshold: str, expected: str
) -> None:
    product = _make_product(quantity, threshold, "8.00", "10.00")
    service = ProductService(FakeProductRepository([product]))

    result = service.list_products()[0]

    assert result.stock_status == expected  # type: ignore[attr-defined]


def test_product_service_computes_decimal_profit_margin() -> None:
    product = _make_product("4", None, "7.50", "10.00")
    service = ProductService(FakeProductRepository([product]))

    result = service.list_products()[0]

    assert result.profit_margin == Decimal("25.00")  # type: ignore[attr-defined]


def test_new_products_are_sellable_by_default() -> None:
    product = ProductService(FakeProductRepository([])).create_product(
        name="Fish",
        sku="FISH-1",
        barcode=None,
        unit=Unit.KG,
        cost_price=Decimal("2.00"),
        selling_price=Decimal("3.00"),
        quantity_in_stock=Decimal("1"),
    )

    assert product.is_for_sale is True


def test_product_service_creates_internal_inventory_product() -> None:
    service = ProductService(FakeProductRepository([]))

    product = service.create_product(
        name="Salt",
        sku="SALT-001",
        barcode=None,
        unit=Unit.KG,
        cost_price=Decimal("2.50"),
        selling_price=None,
        minimum_price=None,
        quantity_in_stock=Decimal("4"),
        is_for_sale=False,
    )

    assert product.is_for_sale is False
    assert product.cost_price == Decimal("2.50")
    assert product.selling_price is None
    assert product.minimum_price is None
    assert product.quantity_in_stock == Decimal("4")


def test_internal_product_purchase_does_not_require_selling_price() -> None:
    product = Product(
        id=uuid.uuid4(),
        name="Cooking Oil",
        sku="OIL-001",
        unit=Unit.LITER,
        cost_price=Decimal("4.25"),
        selling_price=None,
        quantity_in_stock=Decimal("0"),
        is_active=True,
        is_for_sale=False,
    )

    class FakePurchaseRepository:
        saved_items = []

        def create_draft(self, purchase, items):  # type: ignore[no-untyped-def]
            self.saved_items = items
            return purchase

    purchase_repository = FakePurchaseRepository()
    service = PurchaseService(
        purchase_repository, FakeProductRepository([product])
    )

    service.create_draft(
        uuid.uuid4(),
        datetime.now(UTC),
        None,
        [PurchaseLineInput(product.id, Decimal("2"), Decimal("4.25"), None)],
    )

    assert purchase_repository.saved_items[0].selling_price is None
    assert purchase_repository.saved_items[0].markup_percentage == Decimal("0")


def test_product_service_restricts_barbecue_parent_values() -> None:
    repo = FakeProductRepository([])
    service = ProductService(repo)

    product = service.create_product(
        name="Barbecue",
        sku="BBQ-001",
        barcode=None,
        unit=Unit.BARBECUE,
        cost_price=Decimal("1500"),
        selling_price=Decimal("5000"),
        quantity_in_stock=Decimal("25"),
        low_stock_threshold=Decimal("5"),
        is_active=True,
        parent_product_id=None,
    )

    assert product.unit is Unit.BARBECUE
    assert product.cost_price is None
    assert product.selling_price is None
    assert product.quantity_in_stock is None
    assert product.low_stock_threshold is None


def test_product_service_rejects_self_parent_and_multi_level_hierarchies() -> None:
    repo = FakeProductRepository([])
    service = ProductService(repo)
    parent = service.create_product(
        name="Barbecue",
        sku="BBQ-001",
        barcode=None,
        unit=Unit.BARBECUE,
        cost_price=None,
        selling_price=None,
        quantity_in_stock=None,
        low_stock_threshold=None,
        is_active=True,
        parent_product_id=None,
    )
    child = service.create_product(
        name="Barbecue Fish",
        sku="BBQ-FISH",
        barcode=None,
        unit=Unit.KG,
        cost_price=Decimal("12.50"),
        selling_price=Decimal("18.00"),
        quantity_in_stock=Decimal("10"),
        low_stock_threshold=Decimal("2"),
        is_active=True,
        parent_product_id=parent.id,
    )

    with pytest.raises(ValueError):
        service.update_product(
            child.id,
            name="Barbecue Fish",
            sku="BBQ-FISH-2",
            barcode=None,
            unit=Unit.KG,
            cost_price=Decimal("12.50"),
            selling_price=Decimal("18.00"),
            quantity_in_stock=Decimal("10"),
            low_stock_threshold=Decimal("2"),
            is_active=True,
            parent_product_id=child.id,
        )

    with pytest.raises(ValueError):
        service.update_product(
            parent.id,
            name="Barbecue",
            sku="BBQ-001",
            barcode=None,
            unit=Unit.BARBECUE,
            cost_price=None,
            selling_price=None,
            quantity_in_stock=None,
            low_stock_threshold=None,
            is_active=True,
            parent_product_id=child.id,
        )


def test_list_barbecue_products_for_sync_returns_one_dto_per_child() -> None:
    repo = FakeProductRepository([])
    service = ProductService(repo)
    parent = service.create_product(
        name="Barbecue",
        sku="BBQ-001",
        barcode=None,
        unit=Unit.BARBECUE,
        cost_price=None,
        selling_price=None,
        quantity_in_stock=None,
        low_stock_threshold=None,
        is_active=True,
        parent_product_id=None,
    )
    service.create_product(
        name="Pork skewer",
        sku="BBQ-001-1",
        barcode=None,
        unit=Unit.KG,
        cost_price=Decimal("10.00"),
        selling_price=Decimal("1500.00"),
        quantity_in_stock=Decimal("5"),
        low_stock_threshold=None,
        is_active=True,
        parent_product_id=parent.id,
    )
    service.create_product(
        name="Chicken skewer",
        sku="BBQ-001-2",
        barcode=None,
        unit=Unit.KG,
        cost_price=Decimal("8.00"),
        selling_price=Decimal("2000.00"),
        quantity_in_stock=Decimal("5"),
        low_stock_threshold=None,
        is_active=True,
        parent_product_id=parent.id,
    )
    service.create_product(
        name="Standalone",
        sku="STD-001",
        barcode=None,
        unit=Unit.PIECE,
        cost_price=Decimal("1.00"),
        selling_price=Decimal("2.00"),
        quantity_in_stock=Decimal("5"),
        low_stock_threshold=None,
        is_active=True,
        parent_product_id=None,
    )

    dtos = service.list_barbecue_products_for_sync()

    assert len(dtos) == 2
    assert {dto.name for dto in dtos} == {
        "Barbecue -> Pork skewer",
        "Barbecue -> Chicken skewer",
    }
    assert {dto.selling_price for dto in dtos} == {
        Decimal("1500.00"),
        Decimal("2000.00"),
    }
    assert all(dto.is_active for dto in dtos)


def test_list_barbecue_products_for_sync_treats_missing_child_price_as_zero() -> None:
    repo = FakeProductRepository([])
    service = ProductService(repo)
    parent = service.create_product(
        name="Barbecue",
        sku="BBQ-001",
        barcode=None,
        unit=Unit.BARBECUE,
        cost_price=None,
        selling_price=None,
        quantity_in_stock=None,
        low_stock_threshold=None,
        is_active=True,
        parent_product_id=None,
    )
    service.create_product(
        name="Priceless skewer",
        sku="BBQ-001-1",
        barcode=None,
        unit=Unit.KG,
        cost_price=None,
        selling_price=None,
        quantity_in_stock=None,
        low_stock_threshold=None,
        is_active=True,
        parent_product_id=parent.id,
    )

    dtos = service.list_barbecue_products_for_sync()

    assert len(dtos) == 1
    assert dtos[0].selling_price == Decimal("0")


class TestPosSessionService:
    def _service(
        self, user_repo: FakeUserRepository | None = None
    ) -> tuple[PosSessionService, FakeUserRepository, FakePosSessionRepository]:
        users = user_repo or FakeUserRepository()
        sessions = FakePosSessionRepository()
        return PosSessionService(sessions, users), users, sessions

    def test_start_session_rejects_unknown_user_id(self) -> None:
        service, _users, _sessions = self._service()

        with pytest.raises(AuthenticationError):
            service.start_session(uuid.uuid4(), "pos-1")

    def test_start_session_rejects_inactive_user(self) -> None:
        users = FakeUserRepository()
        employee = _make_user("emp1", "pw", Role.EMPLOYEE, is_active=False)
        users.seed(employee)
        service, _users, _sessions = self._service(users)

        with pytest.raises(AuthenticationError):
            service.start_session(employee.id, "pos-1")

    def test_start_session_rejects_non_employee_user(self) -> None:
        users = FakeUserRepository()
        admin = _make_user("admin", "pw", Role.ADMIN)
        users.seed(admin)
        service, _users, _sessions = self._service(users)

        with pytest.raises(AuthenticationError):
            service.start_session(admin.id, "pos-1")

    def test_start_session_creates_active_session_for_valid_employee(self) -> None:
        users = FakeUserRepository()
        employee = _make_user("emp1", "pw", Role.EMPLOYEE)
        users.seed(employee)
        service, _users, _sessions = self._service(users)

        session = service.start_session(employee.id, "pos-1")

        assert session.status is PosSessionStatus.ACTIVE
        assert session.connection_status == "connected"  # type: ignore[attr-defined]

    def test_start_session_rejects_when_terminal_already_has_active_session(
        self,
    ) -> None:
        users = FakeUserRepository()
        employee1 = _make_user("emp1", "pw", Role.EMPLOYEE)
        employee2 = _make_user("emp2", "pw", Role.EMPLOYEE)
        users.seed(employee1)
        users.seed(employee2)
        service, _users, _sessions = self._service(users)
        service.start_session(employee1.id, "pos-1")

        with pytest.raises(SessionAlreadyActiveError):
            service.start_session(employee2.id, "pos-1")

    def test_close_session_is_idempotent(self) -> None:
        users = FakeUserRepository()
        employee = _make_user("emp1", "pw", Role.EMPLOYEE)
        users.seed(employee)
        service, _users, _sessions = self._service(users)
        session = service.start_session(employee.id, "pos-1")

        first_close = service.close_session(session.id)
        second_close = service.close_session(session.id)

        assert first_close.status is PosSessionStatus.CLOSED
        assert second_close.status is PosSessionStatus.CLOSED

    def test_close_session_raises_for_unknown_session(self) -> None:
        service, _users, _sessions = self._service()

        with pytest.raises(SessionNotFoundError):
            service.close_session(uuid.uuid4())

    def test_heartbeat_raises_session_not_found_for_unknown_session(self) -> None:
        service, _users, _sessions = self._service()

        with pytest.raises(SessionNotFoundError):
            service.heartbeat(uuid.uuid4())

    def test_heartbeat_raises_session_closed_for_closed_session(self) -> None:
        users = FakeUserRepository()
        employee = _make_user("emp1", "pw", Role.EMPLOYEE)
        users.seed(employee)
        service, _users, _sessions = self._service(users)
        session = service.start_session(employee.id, "pos-1")
        service.close_session(session.id)

        with pytest.raises(SessionClosedError):
            service.heartbeat(session.id)

    def test_heartbeat_on_active_session_returns_connected(self) -> None:
        users = FakeUserRepository()
        employee = _make_user("emp1", "pw", Role.EMPLOYEE)
        users.seed(employee)
        service, _users, _sessions = self._service(users)
        session = service.start_session(employee.id, "pos-1")

        updated = service.heartbeat(session.id)

        assert updated.connection_status == "connected"  # type: ignore[attr-defined]

    def test_get_current_session_returns_none_when_no_active_session(self) -> None:
        service, _users, _sessions = self._service()

        assert service.get_current_session("pos-1") is None

    @pytest.mark.parametrize(
        ("seconds_since_last_connected", "expected_status"),
        [
            (HEARTBEAT_TIMEOUT_SECONDS - 1, "connected"),
            (HEARTBEAT_TIMEOUT_SECONDS + 1, "disconnected"),
        ],
    )
    def test_connection_status_crosses_heartbeat_timeout_boundary(
        self, seconds_since_last_connected: int, expected_status: str
    ) -> None:
        users = FakeUserRepository()
        employee = _make_user("emp1", "pw", Role.EMPLOYEE)
        users.seed(employee)
        service, _users, sessions = self._service(users)
        session = service.start_session(employee.id, "pos-1")
        # Inject a stale last_connected_at directly on the fake
        # repository's stored row rather than sleeping in the test.
        stored = sessions.get_by_id(session.id)
        assert stored is not None
        stored.last_connected_at = datetime.now(UTC) - timedelta(
            seconds=seconds_since_last_connected
        )

        current = service.get_current_session("pos-1")

        assert current is not None
        assert current.connection_status == expected_status  # type: ignore[attr-defined]

    def test_closed_session_always_reports_disconnected(self) -> None:
        users = FakeUserRepository()
        employee = _make_user("emp1", "pw", Role.EMPLOYEE)
        users.seed(employee)
        service, _users, _sessions = self._service(users)
        session = service.start_session(employee.id, "pos-1")

        closed = service.close_session(session.id)

        assert closed.connection_status == "disconnected"  # type: ignore[attr-defined]

    def test_disconnect_marks_active_session_disconnected_while_status_remains_active(
        self,
    ) -> None:
        users = FakeUserRepository()
        employee = _make_user("emp1", "pw", Role.EMPLOYEE)
        users.seed(employee)
        service, _users, _sessions = self._service(users)
        session = service.start_session(employee.id, "pos-1")

        disconnected = service.disconnect(session.id)

        assert disconnected.status is PosSessionStatus.ACTIVE
        assert disconnected.connection_status == "disconnected"  # type: ignore[attr-defined]

    def test_disconnect_unknown_session_raises(self) -> None:
        service, _users, _sessions = self._service()

        with pytest.raises(SessionNotFoundError):
            service.disconnect(uuid.uuid4())
