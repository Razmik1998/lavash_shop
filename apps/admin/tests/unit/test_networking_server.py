from __future__ import annotations

import json
import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from exceptions import (
    AuthenticationError,
    InvalidQuantityError,
    InvalidSalePriceError,
    SessionAlreadyActiveError,
    SessionClosedError,
    SessionNotFoundError,
)
from models import PosSession, PosSessionStatus, Role, User
from networking.server import (
    AdminTcpServer,
    _parse_price,
    _parse_quantity,
    start_background_server,
)


def test_quantity_parser_reports_the_rejected_value_and_constraint() -> None:
    with pytest.raises(
        InvalidQuantityError,
        match=r"quantity='1.0000'.*at most 3 decimal places",
    ):
        _parse_quantity("1.0000")


def test_price_parser_reports_invalid_price_details() -> None:
    with pytest.raises(
        InvalidSalePriceError,
        match=r"unit_price='1.001'.*at most 2 decimal places",
    ):
        _parse_price("1.001")


def _make_user(username: str, role: Role = Role.EMPLOYEE) -> User:
    return User(
        id=uuid.uuid4(),
        username=username,
        full_name="Employee One",
        hashed_password="hash",
        role=role,
        is_active=True,
        created_at=datetime.now(UTC),
    )


def _make_session(
    status: PosSessionStatus = PosSessionStatus.ACTIVE,
    connection_status: str = "connected",
) -> PosSession:
    now = datetime.now(UTC)
    session = PosSession(
        id=uuid.uuid4(),
        terminal_id="pos-1",
        user_id=uuid.uuid4(),
        status=status,
        started_at=now,
        closed_at=now if status is PosSessionStatus.CLOSED else None,
        last_connected_at=now,
        last_activity_at=now,
        created_at=now,
        updated_at=now,
    )
    session.connection_status = connection_status  # type: ignore[attr-defined]
    return session


class FakeAuthService:
    def __init__(self, user: User | None = None) -> None:
        self._user = user

    def login(self, username: str, password: str, required_role: Role) -> User:
        if self._user is None or self._user.username != username:
            raise AuthenticationError("Invalid username or password.")
        return self._user


class FakePosSessionService:
    """Fake for the `PosSessionService` Protocol declared in
    networking/server.py — configurable per test to return a session or
    raise the exception the dispatch layer is expected to translate."""

    def __init__(
        self,
        session: PosSession | None = None,
        start_error: Exception | None = None,
        close_error: Exception | None = None,
        disconnect_error: Exception | None = None,
        heartbeat_error: Exception | None = None,
    ) -> None:
        self._session = session
        self._start_error = start_error
        self._close_error = close_error
        self._disconnect_error = disconnect_error
        self._heartbeat_error = heartbeat_error

    def start_session(
        self,
        user_id: uuid.UUID,
        terminal_id: str,
        opening_cash: Decimal = Decimal("0"),
    ) -> PosSession:
        if self._start_error is not None:
            raise self._start_error
        assert self._session is not None
        return self._session

    def close_session(
        self, session_id: uuid.UUID, closing_cash: Decimal | None = None
    ) -> PosSession:
        if self._close_error is not None:
            raise self._close_error
        assert self._session is not None
        return self._session

    def disconnect(self, session_id: uuid.UUID) -> PosSession:
        if self._disconnect_error is not None:
            raise self._disconnect_error
        assert self._session is not None
        return self._session

    def heartbeat(self, session_id: uuid.UUID) -> PosSession:
        if self._heartbeat_error is not None:
            raise self._heartbeat_error
        assert self._session is not None
        return self._session

    def get_current_session(self, terminal_id: str) -> PosSession | None:
        return self._session


@contextmanager
def _running_server(
    auth_service: FakeAuthService,
    session_service: FakePosSessionService | None = None,
) -> Iterator[tuple[str, int]]:
    server: AdminTcpServer = start_background_server(
        "127.0.0.1", 0, auth_service, session_service or FakePosSessionService()
    )
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()


def _send_request(
    host: str, port: int, payload: dict[str, object]
) -> dict[str, object]:
    with socket.create_connection((host, port), timeout=3) as sock:
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        with sock.makefile("rb") as reader:
            raw_response = reader.readline(8192)
    return json.loads(raw_response.decode("utf-8"))  # type: ignore[no-any-return]


class TestAdminTcpServer:
    def test_login_succeeds_and_returns_user_payload(self) -> None:
        user = _make_user("emp1")
        with _running_server(FakeAuthService(user)) as (host, port):
            response = _send_request(
                host, port, {"op": "login", "username": "emp1", "password": "secret"}
            )

        assert response["ok"] is True
        assert response["user"] == {
            "id": str(user.id),
            "username": "emp1",
            "full_name": "Employee One",
            "role": "employee",
        }

    def test_login_rejects_invalid_credentials(self) -> None:
        with _running_server(FakeAuthService(_make_user("emp1"))) as (host, port):
            response = _send_request(
                host, port, {"op": "login", "username": "ghost", "password": "x"}
            )

        assert response == {"ok": False, "error": "invalid_credentials"}

    def test_rejects_malformed_json(self) -> None:
        with _running_server(FakeAuthService()) as (host, port):
            with socket.create_connection((host, port), timeout=3) as sock:
                sock.sendall(b"not json\n")
                with sock.makefile("rb") as reader:
                    raw_response = reader.readline(8192)

        assert json.loads(raw_response.decode("utf-8")) == {
            "ok": False,
            "error": "invalid_request",
        }

    @pytest.mark.parametrize(
        "payload",
        [
            {"op": "login", "username": "emp1"},
            {"op": "login", "username": 123, "password": "secret"},
        ],
    )
    def test_rejects_invalid_request_shapes(self, payload: dict[str, object]) -> None:
        with _running_server(FakeAuthService(_make_user("emp1"))) as (host, port):
            response = _send_request(host, port, payload)

        assert response == {"ok": False, "error": "invalid_request"}

    def test_unknown_op_returns_unsupported_operation(self) -> None:
        with _running_server(FakeAuthService(_make_user("emp1"))) as (host, port):
            response = _send_request(host, port, {"op": "logout", "username": "emp1"})

        assert response == {"ok": False, "error": "unsupported_operation"}

    def test_start_session_routes_to_session_service_and_returns_session(
        self,
    ) -> None:
        session = _make_session()
        session_service = FakePosSessionService(session=session)
        with _running_server(
            FakeAuthService(), session_service
        ) as (host, port):
            response = _send_request(
                host,
                port,
                {
                    "op": "start_session",
                    "user_id": str(uuid.uuid4()),
                    "terminal_id": "pos-1",
                },
            )

        assert response["ok"] is True
        assert response["session"]["id"] == str(session.id)  # type: ignore[index]
        assert response["session"]["status"] == "active"  # type: ignore[index]

    def test_start_session_maps_invalid_user_error(self) -> None:
        session_service = FakePosSessionService(
            start_error=AuthenticationError("bad user")
        )
        with _running_server(FakeAuthService(), session_service) as (host, port):
            response = _send_request(
                host,
                port,
                {
                    "op": "start_session",
                    "user_id": str(uuid.uuid4()),
                    "terminal_id": "pos-1",
                },
            )

        assert response == {"ok": False, "error": "invalid_user"}

    def test_start_session_maps_session_already_active_error(self) -> None:
        session_service = FakePosSessionService(
            start_error=SessionAlreadyActiveError("pos-1")
        )
        with _running_server(FakeAuthService(), session_service) as (host, port):
            response = _send_request(
                host,
                port,
                {
                    "op": "start_session",
                    "user_id": str(uuid.uuid4()),
                    "terminal_id": "pos-1",
                },
            )

        assert response == {"ok": False, "error": "session_already_active"}

    def test_close_session_routes_to_session_service(self) -> None:
        session = _make_session(
            status=PosSessionStatus.CLOSED, connection_status="disconnected"
        )
        session_service = FakePosSessionService(session=session)
        with _running_server(FakeAuthService(), session_service) as (host, port):
            response = _send_request(
                host,
                port,
                {"op": "close_session", "session_id": str(session.id)},
            )

        assert response["ok"] is True
        assert response["session"]["status"] == "closed"  # type: ignore[index]

    def test_close_session_maps_session_not_found_error(self) -> None:
        session_service = FakePosSessionService(
            close_error=SessionNotFoundError("missing")
        )
        with _running_server(FakeAuthService(), session_service) as (host, port):
            response = _send_request(
                host,
                port,
                {"op": "close_session", "session_id": str(uuid.uuid4())},
            )

        assert response == {"ok": False, "error": "session_not_found"}

    def test_disconnect_routes_to_session_service(self) -> None:
        session = _make_session(
            status=PosSessionStatus.ACTIVE, connection_status="disconnected"
        )
        session_service = FakePosSessionService(session=session)
        with _running_server(FakeAuthService(), session_service) as (host, port):
            response = _send_request(
                host,
                port,
                {"op": "disconnect", "session_id": str(session.id)},
            )

        assert response["ok"] is True
        assert response["session"]["status"] == "active"  # type: ignore[index]
        assert response["session"]["connection_status"] == "disconnected"  # type: ignore[index]

    def test_disconnect_maps_session_not_found_error(self) -> None:
        session_service = FakePosSessionService(
            disconnect_error=SessionNotFoundError("missing")
        )
        with _running_server(FakeAuthService(), session_service) as (host, port):
            response = _send_request(
                host,
                port,
                {"op": "disconnect", "session_id": str(uuid.uuid4())},
            )

        assert response == {"ok": False, "error": "session_not_found"}

    def test_heartbeat_routes_to_session_service(self) -> None:
        session = _make_session()
        session_service = FakePosSessionService(session=session)
        with _running_server(FakeAuthService(), session_service) as (host, port):
            response = _send_request(
                host,
                port,
                {"op": "heartbeat", "session_id": str(session.id)},
            )

        assert response["ok"] is True
        assert response["session"]["id"] == str(session.id)  # type: ignore[index]

    def test_heartbeat_maps_session_closed_error(self) -> None:
        session_service = FakePosSessionService(
            heartbeat_error=SessionClosedError("closed")
        )
        with _running_server(FakeAuthService(), session_service) as (host, port):
            response = _send_request(
                host,
                port,
                {"op": "heartbeat", "session_id": str(uuid.uuid4())},
            )

        assert response == {"ok": False, "error": "session_closed"}

    def test_get_current_session_returns_null_when_none_active(self) -> None:
        session_service = FakePosSessionService(session=None)
        with _running_server(FakeAuthService(), session_service) as (host, port):
            response = _send_request(
                host, port, {"op": "get_current_session", "terminal_id": "pos-1"}
            )

        assert response == {"ok": True, "session": None}

    def test_get_current_session_returns_active_session(self) -> None:
        session = _make_session()
        session_service = FakePosSessionService(session=session)
        with _running_server(FakeAuthService(), session_service) as (host, port):
            response = _send_request(
                host, port, {"op": "get_current_session", "terminal_id": "pos-1"}
            )

        assert response["ok"] is True
        assert response["session"]["terminal_id"] == "pos-1"  # type: ignore[index]

    def test_login_never_logs_raw_credentials(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("DEBUG")
        with _running_server(FakeAuthService(_make_user("emp1"))) as (host, port):
            _send_request(
                host,
                port,
                {
                    "op": "login",
                    "username": "emp1",
                    "password": "super-secret-password",
                },
            )

        for record in caplog.records:
            assert "super-secret-password" not in record.getMessage()
            assert "emp1" not in record.getMessage()
