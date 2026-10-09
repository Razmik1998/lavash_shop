from __future__ import annotations

import json
import uuid

import pytest

from networking import protocol


class TestEncodeRequests:
    def test_encode_list_products_request(self) -> None:
        request = protocol.ListProductsRequest(auth_token="token")

        encoded = protocol.encode_list_products_request(request)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded == {"op": "list_products", "auth_token": "token"}
    def test_encode_login_request(self) -> None:
        request = protocol.LoginRequest(username="emp1", password="secret")

        encoded = protocol.encode_login_request(request)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded == {"op": "login", "username": "emp1", "password": "secret"}

    def test_encode_start_session_request(self) -> None:
        user_id = str(uuid.uuid4())
        request = protocol.StartSessionRequest(user_id=user_id, terminal_id="pos-1")

        encoded = protocol.encode_start_session_request(request)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded == {
            "op": "start_session",
            "user_id": user_id,
            "terminal_id": "pos-1",
        }

    def test_encode_close_session_request(self) -> None:
        session_id = str(uuid.uuid4())
        request = protocol.CloseSessionRequest(session_id=session_id)

        encoded = protocol.encode_close_session_request(request)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded == {"op": "close_session", "session_id": session_id}

    def test_encode_disconnect_request(self) -> None:
        session_id = str(uuid.uuid4())
        request = protocol.DisconnectRequest(session_id=session_id)

        encoded = protocol.encode_disconnect_request(request)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded == {"op": "disconnect", "session_id": session_id}

    def test_encode_heartbeat_request(self) -> None:
        session_id = str(uuid.uuid4())
        request = protocol.HeartbeatRequest(session_id=session_id)

        encoded = protocol.encode_heartbeat_request(request)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded == {"op": "heartbeat", "session_id": session_id}

    def test_encode_get_current_session_request(self) -> None:
        request = protocol.GetCurrentSessionRequest(terminal_id="pos-1")

        encoded = protocol.encode_get_current_session_request(request)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded == {"op": "get_current_session", "terminal_id": "pos-1"}

    def test_encode_create_sale_request_includes_optional_credit_customer(self) -> None:
        request = protocol.CreateSaleRequest(
            auth_token="token",
            session_id=str(uuid.uuid4()),
            terminal_id="pos-1",
            sale_id=str(uuid.uuid4()),
            items=[protocol.SaleItemRequest("product", "1")],
            credit_customer_id="customer-1",
        )

        encoded = protocol.encode_create_sale_request(request)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded["credit_customer_id"] == "customer-1"

    def test_encode_update_sale_request_omits_credit_customer_by_default(self) -> None:
        request = protocol.UpdateSaleRequest(
            auth_token="token",
            session_id=str(uuid.uuid4()),
            sale_id=str(uuid.uuid4()),
            items=[protocol.SaleItemRequest("product", "1")],
        )

        encoded = protocol.encode_update_sale_request(request)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert "credit_customer_id" not in decoded

    def test_encode_cancel_sale_request_includes_reason(self) -> None:
        request = protocol.CancelSaleRequest(
            auth_token="token",
            session_id=str(uuid.uuid4()),
            sale_id=str(uuid.uuid4()),
            reason="Duplicate order",
        )

        encoded = protocol.encode_cancel_sale_request(request)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded["reason"] == "Duplicate order"

    def test_encode_create_customer_request(self) -> None:
        request = protocol.CreateCustomerRequest(
            auth_token="token",
            first_name="John",
            last_name="Smith",
            phone="123456",
            address="Main St",
            notes="VIP",
        )

        encoded = protocol.encode_create_customer_request(request)
        decoded = json.loads(encoded.decode("utf-8").rstrip("\n"))

        assert decoded["op"] == "create_customer"
        assert decoded["first_name"] == "John"
        assert decoded["phone"] == "123456"


class TestDecodeResponse:
    def test_decodes_a_valid_json_object(self) -> None:
        raw = b'{"ok": true, "session": null}\n'

        data = protocol.decode_response(raw)

        assert data == {"ok": True, "session": None}

    def test_rejects_empty_message(self) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_response(b"")

    def test_rejects_oversized_message(self) -> None:
        oversized = b"x" * (protocol.MAX_MESSAGE_BYTES + 1)
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_response(oversized)

    def test_rejects_malformed_json(self) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_response(b"not json\n")

    def test_rejects_non_object_json(self) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_response(b"[1, 2, 3]\n")


def _valid_session_payload_dict() -> dict[str, object]:
    return {
        "id": str(uuid.uuid4()),
        "terminal_id": "pos-1",
        "user_id": str(uuid.uuid4()),
        "status": "active",
        "connection_status": "connected",
        "started_at": "2026-01-01T00:00:00+00:00",
        "closed_at": None,
        "last_connected_at": "2026-01-01T00:00:00+00:00",
        "last_activity_at": "2026-01-01T00:00:00+00:00",
    }


class TestSessionFromPayload:
    def test_round_trips_a_valid_payload(self) -> None:
        raw = _valid_session_payload_dict()

        session = protocol.session_from_payload(raw)

        assert session.terminal_id == "pos-1"
        assert session.status == "active"
        assert session.closed_at is None

    def test_rejects_non_dict_payload(self) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.session_from_payload("not-a-dict")

    def test_rejects_payload_missing_required_field(self) -> None:
        raw = _valid_session_payload_dict()
        del raw["status"]

        with pytest.raises(protocol.ProtocolError):
            protocol.session_from_payload(raw)


def test_products_from_payload_decodes_catalog_fields_without_cost_price() -> None:
    products = protocol.products_from_payload(
        [
            {
                "id": str(uuid.uuid4()),
                "sku": "SKU-1",
                "barcode": None,
                "name": "Coffee",
                "unit": "piece",
                "selling_price": "2.50",
                "available_stock": "4.000",
            }
        ]
    )

    assert products[0].name == "Coffee"
    assert products[0].available_stock == "4.000"


def test_sale_payload_decodes_optional_cancellation_reason() -> None:
    sale = protocol.sale_from_payload(
        {
            "id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "terminal_id": "pos-1",
            "employee_user_id": str(uuid.uuid4()),
            "status": "cancelled",
            "total": "6.00",
            "created_at": "2026-01-01T00:00:00+00:00",
            "items": [],
            "audit_events": [],
            "cancellation_reason": "Duplicate order",
        }
    )

    assert sale.cancellation_reason == "Duplicate order"
