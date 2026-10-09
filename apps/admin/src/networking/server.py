"""Background TCP listener for POS requests: login, and POS session
lifecycle (start/close/heartbeat/get-current-session).

Runs in a daemon thread inside the Admin process (started/stopped with
the app lifecycle from main.py). Delegates authentication to the
existing AuthService and session lifecycle to a PosSessionService (see
the `PosSessionService` Protocol below) — this module never touches
SQL or any table directly (see .claude/rules/database.md).

Trust model: this listens on all interfaces (0.0.0.0) so it is already
reachable from the LAN in principle, but no TLS is implemented yet.
That is acceptable only for today's same-machine LocalConnection
client (loopback traffic never leaves the machine); a future
cross-machine LanConnection client must not be pointed at this server
until TLS is added, per .claude/rules/security.md.

Never log raw request/response bodies — only `op=<op> outcome=<outcome>`."""

from __future__ import annotations

import logging
import secrets
import socketserver
import threading
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol

from exceptions import (
    AuthenticationError,
    CustomerNotFoundError,
    CustomerPhoneAlreadyExistsError,
    InvalidCreditPaymentError,
    InvalidQuantityError,
    InvalidSaleCancellationReasonError,
    InvalidSalePriceError,
    InvalidSaleUnlockKeyError,
    ProductNotFoundError,
    SaleAlreadyEditingError,
    SaleIdConflictError,
    SaleNotEditableError,
    SaleNotFoundError,
    SessionAlreadyActiveError,
    SessionClosedError,
    SessionNotFoundError,
    SessionNotOwnedError,
    TerminalMismatchError,
)
from models import PosSession, Role, User
from networking import protocol
from services import AuthService

logger = logging.getLogger(__name__)

_READ_TIMEOUT_SECONDS = 5.0


class PosSessionService(Protocol):
    """Interface the request handler below depends on for POS session
    lifecycle operations. Implemented elsewhere (services.py, by
    implementer) and constructed by main.py; this module only depends
    on this shape, never on a repository or SQLAlchemy session
    directly.

    Every `PosSession` returned by these methods must carry a
    `connection_status` attribute (`"connected"` | `"disconnected"`),
    attached the same way `ProductService` attaches `stock_status`/
    `profit_margin` in services.py (`# type: ignore[attr-defined]`) —
    it is computed at read time from `last_connected_at`, never a DB
    column.
    """

    def start_session(
        self, user_id: uuid.UUID, terminal_id: str, opening_cash: Decimal = Decimal("0")
    ) -> PosSession:
        """Starts (creates) a new ACTIVE session for `terminal_id`,
        owned by `user_id`.

        Raises:
            AuthenticationError: `user_id` does not reference a valid,
                active employee user (wire error: "invalid_user").
            SessionAlreadyActiveError: `terminal_id` already has an
                active session (wire error: "session_already_active").
        """
        ...

    def close_session(
        self, session_id: uuid.UUID, closing_cash: Decimal | None = None
    ) -> PosSession:
        """Closes the session (status=CLOSED, closed_at=now()).
        Idempotent: closing an already-closed session returns it
        unchanged rather than raising.

        Raises:
            SessionNotFoundError: no session exists with this id (wire
                error: "session_not_found").
        """
        ...

    def disconnect(self, session_id: uuid.UUID) -> PosSession:
        """Marks the session connection status as disconnected while
        leaving the session active.

        Raises:
            SessionNotFoundError: no session exists with this id (wire
                error: "session_not_found").
        """
        ...

    def heartbeat(self, session_id: uuid.UUID) -> PosSession:
        """Updates `last_connected_at`/`last_activity_at` to now() for
        an active session.

        Raises:
            SessionNotFoundError: no session exists with this id (wire
                error: "session_not_found").
            SessionClosedError: session exists but is already closed
                (wire error: "session_closed").
        """
        ...

    def get_current_session(self, terminal_id: str) -> PosSession | None:
        """Returns the active session for `terminal_id`, or None if
        there isn't one. Never raises for an unknown terminal_id."""
        ...


class SalesService(Protocol):
    def search_customers(self, query: str) -> list[object]: ...

    def create_customer(
        self,
        first_name: str,
        last_name: str,
        phone: str,
        address: str | None = None,
        notes: str | None = None,
    ) -> object: ...

    def record_payment(
        self,
        authenticated_user_id: uuid.UUID,
        customer_id: uuid.UUID,
        amount: Decimal,
        session_id: uuid.UUID,
    ) -> object: ...

    def create_sale(
        self,
        authenticated_user_id: uuid.UUID,
        session_id: uuid.UUID,
        terminal_id: str,
        client_sale_id: uuid.UUID,
        requested_items: list[tuple[uuid.UUID, Decimal]],
        credit_customer_id: uuid.UUID | None = None,
    ) -> object: ...

    def list_session_sales(
        self, authenticated_user_id: uuid.UUID, session_id: uuid.UUID
    ) -> object: ...

    def get_session_sale_detail(
        self,
        authenticated_user_id: uuid.UUID,
        session_id: uuid.UUID,
        sale_id: uuid.UUID,
    ) -> object: ...

    def unlock_sale(
        self,
        authenticated_user_id: uuid.UUID,
        session_id: uuid.UUID,
        sale_id: uuid.UUID,
        secret_key: str,
    ) -> object: ...

    def update_sale(
        self,
        authenticated_user_id: uuid.UUID,
        session_id: uuid.UUID,
        sale_id: uuid.UUID,
        requested_items: list[tuple[uuid.UUID, Decimal]],
        credit_customer_id: uuid.UUID | None = None,
    ) -> object: ...

    def cancel_sale(
        self,
        authenticated_user_id: uuid.UUID,
        session_id: uuid.UUID,
        sale_id: uuid.UUID,
        reason: str,
    ) -> object: ...


class ProductCatalogService(Protocol):
    def list_active_products(self) -> list[object]: ...

    def list_active_sellable_products(self) -> list[object]: ...


class AdminTcpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        host: str,
        port: int,
        auth_service: AuthService,
        session_service: PosSessionService,
        sales_service: SalesService | None = None,
        product_service: ProductCatalogService | None = None,
    ) -> None:
        self.auth_service = auth_service
        self.session_service = session_service
        self.sales_service = sales_service
        self.product_service = product_service
        self.tokens: dict[str, tuple[User, datetime]] = {}
        super().__init__((host, port), _RequestHandler)


class _RequestHandler(socketserver.StreamRequestHandler):
    server: AdminTcpServer

    def setup(self) -> None:
        self.request.settimeout(_READ_TIMEOUT_SECONDS)
        super().setup()

    def handle(self) -> None:
        try:
            raw_line = self.rfile.readline(protocol.MAX_MESSAGE_BYTES)
        except OSError:
            logger.info("networking op=unknown outcome=read_timeout")
            return

        try:
            data = protocol.decode_envelope(raw_line)
        except protocol.ProtocolError:
            logger.info("networking op=unknown outcome=invalid_request")
            self._send(protocol.encode_error_response("invalid_request"))
            return

        op = data.get("op")
        handler = self._OPS.get(op) if isinstance(op, str) else None
        if handler is None:
            logger.info("networking op=%s outcome=unsupported_operation", op)
            self._send(protocol.encode_error_response("unsupported_operation"))
            return
        handler(self, data)

    def _handle_login(self, data: dict[str, object]) -> None:
        try:
            request = protocol.decode_login(data)
        except protocol.ProtocolError:
            logger.info("networking op=login outcome=invalid_request")
            self._send(protocol.encode_error_response("invalid_request"))
            return

        try:
            user = self.server.auth_service.login(
                request.username, request.password, Role.EMPLOYEE
            )
        except AuthenticationError:
            logger.info("networking op=login outcome=invalid_credentials")
            self._send(protocol.encode_error_response("invalid_credentials"))
            return

        logger.info("networking op=login outcome=ok")
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        self.server.tokens[token] = (user, expires_at)
        self._send(
            protocol.encode_ok_response(
                protocol.LoginPayload(
                    _to_user_payload(user), token, expires_at.isoformat()
                )
            )
        )

    def _authenticated_user(self, token: str | None) -> User | None:
        if token is None:
            raise PermissionError("invalid_token")
        entry = self.server.tokens.get(token)
        if entry is None:
            raise PermissionError("invalid_token")
        user, expires_at = entry
        if expires_at <= datetime.now(UTC):
            self.server.tokens.pop(token, None)
            raise PermissionError("token_expired")
        if not user.is_active or user.role is not Role.EMPLOYEE:
            raise PermissionError("invalid_token")
        return user

    def _handle_start_session(self, data: dict[str, object]) -> None:
        try:
            request = protocol.decode_start_session(data)
        except protocol.ProtocolError:
            logger.info("networking op=start_session outcome=invalid_request")
            self._send(protocol.encode_error_response("invalid_request"))
            return
        try:
            user = self._authenticated_user(request.auth_token)
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return
        if str(user.id) != request.user_id:
            self._send(protocol.encode_error_response("invalid_token"))
            return

        try:
            if request.opening_cash is None:
                session = self.server.session_service.start_session(
                    uuid.UUID(request.user_id), request.terminal_id
                )
            else:
                session = self.server.session_service.start_session(
                    uuid.UUID(request.user_id),
                    request.terminal_id,
                    _parse_cash(request.opening_cash),
                )
        except AuthenticationError:
            logger.info("networking op=start_session outcome=invalid_user")
            self._send(protocol.encode_error_response("invalid_user"))
            return
        except SessionAlreadyActiveError:
            logger.info("networking op=start_session outcome=session_already_active")
            self._send(protocol.encode_error_response("session_already_active"))
            return
        except (InvalidOperation, ValueError):
            logger.info("networking op=start_session outcome=invalid_request")
            self._send(protocol.encode_error_response("invalid_request"))
            return

        logger.info("networking op=start_session outcome=ok")
        self._send(protocol.encode_session_response(_to_session_payload(session)))

    def _handle_close_session(self, data: dict[str, object]) -> None:
        try:
            request = protocol.decode_close_session(data)
        except protocol.ProtocolError:
            logger.info("networking op=close_session outcome=invalid_request")
            self._send(protocol.encode_error_response("invalid_request"))
            return
        try:
            self._authenticated_user(request.auth_token)
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return

        try:
            if request.closing_cash is None:
                session = self.server.session_service.close_session(
                    uuid.UUID(request.session_id)
                )
            else:
                session = self.server.session_service.close_session(
                    uuid.UUID(request.session_id), _parse_cash(request.closing_cash)
                )
        except SessionNotFoundError:
            logger.info("networking op=close_session outcome=session_not_found")
            self._send(protocol.encode_error_response("session_not_found"))
            return
        except (InvalidOperation, ValueError):
            logger.info("networking op=close_session outcome=invalid_request")
            self._send(protocol.encode_error_response("invalid_request"))
            return

        logger.info("networking op=close_session outcome=ok")
        self._send(protocol.encode_session_response(_to_session_payload(session)))

    def _handle_disconnect(self, data: dict[str, object]) -> None:
        try:
            request = protocol.decode_disconnect(data)
        except protocol.ProtocolError:
            logger.info("networking op=disconnect outcome=invalid_request")
            self._send(protocol.encode_error_response("invalid_request"))
            return
        try:
            self._authenticated_user(request.auth_token)
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return

        try:
            session = self.server.session_service.disconnect(
                uuid.UUID(request.session_id)
            )
        except SessionNotFoundError:
            logger.info("networking op=disconnect outcome=session_not_found")
            self._send(protocol.encode_error_response("session_not_found"))
            return

        logger.info("networking op=disconnect outcome=ok")
        self._send(protocol.encode_session_response(_to_session_payload(session)))

    def _handle_heartbeat(self, data: dict[str, object]) -> None:
        try:
            request = protocol.decode_heartbeat(data)
        except protocol.ProtocolError:
            logger.info("networking op=heartbeat outcome=invalid_request")
            self._send(protocol.encode_error_response("invalid_request"))
            return
        try:
            self._authenticated_user(request.auth_token)
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return

        try:
            session = self.server.session_service.heartbeat(
                uuid.UUID(request.session_id)
            )
        except SessionNotFoundError:
            logger.info("networking op=heartbeat outcome=session_not_found")
            self._send(protocol.encode_error_response("session_not_found"))
            return
        except SessionClosedError:
            logger.info("networking op=heartbeat outcome=session_closed")
            self._send(protocol.encode_error_response("session_closed"))
            return

        logger.info("networking op=heartbeat outcome=ok")
        self._send(protocol.encode_session_response(_to_session_payload(session)))

    def _handle_get_current_session(self, data: dict[str, object]) -> None:
        try:
            request = protocol.decode_get_current_session(data)
        except protocol.ProtocolError:
            logger.info("networking op=get_current_session outcome=invalid_request")
            self._send(protocol.encode_error_response("invalid_request"))
            return
        try:
            self._authenticated_user(request.auth_token)
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return

        session = self.server.session_service.get_current_session(request.terminal_id)
        logger.info("networking op=get_current_session outcome=ok")
        payload = _to_session_payload(session) if session is not None else None
        self._send(protocol.encode_session_response(payload))

    def _handle_create_sale(self, data: dict[str, object]) -> None:
        if self.server.sales_service is None:
            self._send(protocol.encode_error_response("unsupported_operation"))
            return
        try:
            request = protocol.decode_create_sale(data)
            user = self._authenticated_user(request.auth_token)
            items = [
                (
                    uuid.UUID(item.product_id),
                    _parse_quantity(item.quantity),
                    _parse_price(item.unit_price)
                    if item.unit_price is not None
                    else None,
                )
                for item in request.items
            ]
            receipt = self.server.sales_service.create_sale(
                user.id,
                uuid.UUID(request.session_id),
                request.terminal_id,
                uuid.UUID(request.sale_id),
                items,
                uuid.UUID(request.credit_customer_id)
                if request.credit_customer_id
                else None,
            )
        except protocol.ProtocolError:
            self._send(protocol.encode_error_response("invalid_request"))
            return
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return
        except InvalidSalePriceError as exc:
            logger.warning(
                "networking op=create_sale outcome=rejected reason=invalid_price "
                "sale_id=%s detail=%s",
                request.sale_id,
                exc,
            )
            self._send(protocol.encode_error_response("invalid_price"))
            return
        except InvalidQuantityError as exc:
            logger.warning(
                "networking op=create_sale outcome=rejected reason=invalid_quantity "
                "detail=%s",
                exc,
            )
            self._send(protocol.encode_error_response("invalid_quantity"))
            return
        except SessionNotFoundError:
            self._send(protocol.encode_error_response("session_not_found"))
            return
        except SessionClosedError:
            self._send(protocol.encode_error_response("session_closed"))
            return
        except SessionNotOwnedError:
            self._send(protocol.encode_error_response("session_not_owned"))
            return
        except TerminalMismatchError:
            self._send(protocol.encode_error_response("terminal_mismatch"))
            return
        except ProductNotFoundError:
            self._send(protocol.encode_error_response("product_not_found"))
            return
        except SaleIdConflictError as exc:
            logger.warning(
                "networking op=create_sale outcome=rejected "
                "reason=sale_id_conflict detail=%s",
                exc,
            )
            self._send(protocol.encode_error_response("sale_id_conflict"))
            return
        except (InvalidOperation, ValueError):
            logger.exception(
                "networking op=create_sale outcome=failed "
                "reason=unexpected_validation_or_service_error sale_id=%s",
                request.sale_id,
            )
            self._send(protocol.encode_error_response("internal_error"))
            return
        self._send(protocol.encode_sale_response(receipt))

    def _handle_list_session_sales(self, data: dict[str, object]) -> None:
        if self.server.sales_service is None:
            self._send(protocol.encode_error_response("unsupported_operation"))
            return
        try:
            request = protocol.decode_session_sales(data)
            user = self._authenticated_user(request.auth_token)
            if user is None:
                raise PermissionError("invalid_token")
            page = self.server.sales_service.list_session_sales(
                user.id, uuid.UUID(request.session_id)
            )
        except protocol.ProtocolError:
            self._send(protocol.encode_error_response("invalid_request"))
            return
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return
        except SessionNotFoundError:
            self._send(protocol.encode_error_response("session_not_found"))
            return
        except SessionClosedError:
            self._send(protocol.encode_error_response("session_closed"))
            return
        except SessionNotOwnedError:
            self._send(protocol.encode_error_response("session_not_owned"))
            return
        self._send(protocol.encode_sales_response(page))

    def _handle_sale_detail(self, data: dict[str, object]) -> None:
        if self.server.sales_service is None:
            self._send(protocol.encode_error_response("unsupported_operation"))
            return
        try:
            request = protocol.decode_sale_detail(data)
            user = self._authenticated_user(request.auth_token)
            if user is None:
                raise PermissionError("invalid_token")
            detail = self.server.sales_service.get_session_sale_detail(
                user.id, uuid.UUID(request.session_id), uuid.UUID(request.sale_id)
            )
        except protocol.ProtocolError:
            self._send(protocol.encode_error_response("invalid_request"))
            return
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return
        except SessionNotFoundError:
            self._send(protocol.encode_error_response("session_not_found"))
            return
        except SessionClosedError:
            self._send(protocol.encode_error_response("session_closed"))
            return
        except SessionNotOwnedError:
            self._send(protocol.encode_error_response("session_not_owned"))
            return
        except SaleNotFoundError:
            self._send(protocol.encode_error_response("sale_not_found"))
            return
        self._send(protocol.encode_sale_response(detail))

    def _handle_unlock_sale(self, data: dict[str, object]) -> None:
        if self.server.sales_service is None:
            self._send(protocol.encode_error_response("unsupported_operation"))
            return
        try:
            request = protocol.decode_unlock_sale(data)
            user = self._authenticated_user(request.auth_token)
            detail = self.server.sales_service.unlock_sale(
                user.id,
                uuid.UUID(request.session_id),
                uuid.UUID(request.sale_id),
                request.secret_key,
            )
        except protocol.ProtocolError:
            self._send(protocol.encode_error_response("invalid_request"))
            return
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return
        except InvalidSaleUnlockKeyError:
            self._send(protocol.encode_error_response("invalid_unlock_key"))
            return
        except (SaleAlreadyEditingError, SaleNotEditableError):
            self._send(protocol.encode_error_response("sale_not_editable"))
            return
        self._send(protocol.encode_sale_response(detail))

    def _handle_update_sale(self, data: dict[str, object]) -> None:
        if self.server.sales_service is None:
            self._send(protocol.encode_error_response("unsupported_operation"))
            return
        try:
            request = protocol.decode_update_sale(data)
            user = self._authenticated_user(request.auth_token)
            items = [
                (
                    uuid.UUID(item.product_id),
                    _parse_quantity(item.quantity),
                    _parse_price(item.unit_price)
                    if item.unit_price is not None
                    else None,
                )
                for item in request.items
            ]
            detail = self.server.sales_service.update_sale(
                user.id,
                uuid.UUID(request.session_id),
                uuid.UUID(request.sale_id),
                items,
                uuid.UUID(request.credit_customer_id)
                if request.credit_customer_id
                else None,
            )
        except protocol.ProtocolError:
            self._send(protocol.encode_error_response("invalid_request"))
            return
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return
        except InvalidSalePriceError as exc:
            logger.warning(
                "networking op=update_sale outcome=rejected reason=invalid_price "
                "sale_id=%s detail=%s",
                request.sale_id,
                exc,
            )
            self._send(protocol.encode_error_response("invalid_price"))
            return
        except InvalidQuantityError as exc:
            logger.warning(
                "networking op=update_sale outcome=rejected "
                "reason=invalid_quantity detail=%s",
                exc,
            )
            self._send(protocol.encode_error_response("invalid_quantity"))
            return
        except (SaleAlreadyEditingError, SaleNotEditableError):
            self._send(protocol.encode_error_response("sale_not_editable"))
            return
        except ProductNotFoundError:
            self._send(protocol.encode_error_response("product_not_found"))
            return
        except (InvalidOperation, ValueError):
            logger.exception(
                "networking op=update_sale outcome=failed "
                "reason=unexpected_validation_or_service_error sale_id=%s",
                request.sale_id,
            )
            self._send(protocol.encode_error_response("internal_error"))
            return
        self._send(protocol.encode_sale_response(detail))

    def _handle_cancel_sale(self, data: dict[str, object]) -> None:
        if self.server.sales_service is None:
            self._send(protocol.encode_error_response("unsupported_operation"))
            return
        try:
            request = protocol.decode_cancel_sale(data)
            user = self._authenticated_user(request.auth_token)
            detail = self.server.sales_service.cancel_sale(
                user.id,
                uuid.UUID(request.session_id),
                uuid.UUID(request.sale_id),
                request.reason,
            )
        except protocol.ProtocolError:
            self._send(protocol.encode_error_response("invalid_request"))
            return
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return
        except InvalidSaleCancellationReasonError:
            self._send(protocol.encode_error_response("invalid_cancellation_reason"))
            return
        except (SaleAlreadyEditingError, SaleNotEditableError):
            self._send(protocol.encode_error_response("sale_not_editable"))
            return
        self._send(protocol.encode_sale_response(detail))

    def _handle_list_products(self, data: dict[str, object]) -> None:
        if self.server.product_service is None:
            self._send(protocol.encode_error_response("unsupported_operation"))
            return
        try:
            request = protocol.decode_list_products(data)
            self._authenticated_user(request.auth_token)
            list_sellable = getattr(
                self.server.product_service, "list_active_sellable_products", None
            )
            products = (
                list_sellable()
                if list_sellable is not None
                else [
                    product
                    for product in self.server.product_service.list_active_products()
                    if getattr(product, "is_for_sale", True)
                ]
            )
        except protocol.ProtocolError:
            logger.info("networking op=list_products outcome=invalid_request")
            self._send(protocol.encode_error_response("invalid_request"))
            return
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return
        logger.info("networking op=list_products outcome=ok count=%s", len(products))
        self._send(
            protocol.encode_products_response(
                [_to_product_payload(product) for product in products]
            )
        )

    def _handle_search_customers(self, data: dict[str, object]) -> None:
        if self.server.sales_service is None:
            self._send(protocol.encode_error_response("unsupported_operation"))
            return
        try:
            request = protocol.decode_search_customers(data)
            self._authenticated_user(request.auth_token)
            customers = self.server.sales_service.search_customers(request.query)
        except protocol.ProtocolError:
            self._send(protocol.encode_error_response("invalid_request"))
            return
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return
        self._send(
            protocol.encode_customers_response(
                [_to_customer_payload(customer) for customer in customers]
            )
        )

    def _handle_create_customer(self, data: dict[str, object]) -> None:
        if self.server.sales_service is None:
            self._send(protocol.encode_error_response("unsupported_operation"))
            return
        try:
            request = protocol.decode_create_customer(data)
            self._authenticated_user(request.auth_token)
            customer = self.server.sales_service.create_customer(
                request.first_name,
                request.last_name,
                request.phone,
                request.address,
                request.notes,
            )
        except protocol.ProtocolError:
            self._send(protocol.encode_error_response("invalid_request"))
            return
        except CustomerPhoneAlreadyExistsError:
            self._send(protocol.encode_error_response("customer_phone_exists"))
            return
        self._send(protocol.encode_customer_response(_to_customer_payload(customer)))

    def _handle_record_payment(self, data: dict[str, object]) -> None:
        if self.server.sales_service is None:
            self._send(protocol.encode_error_response("unsupported_operation"))
            return
        try:
            request = protocol.decode_record_payment(data)
            user = self._authenticated_user(request.auth_token)
            payment = self.server.sales_service.record_payment(
                user.id,
                uuid.UUID(request.customer_id),
                _parse_payment_amount(request.amount),
                uuid.UUID(request.session_id),
            )
        except protocol.ProtocolError:
            self._send(protocol.encode_error_response("invalid_request"))
            return
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
            return
        except CustomerNotFoundError:
            self._send(protocol.encode_error_response("customer_not_found"))
            return
        except InvalidCreditPaymentError:
            self._send(protocol.encode_error_response("invalid_credit_payment"))
            return
        except SessionNotFoundError:
            self._send(protocol.encode_error_response("session_not_found"))
            return
        except SessionClosedError:
            self._send(protocol.encode_error_response("session_closed"))
            return
        except SessionNotOwnedError:
            self._send(protocol.encode_error_response("session_not_owned"))
            return
        self._send(protocol.encode_payment_response(_to_payment_payload(payment)))

    def _handle_cash(self, data):
        import json

        try:
            token = data.get("auth_token")
            if not isinstance(token, str):
                raise ValueError("Authentication required")
            user = self._authenticated_user(token)
            repo = self.server.session_service.cash_repository
            op = data["op"]
            if op == "list_cash_recipients":
                result = {"recipients": repo.recipients(active_only=True)}
            else:
                session_id = uuid.UUID(data["session_id"])
                pos = self.server.session_service._pos_session_repository.get_by_id(
                    session_id
                )
                if pos is None or pos.user_id != user.id:
                    raise ValueError("Session does not belong to this cashier")
                if op == "list_cash_withdrawals":
                    result = {"withdrawals": repo.history(session_id)}
                else:
                    result = {
                        "withdrawal": repo.record(
                            uuid.UUID(data["withdrawal_id"]),
                            session_id,
                            user.id,
                            uuid.UUID(data["recipient_id"]),
                            Decimal(data["amount"]),
                            data["reason"],
                        )
                    }
            self._send((json.dumps({"ok": True, **result}) + "\n").encode())
        except PermissionError as exc:
            self._send(protocol.encode_error_response(str(exc)))
        except (
            ValueError,
            TypeError,
            KeyError,
            InvalidOperation,
            AttributeError,
        ) as exc:
            self._send(protocol.encode_error_response(str(exc)))

    _OPS = {
        "list_cash_recipients": _handle_cash,
        "list_cash_withdrawals": _handle_cash,
        "record_cash_withdrawal": _handle_cash,
        "login": _handle_login,
        "start_session": _handle_start_session,
        "close_session": _handle_close_session,
        "disconnect": _handle_disconnect,
        "heartbeat": _handle_heartbeat,
        "get_current_session": _handle_get_current_session,
        "create_sale": _handle_create_sale,
        "list_session_sales": _handle_list_session_sales,
        "get_sale_detail": _handle_sale_detail,
        "unlock_sale": _handle_unlock_sale,
        "update_sale": _handle_update_sale,
        "cancel_sale": _handle_cancel_sale,
        "list_products": _handle_list_products,
        "search_customers": _handle_search_customers,
        "create_customer": _handle_create_customer,
        "record_payment": _handle_record_payment,
    }

    def _send(self, data: bytes) -> None:
        try:
            self.wfile.write(data)
        except OSError:
            logger.info("networking op=unknown outcome=write_failed")


def _to_user_payload(user: User) -> protocol.UserPayload:
    return protocol.UserPayload(
        id=str(user.id),
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
    )


def _to_session_payload(session: PosSession) -> protocol.SessionPayload:
    connection_status = getattr(session, "connection_status", "disconnected")
    return protocol.SessionPayload(
        id=str(session.id),
        terminal_id=session.terminal_id,
        user_id=str(session.user_id),
        status=session.status.value,
        connection_status=connection_status,
        started_at=session.started_at.isoformat(),
        closed_at=session.closed_at.isoformat() if session.closed_at else None,
        last_connected_at=session.last_connected_at.isoformat(),
        last_activity_at=session.last_activity_at.isoformat(),
    )


def _to_product_payload(product: object) -> protocol.ProductPayload:
    return protocol.ProductPayload(
        id=str(product.id),
        sku=product.sku,
        barcode=product.barcode,
        name=product.name,
        unit=product.unit.value,
        selling_price=(
            None if product.selling_price is None else str(product.selling_price)
        ),
        minimum_price=(
            None if product.minimum_price is None else str(product.minimum_price)
        ),
        available_stock=(
            None
            if product.quantity_in_stock is None
            else str(product.quantity_in_stock)
        ),
        parent_product_id=(
            None
            if product.parent_product_id is None
            else str(product.parent_product_id)
        ),
    )


def _to_customer_payload(customer: object) -> protocol.CustomerPayload:
    return protocol.CustomerPayload(
        id=str(customer.id),
        first_name=customer.first_name,
        last_name=customer.last_name,
        phone=customer.phone,
        current_debt=str(customer.current_debt),
    )


def _to_payment_payload(payment: object) -> protocol.PaymentPayload:
    return protocol.PaymentPayload(
        id=str(payment.id),
        customer_id=str(payment.customer_id),
        amount=str(payment.amount),
        session_id=str(payment.pos_session_id),
        user_id=str(payment.pos_user_id),
        paid_at=payment.paid_at.isoformat(),
    )


def start_background_server(
    host: str,
    port: int,
    auth_service: AuthService,
    session_service: PosSessionService,
    sales_service: SalesService | None = None,
    product_service: ProductCatalogService | None = None,
) -> AdminTcpServer:
    """Starts the TCP listener on a daemon thread and returns the server
    handle; caller is responsible for calling shutdown()+server_close()
    on app exit."""
    server = AdminTcpServer(
        host, port, auth_service, session_service, sales_service, product_service
    )
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.05),
        name="admin-tcp-server",
        daemon=True,
    )
    thread.start()
    logger.info("networking event=server_started host=%s port=%s", host, port)
    return server


def _parse_quantity(value: str) -> Decimal:
    try:
        quantity = Decimal(value)
    except InvalidOperation as exc:
        raise InvalidQuantityError(
            f"quantity={value!r} is not a valid decimal"
        ) from exc
    if not quantity.is_finite() or quantity <= 0 or quantity.as_tuple().exponent < -3:
        raise InvalidQuantityError(
            f"quantity={value!r} must be positive with at most 3 decimal places"
        )
    return quantity


def _parse_price(value: str) -> Decimal:
    try:
        price = Decimal(value)
    except InvalidOperation as exc:
        raise InvalidSalePriceError(
            f"unit_price={value!r} is not a valid decimal"
        ) from exc
    if not price.is_finite() or price < 0 or price.as_tuple().exponent < -2:
        raise InvalidSalePriceError(
            f"unit_price={value!r} must be non-negative with at most 2 decimal places"
        )
    return price


def _parse_cash(value: str) -> Decimal:
    cash = Decimal(value)
    if not cash.is_finite() or cash < 0 or cash.as_tuple().exponent < -2:
        raise InvalidOperation
    return cash


def _parse_payment_amount(value: str) -> Decimal:
    amount = Decimal(value)
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
        raise InvalidOperation
    return amount
