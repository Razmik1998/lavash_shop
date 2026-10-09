"""Compatibility facade for the repositories package."""

from repositories import (
    CustomerRepository,
    KitchenRepository,
    OnlineOrderRepository,
    PosSessionRepository,
    ProductRepository,
    PurchaseRepository,
    SaleRepository,
    SupplierRepository,
    UserRepository,
)

__all__ = [
    "OnlineOrderRepository",
    "KitchenRepository",
    "CustomerRepository",
    "PosSessionRepository",
    "ProductRepository",
    "PurchaseRepository",
    "SaleRepository",
    "SupplierRepository",
    "UserRepository",
]
