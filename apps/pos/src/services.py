"""Application layer: AuthService (employee-only login for POS),
PosSessionService (POS session lifecycle) — both talking to Admin over
AdminConnection, never to a database or socket directly."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from exceptions import AuthenticationError
from models import User
from networking.connection import AdminConnection
from networking.protocol import (
    CustomerPayload,
    PaymentPayload,
    ProductPayload,
    SalePayload,
    SessionPayload,
)


class AuthService:
    def __init__(self, connection: AdminConnection) -> None:
        self._connection = connection
        self._credentials: tuple[str, str] | None = None

    def login(self, username: str, password: str) -> User:
        user = self._connection.login(username, password)
        self._credentials = (username, password)
        return user

    def reconnect(self) -> User:
        """Refresh the in-memory auth token after Admin restarts."""
        if self._credentials is None:
            raise AuthenticationError("Authentication required.")
        username, password = self._credentials
        return self.login(username, password)


class PosSessionService:
    """Thin facade over `AdminConnection` for POS session lifecycle
    operations, mirroring `AuthService` above 1:1: no logic of its own,
    exceptions pass through unchanged. Satisfies the `PosSessionService`
    Protocol declared in ui/session_status.py (never imported here —
    duck-typed, same as AuthService's relationship to LoginWindow)."""

    def __init__(self, connection: AdminConnection) -> None:
        self._connection = connection

    def cash_request(self, op, **fields):
        return self._connection.cash_request(op, **fields)

    def start_session(
        self, user_id: str, terminal_id: str, opening_cash: Decimal = Decimal("0")
    ) -> SessionPayload:
        if opening_cash == Decimal("0"):
            return self._connection.start_session(user_id, terminal_id)
        return self._connection.start_session(user_id, terminal_id, opening_cash)

    def close_session(
        self, session_id: str, closing_cash: Decimal | None = None
    ) -> SessionPayload:
        if closing_cash is None:
            return self._connection.close_session(session_id)
        return self._connection.close_session(session_id, closing_cash)

    def disconnect(self, session_id: str) -> SessionPayload:
        return self._connection.disconnect(session_id)

    def heartbeat(self, session_id: str) -> SessionPayload:
        return self._connection.heartbeat(session_id)

    def get_current_session(self, terminal_id: str) -> SessionPayload | None:
        return self._connection.get_current_session(terminal_id)


class SaleService:
    def __init__(self, connection: AdminConnection) -> None:
        self._connection = connection

    def create_sale(
        self,
        session_id: str,
        terminal_id: str,
        sale_id: str,
        items: Sequence[tuple[str, str, str | None]],
        credit_customer_id: str | None = None,
    ) -> SalePayload:
        return self._connection.create_sale(
            session_id, terminal_id, sale_id, items, credit_customer_id
        )

    def list_session_sales(self, session_id: str) -> list[SalePayload]:
        return self._connection.list_session_sales(session_id)

    def get_sale_detail(self, session_id: str, sale_id: str) -> SalePayload:
        return self._connection.get_sale_detail(session_id, sale_id)

    def unlock_sale(
        self, session_id: str, sale_id: str, secret_key: str
    ) -> SalePayload:
        return self._connection.unlock_sale(session_id, sale_id, secret_key)

    def update_sale(
        self,
        session_id: str,
        sale_id: str,
        items: Sequence[tuple[str, str, str | None]],
        credit_customer_id: str | None = None,
    ) -> SalePayload:
        return self._connection.update_sale(
            session_id, sale_id, items, credit_customer_id
        )

    def cancel_sale(self, session_id: str, sale_id: str, reason: str) -> SalePayload:
        return self._connection.cancel_sale(session_id, sale_id, reason)


class ProductService:
    def __init__(self, connection: AdminConnection) -> None:
        self._connection = connection

    def list_products(self) -> list[ProductPayload]:
        return self._connection.list_products()


class CustomerService:
    def __init__(self, connection: AdminConnection) -> None:
        self._connection = connection

    def search_customers(self, query: str) -> list[CustomerPayload]:
        return self._connection.search_customers(query)

    def create_customer(
        self,
        first_name: str,
        last_name: str,
        phone: str,
        address: str | None = None,
        notes: str | None = None,
    ) -> CustomerPayload:
        return self._connection.create_customer(
            first_name, last_name, phone, address, notes
        )

    def record_payment(
        self, customer_id: str, amount: Decimal, session_id: str
    ) -> PaymentPayload:
        return self._connection.record_payment(customer_id, amount, session_id)

    def record_full_payment(
        self, customer_id: str, amount: Decimal, session_id: str
    ) -> PaymentPayload:
        return self.record_payment(customer_id, amount, session_id)
