import enum


class Role(enum.Enum):
    ADMIN = "admin"
    EMPLOYEE = "employee"


class Unit(enum.Enum):
    PIECE = "piece"
    KG = "kg"
    GRAM = "g"
    LITER = "l"
    BARBECUE = "barbecue"


class PosSessionStatus(enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class SaleStatus(enum.Enum):
    COMPLETED = "completed"
    VOIDED = "voided"
    EDITING = "editing"
    CANCELLED = "cancelled"


class SaleItemAction(enum.Enum):
    ADDED = "added"
    EDITED = "edited"
    DELETED = "deleted"
    DISCOUNT_ADDED = "discount_added"
    DISCOUNT_REMOVED = "discount_removed"
    DISCOUNT_CHANGED = "discount_changed"


class SaleRevisionOutcome(enum.Enum):
    CREATED = "created"
    UNLOCKED = "unlocked"
    COMPLETED = "completed"
    COMPLETED_UNCHANGED = "completed_unchanged"
    CANCELLED = "cancelled"


class PurchaseStatus(enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    CANCELLED = "cancelled"


class PaymentMethod(enum.Enum):
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"
    OTHER = "other"


class InventoryMovementType(enum.Enum):
    RECEIPT = "receipt"
    REVERSAL = "reversal"

__all__ = [
    "InventoryMovementType",
    "PaymentMethod",
    "PosSessionStatus",
    "PurchaseStatus",
    "Role",
    "SaleStatus",
    "Unit",
]