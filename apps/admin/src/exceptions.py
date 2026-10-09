"""Domain and application exceptions for the admin app."""

from __future__ import annotations


class AdminAppError(Exception):
    """Base class for all admin-app domain/application errors."""


class AuthenticationError(AdminAppError):
    """Raised when lo gin fails: unknown user, bad password, or wrong role."""


class UsernameAlreadyExistsError(AdminAppError):
    """Raised when creating an employee with a username already in use."""

    def __init__(self, username: str) -> None:
        super().__init__(f"Username already exists: {username}")
        self.username = username


class SkuAlreadyExistsError(AdminAppError):
    """Raised when a product SKU is already in use."""

    def __init__(self, sku: str) -> None:
        super().__init__(f"SKU already exists: {sku}")
        self.sku = sku


class BarcodeAlreadyExistsError(AdminAppError):
    """Raised when a product barcode is already in use."""

    def __init__(self, barcode: str) -> None:
        super().__init__(f"Barcode already exists: {barcode}")
        self.barcode = barcode


class SessionAlreadyActiveError(AdminAppError):
    """Raised when starting a session for a terminal that already has an
    active (unclosed) session."""


class SessionNotFoundError(AdminAppError):
    """Raised when a session_id does not correspond to any POS session."""


class SessionClosedError(AdminAppError):
    """Raised when an operation (e.g. heartbeat) targets a session that
    has already been closed."""


class SaleError(AdminAppError):
    """Base class for sale creation and history errors."""


class ProductNotFoundError(SaleError):
    pass


class InvalidQuantityError(SaleError):
    pass


class InvalidSalePriceError(SaleError):
    pass


class SaleIdConflictError(SaleError):
    pass


class SaleNotFoundError(SaleError):
    pass


class SessionNotOwnedError(SaleError):
    pass


class CustomerNotFoundError(AdminAppError):
    pass


class CustomerPhoneAlreadyExistsError(AdminAppError):
    pass


class InvalidCreditPaymentError(AdminAppError):
    pass


class TerminalMismatchError(SaleError):
    pass


class InvalidFiltersError(SaleError):
    pass


class InvalidCursorError(SaleError):
    pass


class SaleUnlockError(SaleError):
    pass


class InvalidSaleUnlockKeyError(SaleUnlockError):
    pass


class SaleAlreadyEditingError(SaleUnlockError):
    pass


class SaleNotEditableError(SaleUnlockError):
    pass


class InvalidSaleCancellationReasonError(SaleError):
    """Raised when a sale cancellation has no explanation."""


class PurchaseError(AdminAppError):
    """Base class for supplier and purchasing workflow errors."""


class SupplierNotFoundError(PurchaseError):
    pass


class PurchaseNotFoundError(PurchaseError):
    pass


class InvalidPurchaseError(PurchaseError):
    pass


class PurchaseAlreadyConfirmedError(PurchaseError):
    pass


class PurchaseCancellationError(PurchaseError):
    pass


class PaymentError(PurchaseError):
    pass


class KitchenDocumentError(AdminAppError):
    """Base class for Kitchen stock issue documents."""


class InvalidKitchenDocumentError(KitchenDocumentError):
    pass


class SyncError(AdminAppError):
    """Base class for errors from the outbound Django order-sync
    transport (networking/order_sync_client.py)."""


class SyncConnectionError(SyncError):
    """Raised when the WebSocket/HTTP transport cannot reach Django
    (connect/read timeout, connection dropped, retries exhausted)."""


class SyncAuthenticationError(SyncError):
    """Raised when Django rejects the shared `X-API-Key` (WebSocket
    handshake refused, or an HTTP call returns 401/403)."""


class SyncProtocolError(SyncError):
    """Raised when an inbound WebSocket/HTTP payload from Django is
    missing fields, has the wrong types, or is otherwise malformed --
    never trust data from the network, even from the admin's own web
    app."""


class OnlineOrderError(AdminAppError):
    """Base class for `OnlineOrderService` (services/online_orders.py)
    errors -- see .claude/specs/9/admin-architecture.md §7/§8."""


class OnlineOrderNotFoundError(OnlineOrderError):
    """Raised when an `online_order_id` does not correspond to any
    `OnlineOrder` row."""


class OnlineOrderNotPendingError(OnlineOrderError):
    """Raised by confirm/reject when the order's `business_status` is no
    longer `PENDING` -- defensive: the UI only offers these actions for
    pending orders, but the service must not trust that."""


class OnlineOrderNotConfirmedError(OnlineOrderError):
    """Raised by conversion/retry when the order's `business_status` is
    not `CONFIRMED` (a rejected order must never produce a `Sale`)."""


class SaleAlreadyConvertedError(OnlineOrderError):
    """Raised by the repository layer when a `Sale` insert collides on
    the unique `web_order_id` constraint; the service treats this as an
    idempotent no-op, not a failure -- see admin-architecture.md §6."""
