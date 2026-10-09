from __future__ import annotations

import json
import socket
import socketserver
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from exceptions import (
    AdminUnavailableError,
    AuthenticationError,
    SessionAlreadyActiveError,
    SessionClosedError,
    SessionNotFoundError,
)
from networking.local_connection import LocalConnection

_ResponderFn = Callable[[dict[str, object]], bytes]


class _Handler(socketserver.StreamRequestHandler):
    server: _FakeServer

    def handle(self) -> None:
        raw = self.rfile.readline(8192)
        if not raw:
            return  # client (e.g. is_available()) connected and disconnected
        request = json.loads(raw.decode("utf-8"))
        self.wfile.write(self.server.responder(request))


class _FakeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, responder: _ResponderFn) -> None:
        self.responder = responder
        super().__init__(("127.0.0.1", 0), _Handler)


@contextmanager
def _running_fake_server(responder: _ResponderFn) -> Iterator[tuple[str, int]]:
    server = _FakeServer(responder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()


def _closed_port() -> int:
    """A loopback TCP port nothing is listening on, so connecting to it
    fails immediately with connection-refused."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _ok_responder(request: dict[str, object]) -> bytes:
    payload = {
        "ok": True,
        "user": {
            "id": "11111111-1111-1111-1111-111111111111",
            "username": request["username"],
            "full_name": "Employee One",
            "role": "employee",
        },
        "auth_token": "token-123",
        "expires_at": "2030-01-01T00:00:00+00:00",
    }
    return (json.dumps(payload) + "\n").encode("utf-8")


def _invalid_credentials_responder(_request: dict[str, object]) -> bytes:
    return (json.dumps({"ok": False, "error": "invalid_credentials"}) + "\n").encode(
        "utf-8"
    )


def _malformed_responder(_request: dict[str, object]) -> bytes:
    return b"not json\n"


class TestLocalConnectionIsAvailable:
    def test_is_available_true_when_server_listening(self) -> None:
        with _running_fake_server(_ok_responder) as (host, port):
            assert LocalConnection(host, port).is_available() is True

    def test_is_available_false_when_connection_refused(self) -> None:
        connection = LocalConnection("127.0.0.1", _closed_port())
        assert connection.is_available() is False


class TestLocalConnectionLogin:
    def test_login_succeeds(self) -> None:
        with _running_fake_server(_ok_responder) as (host, port):
            user = LocalConnection(host, port).login("emp1", "secret")

        assert user.username == "emp1"

    def test_login_raises_authentication_error_on_invalid_credentials(self) -> None:
        with _running_fake_server(_invalid_credentials_responder) as (host, port):
            with pytest.raises(AuthenticationError):
                LocalConnection(host, port).login("emp1", "wrong")

    def test_login_raises_admin_unavailable_on_malformed_response(self) -> None:
        with _running_fake_server(_malformed_responder) as (host, port):
            with pytest.raises(AdminUnavailableError):
                LocalConnection(host, port).login("emp1", "secret")

    def test_login_raises_admin_unavailable_on_refused_connection(self) -> None:
        connection = LocalConnection("127.0.0.1", _closed_port())

        with pytest.raises(AdminUnavailableError):
            connection.login("emp1", "secret")

    def test_login_retries_once_before_failing(self) -> None:
        connection = LocalConnection("127.0.0.1", _closed_port())

        with patch(
            "socket.create_connection", side_effect=ConnectionRefusedError
        ) as mock_connect:
            with pytest.raises(AdminUnavailableError):
                connection.login("emp1", "secret")

        assert mock_connect.call_count == 2

    def test_login_raises_admin_unavailable_on_connect_timeout(self) -> None:
        connection = LocalConnection("127.0.0.1", _closed_port())

        with patch("socket.create_connection", side_effect=TimeoutError):
            with pytest.raises(AdminUnavailableError):
                connection.login("emp1", "secret")


def _session_payload_dict(
    status: str = "active", connection_status: str = "connected"
) -> dict[str, object]:
    return {
        "id": str(uuid.uuid4()),
        "terminal_id": "pos-1",
        "user_id": str(uuid.uuid4()),
        "status": status,
        "connection_status": connection_status,
        "started_at": "2026-01-01T00:00:00+00:00",
        "closed_at": None,
        "last_connected_at": "2026-01-01T00:00:00+00:00",
        "last_activity_at": "2026-01-01T00:00:00+00:00",
    }


def _session_ok_responder(_request: dict[str, object]) -> bytes:
    payload = {"ok": True, "session": _session_payload_dict()}
    return (json.dumps(payload) + "\n").encode("utf-8")


def _null_session_ok_responder(_request: dict[str, object]) -> bytes:
    return (json.dumps({"ok": True, "session": None}) + "\n").encode("utf-8")


def _error_responder(error: str) -> _ResponderFn:
    def _responder(_request: dict[str, object]) -> bytes:
        return (json.dumps({"ok": False, "error": error}) + "\n").encode("utf-8")

    return _responder


class TestLocalConnectionStartSession:
    def test_start_session_succeeds(self) -> None:
        with _running_fake_server(_session_ok_responder) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            session = connection.start_session(str(uuid.uuid4()), "pos-1")

        assert session.terminal_id == "pos-1"
        assert session.status == "active"

    def test_start_session_maps_session_already_active_error(self) -> None:
        with _running_fake_server(
            _error_responder("session_already_active")
        ) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            with pytest.raises(SessionAlreadyActiveError):
                connection.start_session(str(uuid.uuid4()), "pos-1")

    def test_start_session_maps_invalid_user_error(self) -> None:
        with _running_fake_server(_error_responder("invalid_user")) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            with pytest.raises(AuthenticationError):
                connection.start_session(str(uuid.uuid4()), "pos-1")

    def test_start_session_raises_admin_unavailable_on_null_session(self) -> None:
        with _running_fake_server(_null_session_ok_responder) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            with pytest.raises(AdminUnavailableError):
                connection.start_session(str(uuid.uuid4()), "pos-1")

    def test_start_session_raises_admin_unavailable_on_refused_connection(
        self,
    ) -> None:
        connection = LocalConnection("127.0.0.1", _closed_port())
        connection._auth_token = "token-123"

        with pytest.raises(AdminUnavailableError):
            connection.start_session(str(uuid.uuid4()), "pos-1")

    def test_start_session_retries_once_before_failing(self) -> None:
        connection = LocalConnection("127.0.0.1", _closed_port())
        connection._auth_token = "token-123"

        with patch(
            "socket.create_connection", side_effect=ConnectionRefusedError
        ) as mock_connect:
            with pytest.raises(AdminUnavailableError):
                connection.start_session(str(uuid.uuid4()), "pos-1")

        assert mock_connect.call_count == 2


class TestLocalConnectionCloseSession:
    def test_close_session_succeeds(self) -> None:
        with _running_fake_server(_session_ok_responder) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            session = connection.close_session(str(uuid.uuid4()))

        assert session.terminal_id == "pos-1"

    def test_close_session_maps_session_not_found_error(self) -> None:
        with _running_fake_server(
            _error_responder("session_not_found")
        ) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            with pytest.raises(SessionNotFoundError):
                connection.close_session(str(uuid.uuid4()))

    def test_close_session_raises_admin_unavailable_on_refused_connection(
        self,
    ) -> None:
        connection = LocalConnection("127.0.0.1", _closed_port())
        connection._auth_token = "token-123"

        with pytest.raises(AdminUnavailableError):
            connection.close_session(str(uuid.uuid4()))


class TestLocalConnectionDisconnect:
    def test_disconnect_succeeds(self) -> None:
        with _running_fake_server(_session_ok_responder) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            session = connection.disconnect(str(uuid.uuid4()))

        assert session.terminal_id == "pos-1"

    def test_disconnect_maps_session_not_found_error(self) -> None:
        with _running_fake_server(
            _error_responder("session_not_found")
        ) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            with pytest.raises(SessionNotFoundError):
                connection.disconnect(str(uuid.uuid4()))

    def test_disconnect_raises_admin_unavailable_on_refused_connection(
        self,
    ) -> None:
        connection = LocalConnection("127.0.0.1", _closed_port())
        connection._auth_token = "token-123"

        with pytest.raises(AdminUnavailableError):
            connection.disconnect(str(uuid.uuid4()))


class TestLocalConnectionHeartbeat:
    def test_heartbeat_succeeds(self) -> None:
        with _running_fake_server(_session_ok_responder) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            session = connection.heartbeat(str(uuid.uuid4()))

        assert session.connection_status == "connected"

    def test_heartbeat_maps_session_not_found_error(self) -> None:
        with _running_fake_server(
            _error_responder("session_not_found")
        ) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            with pytest.raises(SessionNotFoundError):
                connection.heartbeat(str(uuid.uuid4()))

    def test_heartbeat_maps_session_closed_error(self) -> None:
        with _running_fake_server(_error_responder("session_closed")) as (
            host,
            port,
        ):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            with pytest.raises(SessionClosedError):
                connection.heartbeat(str(uuid.uuid4()))

    def test_heartbeat_clears_stale_token_and_raises_authentication_error(self) -> None:
        with _running_fake_server(_error_responder("invalid_token")) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "stale-token"

            with pytest.raises(AuthenticationError):
                connection.heartbeat(str(uuid.uuid4()))

        assert connection._auth_token is None

    def test_heartbeat_retries_once_before_failing(self) -> None:
        connection = LocalConnection("127.0.0.1", _closed_port())
        connection._auth_token = "token-123"

        with patch(
            "socket.create_connection", side_effect=ConnectionRefusedError
        ) as mock_connect:
            with pytest.raises(AdminUnavailableError):
                connection.heartbeat(str(uuid.uuid4()))

        assert mock_connect.call_count == 2


class TestLocalConnectionGetCurrentSession:
    def test_returns_active_session(self) -> None:
        with _running_fake_server(_session_ok_responder) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            session = connection.get_current_session("pos-1")

        assert session is not None
        assert session.terminal_id == "pos-1"

    def test_returns_none_when_no_active_session(self) -> None:
        with _running_fake_server(_null_session_ok_responder) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            session = connection.get_current_session("pos-1")

        assert session is None

    def test_raises_admin_unavailable_on_malformed_response(self) -> None:
        with _running_fake_server(_malformed_responder) as (host, port):
            connection = LocalConnection(host, port)
            connection._auth_token = "token-123"
            with pytest.raises(AdminUnavailableError):
                connection.get_current_session("pos-1")

    def test_raises_admin_unavailable_on_refused_connection(self) -> None:
        connection = LocalConnection("127.0.0.1", _closed_port())
        connection._auth_token = "token-123"

        with pytest.raises(AdminUnavailableError):
            connection.get_current_session("pos-1")
