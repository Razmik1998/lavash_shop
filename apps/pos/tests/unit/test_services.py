from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from exceptions import AdminUnavailableError, AuthenticationError
from models import Role, User
from networking.protocol import ProductPayload, SessionPayload
from services import AuthService, PosSessionService, ProductService


def _make_user(username: str) -> User:
    return User(
        id=uuid.uuid4(),
        username=username,
        full_name="Someone",
        role=Role.EMPLOYEE,
        is_active=True,
    )


def _make_session() -> SessionPayload:
    return SessionPayload(
        id=str(uuid.uuid4()),
        terminal_id="pos-1",
        user_id=str(uuid.uuid4()),
        status="active",
        connection_status="connected",
        started_at="2026-01-01T00:00:00+00:00",
        closed_at=None,
        last_connected_at="2026-01-01T00:00:00+00:00",
        last_activity_at="2026-01-01T00:00:00+00:00",
    )


class FakeAdminConnection:
    """Fake AdminConnection: AuthService must depend only on this
    interface, never on socket/json directly."""

    def __init__(
        self,
        user: User | None = None,
        session: SessionPayload | None = None,
        error: Exception | None = None,
        products: list[ProductPayload] | None = None,
    ) -> None:
        self._user = user
        self._session = session
        self._error = error
        self._products = products or []

    def is_available(self) -> bool:
        return self._error is None

    def login(self, username: str, password: str) -> User:
        if self._error is not None:
            raise self._error
        assert self._user is not None
        return self._user

    def start_session(
        self, user_id: str, terminal_id: str, opening_cash: Decimal = Decimal("0")
    ) -> SessionPayload:
        if self._error is not None:
            raise self._error
        assert self._session is not None
        return self._session

    def close_session(
        self, session_id: str, closing_cash: Decimal | None = None
    ) -> SessionPayload:
        if self._error is not None:
            raise self._error
        assert self._session is not None
        return self._session

    def disconnect(self, session_id: str) -> SessionPayload:
        if self._error is not None:
            raise self._error
        assert self._session is not None
        return self._session

    def heartbeat(self, session_id: str) -> SessionPayload:
        if self._error is not None:
            raise self._error
        assert self._session is not None
        return self._session

    def get_current_session(self, terminal_id: str) -> SessionPayload | None:
        if self._error is not None:
            raise self._error
        return self._session

    def list_products(self) -> list[ProductPayload]:
        if self._error is not None:
            raise self._error
        return self._products


class TestAuthService:
    def test_login_returns_user_from_connection(self) -> None:
        auth_service = AuthService(FakeAdminConnection(user=_make_user("emp1")))

        user = auth_service.login("emp1", "secret")

        assert user.username == "emp1"

    def test_reconnect_reuses_successful_login_credentials(self) -> None:
        auth_service = AuthService(FakeAdminConnection(user=_make_user("emp1")))

        auth_service.login("emp1", "secret")
        user = auth_service.reconnect()

        assert user.username == "emp1"

    def test_login_propagates_authentication_error(self) -> None:
        auth_service = AuthService(
            FakeAdminConnection(error=AuthenticationError("bad credentials"))
        )

        with pytest.raises(AuthenticationError):
            auth_service.login("emp1", "wrong")

    def test_login_propagates_admin_unavailable_error(self) -> None:
        auth_service = AuthService(
            FakeAdminConnection(error=AdminUnavailableError("unreachable"))
        )

        with pytest.raises(AdminUnavailableError):
            auth_service.login("emp1", "secret")


def test_product_service_delegates_to_connection() -> None:
    expected = [
        ProductPayload("id", "sku", None, "Coffee", "piece", "2.50", "4")
    ]

    products = ProductService(
        FakeAdminConnection(products=expected)
    ).list_products()

    assert products == expected


class TestPosSessionService:
    def test_start_session_delegates_to_connection(self) -> None:
        expected = _make_session()
        service = PosSessionService(FakeAdminConnection(session=expected))

        session = service.start_session(str(uuid.uuid4()), "pos-1")

        assert session == expected

    def test_close_session_delegates_to_connection(self) -> None:
        expected = _make_session()
        service = PosSessionService(FakeAdminConnection(session=expected))

        session = service.close_session(expected.id)

        assert session == expected

    def test_disconnect_delegates_to_connection(self) -> None:
        expected = _make_session()
        service = PosSessionService(FakeAdminConnection(session=expected))

        session = service.disconnect(expected.id)

        assert session == expected

    def test_heartbeat_delegates_to_connection(self) -> None:
        expected = _make_session()
        service = PosSessionService(FakeAdminConnection(session=expected))

        session = service.heartbeat(expected.id)

        assert session == expected

    def test_get_current_session_delegates_to_connection(self) -> None:
        expected = _make_session()
        service = PosSessionService(FakeAdminConnection(session=expected))

        session = service.get_current_session("pos-1")

        assert session == expected
