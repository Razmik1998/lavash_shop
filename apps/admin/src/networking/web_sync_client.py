"""Outbound HTTP client for the Admin -> web_barbecue product sync.

Distinct from protocol.py/server.py, which implement the inbound POS
TCP protocol: this module is the outbound side of the app's network
boundary, POSTing barbecue products to the independent web_barbecue
Django app's `/api/products/sync/` endpoint. Kept in `networking/`
because that package is this app's network-I/O boundary in general,
not exclusively TCP.

Authenticates with a shared API key (X-API-Key header) rather than
TLS-backed session auth, matching web_barbecue's sync endpoint
contract; the request/response bodies here carry no credentials, so
they are safe to log at a coarse level (unlike protocol.py/server.py).
"""

from __future__ import annotations

from typing import Any, cast

import requests


class WebSyncError(Exception):
    """Raised when the web_barbecue sync request fails."""


class WebSyncClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self._sync_url = f"{base_url.rstrip('/')}/api/products/sync/"
        self._api_key = api_key
        self._timeout = timeout
        self.enabled = True

    def sync_products(self, products: list[dict[str, object]]) -> dict[str, object]:
        if not self.enabled:
            raise WebSyncError("Online service is disabled")
        payload: dict[str, Any] = {"products": products}
        try:
            response = requests.post(
                self._sync_url,
                json=payload,
                headers={"X-API-Key": self._api_key},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise WebSyncError(f"Unable to reach web_barbecue: {exc}") from exc
        return cast(dict[str, object], response.json())
