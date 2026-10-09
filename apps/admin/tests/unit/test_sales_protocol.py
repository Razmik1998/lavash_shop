from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from networking import protocol


def _valid_request() -> dict[str, object]:
    return {
        "op": "create_sale",
        "auth_token": "session-token",
        "session_id": str(uuid.uuid4()),
        "terminal_id": "pos-1",
        "sale_id": str(uuid.uuid4()),
        "items": [{"product_id": str(uuid.uuid4()), "quantity": "2.000"}],
    }


def test_create_sale_protocol_preserves_token_identity_and_items() -> None:
    request = protocol.decode_create_sale(_valid_request())

    assert request.auth_token == "session-token"
    assert request.terminal_id == "pos-1"
    assert request.items[0].quantity == "2.000"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.pop("auth_token"),
        lambda data: data.update(session_id="not-a-uuid"),
        lambda data: data.update(items=[]),
        lambda data: data.update(items=[{"product_id": "not-a-uuid", "quantity": "1"}]),
        lambda data: data.update(extra=True),
    ],
)
def test_create_sale_protocol_rejects_invalid_identity_or_shape(mutate) -> None:  # type: ignore[no-untyped-def]
    data = _valid_request()
    mutate(data)

    with pytest.raises(protocol.ProtocolError):
        protocol.decode_create_sale(data)


def test_cancel_sale_protocol_requires_reason() -> None:
    data: dict[str, object] = {
        "op": "cancel_sale",
        "auth_token": "session-token",
        "session_id": str(uuid.uuid4()),
        "sale_id": str(uuid.uuid4()),
        "reason": "Duplicate order",
    }

    request = protocol.decode_cancel_sale(data)

    assert request.reason == "Duplicate order"

    del data["reason"]
    with pytest.raises(protocol.ProtocolError):
        protocol.decode_cancel_sale(data)


def test_sale_response_includes_cancellation_reason() -> None:
    detail = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        terminal_id="pos-1",
        employee_user_id=uuid.uuid4(),
        status="cancelled",
        total=Decimal("6.00"),
        created_at=datetime.now(UTC),
        cancellation_reason="Duplicate order",
        credit_customer_id=None,
        items=[],
        audit_events=[],
    )

    encoded = protocol.encode_sale_response(detail)
    response = json.loads(encoded.decode("utf-8"))

    assert response["sale"]["cancellation_reason"] == "Duplicate order"
