"""Wire protocol for the POS <-> Admin TCP connection: one JSON object
per line (newline-delimited), one request/response per TCP connection.
Mirrors apps/pos/src/networking/protocol.py — kept as two small,
independent copies rather than a shared package, since apps/admin and
apps/pos import nothing from each other.

Never log raw request/response bodies here or in callers — the login
op carries the password."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MAX_MESSAGE_BYTES = 65536
_MAX_FIELD_LENGTH = 256


class ProtocolError(Exception):
    """Raised when a message cannot be parsed as a valid protocol message."""


@dataclass(frozen=True)
class LoginRequest:
    username: str
    password: str


@dataclass(frozen=True)
class StartSessionRequest:
    user_id: str
    terminal_id: str
    auth_token: str | None = None
    opening_cash: str | None = None


@dataclass(frozen=True)
class CloseSessionRequest:
    session_id: str
    auth_token: str | None = None
    closing_cash: str | None = None


@dataclass(frozen=True)
class DisconnectRequest:
    session_id: str
    auth_token: str | None = None


@dataclass(frozen=True)
class HeartbeatRequest:
    session_id: str
    auth_token: str | None = None


@dataclass(frozen=True)
class GetCurrentSessionRequest:
    terminal_id: str
    auth_token: str | None = None


@dataclass(frozen=True)
class ListProductsRequest:
    auth_token: str | None = None


@dataclass(frozen=True)
class SaleItemRequest:
    product_id: str
    quantity: str
    unit_price: str | None = None


@dataclass(frozen=True)
class CreateSaleRequest:
    auth_token: str
    session_id: str
    terminal_id: str
    sale_id: str
    items: list[SaleItemRequest]
    credit_customer_id: str | None = None


@dataclass(frozen=True)
class SessionSalesRequest:
    auth_token: str
    session_id: str


@dataclass(frozen=True)
class SaleDetailRequest:
    auth_token: str
    session_id: str
    sale_id: str


@dataclass(frozen=True)
class UnlockSaleRequest:
    auth_token: str
    session_id: str
    sale_id: str
    secret_key: str


@dataclass(frozen=True)
class UpdateSaleRequest:
    auth_token: str
    session_id: str
    sale_id: str
    items: list[SaleItemRequest]
    credit_customer_id: str | None = None


@dataclass(frozen=True)
class CancelSaleRequest:
    auth_token: str
    session_id: str
    sale_id: str
    reason: str


@dataclass(frozen=True)
class CreateCustomerRequest:
    auth_token: str
    first_name: str
    last_name: str
    phone: str
    address: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class SearchCustomersRequest:
    auth_token: str
    query: str


@dataclass(frozen=True)
class RecordPaymentRequest:
    auth_token: str
    customer_id: str
    amount: str
    session_id: str


@dataclass(frozen=True)
class UserPayload:
    id: str
    username: str
    full_name: str
    role: str


@dataclass(frozen=True)
class LoginPayload:
    user: UserPayload
    auth_token: str
    expires_at: str


@dataclass(frozen=True)
class SessionPayload:
    id: str
    terminal_id: str
    user_id: str
    status: str
    connection_status: str
    started_at: str
    closed_at: str | None
    last_connected_at: str
    last_activity_at: str


@dataclass(frozen=True)
class ProductPayload:
    id: str
    sku: str
    barcode: str | None
    name: str
    unit: str
    selling_price: str | None
    available_stock: str | None
    parent_product_id: str | None = None
    minimum_price: str | None = None


@dataclass(frozen=True)
class CustomerPayload:
    id: str
    first_name: str
    last_name: str
    phone: str
    current_debt: str


@dataclass(frozen=True)
class PaymentPayload:
    id: str
    customer_id: str
    amount: str
    session_id: str
    user_id: str
    paid_at: str


def decode_envelope(raw: bytes) -> dict[str, object]:
    """Parses `raw` as a JSON object with the same size/shape guards as
    every op below. Does NOT validate `op` or any op-specific fields —
    callers read `data["op"]` to dispatch, then call the matching
    per-op decoder on the returned dict."""
    return _decode_json_object(raw)


def decode_login(data: dict[str, object]) -> LoginRequest:
    if data.get("op") != "login":
        raise ProtocolError("unsupported operation")
    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        raise ProtocolError("username/password must be strings")
    if not username or not password:
        raise ProtocolError("username/password must not be empty")
    if len(username) > _MAX_FIELD_LENGTH or len(password) > _MAX_FIELD_LENGTH:
        raise ProtocolError("username/password too long")
    return LoginRequest(username=username, password=password)


def decode_start_session(data: dict[str, object]) -> StartSessionRequest:
    if data.get("op") != "start_session":
        raise ProtocolError("unsupported operation")
    auth_token = data.get("auth_token")
    user_id = data.get("user_id")
    terminal_id = data.get("terminal_id")
    if not isinstance(user_id, str) or not isinstance(terminal_id, str):
        raise ProtocolError("user_id/terminal_id must be strings")
    if not isinstance(auth_token, str) or not auth_token:
        raise ProtocolError("auth_token must be a non-empty string")
    if not terminal_id or len(terminal_id) > _MAX_FIELD_LENGTH:
        raise ProtocolError("terminal_id invalid")
    _validate_uuid(user_id)
    opening_cash = data.get("opening_cash")
    if opening_cash is not None and not isinstance(opening_cash, str):
        raise ProtocolError("opening_cash must be a string")
    return StartSessionRequest(
        user_id=user_id,
        terminal_id=terminal_id,
        auth_token=auth_token,
        opening_cash=opening_cash,
    )


def decode_close_session(data: dict[str, object]) -> CloseSessionRequest:
    if data.get("op") != "close_session":
        raise ProtocolError("unsupported operation")
    auth_token = data.get("auth_token")
    session_id = data.get("session_id")
    if not isinstance(auth_token, str) or not auth_token:
        raise ProtocolError("auth_token must be a non-empty string")
    if not isinstance(session_id, str):
        raise ProtocolError("session_id must be a string")
    _validate_uuid(session_id)
    closing_cash = data.get("closing_cash")
    if closing_cash is not None and not isinstance(closing_cash, str):
        raise ProtocolError("closing_cash must be a string")
    return CloseSessionRequest(
        session_id=session_id,
        auth_token=auth_token,
        closing_cash=closing_cash,
    )


def decode_disconnect(data: dict[str, object]) -> DisconnectRequest:
    if data.get("op") != "disconnect":
        raise ProtocolError("unsupported operation")
    auth_token = data.get("auth_token")
    session_id = data.get("session_id")
    if not isinstance(auth_token, str) or not auth_token:
        raise ProtocolError("auth_token must be a non-empty string")
    if not isinstance(session_id, str):
        raise ProtocolError("session_id must be a string")
    _validate_uuid(session_id)
    return DisconnectRequest(session_id=session_id, auth_token=auth_token)


def decode_heartbeat(data: dict[str, object]) -> HeartbeatRequest:
    if data.get("op") != "heartbeat":
        raise ProtocolError("unsupported operation")
    auth_token = data.get("auth_token")
    session_id = data.get("session_id")
    if not isinstance(auth_token, str) or not auth_token:
        raise ProtocolError("auth_token must be a non-empty string")
    if not isinstance(session_id, str):
        raise ProtocolError("session_id must be a string")
    _validate_uuid(session_id)
    return HeartbeatRequest(session_id=session_id, auth_token=auth_token)


def decode_get_current_session(data: dict[str, object]) -> GetCurrentSessionRequest:
    if data.get("op") != "get_current_session":
        raise ProtocolError("unsupported operation")
    auth_token = data.get("auth_token")
    terminal_id = data.get("terminal_id")
    if not isinstance(auth_token, str) or not auth_token:
        raise ProtocolError("auth_token must be a non-empty string")
    if not isinstance(terminal_id, str):
        raise ProtocolError("terminal_id must be a string")
    if not terminal_id or len(terminal_id) > _MAX_FIELD_LENGTH:
        raise ProtocolError("terminal_id invalid")
    return GetCurrentSessionRequest(terminal_id=terminal_id, auth_token=auth_token)


def decode_list_products(data: dict[str, object]) -> ListProductsRequest:
    if data.get("op") != "list_products":
        raise ProtocolError("unsupported operation")
    auth_token = data.get("auth_token")
    if set(data) != {"op", "auth_token"}:
        raise ProtocolError("invalid list_products fields")
    if not isinstance(auth_token, str) or not auth_token:
        raise ProtocolError("auth_token must be a non-empty string")
    return ListProductsRequest(auth_token)


def decode_create_sale(data: dict[str, object]) -> CreateSaleRequest:
    if data.get("op") != "create_sale":
        raise ProtocolError("unsupported operation")
    fields = {
        "op",
        "auth_token",
        "session_id",
        "terminal_id",
        "sale_id",
        "items",
        "credit_customer_id",
    }
    if not set(data).issubset(fields) or not {
        "op",
        "auth_token",
        "session_id",
        "terminal_id",
        "sale_id",
        "items",
    }.issubset(data):
        raise ProtocolError("invalid create_sale fields")
    values = [
        data.get(key) for key in ("auth_token", "session_id", "terminal_id", "sale_id")
    ]
    if not all(isinstance(value, str) and value for value in values):
        raise ProtocolError("invalid create_sale identity")
    _validate_uuid(values[1])
    _validate_uuid(values[3])
    items = data["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise ProtocolError("invalid sale items")
    decoded: list[SaleItemRequest] = []
    for item in items:
        if (
            not isinstance(item, dict)
            or not {"product_id", "quantity"}.issubset(item)
            or not set(item).issubset({"product_id", "quantity", "unit_price"})
        ):
            raise ProtocolError("invalid sale item")
        product_id = item["product_id"]
        quantity = item["quantity"]
        unit_price = item.get("unit_price")
        if not isinstance(product_id, str) or not isinstance(quantity, str):
            raise ProtocolError("invalid sale item values")
        _validate_uuid(product_id)
        if unit_price is not None and not isinstance(unit_price, str):
            raise ProtocolError("invalid sale item price")
        decoded.append(SaleItemRequest(product_id, quantity, unit_price))
    customer_id = data.get("credit_customer_id")
    if customer_id is not None:
        if not isinstance(customer_id, str):
            raise ProtocolError("invalid credit customer")
        _validate_uuid(customer_id)
    return CreateSaleRequest(
        values[0], values[1], values[2], values[3], decoded, customer_id
    )


def decode_session_sales(data: dict[str, object]) -> SessionSalesRequest:
    fields = {"op", "auth_token", "session_id"}
    if data.get("op") != "list_session_sales" or set(data) != fields:
        raise ProtocolError("invalid list_session_sales fields")
    token, session_id = data["auth_token"], data["session_id"]
    if not isinstance(token, str) or not token or not isinstance(session_id, str):
        raise ProtocolError("invalid list_session_sales identity")
    _validate_uuid(session_id)
    return SessionSalesRequest(token, session_id)


def decode_sale_detail(data: dict[str, object]) -> SaleDetailRequest:
    fields = {"op", "auth_token", "session_id", "sale_id"}
    if data.get("op") != "get_sale_detail" or set(data) != fields:
        raise ProtocolError("invalid get_sale_detail fields")
    token, session_id, sale_id = (
        data[key] for key in ("auth_token", "session_id", "sale_id")
    )
    if not all(
        isinstance(value, str) and value for value in (token, session_id, sale_id)
    ):
        raise ProtocolError("invalid sale detail identity")
    _validate_uuid(session_id)
    _validate_uuid(sale_id)
    return SaleDetailRequest(token, session_id, sale_id)


def decode_unlock_sale(data: dict[str, object]) -> UnlockSaleRequest:
    fields = {"op", "auth_token", "session_id", "sale_id", "secret_key"}
    if data.get("op") != "unlock_sale" or set(data) != fields:
        raise ProtocolError("invalid unlock_sale fields")
    values = [
        data[key] for key in ("auth_token", "session_id", "sale_id", "secret_key")
    ]
    if not all(isinstance(value, str) and value for value in values):
        raise ProtocolError("invalid unlock_sale values")
    _validate_uuid(values[1])
    _validate_uuid(values[2])
    return UnlockSaleRequest(*values)


def decode_update_sale(data: dict[str, object]) -> UpdateSaleRequest:
    fields = {
        "op",
        "auth_token",
        "session_id",
        "sale_id",
        "items",
        "credit_customer_id",
    }
    if (
        data.get("op") != "update_sale"
        or not set(data).issubset(fields)
        or not {"op", "auth_token", "session_id", "sale_id", "items"}.issubset(data)
    ):
        raise ProtocolError("invalid update_sale fields")
    token, session_id, sale_id = (
        data[key] for key in ("auth_token", "session_id", "sale_id")
    )
    if not all(
        isinstance(value, str) and value for value in (token, session_id, sale_id)
    ):
        raise ProtocolError("invalid update_sale identity")
    _validate_uuid(session_id)
    _validate_uuid(sale_id)
    items = data["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise ProtocolError("invalid sale items")
    decoded: list[SaleItemRequest] = []
    for item in items:
        if (
            not isinstance(item, dict)
            or not {"product_id", "quantity"}.issubset(item)
            or not set(item).issubset({"product_id", "quantity", "unit_price"})
        ):
            raise ProtocolError("invalid sale item")
        product_id, quantity = item["product_id"], item["quantity"]
        unit_price = item.get("unit_price")
        if not isinstance(product_id, str) or not isinstance(quantity, str):
            raise ProtocolError("invalid sale item values")
        if unit_price is not None and not isinstance(unit_price, str):
            raise ProtocolError("invalid sale item price")
        _validate_uuid(product_id)
        decoded.append(SaleItemRequest(product_id, quantity, unit_price))
    customer_id = data.get("credit_customer_id")
    if customer_id is not None:
        if not isinstance(customer_id, str):
            raise ProtocolError("invalid credit customer")
        _validate_uuid(customer_id)
    return UpdateSaleRequest(token, session_id, sale_id, decoded, customer_id)


def decode_cancel_sale(data: dict[str, object]) -> CancelSaleRequest:
    fields = {"op", "auth_token", "session_id", "sale_id", "reason"}
    if data.get("op") != "cancel_sale" or set(data) != fields:
        raise ProtocolError("invalid cancel_sale fields")
    values = [data[key] for key in ("auth_token", "session_id", "sale_id")]
    if not all(isinstance(value, str) and value for value in values):
        raise ProtocolError("invalid cancel_sale values")
    reason = data["reason"]
    if not isinstance(reason, str):
        raise ProtocolError("invalid cancel_sale reason")
    _validate_uuid(values[1])
    _validate_uuid(values[2])
    return CancelSaleRequest(*values, reason)


def decode_create_customer(data: dict[str, object]) -> CreateCustomerRequest:
    if data.get("op") != "create_customer":
        raise ProtocolError("unsupported operation")
    fields = {"op", "auth_token", "first_name", "last_name", "phone"}
    if not set(data).issubset(fields | {"address", "notes"}):
        raise ProtocolError("invalid create_customer fields")
    token = data.get("auth_token")
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    phone = data.get("phone")
    if not isinstance(token, str) or not token:
        raise ProtocolError("auth_token must be a non-empty string")
    if not all(isinstance(value, str) for value in (first_name, last_name, phone)):
        raise ProtocolError("customer name and phone must be strings")
    if not first_name.strip() or not last_name.strip() or not phone.strip():
        raise ProtocolError("customer fields must not be empty")
    address = data.get("address")
    notes = data.get("notes")
    if address is not None and not isinstance(address, str):
        raise ProtocolError("address must be a string")
    if notes is not None and not isinstance(notes, str):
        raise ProtocolError("notes must be a string")
    return CreateCustomerRequest(
        token,
        first_name.strip(),
        last_name.strip(),
        phone.strip(),
        address.strip() if address is not None else None,
        notes.strip() if notes is not None else None,
    )


def decode_search_customers(data: dict[str, object]) -> SearchCustomersRequest:
    fields = {"op", "auth_token", "query"}
    if data.get("op") != "search_customers" or set(data) != fields:
        raise ProtocolError("invalid search_customers fields")
    token, query = data["auth_token"], data["query"]
    if not isinstance(token, str) or not token:
        raise ProtocolError("auth_token must be a non-empty string")
    if not isinstance(query, str) or len(query) > _MAX_FIELD_LENGTH:
        raise ProtocolError("query must be a string of at most 256 characters")
    return SearchCustomersRequest(token, query)


def decode_record_payment(data: dict[str, object]) -> RecordPaymentRequest:
    fields = {"op", "auth_token", "customer_id", "amount", "session_id"}
    if data.get("op") != "record_payment" or set(data) != fields:
        raise ProtocolError("invalid record_payment fields")
    values = [
        data[key] for key in ("auth_token", "customer_id", "amount", "session_id")
    ]
    if not all(isinstance(value, str) and value for value in values):
        raise ProtocolError("invalid record_payment values")
    _validate_uuid(values[1])
    _validate_uuid(values[3])
    _validate_decimal(values[2])
    return RecordPaymentRequest(*values)


def encode_ok_response(payload: LoginPayload) -> bytes:
    response = {
        "ok": True,
        "user": {
            "id": payload.user.id,
            "username": payload.user.username,
            "full_name": payload.user.full_name,
            "role": payload.user.role,
        },
        "auth_token": payload.auth_token,
        "expires_at": payload.expires_at,
    }
    return (json.dumps(response) + "\n").encode("utf-8")


def encode_session_response(session: SessionPayload | None) -> bytes:
    payload = {
        "ok": True,
        "session": _session_to_dict(session) if session is not None else None,
    }
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_products_response(products: list[ProductPayload]) -> bytes:
    payload = {
        "ok": True,
        "products": [
            {
                "id": product.id,
                "sku": product.sku,
                "barcode": product.barcode,
                "name": product.name,
                "unit": product.unit,
                "selling_price": product.selling_price,
                "minimum_price": product.minimum_price,
                "available_stock": product.available_stock,
                "parent_product_id": product.parent_product_id,
            }
            for product in products
        ],
    }
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_customer_response(customer: CustomerPayload) -> bytes:
    payload = {"ok": True, "customer": customer.__dict__}
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_customers_response(customers: list[CustomerPayload]) -> bytes:
    payload = {"ok": True, "customers": [customer.__dict__ for customer in customers]}
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_payment_response(payment: PaymentPayload) -> bytes:
    payload = {"ok": True, "payment": payment.__dict__}
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_sale_response(detail: object) -> bytes:
    payload = {
        "id": str(detail.id),
        "session_id": str(detail.session_id),
        "terminal_id": detail.terminal_id,
        "employee_user_id": str(detail.employee_user_id),
        "status": detail.status,
        "total": str(detail.total),
        "created_at": detail.created_at.isoformat(),
        "cancellation_reason": getattr(detail, "cancellation_reason", None),
        "credit_customer_id": (
            str(detail.credit_customer_id) if detail.credit_customer_id else None
        ),
        "items": [
            {
                "product_id": str(item.product_id) if item.product_id else None,
                "product_name": item.product_name,
                "product_sku": item.product_sku,
                "unit": item.unit,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
                "original_unit_price": str(
                    getattr(item, "original_unit_price", item.unit_price)
                ),
                "discount_amount": str(getattr(item, "discount_amount", Decimal("0"))),
                "line_total": str(item.line_total),
            }
            for item in detail.items
        ],
    }
    payload["audit_events"] = [
        {
            "event_type": audit.event_type,
            "field_name": audit.field_name,
            "old_value": audit.old_value,
            "new_value": audit.new_value,
            "actor_user_id": str(audit.actor_user_id),
            "created_at": audit.created_at.isoformat(),
        }
        for audit in detail.audit_events
    ]
    return (json.dumps({"ok": True, "sale": payload}) + "\n").encode("utf-8")


def encode_sales_response(page: object) -> bytes:
    sales = [
        {
            "id": str(row.id),
            "session_id": str(row.session_id),
            "terminal_id": row.terminal_id,
            "employee_user_id": str(row.employee_user_id),
            "status": row.status,
            "total": str(row.total),
            "created_at": row.created_at.isoformat(),
            "items": [],
            "audit_events": [],
            "credit_customer_id": (
                str(row.credit_customer_id) if row.credit_customer_id else None
            ),
        }
        for row in page.items
    ]
    return (json.dumps({"ok": True, "sales": sales}) + "\n").encode("utf-8")


def encode_error_response(error: str) -> bytes:
    return (json.dumps({"ok": False, "error": error}) + "\n").encode("utf-8")


def _session_to_dict(session: SessionPayload) -> dict[str, object]:
    return {
        "id": session.id,
        "terminal_id": session.terminal_id,
        "user_id": session.user_id,
        "status": session.status,
        "connection_status": session.connection_status,
        "started_at": session.started_at,
        "closed_at": session.closed_at,
        "last_connected_at": session.last_connected_at,
        "last_activity_at": session.last_activity_at,
    }


def _validate_uuid(value: str) -> None:
    try:
        uuid.UUID(value)
    except ValueError as exc:
        raise ProtocolError("invalid UUID") from exc


def _validate_decimal(value: str) -> None:
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:
        raise ProtocolError("invalid decimal") from exc
    if not decimal.is_finite() or decimal <= 0 or decimal.as_tuple().exponent < -2:
        raise ProtocolError("invalid decimal")


def _decode_json_object(raw: bytes) -> dict[str, object]:
    if not raw or len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message missing or too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("malformed JSON") from exc
    if not isinstance(data, dict):
        raise ProtocolError("message must be a JSON object")
    return data
