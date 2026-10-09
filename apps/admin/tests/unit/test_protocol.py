from __future__ import annotations

import json
import uuid

import pytest

from networking import protocol


class TestDecodeEnvelope:
    def test_decodes_a_valid_json_object(self) -> None:
        raw = b'{"op": "login", "username": "emp1"}\n'

        data = protocol.decode_envelope(raw)

        assert data == {"op": "login", "username": "emp1"}

    def test_rejects_empty_message(self) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_envelope(b"")

    def test_rejects_oversized_message(self) -> None:
        oversized = b"x" * (protocol.MAX_MESSAGE_BYTES + 1)
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_envelope(oversized)

    def test_rejects_malformed_json(self) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_envelope(b"not json\n")

    def test_rejects_non_object_json(self) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_envelope(b"[1, 2, 3]\n")


class TestDecodeLogin:
    def test_round_trips_valid_request(self) -> None:
        data = {"op": "login", "username": "emp1", "password": "secret"}

        request = protocol.decode_login(data)

        assert request == protocol.LoginRequest(username="emp1", password="secret")

    @pytest.mark.parametrize(
        "data",
        [
            {"op": "start_session", "username": "emp1", "password": "secret"},
            {"op": "login", "username": "emp1"},
            {"op": "login", "username": 1, "password": "secret"},
            {"op": "login", "username": "", "password": "secret"},
            {"op": "login", "username": "x" * 300, "password": "secret"},
        ],
    )
    def test_rejects_malformed_payload(self, data: dict[str, object]) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_login(data)


class TestDecodeStartSession:
    def test_round_trips_valid_request(self) -> None:
        user_id = str(uuid.uuid4())
        data = {"op": "start_session", "user_id": user_id, "terminal_id": "pos-1"}

        request = protocol.decode_start_session(data)

        assert request == protocol.StartSessionRequest(
            user_id=user_id, terminal_id="pos-1"
        )

    @pytest.mark.parametrize(
        "data",
        [
            {"op": "login", "user_id": str(uuid.uuid4()), "terminal_id": "pos-1"},
            {"op": "start_session", "user_id": "not-a-uuid", "terminal_id": "pos-1"},
            {"op": "start_session", "user_id": str(uuid.uuid4()), "terminal_id": ""},
            {"op": "start_session", "user_id": str(uuid.uuid4())},
        ],
    )
    def test_rejects_malformed_payload(self, data: dict[str, object]) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_start_session(data)


class TestDecodeCloseSession:
    def test_round_trips_valid_request(self) -> None:
        session_id = str(uuid.uuid4())
        data = {"op": "close_session", "session_id": session_id}

        request = protocol.decode_close_session(data)

        assert request == protocol.CloseSessionRequest(session_id=session_id)

    @pytest.mark.parametrize(
        "data",
        [
            {"op": "heartbeat", "session_id": str(uuid.uuid4())},
            {"op": "close_session", "session_id": "not-a-uuid"},
            {"op": "close_session"},
        ],
    )
    def test_rejects_malformed_payload(self, data: dict[str, object]) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_close_session(data)


class TestDecodeDisconnect:
    def test_round_trips_valid_request(self) -> None:
        session_id = str(uuid.uuid4())
        data = {"op": "disconnect", "session_id": session_id}

        request = protocol.decode_disconnect(data)

        assert request == protocol.DisconnectRequest(session_id=session_id)

    @pytest.mark.parametrize(
        "data",
        [
            {"op": "heartbeat", "session_id": str(uuid.uuid4())},
            {"op": "disconnect", "session_id": "not-a-uuid"},
            {"op": "disconnect"},
        ],
    )
    def test_rejects_malformed_payload(self, data: dict[str, object]) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_disconnect(data)


class TestDecodeHeartbeat:
    def test_round_trips_valid_request(self) -> None:
        session_id = str(uuid.uuid4())
        data = {"op": "heartbeat", "session_id": session_id}

        request = protocol.decode_heartbeat(data)

        assert request == protocol.HeartbeatRequest(session_id=session_id)

    @pytest.mark.parametrize(
        "data",
        [
            {"op": "close_session", "session_id": str(uuid.uuid4())},
            {"op": "heartbeat", "session_id": "not-a-uuid"},
            {"op": "heartbeat"},
        ],
    )
    def test_rejects_malformed_payload(self, data: dict[str, object]) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_heartbeat(data)


class TestDecodeGetCurrentSession:
    def test_round_trips_valid_request(self) -> None:
        data = {"op": "get_current_session", "terminal_id": "pos-1"}

        request = protocol.decode_get_current_session(data)

        assert request == protocol.GetCurrentSessionRequest(terminal_id="pos-1")

    @pytest.mark.parametrize(
        "data",
        [
            {"op": "heartbeat", "terminal_id": "pos-1"},
            {"op": "get_current_session", "terminal_id": ""},
            {"op": "get_current_session", "terminal_id": 1},
            {"op": "get_current_session"},
        ],
    )
    def test_rejects_malformed_payload(self, data: dict[str, object]) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_get_current_session(data)


class TestEncodeSessionResponse:
    def test_encodes_product_catalog_without_cost_price(self) -> None:
        product = protocol.ProductPayload(
            id=str(uuid.uuid4()), sku="SKU-1", barcode=None, name="Coffee",
            unit="piece", selling_price="2.50", available_stock="4.000",
        )

        decoded = json.loads(
            protocol.encode_products_response([product]).decode("utf-8").rstrip("\n")
        )

        assert decoded["products"] == [{
            "id": product.id,
            "sku": "SKU-1",
            "barcode": None,
            "name": "Coffee",
            "unit": "piece",
            "selling_price": "2.50",
            "available_stock": "4.000",
            "parent_product_id": None,
        }]
        assert "cost_price" not in decoded["products"][0]

    def test_encodes_a_session_payload(self) -> None:
        payload = protocol.SessionPayload(
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

        encoded = protocol.encode_session_response(payload)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded["ok"] is True
        assert decoded["session"]["terminal_id"] == "pos-1"
        assert decoded["session"]["closed_at"] is None

    def test_encodes_none_session_as_null(self) -> None:
        encoded = protocol.encode_session_response(None)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded == {"ok": True, "session": None}


def test_encode_error_response() -> None:
    encoded = protocol.encode_error_response("session_not_found")
    decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

    assert decoded == {"ok": False, "error": "session_not_found"}
