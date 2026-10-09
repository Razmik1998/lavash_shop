from __future__ import annotations

import uuid
from decimal import Decimal

from services.product import BarbecueSyncDTO
from services.web_sync import WebSyncService


class FakeProductService:
    def __init__(self, dtos: list[BarbecueSyncDTO]) -> None:
        self._dtos = dtos

    def list_barbecue_products_for_sync(self) -> list[BarbecueSyncDTO]:
        return self._dtos


class FakeWebSyncClient:
    def __init__(self) -> None:
        self.sent_products: list[dict[str, object]] | None = None

    def sync_products(self, products: list[dict[str, object]]) -> dict[str, object]:
        self.sent_products = products
        return {"created": 1, "updated": 0, "failed": 0, "failed_items": []}


def test_synchronize_barbecue_products_serializes_and_sends_payload() -> None:
    admin_id = uuid.uuid4()
    dto = BarbecueSyncDTO(
        admin_product_id=admin_id,
        name="Barbecue",
        selling_price=Decimal("3500.00"),
        is_active=True,
    )
    product_service = FakeProductService([dto])
    client = FakeWebSyncClient()
    service = WebSyncService(product_service, client)

    result = service.synchronize_barbecue_products()

    assert client.sent_products == [
        {
            "admin_product_id": str(admin_id),
            "name": "Barbecue",
            "selling_price": "3500.00",
            "is_active": True,
        }
    ]
    assert result == {"created": 1, "updated": 0, "failed": 0, "failed_items": []}
