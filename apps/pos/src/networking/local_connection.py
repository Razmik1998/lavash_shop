"""TCP implementation of AdminConnection for a same-machine Admin
instance (loopback only). Opens one short-lived connection per request
— no persistent connection to manage or heal — with a connect timeout,
a read timeout, and a single immediate retry on connection failure
before surfacing AdminUnavailableError (see
.claude/specs/2/task-plan.md and .claude/specs/4/task-plan.md).

Trust model (documented exception): loopback traffic never leaves the
machine, so this sends the login request (which carries the password)
in plaintext without TLS. A future LanConnection for a real
cross-machine Admin must not reuse this exception — it requires TLS
per .claude/rules/security.md.

Never log raw request/response bodies — only operation name + outcome."""

from __future__ import annotations

import logging
import socket
import uuid
from collections.abc import Sequence
from decimal import Decimal

from exceptions import (
    AdminUnavailableError,
    AuthenticationError,
    CreditPaymentError,
    CustomerNotFoundError,
    CustomerPhoneAlreadyExistsError,
    SessionAlreadyActiveError,
    SessionClosedError,
    SessionNotFoundError,
)
from models import Role, User
from networking import protocol
from networking.connection import AdminConnection
from networking.protocol import (
    CustomerPayload,
    PaymentPayload,
    ProductPayload,
    SalePayload,
    SessionPayload,
)

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_SECONDS = 3.0
_READ_TIMEOUT_SECONDS = 5.0
_ADMIN_UNAVAILABLE_MESSAGE = "Ադմինիստրատոր հասանելի չէ։"

# Per-op wire-error -> domain-exception mapping. Any error not listed
# here (including "unsupported_operation" / "invalid_request") falls
# back to AdminUnavailableError, matching the existing malformed-
# response handling below.
_START_SESSION_ERRORS: dict[str, type[Exception]] = {
    "session_already_active": SessionAlreadyActiveError,
    "invalid_user": AuthenticationError,
}
_CLOSE_SESSION_ERRORS: dict[str, type[Exception]] = {
    "session_not_found": SessionNotFoundError,
}
_DISCONNECT_ERRORS: dict[str, type[Exception]] = {
    "session_not_found": SessionNotFoundError,
}
_HEARTBEAT_ERRORS: dict[str, type[Exception]] = {
    "session_not_found": SessionNotFoundError,
    "session_closed": SessionClosedError,
}
_CUSTOMER_ERRORS: dict[str, type[Exception]] = {
    "customer_not_found": CustomerNotFoundError,
    "customer_phone_exists": CustomerPhoneAlreadyExistsError,
}
_PAYMENT_ERRORS: dict[str, type[Exception]] = {
    "customer_not_found": CustomerNotFoundError,
    "invalid_credit_payment": CreditPaymentError,
    "session_not_found": SessionNotFoundError,
    "session_closed": SessionClosedError,
}


class LocalConnection(AdminConnection):
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._auth_token: str | None = None

    def is_available(self) -> bool:
        try:
            with socket.create_connection(
                (self._host, self._port), timeout=_CONNECT_TIMEOUT_SECONDS
            ):
                return True
        except OSError:
            return False

    def login(self, username: str, password: str) -> User:
        request = protocol.encode_login_request(
            protocol.LoginRequest(username=username, password=password)
        )
        raw_response = self._send("login", request)
        user = self._parse_login_response(raw_response)
        self._auth_token = user.auth_token
        return user

    def start_session(
        self, user_id: str, terminal_id: str, opening_cash: Decimal = Decimal("0")
    ) -> SessionPayload:
        request = protocol.encode_start_session_request(
            protocol.StartSessionRequest(
                user_id=user_id,
                terminal_id=terminal_id,
                auth_token=self._require_token(),
                opening_cash=(
                    None if opening_cash == Decimal("0") else str(opening_cash)
                ),
            )
        )
        raw_response = self._send("start_session", request)
        session = self._parse_session_response(
            raw_response, "start_session", _START_SESSION_ERRORS
        )
        if session is None:
            # Server contract guarantees a non-null session on ok=True
            # for this op; treat a null session as a malformed response.
            logger.info("networking op=start_session outcome=malformed_response")
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE)
        return session

    def close_session(
        self, session_id: str, closing_cash: Decimal | None = None
    ) -> SessionPayload:
        request = protocol.encode_close_session_request(
            protocol.CloseSessionRequest(
                session_id=session_id,
                auth_token=self._require_token(),
                closing_cash=None if closing_cash is None else str(closing_cash),
            )
        )
        raw_response = self._send("close_session", request)
        session = self._parse_session_response(
            raw_response, "close_session", _CLOSE_SESSION_ERRORS
        )
        if session is None:
            logger.info("networking op=close_session outcome=malformed_response")
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE)
        return session

    def disconnect(self, session_id: str) -> SessionPayload:
        request = protocol.encode_disconnect_request(
            protocol.DisconnectRequest(
                session_id=session_id, auth_token=self._require_token()
            )
        )
        raw_response = self._send("disconnect", request)
        session = self._parse_session_response(
            raw_response, "disconnect", _DISCONNECT_ERRORS
        )
        if session is None:
            logger.info("networking op=disconnect outcome=malformed_response")
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE)
        return session

    def heartbeat(self, session_id: str) -> SessionPayload:
        request = protocol.encode_heartbeat_request(
            protocol.HeartbeatRequest(
                session_id=session_id, auth_token=self._require_token()
            )
        )
        raw_response = self._send("heartbeat", request)
        session = self._parse_session_response(
            raw_response, "heartbeat", _HEARTBEAT_ERRORS
        )
        if session is None:
            logger.info("networking op=heartbeat outcome=malformed_response")
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE)
        return session

    def get_current_session(self, terminal_id: str) -> SessionPayload | None:
        request = protocol.encode_get_current_session_request(
            protocol.GetCurrentSessionRequest(
                terminal_id=terminal_id, auth_token=self._require_token()
            )
        )
        raw_response = self._send("get_current_session", request)
        return self._parse_session_response(raw_response, "get_current_session", {})

    def list_products(self) -> list[ProductPayload]:
        request = protocol.encode_list_products_request(
            protocol.ListProductsRequest(self._require_token())
        )
        raw_response = self._send("list_products", request)
        try:
            data = protocol.decode_response(raw_response)
            if data.get("ok") is True:
                products = protocol.products_from_payload(data.get("products"))
                logger.info(
                    "networking op=list_products outcome=ok count=%s", len(products)
                )
                return products
            error = str(data.get("error"))
        except protocol.ProtocolError as exc:
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE) from exc
        if error == "invalid_token":
            self._auth_token = None
            raise AuthenticationError("Authentication expired.")
        raise AdminUnavailableError(_error_message(error))

    def search_customers(self, query: str) -> list[CustomerPayload]:
        raw_response = self._send(
            "search_customers",
            protocol.encode_search_customers_request(
                protocol.SearchCustomersRequest(self._require_token(), query)
            ),
        )
        try:
            data = protocol.decode_response(raw_response)
            if data.get("ok") is True:
                return protocol.customers_from_payload(data.get("customers"))
            error = str(data.get("error"))
        except protocol.ProtocolError as exc:
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE) from exc
        self._raise_wire_error("search_customers", error, _CUSTOMER_ERRORS)
        raise AssertionError("unreachable")

    def create_customer(
        self,
        first_name: str,
        last_name: str,
        phone: str,
        address: str | None = None,
        notes: str | None = None,
    ) -> CustomerPayload:
        raw_response = self._send(
            "create_customer",
            protocol.encode_create_customer_request(
                protocol.CreateCustomerRequest(
                    self._require_token(), first_name, last_name, phone, address, notes
                )
            ),
        )
        try:
            data = protocol.decode_response(raw_response)
            if data.get("ok") is True:
                return protocol.customer_from_payload(data.get("customer"))
            error = str(data.get("error"))
        except protocol.ProtocolError as exc:
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE) from exc
        self._raise_wire_error("create_customer", error, _CUSTOMER_ERRORS)
        raise AssertionError("unreachable")

    def record_payment(
        self, customer_id: str, amount: Decimal, session_id: str
    ) -> PaymentPayload:
        raw_response = self._send(
            "record_payment",
            protocol.encode_record_payment_request(
                protocol.RecordPaymentRequest(
                    self._require_token(), customer_id, str(amount), session_id
                )
            ),
        )
        try:
            data = protocol.decode_response(raw_response)
            if data.get("ok") is True:
                return protocol.payment_from_payload(data.get("payment"))
            error = str(data.get("error"))
        except protocol.ProtocolError as exc:
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE) from exc
        self._raise_wire_error("record_payment", error, _PAYMENT_ERRORS)
        raise AssertionError("unreachable")

    def record_full_payment(
        self, customer_id: str, amount: Decimal, session_id: str
    ) -> PaymentPayload:
        return self.record_payment(customer_id, amount, session_id)

    def _send(self, op: str, request: bytes) -> bytes:
        try:
            return self._send_with_one_retry(request)
        except OSError as exc:
            logger.info("networking op=%s outcome=admin_unavailable", op)
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE) from exc

    def create_sale(
        self,
        session_id: str,
        terminal_id: str,
        sale_id: str,
        items: Sequence[tuple[str, str, str | None]],
        credit_customer_id: str | None = None,
    ) -> SalePayload:
        request = protocol.encode_create_sale_request(
            protocol.CreateSaleRequest(
                self._require_token(),
                session_id,
                terminal_id,
                sale_id,
                [
                    protocol.SaleItemRequest(product_id, quantity, unit_price)
                    for product_id, quantity, unit_price in items
                ],
                credit_customer_id,
            )
        )
        raw_response = self._send("create_sale", request)
        try:
            data = protocol.decode_response(raw_response)
            if data.get("ok") is True:
                return protocol.sale_from_payload(data["sale"])
            error = str(data.get("error"))
        except (protocol.ProtocolError, KeyError) as exc:
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE) from exc
        if error == "invalid_token":
            raise AuthenticationError("Authentication expired.")
        raise AdminUnavailableError(_error_message(error))

    def list_session_sales(self, session_id: str) -> list[SalePayload]:
        raw_response = self._send(
            "list_session_sales",
            protocol.encode_session_sales_request(
                protocol.SessionSalesRequest(self._require_token(), session_id)
            ),
        )
        try:
            data = protocol.decode_response(raw_response)
            if data.get("ok") is True:
                return protocol.sales_from_payload(data.get("sales"))
            error = str(data.get("error"))
        except protocol.ProtocolError as exc:
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE) from exc
        if error == "invalid_token":
            self._auth_token = None
            raise AuthenticationError("Authentication expired.")
        raise AdminUnavailableError(_error_message(error))

    def get_sale_detail(self, session_id: str, sale_id: str) -> SalePayload:
        raw_response = self._send(
            "get_sale_detail",
            protocol.encode_sale_detail_request(
                protocol.SaleDetailRequest(self._require_token(), session_id, sale_id)
            ),
        )
        try:
            data = protocol.decode_response(raw_response)
            if data.get("ok") is True:
                return protocol.sale_from_payload(data.get("sale"))
            error = str(data.get("error"))
        except protocol.ProtocolError as exc:
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE) from exc
        if error == "invalid_token":
            self._auth_token = None
            raise AuthenticationError("Authentication expired.")
        raise AdminUnavailableError(_error_message(error))

    def unlock_sale(
        self, session_id: str, sale_id: str, secret_key: str
    ) -> SalePayload:
        raw_response = self._send(
            "unlock_sale",
            protocol.encode_unlock_sale_request(
                protocol.UnlockSaleRequest(
                    self._require_token(), session_id, sale_id, secret_key
                )
            ),
        )
        return self._sale_response(raw_response)

    def update_sale(
        self,
        session_id: str,
        sale_id: str,
        items: Sequence[tuple[str, str, str | None]],
        credit_customer_id: str | None = None,
    ) -> SalePayload:
        raw_response = self._send(
            "update_sale",
            protocol.encode_update_sale_request(
                protocol.UpdateSaleRequest(
                    self._require_token(),
                    session_id,
                    sale_id,
                    [
                        protocol.SaleItemRequest(product_id, quantity, unit_price)
                        for product_id, quantity, unit_price in items
                    ],
                    credit_customer_id,
                )
            ),
        )
        return self._sale_response(raw_response)

    def cancel_sale(self, session_id: str, sale_id: str, reason: str) -> SalePayload:
        raw_response = self._send(
            "cancel_sale",
            protocol.encode_cancel_sale_request(
                protocol.CancelSaleRequest(
                    self._require_token(), session_id, sale_id, reason
                )
            ),
        )
        return self._sale_response(raw_response)

    def _sale_response(self, raw_response: bytes) -> SalePayload:
        try:
            data = protocol.decode_response(raw_response)
            if data.get("ok") is True:
                return protocol.sale_from_payload(data["sale"])
            error = str(data.get("error"))
        except (protocol.ProtocolError, KeyError) as exc:
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE) from exc
        if error == "invalid_token":
            raise AuthenticationError("Authentication expired.")
        raise AdminUnavailableError(_error_message(error))

    def _send_with_one_retry(self, request: bytes) -> bytes:
        try:
            return self._send_once(request)
        except OSError:
            return self._send_once(request)

    def _send_once(self, request: bytes) -> bytes:
        with socket.create_connection(
            (self._host, self._port), timeout=_CONNECT_TIMEOUT_SECONDS
        ) as sock:
            sock.settimeout(_READ_TIMEOUT_SECONDS)
            sock.sendall(request)
            with sock.makefile("rb") as reader:
                return reader.readline(protocol.MAX_MESSAGE_BYTES)

    def _parse_login_response(self, raw_response: bytes) -> User:
        try:
            data = protocol.decode_response(raw_response)
            if data.get("ok") is True:
                user = _user_from_payload(
                    data.get("user"), str(data["auth_token"]), str(data["expires_at"])
                )
                logger.info("networking op=login outcome=ok")
                return user
            error = data.get("error")
        except protocol.ProtocolError as exc:
            logger.info("networking op=login outcome=malformed_response")
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE) from exc

        if error == "invalid_credentials":
            logger.info("networking op=login outcome=invalid_credentials")
            raise AuthenticationError("Invalid username or password.")

        logger.info("networking op=login outcome=%s", error)
        raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE)

    def cash_request(self, op, **fields):
        import json

        request = {"op": op, "auth_token": self._require_token(), **fields}
        response = json.loads(self._send(op, (json.dumps(request) + "\n").encode()))
        if not response.get("ok"):
            raise ValueError(response.get("error", "Cash operation failed"))
        return response

    def _require_token(self) -> str:
        if not self._auth_token:
            raise AuthenticationError("Authentication required.")
        return self._auth_token

    def _parse_session_response(
        self,
        raw_response: bytes,
        op: str,
        error_map: dict[str, type[Exception]],
    ) -> SessionPayload | None:
        try:
            data = protocol.decode_response(raw_response)
            if data.get("ok") is True:
                session_data = data.get("session")
                logger.info("networking op=%s outcome=ok", op)
                if session_data is None:
                    return None
                return protocol.session_from_payload(session_data)
            error = data.get("error")
        except protocol.ProtocolError as exc:
            logger.info("networking op=%s outcome=malformed_response", op)
            raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE) from exc

        if str(error) == "invalid_token":
            self._auth_token = None
            logger.info("networking op=%s outcome=invalid_token", op)
            raise AuthenticationError("Authentication expired.")

        exc_type = error_map.get(str(error))
        if exc_type is not None:
            logger.info("networking op=%s outcome=%s", op, error)
            raise exc_type(_error_message(str(error)))

        logger.info("networking op=%s outcome=%s", op, error)
        raise AdminUnavailableError(_ADMIN_UNAVAILABLE_MESSAGE)


def _error_message(error: str) -> str:
    if error == "invalid_cancellation_reason":
        return "Չեղարկման պատճառը պարտադիր է։"
    if error == "invalid_price":
        return "Ապրանքի գինը փոխվել է կամ զեղչը թույլատրելի միջակայքից դուրս է։"
    if error == "invalid_quantity":
        return "Ապրանքի քանակը պետք է լինի դրական և ունենա առավելագույնը 3 տասնորդական նիշ։"
    if error == "sale_id_conflict":
        return "Վաճառքի նույնացուցիչի հետ անհամապատասխանություն կա։"
    if error == "internal_error":
        return (
            "Վաճառքի պահպանումը չհաստատվեց։ Կրկնելուց առաջ ստուգեք "
            "վաճառքների պատմությունը։"
        )
    return f"Request rejected: {error}"


def _user_from_payload(payload: object, auth_token: str, expires_at: str) -> User:
    if not isinstance(payload, dict):
        raise protocol.ProtocolError("missing user payload")
    try:
        return User(
            id=uuid.UUID(str(payload["id"])),
            username=str(payload["username"]),
            full_name=str(payload["full_name"]),
            role=Role(str(payload["role"])),
            is_active=True,
            auth_token=auth_token,
            token_expires_at=expires_at,
        )
    except (KeyError, ValueError) as exc:
        raise protocol.ProtocolError("invalid user payload") from exc
