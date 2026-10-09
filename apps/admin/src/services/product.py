"""Application layer: AuthService, EmployeeService."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo

from models import (
    Product,
    Unit,
)
from repository import (
    ProductRepository,
)

# How long a POS terminal may go without a heartbeat before the admin
# panel/UI shows its connection as DISCONNECTED. Kept a small multiple
# (3x) of `HEARTBEAT_INTERVAL_MS` (15s) in
# apps/pos/src/ui/session_status.py, per that module's docstring
# ("the backend's connected/disconnected threshold must be kept a
# small multiple of this, e.g. 2-3x, so a single missed beat doesn't
# flip the indicator") and the networking/server.py PosSessionService
# Protocol docstring assuming this exact computation.
HEARTBEAT_TIMEOUT_SECONDS = 45
ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


@dataclass(frozen=True)
class BarbecueSyncDTO:
    """A child of a Unit.BARBECUE parent, as sent to web_barbecue's sync endpoint.

    Barbecue parent products (Unit.BARBECUE) are just groupings with no
    price of their own (selling_price=None, see
    ProductService._validate_product); their children hold the real
    unit/price. Sync therefore sends one DTO per child, not per parent.
    """

    admin_product_id: uuid.UUID
    name: str
    selling_price: Decimal
    is_active: bool


class ProductService:
    def __init__(self, product_repository: ProductRepository) -> None:
        self._product_repository = product_repository

    def list_products(self) -> list[Product]:
        return self._decorate_products(self._product_repository.list_all())

    def list_active_products(self) -> list[Product]:
        return self._decorate_products(self._product_repository.list_active())

    def list_active_sellable_products(self) -> list[Product]:
        return self._decorate_products(self._product_repository.list_active_for_sale())

    def search_products(self, term: str) -> list[Product]:
        return self._decorate_products(self._product_repository.search(term))

    def list_barbecue_products_for_sync(self) -> list[BarbecueSyncDTO]:
        parents = self._product_repository.list_by_unit(Unit.BARBECUE)
        all_products = self._product_repository.list_all()
        children_by_parent: dict[uuid.UUID, list[Product]] = {}
        for product in all_products:
            if product.parent_product_id is not None:
                children_by_parent.setdefault(product.parent_product_id, []).append(
                    product
                )

        return [
            BarbecueSyncDTO(
                admin_product_id=child.id,
                name=child.display_name(parent),
                selling_price=child.selling_price or Decimal("0"),
                is_active=child.is_active,
            )
            for parent in parents
            for child in children_by_parent.get(parent.id, [])
            if child.is_for_sale is not False
        ]

    def next_product_sku(self) -> str | None:
        last_sku = self._product_repository.get_latest_sku()
        if last_sku is None or not last_sku.strip():
            return "1"
        digits = "".join(ch for ch in last_sku if ch.isdigit())
        if not digits:
            return "1"
        return str(int(digits) + 1)

    def create_product(
        self,
        name: str,
        sku: str,
        barcode: str | None,
        unit: Unit,
        cost_price: Decimal | None,
        selling_price: Decimal | None,
        minimum_price: Decimal | None = None,
        quantity_in_stock: Decimal | None = None,
        low_stock_threshold: Decimal | None = None,
        is_active: bool = True,
        parent_product_id: uuid.UUID | None = None,
        is_for_sale: bool = True,
    ) -> Product:
        validated = self._validate_product(
            product_id=None,
            name=name,
            sku=sku,
            barcode=barcode,
            unit=unit,
            cost_price=cost_price,
            selling_price=selling_price,
            minimum_price=minimum_price,
            quantity_in_stock=quantity_in_stock,
            low_stock_threshold=low_stock_threshold,
            is_active=is_active,
            parent_product_id=parent_product_id,
            is_for_sale=is_for_sale,
        )
        product = Product(
            id=uuid.uuid4(),
            name=validated["name"],
            sku=validated["sku"],
            barcode=validated["barcode"],
            unit=validated["unit"],
            cost_price=validated["cost_price"],
            selling_price=validated["selling_price"],
            minimum_price=validated["minimum_price"],
            quantity_in_stock=validated["quantity_in_stock"],
            low_stock_threshold=validated["low_stock_threshold"],
            is_active=validated["is_active"],
            parent_product_id=validated["parent_product_id"],
            is_for_sale=validated["is_for_sale"],
        )
        return self._decorate_product(self._product_repository.add(product))

    def update_product(
        self,
        product_id: uuid.UUID,
        name: str,
        sku: str,
        barcode: str | None,
        unit: Unit,
        cost_price: Decimal | None,
        selling_price: Decimal | None,
        minimum_price: Decimal | None = None,
        quantity_in_stock: Decimal | None = None,
        low_stock_threshold: Decimal | None = None,
        is_active: bool = True,
        parent_product_id: uuid.UUID | None = None,
        is_for_sale: bool = True,
    ) -> Product:
        product = self._product_repository.get_by_id(product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")
        validated = self._validate_product(
            product_id=product.id,
            name=name,
            sku=sku,
            barcode=barcode,
            unit=unit,
            cost_price=cost_price,
            selling_price=selling_price,
            minimum_price=minimum_price,
            quantity_in_stock=quantity_in_stock,
            low_stock_threshold=low_stock_threshold,
            is_active=is_active,
            parent_product_id=parent_product_id,
            is_for_sale=is_for_sale,
        )
        product.name = validated["name"]
        product.sku = validated["sku"]
        product.barcode = validated["barcode"]
        product.unit = validated["unit"]
        product.cost_price = validated["cost_price"]
        product.selling_price = validated["selling_price"]
        product.minimum_price = validated["minimum_price"]
        product.quantity_in_stock = validated["quantity_in_stock"]
        product.low_stock_threshold = validated["low_stock_threshold"]
        product.is_active = validated["is_active"]
        product.parent_product_id = validated["parent_product_id"]
        product.is_for_sale = validated["is_for_sale"]
        return self._decorate_product(self._product_repository.update(product))

    def _validate_product(
        self,
        *,
        product_id: uuid.UUID | None,
        name: str,
        sku: str,
        barcode: str | None,
        unit: Unit,
        cost_price: Decimal | None,
        selling_price: Decimal | None,
        minimum_price: Decimal | None,
        quantity_in_stock: Decimal | None,
        low_stock_threshold: Decimal | None,
        is_active: bool,
        parent_product_id: uuid.UUID | None,
        is_for_sale: bool,
    ) -> dict[str, object]:
        if not isinstance(is_for_sale, bool):
            raise ValueError("is_for_sale must be a boolean.")
        if unit is Unit.BARBECUE:
            if parent_product_id is not None:
                raise ValueError("A barbecue parent product cannot belong to another product.")
            cost_price = None
            selling_price = None
            quantity_in_stock = None
            low_stock_threshold = None
            minimum_price = None
        elif not is_for_sale:
            selling_price = None
            minimum_price = None
        elif minimum_price is None:
            minimum_price = selling_price
        elif selling_price is not None and minimum_price > selling_price:
            raise ValueError("Minimum price cannot exceed selling price.")

        if product_id is not None:
            current = self._product_repository.get_by_id(product_id)
            if current is not None and _has_children(self._product_repository, product_id):
                if unit is not Unit.BARBECUE:
                    raise ValueError("A product with children must remain a barbecue parent.")
                if (
                    cost_price is not None
                    or selling_price is not None
                    or quantity_in_stock is not None
                    or low_stock_threshold is not None
                ):
                    raise ValueError("Parent products cannot have their own price or stock values.")

        if parent_product_id is not None:
            if parent_product_id == product_id:
                raise ValueError("A product cannot be its own parent.")
            parent = self._product_repository.get_by_id(parent_product_id)
            if parent is None:
                raise ValueError("Parent product does not exist.")
            if parent.unit is not Unit.BARBECUE:
                raise ValueError("Only barbecue products can be parents.")

        return {
            "name": name,
            "sku": sku,
            "barcode": barcode,
            "unit": unit,
            "cost_price": cost_price,
            "selling_price": selling_price,
            "minimum_price": minimum_price,
            "quantity_in_stock": quantity_in_stock,
            "low_stock_threshold": low_stock_threshold,
            "is_active": is_active,
            "parent_product_id": parent_product_id,
            "is_for_sale": is_for_sale,
        }

    @classmethod
    def _decorate_products(cls, products: list[Product]) -> list[Product]:
        return [cls._decorate_product(product) for product in products]

    @staticmethod
    def _decorate_product(product: Product) -> Product:
        if product.unit is Unit.BARBECUE:
            product.stock_status = "bundle"  # type: ignore[attr-defined]
            product.profit_margin = None  # type: ignore[attr-defined]
            return product

        quantity = product.quantity_in_stock
        if quantity is None or quantity <= 0:
            stock_status = "out_of_stock"
        elif (
            product.low_stock_threshold is not None
            and quantity <= product.low_stock_threshold
        ):
            stock_status = "low_stock"
        else:
            stock_status = "in_stock"
        profit_margin = None
        if product.cost_price is not None and product.selling_price not in (None, 0):
            profit_margin = (
                (product.selling_price - product.cost_price)
                / product.selling_price
                * Decimal("100")
            )
        product.stock_status = stock_status  # type: ignore[attr-defined]
        product.profit_margin = profit_margin  # type: ignore[attr-defined]
        return product


def _has_children(repository: ProductRepository, product_id: uuid.UUID | None) -> bool:
    if product_id is None:
        return False
    return any(child.parent_product_id == product_id for child in repository.list_all())
