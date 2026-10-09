from dataclasses import dataclass
from decimal import Decimal

from products.models import Product

SESSION_KEY = "basket"


@dataclass(frozen=True)
class BasketLine:
    product: Product
    quantity: int

    @property
    def unit_price(self) -> Decimal:
        return self.product.effective_price()

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


class Basket:
    """Server-side basket stored in the session.

    Only {product_id: quantity} is kept in the session; prices and
    product names are always re-read from the live Product on every
    request, so nothing basket-related ever trusts client-supplied
    price/name data.
    """

    def __init__(self, request):
        self.session = request.session
        self._data: dict[str, int] = self.session.setdefault(SESSION_KEY, {})

    def _save(self):
        self.session[SESSION_KEY] = self._data
        self.session.modified = True

    def add(self, product_id: str, quantity: int = 1) -> None:
        product_id = str(product_id)
        self._data[product_id] = self._data.get(product_id, 0) + quantity
        self._save()

    def set_quantity(self, product_id: str, quantity: int) -> None:
        product_id = str(product_id)
        if quantity <= 0:
            self._data.pop(product_id, None)
        else:
            self._data[product_id] = quantity
        self._save()

    def remove(self, product_id: str) -> None:
        product_id = str(product_id)
        if self._data.pop(product_id, None) is not None:
            self._save()

    def clear(self) -> None:
        self._data = {}
        self._save()

    def raw_quantities(self) -> dict[str, int]:
        return dict(self._data)

    def lines(self) -> list[BasketLine]:
        if not self._data:
            return []

        products = Product.objects.filter(
            id__in=self._data.keys(), is_active=True, is_visible=True
        )
        products_by_id = {str(product.id): product for product in products}

        lines = []
        stale_ids = []
        for product_id, quantity in self._data.items():
            product = products_by_id.get(product_id)
            if product is None:
                stale_ids.append(product_id)
                continue
            lines.append(BasketLine(product=product, quantity=quantity))

        if stale_ids:
            for product_id in stale_ids:
                self._data.pop(product_id, None)
            self._save()

        return lines

    def total(self) -> Decimal:
        return sum((line.line_total for line in self.lines()), Decimal("0"))

    def count(self) -> int:
        return sum(line.quantity for line in self.lines())

    def is_empty(self) -> bool:
        return not self.lines()

    def summary(self) -> dict:
        lines = self.lines()
        return {
            "items": [
                {
                    "product_id": str(line.product.id),
                    "name": line.product.display_name or line.product.name,
                    "unit_price": str(line.unit_price),
                    "quantity": line.quantity,
                    "line_total": str(line.line_total),
                }
                for line in lines
            ],
            "count": sum(line.quantity for line in lines),
            "total": str(sum((line.line_total for line in lines), Decimal("0"))),
        }
