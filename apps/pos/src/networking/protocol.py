"""Wire protocol for the POS -> Admin TCP connection: one JSON object
per line (newline-delimited), one request/response per TCP connection.
Mirrors apps/admin/src/networking/protocol.py — kept as two small,
independent copies rather than a shared package, since apps/pos and
apps/admin import nothing from each other.

Never log raw request/response bodies here or in callers — the login
op carries the password."""

from __future__ import annotations

import json
from dataclasses import dataclass

MAX_MESSAGE_BYTES = 65536


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
    auth_token: str


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


@dataclass(frozen=True)
class SaleItemPayload:
    product_id: str | None
    product_name: str
    product_sku: str
    unit: str
    quantity: str
    unit_price: str
    line_total: str
    discount_amount: str = "0"
    original_unit_price: str = "0"


@dataclass(frozen=True)
class SaleAuditPayload:
    event_type: str
    field_name: str | None
    old_value: dict[str, object] | None
    new_value: dict[str, object] | None
    actor_user_id: str
    created_at: str


@dataclass(frozen=True)
class SalePayload:
    id: str
    session_id: str
    terminal_id: str
    employee_user_id: str
    status: str
    total: str
    created_at: str
    items: list[SaleItemPayload]
    audit_events: list[SaleAuditPayload]
    credit_customer_id: str | None = None
    cancellation_reason: str | None = None


def encode_login_request(request: LoginRequest) -> bytes:
    payload = {
        "op": "login",
        "username": request.username,
        "password": request.password,
    }
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_start_session_request(request: StartSessionRequest) -> bytes:
    payload = {
        "op": "start_session",
        "user_id": request.user_id,
        "terminal_id": request.terminal_id,
    }
    if request.auth_token is not None:
        payload["auth_token"] = request.auth_token
    if request.opening_cash is not None:
        payload["opening_cash"] = request.opening_cash
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_close_session_request(request: CloseSessionRequest) -> bytes:
    payload = {"op": "close_session", "session_id": request.session_id}
    if request.auth_token is not None:
        payload["auth_token"] = request.auth_token
    if request.closing_cash is not None:
        payload["closing_cash"] = request.closing_cash
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_disconnect_request(request: DisconnectRequest) -> bytes:
    payload = {"op": "disconnect", "session_id": request.session_id}
    if request.auth_token is not None:
        payload["auth_token"] = request.auth_token
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_heartbeat_request(request: HeartbeatRequest) -> bytes:
    payload = {"op": "heartbeat", "session_id": request.session_id}
    if request.auth_token is not None:
        payload["auth_token"] = request.auth_token
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_get_current_session_request(request: GetCurrentSessionRequest) -> bytes:
    payload = {
        "op": "get_current_session",
        "terminal_id": request.terminal_id,
    }
    if request.auth_token is not None:
        payload["auth_token"] = request.auth_token
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_list_products_request(request: ListProductsRequest) -> bytes:
    payload = {"op": "list_products", "auth_token": request.auth_token}
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_create_sale_request(request: CreateSaleRequest) -> bytes:
    payload = {
        "op": "create_sale",
        "auth_token": request.auth_token,
        "session_id": request.session_id,
        "terminal_id": request.terminal_id,
        "sale_id": request.sale_id,
        "items": [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                **(
                    {"unit_price": item.unit_price}
                    if item.unit_price is not None
                    else {}
                ),
            }
            for item in request.items
        ],
    }
    if request.credit_customer_id is not None:
        payload["credit_customer_id"] = request.credit_customer_id
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_session_sales_request(request: SessionSalesRequest) -> bytes:
    payload = {"op": "list_session_sales", "auth_token": request.auth_token,
               "session_id": request.session_id}
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_sale_detail_request(request: SaleDetailRequest) -> bytes:
    payload = {"op": "get_sale_detail", "auth_token": request.auth_token,
               "session_id": request.session_id, "sale_id": request.sale_id}
    return (json.dumps(payload) + "\n").encode("utf-8")


def encode_unlock_sale_request(request: UnlockSaleRequest) -> bytes:
    return _encode_request("unlock_sale", request.__dict__)


def encode_update_sale_request(request: UpdateSaleRequest) -> bytes:
    payload = {
        "auth_token": request.auth_token, "session_id": request.session_id,
        "sale_id": request.sale_id,
        "items": [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                **(
                    {"unit_price": item.unit_price}
                    if item.unit_price is not None
                    else {}
                ),
            }
            for item in request.items
        ],
    }
    if request.credit_customer_id is not None:
        payload["credit_customer_id"] = request.credit_customer_id
    return _encode_request("update_sale", payload)


def encode_cancel_sale_request(request: CancelSaleRequest) -> bytes:
    return _encode_request("cancel_sale", request.__dict__)


def encode_create_customer_request(request: CreateCustomerRequest) -> bytes:
    payload = {
        "auth_token": request.auth_token,
        "first_name": request.first_name,
        "last_name": request.last_name,
        "phone": request.phone,
    }
    if request.address is not None:
        payload["address"] = request.address
    if request.notes is not None:
        payload["notes"] = request.notes
    return _encode_request("create_customer", payload)


def encode_search_customers_request(request: SearchCustomersRequest) -> bytes:
    return _encode_request("search_customers", request.__dict__)


def encode_record_payment_request(request: RecordPaymentRequest) -> bytes:
    return _encode_request("record_payment", request.__dict__)


def _encode_request(operation: str, payload: dict[str, object]) -> bytes:
    return (json.dumps({"op": operation, **payload}) + "\n").encode("utf-8")


def decode_response(raw: bytes) -> dict[str, object]:
    if not raw or len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message missing or too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("malformed JSON") from exc
    if not isinstance(data, dict):
        raise ProtocolError("message must be a JSON object")
    return data


def session_from_payload(payload: object) -> SessionPayload:
    """Parses the `session` field of a decoded response into a
    SessionPayload. Raises ProtocolError if the shape is wrong -
    callers must not trust the wire blindly."""
    if not isinstance(payload, dict):
        raise ProtocolError("missing session payload")
    try:
        return SessionPayload(
            id=str(payload["id"]),
            terminal_id=str(payload["terminal_id"]),
            user_id=str(payload["user_id"]),
            status=str(payload["status"]),
            connection_status=str(payload["connection_status"]),
            started_at=str(payload["started_at"]),
            closed_at=(
                None
                if payload.get("closed_at") is None
                else str(payload["closed_at"])
            ),
            last_connected_at=str(payload["last_connected_at"]),
            last_activity_at=str(payload["last_activity_at"]),
        )
    except (KeyError, ValueError) as exc:
        raise ProtocolError("invalid session payload") from exc


def products_from_payload(payload: object) -> list[ProductPayload]:
    if not isinstance(payload, list):
        raise ProtocolError("missing products payload")
    products: list[ProductPayload] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ProtocolError("invalid product payload")
        try:
            values = [item["id"], item["sku"], item["name"], item["unit"]]
            barcode = item["barcode"]
            if not all(isinstance(value, str) and value for value in values):
                raise ProtocolError("invalid product fields")
            if barcode is not None and not isinstance(barcode, str):
                raise ProtocolError("invalid product barcode")
            selling_price = item["selling_price"]
            minimum_price = item.get("minimum_price")
            available_stock = item["available_stock"]
            parent_product_id = item.get("parent_product_id")
            if selling_price is not None and not isinstance(selling_price, str):
                raise ProtocolError("invalid product selling price")
            if minimum_price is not None and not isinstance(minimum_price, str):
                raise ProtocolError("invalid product minimum price")
            if available_stock is not None and not isinstance(available_stock, str):
                raise ProtocolError("invalid product stock")
            if parent_product_id is not None and not isinstance(parent_product_id, str):
                raise ProtocolError("invalid product parent")
            if selling_price is None and available_stock is not None:
                raise ProtocolError("invalid parent product values")
            products.append(
                ProductPayload(
                    id=values[0],
                    sku=values[1],
                    barcode=barcode,
                    name=values[2],
                    unit=values[3],
                    selling_price=selling_price,
                    minimum_price=minimum_price,
                    available_stock=available_stock,
                    parent_product_id=parent_product_id,
                )
            )
        except (KeyError, ValueError) as exc:
            raise ProtocolError("invalid product payload") from exc
    return products


def customer_from_payload(payload: object) -> CustomerPayload:
    if not isinstance(payload, dict):
        raise ProtocolError("missing customer payload")
    try:
        return CustomerPayload(
            str(payload["id"]),
            str(payload["first_name"]),
            str(payload["last_name"]),
            str(payload["phone"]),
            str(payload["current_debt"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError("invalid customer payload") from exc


def customers_from_payload(payload: object) -> list[CustomerPayload]:
    if not isinstance(payload, list):
        raise ProtocolError("missing customers payload")
    customers: list[CustomerPayload] = []
    for item in payload:
        customers.append(customer_from_payload(item))
    return customers


def payment_from_payload(payload: object) -> PaymentPayload:
    if not isinstance(payload, dict):
        raise ProtocolError("missing payment payload")
    try:
        return PaymentPayload(
            str(payload["id"]),
            str(payload["customer_id"]),
            str(payload["amount"]),
            str(payload["session_id"]),
            str(payload["user_id"]),
            str(payload["paid_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError("invalid payment payload") from exc


def sales_from_payload(payload: object) -> list[SalePayload]:
    if not isinstance(payload, list):
        raise ProtocolError("missing sales payload")
    return [_sale_from_payload(item) for item in payload]


def sale_from_payload(payload: object) -> SalePayload:
    return _sale_from_payload(payload)


def _sale_from_payload(payload: object) -> SalePayload:
    if not isinstance(payload, dict):
        raise ProtocolError("invalid sale payload")
    try:
        items = payload["items"]
        audits = payload["audit_events"]
        if not isinstance(items, list) or not isinstance(audits, list):
            raise ProtocolError("invalid sale detail lists")
        return SalePayload(
            id=str(payload["id"]), session_id=str(payload["session_id"]),
            terminal_id=str(payload["terminal_id"]),
            employee_user_id=str(payload["employee_user_id"]),
            status=str(payload["status"]), total=str(payload["total"]),
            created_at=str(payload["created_at"]),
            items=[SaleItemPayload(
                None if item.get("product_id") is None else str(item["product_id"]),
                str(item["product_name"]), str(item["product_sku"]),
                str(item["unit"]), str(item["quantity"]), str(item["unit_price"]),
                str(item["line_total"]), str(item.get("discount_amount", "0")),
                str(item.get("original_unit_price", item["unit_price"])),
            ) for item in items if isinstance(item, dict)],
            audit_events=[SaleAuditPayload(
                str(audit["event_type"]),
                (
                    None
                    if audit.get("field_name") is None
                    else str(audit["field_name"])
                ),
                (
                    audit.get("old_value")
                    if isinstance(audit.get("old_value"), dict)
                    else None
                ),
                (
                    audit.get("new_value")
                    if isinstance(audit.get("new_value"), dict)
                    else None
                ),
                str(audit["actor_user_id"]), str(audit["created_at"]),
            ) for audit in audits if isinstance(audit, dict)],
            credit_customer_id=(
                None
                if payload.get("credit_customer_id") is None
                else str(payload["credit_customer_id"])
            ),
            cancellation_reason=(
                None
                if payload.get("cancellation_reason") is None
                else str(payload["cancellation_reason"])
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError("invalid sale payload") from exc
