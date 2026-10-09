"""Abstract interface POS's application layer depends on to reach the
Admin application. services.py and the UI must never import socket/json
directly — only implementations in this package do (see
.claude/rules/python-architecture)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from decimal import Decimal

from models import User
from networking.protocol import (
    CustomerPayload,
    PaymentPayload,
    ProductPayload,
    SalePayload,
    SessionPayload,
)


class AdminConnection(ABC):
    def cash_request(self, op: str, **fields: str) -> dict:
        """Authenticated cash recipient and withdrawal operations."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Best-effort reachability check, used at startup before the
        login screen is shown."""

    @abstractmethod
    def login(self, username: str, password: str) -> User:
        """Authenticates an employee against Admin.

        Raises AuthenticationError for unknown user/bad password/wrong
        role, AdminUnavailableError if Admin cannot be reached or
        returns a malformed response."""

    @abstractmethod
    def start_session(
        self, user_id: str, terminal_id: str, opening_cash: Decimal = Decimal("0")
    ) -> SessionPayload:
        """Starts a new active POS session for `terminal_id`, owned by
        `user_id`.

        Raises SessionAlreadyActiveError if the terminal already has an
        active session, AuthenticationError if `user_id` is not a valid
        user, AdminUnavailableError if Admin cannot be reached or
        returns a malformed response."""

    @abstractmethod
    def close_session(
        self, session_id: str, closing_cash: Decimal | None = None
    ) -> SessionPayload:
        """Closes a POS session. Idempotent: closing an
        already-closed session returns it unchanged.

        Raises SessionNotFoundError if `session_id` does not exist,
        AdminUnavailableError if Admin cannot be reached or returns a
        malformed response."""

    @abstractmethod
    def disconnect(self, session_id: str) -> SessionPayload:
        """Reports disconnect for a POS session, marking connection status
        as disconnected without closing the active session.

        Raises SessionNotFoundError if `session_id` does not exist,
        AdminUnavailableError if Admin cannot be reached or returns a
        malformed response."""

    @abstractmethod
    def heartbeat(self, session_id: str) -> SessionPayload:
        """Reports liveness for an active session, refreshing its
        connection/activity timestamps.

        Raises SessionNotFoundError if `session_id` does not exist,
        SessionClosedError if the session is already closed,
        AdminUnavailableError if Admin cannot be reached or returns a
        malformed response."""

    @abstractmethod
    def get_current_session(self, terminal_id: str) -> SessionPayload | None:
        """Returns the active session for `terminal_id`, or None if
        there isn't one.

        Raises AdminUnavailableError if Admin cannot be reached or
        returns a malformed response."""

    @abstractmethod
    def list_products(self) -> list[ProductPayload]:
        """Returns active products available for checkout."""

    @abstractmethod
    def search_customers(self, query: str) -> list[CustomerPayload]:
        """Searches active customers by one name/phone query."""

    @abstractmethod
    def create_customer(
        self,
        first_name: str,
        last_name: str,
        phone: str,
        address: str | None = None,
        notes: str | None = None,
    ) -> CustomerPayload:
        """Creates a credit customer and returns the created customer."""

    @abstractmethod
    def record_payment(
        self, customer_id: str, amount: Decimal, session_id: str
    ) -> PaymentPayload:
        """Records an exact full repayment for a customer in a POS session."""

    @abstractmethod
    def create_sale(
        self,
        session_id: str,
        terminal_id: str,
        sale_id: str,
        items: Sequence[tuple[str, str, str | None]],
        credit_customer_id: str | None = None,
    ) -> SalePayload:
        """Finalizes a sale using Admin's authoritative prices."""

    @abstractmethod
    def list_session_sales(self, session_id: str) -> list[SalePayload]:
        """Returns only sales belonging to the authenticated session."""

    @abstractmethod
    def get_sale_detail(self, session_id: str, sale_id: str) -> SalePayload:
        """Returns a session sale with its append-only audit events."""

    @abstractmethod
    def unlock_sale(
        self, session_id: str, sale_id: str, secret_key: str
    ) -> SalePayload:
        """Authorizes and starts editing a confirmed sale."""

    @abstractmethod
    def update_sale(
        self,
        session_id: str,
        sale_id: str,
        items: Sequence[tuple[str, str, str | None]],
        credit_customer_id: str | None = None,
    ) -> SalePayload:
        """Recalculates and reconfirms an unlocked sale."""

    @abstractmethod
    def cancel_sale(self, session_id: str, sale_id: str, reason: str) -> SalePayload:
        """Cancels an unlocked sale without deleting its history."""
