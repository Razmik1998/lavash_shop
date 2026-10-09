"""Domain and application exceptions for the POS app."""

from __future__ import annotations


class PosAppError(Exception):
    """Base class for all POS-app domain/application errors."""


class AuthenticationError(PosAppError):
    """Raised when login fails: unknown user, bad password, or wrong role."""


class AdminUnavailableError(PosAppError):
    """Raised when the Admin application cannot be reached: unreachable,
    timed out, or returned a malformed response."""


class SessionAlreadyActiveError(PosAppError):
    """Raised when starting a session for a terminal that already has an
    active (unclosed) session."""


class SessionNotFoundError(PosAppError):
    """Raised when a session_id does not correspond to any POS session."""


class SessionClosedError(PosAppError):
    """Raised when an operation (e.g. heartbeat) targets a session that
    has already been closed."""


class CustomerNotFoundError(PosAppError):
    """Raised when a customer lookup or payment targets no customer."""


class CustomerPhoneAlreadyExistsError(PosAppError):
    """Raised when a customer phone number is already registered."""


class CreditPaymentError(PosAppError):
    """Raised when a repayment is not the customer's exact outstanding debt."""
