"""Application layer: WebSyncService."""

from __future__ import annotations

from networking.web_sync_client import WebSyncClient
from services.product import ProductService


class WebSyncService:
    def __init__(
        self, product_service: ProductService, web_sync_client: WebSyncClient
    ) -> None:
        self._product_service = product_service
        self._web_sync_client = web_sync_client

    def synchronize_barbecue_products(self) -> dict[str, object]:
        dtos = self._product_service.list_barbecue_products_for_sync()
        payload = [
            {
                "admin_product_id": str(dto.admin_product_id),
                "name": dto.name,
                "selling_price": str(dto.selling_price),
                "is_active": dto.is_active,
            }
            for dto in dtos
        ]
        return self._web_sync_client.sync_products(payload)
