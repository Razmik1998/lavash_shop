"""Outbound WebSocket+HTTP client for the Admin -> web_barbecue *order*
sync contract (spec task 9, "Online Selling").

Distinct from:
  - `protocol.py`/`server.py`: the inbound, loopback-only POS TCP
    protocol. That path never talks to Django and is untouched here.
  - `web_sync_client.py`: the existing outbound HTTP-only *product*
    sync to `/api/products/sync/`. Unrelated endpoint, left as-is.

This module is the transport `services/sync.py`'s `SyncService`
depends on (via the `OrderSyncClient` Protocol below), mirroring the
abstraction/implementation split `apps/pos/src/networking/connection.py`
already uses for `AdminConnection`: `SyncService` never imports
`websocket`/`requests`/`json` directly, only this module does.

Wire contract (per `.claude/specs/9/input/task-9-online-selling.md`
sections 22-27 and the reconciled task-plan/architecture docs):

  - WebSocket endpoint: `/ws/admin/orders/`, authenticated at connect
    time via an `X-API-Key` header (same shared secret as the existing
    `web_sync_client.py`/`WEB_SYNC_API_KEY` pattern).
  - Handshake, sent immediately after the socket opens:
    `{"type": "connect", "device_id": <str>, "last_event_id": <int|null>}`.
    Django replies `{"type": "connection.ready"}` once it has queued
    any replay, then streams live events as
    `{"type": "event", "event_id": <int>, "order_id": <int>,
    "event_type": "order.created"|"order.confirmed"|"order.rejected",
    "created_at": <ISO8601 str>}`.
    NOTE: the exact envelope names (`"type"`/`"connection.ready"`) are
    this client's documented assumption reconciling the input spec's
    prose with the "type": "connect" shape it gives verbatim; if the
    Django implementation (running in parallel per the same input doc)
    lands on different framing, only `_decode_ws_message`/
    `send_connect_handshake` below need to change -- `SyncService` and
    the `OrderSyncClient` Protocol are unaffected.
  - HTTP recovery: `GET /api/admin/orders/sync/?device_id=...&after_event_id=...`
    -> `{"events": [{"event_id":..., "order_id":..., "event_type":...,
    "created_at":...}, ...]}`.
  - Order detail: `GET /api/admin/orders/<id>/`.
  - Actions: `POST /api/admin/orders/<id>/confirm/` `{"device_id":...}`
    -> `{"order_id":..., "status":"CONFIRMED"}`;
    `POST /api/admin/orders/<id>/reject/` `{"device_id":..., "reason":...}`
    -> `{"order_id":..., "status":"REJECTED"}`;
    `POST /api/admin/orders/<id>/acknowledge/`
    `{"device_id":..., "event_id":...}` -> 2xx, no body required.
  - Every HTTP call and the WebSocket handshake carry the same
    `X-API-Key` header.

Every boundary defined here per `.claude/rules/networking.md`:
  - Timeouts: separate connect/read/HTTP timeouts, all bounded.
  - Retry/reconnect: `connect()` retries the initial dial with bounded
    exponential backoff (never an infinite tight loop); resuming after
    a live disconnect (calling `connect()` again) is `SyncService`'s
    job, since only it knows the app's shutdown/backoff cadence.
  - Authentication: `X-API-Key` on the WebSocket handshake and on
    every HTTP call.
  - Serialization/validation: every inbound JSON payload is validated
    field-by-field; malformed data raises `SyncProtocolError` rather
    than propagating a `KeyError`/`TypeError` or crashing the receive
    loop.
  - Logging: structured, operation + outcome only -- this module never
    logs the API key or full request/response bodies (order data is
    customer PII), matching `protocol.py`'s convention.
  - Security: no TLS is enforced by this module itself (the Django
    storefront is internet-facing; see the task-plan's flagged,
    required security-review follow-up on the TLS gap) -- `base_url`
    determines `ws://`/`wss://` and `http://`/`https://` and is the
    deployment's responsibility to set correctly.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, cast
from urllib.parse import urlsplit, urlunsplit

import requests
import websocket

from exceptions import SyncAuthenticationError, SyncConnectionError, SyncProtocolError
from models import DEFAULT_DEVICE_ID
from schemas.order_sync_events import (
    OrderEventType,
    OrderSyncActionResult,
    OrderSyncDetail,
    OrderSyncEvent,
    OrderSyncItemDetail,
)

logger = logging.getLogger(__name__)

_WS_PATH = "/ws/admin/orders/"
_DEFAULT_CONNECT_TIMEOUT = 5.0
_DEFAULT_READ_TIMEOUT = 30.0
_DEFAULT_HTTP_TIMEOUT = 10.0
_DEFAULT_MAX_CONNECT_ATTEMPTS = 5
_DEFAULT_BACKOFF_BASE_SECONDS = 1.0
_DEFAULT_BACKOFF_MAX_SECONDS = 30.0
_MAX_WS_MESSAGE_BYTES = 65536


class OrderSyncClient(Protocol):
    """The abstraction `SyncService` depends on. `SyncService` never
    imports `websocket`/`requests`/`json` itself -- only implementations
    of this Protocol (in this module) do."""

    def connect(self) -> None:
        """Dials the WebSocket endpoint. Retries the dial internally
        with bounded exponential backoff.

        Raises:
            SyncConnectionError: all connect attempts were exhausted.
        """
        ...

    def disconnect(self) -> None:
        """Closes the WebSocket if open. Idempotent -- calling it when
        already disconnected is a no-op, never raises."""
        ...

    def send_connect_handshake(self, last_event_id: int | None) -> None:
        """Sends the `connect` handshake and waits for Django's
        `connection.ready` acknowledgement.

        Raises:
            SyncConnectionError: not connected, or the socket dropped
                before the handshake completed.
            SyncAuthenticationError: Django rejected the API key.
            SyncProtocolError: the handshake response was malformed.
        """
        ...

    def receive_event(self, timeout: float) -> OrderSyncEvent | None:
        """Blocks for up to `timeout` seconds for the next event.
        Returns `None` on a plain timeout (the normal, expected case
        that lets the caller's loop check for a stop signal) --
        callers must not treat `None` as an error.

        Raises:
            SyncConnectionError: the connection dropped.
            SyncProtocolError: an inbound message was malformed.
        """
        ...

    def fetch_missed_events(self, after_event_id: int | None) -> list[OrderSyncEvent]:
        """HTTP recovery fallback: `GET /api/admin/orders/sync/`.
        `after_event_id=None` requests a full backfill.

        Raises:
            SyncConnectionError: the HTTP call failed or timed out.
            SyncAuthenticationError: Django rejected the API key.
            SyncProtocolError: the response body was malformed.
        """
        ...

    def fetch_order_detail(self, order_id: uuid.UUID) -> OrderSyncDetail:
        """`GET /api/admin/orders/<id>/`.

        Raises:
            SyncConnectionError: the HTTP call failed or timed out.
            SyncAuthenticationError: Django rejected the API key.
            SyncProtocolError: the response body was malformed.
        """
        ...

    def confirm_order(
        self, order_id: uuid.UUID, device_id: str
    ) -> OrderSyncActionResult:
        """`POST /api/admin/orders/<id>/confirm/`.

        Raises:
            SyncConnectionError: the HTTP call failed or timed out.
            SyncAuthenticationError: Django rejected the API key.
            SyncProtocolError: the response body was malformed.
        """
        ...

    def reject_order(
        self, order_id: uuid.UUID, device_id: str, reason: str
    ) -> OrderSyncActionResult:
        """`POST /api/admin/orders/<id>/reject/`.

        Raises:
            SyncConnectionError: the HTTP call failed or timed out.
            SyncAuthenticationError: Django rejected the API key.
            SyncProtocolError: the response body was malformed.
        """
        ...

    def acknowledge(self, order_id: uuid.UUID, device_id: str, event_id: int) -> None:
        """`POST /api/admin/orders/<id>/acknowledge/`. Callers must
        only invoke this after the corresponding local write has been
        committed (commit-then-ack; see the admin architecture doc
        §7/§9) -- this method does not enforce that ordering itself.

        Raises:
            SyncConnectionError: the HTTP call failed or timed out.
            SyncAuthenticationError: Django rejected the API key.
            SyncProtocolError: the response body was malformed.
        """
        ...


class DjangoOrderSyncClient:
    """Concrete `OrderSyncClient`: a synchronous WebSocket connection
    (via `websocket-client`) for the live event stream, plus `requests`
    for HTTP recovery/detail/action calls.

    Deliberately synchronous/blocking rather than asyncio-based: this
    app's TCP server (`networking/server.py`) and its Qt background
    worker helper (`ui/workers.py`'s `run_in_background`) are both
    thread-based, not asyncio-based, so `SyncService` runs this
    client's `receive_event(timeout)` in a polling loop on its own
    background `QThread` rather than requiring an event loop.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        device_id: str = DEFAULT_DEVICE_ID,
        connect_timeout: float = _DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = _DEFAULT_READ_TIMEOUT,
        http_timeout: float = _DEFAULT_HTTP_TIMEOUT,
        max_connect_attempts: int = _DEFAULT_MAX_CONNECT_ATTEMPTS,
        backoff_base_seconds: float = _DEFAULT_BACKOFF_BASE_SECONDS,
        backoff_max_seconds: float = _DEFAULT_BACKOFF_MAX_SECONDS,
    ) -> None:
        self._http_base = base_url.rstrip("/")
        self._ws_url = _to_ws_url(self._http_base) + _WS_PATH
        self._api_key = api_key
        self._device_id = device_id
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._http_timeout = http_timeout
        self._max_connect_attempts = max_connect_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_max_seconds = backoff_max_seconds
        self._ws: websocket.WebSocket | None = None
        self._lock = threading.Lock()
        self._disabled = threading.Event()

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self._disabled.clear()
        else:
            self._disabled.set()
            self.disconnect()

    def _check_enabled(self) -> None:
        if self._disabled.is_set():
            raise SyncConnectionError("Online service is disabled")

    # -- WebSocket: connect / handshake / receive ------------------------

    def connect(self) -> None:
        last_exc: Exception | None = None
        for attempt in range(self._max_connect_attempts):
            self._check_enabled()
            if attempt > 0:
                delay = min(
                    self._backoff_base_seconds * (2 ** (attempt - 1)),
                    self._backoff_max_seconds,
                )
                if self._disabled.wait(delay):
                    self._check_enabled()
            try:
                ws = websocket.create_connection(
                    self._ws_url,
                    timeout=self._connect_timeout,
                    header=[f"X-API-Key: {self._api_key}"],
                )
            except (websocket.WebSocketException, OSError) as exc:
                last_exc = exc
                logger.warning(
                    "order_sync op=connect outcome=retry attempt=%s/%s",
                    attempt + 1,
                    self._max_connect_attempts,
                )
                continue
            with self._lock:
                if self._disabled.is_set():
                    ws.close(timeout=0.2)
                    self._check_enabled()
                self._ws = ws
            logger.info("order_sync op=connect outcome=ok attempt=%s", attempt + 1)
            return
        logger.error(
            "order_sync op=connect outcome=exhausted attempts=%s",
            self._max_connect_attempts,
        )
        raise SyncConnectionError(
            "Unable to connect to Django order-sync WebSocket"
        ) from last_exc

    def disconnect(self) -> None:
        with self._lock:
            ws, self._ws = self._ws, None
        if ws is None:
            return
        try:
            ws.close(timeout=0.2)
        except (websocket.WebSocketException, OSError):
            logger.info("order_sync op=disconnect outcome=close_error")
            return
        logger.info("order_sync op=disconnect outcome=ok")

    def send_connect_handshake(self, last_event_id: int | None) -> None:
        ws = self._require_ws()
        handshake = {
            "type": "connect",
            "device_id": self._device_id,
            "last_event_id": last_event_id,
        }
        try:
            ws.settimeout(self._connect_timeout)
            ws.send(json.dumps(handshake))
            raw = ws.recv()
        except websocket.WebSocketTimeoutException as exc:
            logger.warning("order_sync op=handshake outcome=timeout")
            raise SyncConnectionError("Handshake timed out") from exc
        except (websocket.WebSocketException, OSError) as exc:
            logger.warning("order_sync op=handshake outcome=connection_error")
            raise SyncConnectionError("Handshake failed") from exc

        message = _decode_ws_message(raw)
        if message.get("type") == "error" and message.get("code") in (
            "unauthorized",
            "forbidden",
        ):
            logger.warning("order_sync op=handshake outcome=unauthorized")
            raise SyncAuthenticationError("Django rejected the API key")
        if message.get("type") != "connection.ready":
            logger.warning("order_sync op=handshake outcome=unexpected_message")
            raise SyncProtocolError("Expected a connection.ready handshake response")
        logger.info("order_sync op=handshake outcome=ok device_id=%s", self._device_id)

    def receive_event(self, timeout: float) -> OrderSyncEvent | None:
        ws = self._require_ws()
        try:
            ws.settimeout(timeout)
            raw = ws.recv()
        except websocket.WebSocketTimeoutException:
            return None
        except (websocket.WebSocketConnectionClosedException, OSError) as exc:
            logger.warning("order_sync op=receive_event outcome=connection_closed")
            raise SyncConnectionError("Connection closed") from exc

        if raw == "" or raw is None:
            logger.warning("order_sync op=receive_event outcome=connection_closed")
            raise SyncConnectionError("Connection closed")

        message = _decode_ws_message(raw)
        message_type = message.get("type")
        if message_type == "connection.ready":
            # A duplicate/late handshake ack -- benign, keep polling.
            logger.info("order_sync op=receive_event outcome=ignored_duplicate_ready")
            return None
        if message_type != "event":
            logger.warning(
                "order_sync op=receive_event outcome=unknown_message_type type=%s",
                message_type,
            )
            raise SyncProtocolError(f"Unknown message type: {message_type!r}")

        event = _parse_event_fields(message)
        logger.info(
            "order_sync op=receive_event outcome=ok event_id=%s event_type=%s",
            event.event_id,
            event.event_type.value,
        )
        return event

    def _require_ws(self) -> websocket.WebSocket:
        with self._lock:
            ws = self._ws
        if ws is None:
            raise SyncConnectionError("Not connected")
        return ws

    # -- HTTP: recovery / detail / actions --------------------------------

    def fetch_missed_events(self, after_event_id: int | None) -> list[OrderSyncEvent]:
        params: dict[str, str | int] = {"device_id": self._device_id}
        if after_event_id is not None:
            params["after_event_id"] = after_event_id
        body = self._http_get(f"{self._http_base}/api/admin/orders/sync/", params)
        raw_events = body.get("events")
        if not isinstance(raw_events, list):
            raise SyncProtocolError("sync response missing 'events' list")
        events = [_parse_event_fields(_require_dict(item)) for item in raw_events]
        logger.info(
            "order_sync op=fetch_missed_events outcome=ok count=%s", len(events)
        )
        return events

    def fetch_order_detail(self, order_id: uuid.UUID) -> OrderSyncDetail:
        body = self._http_get(f"{self._http_base}/api/admin/orders/{order_id}/", {})
        detail = _parse_order_detail(body)
        logger.info("order_sync op=fetch_order_detail outcome=ok order_id=%s", order_id)
        return detail

    def confirm_order(
        self, order_id: uuid.UUID, device_id: str
    ) -> OrderSyncActionResult:
        body = self._http_post(
            f"{self._http_base}/api/admin/orders/{order_id}/confirm/",
            {"device_id": device_id},
        )
        result = _parse_action_result(body)
        logger.info("order_sync op=confirm_order outcome=ok order_id=%s", order_id)
        return result

    def reject_order(
        self, order_id: uuid.UUID, device_id: str, reason: str
    ) -> OrderSyncActionResult:
        body = self._http_post(
            f"{self._http_base}/api/admin/orders/{order_id}/reject/",
            {"device_id": device_id, "reason": reason},
        )
        result = _parse_action_result(body)
        logger.info("order_sync op=reject_order outcome=ok order_id=%s", order_id)
        return result

    def acknowledge(self, order_id: uuid.UUID, device_id: str, event_id: int) -> None:
        self._http_post(
            f"{self._http_base}/api/admin/orders/{order_id}/acknowledge/",
            {"device_id": device_id, "event_id": event_id},
        )
        logger.info(
            "order_sync op=acknowledge outcome=ok order_id=%s event_id=%s",
            order_id,
            event_id,
        )

    def _http_get(self, url: str, params: dict[str, str | int]) -> dict[str, object]:
        self._check_enabled()
        try:
            response = requests.get(
                url,
                params=params,
                headers={"X-API-Key": self._api_key},
                timeout=self._http_timeout,
            )
        except requests.RequestException as exc:
            logger.warning("order_sync op=http_get outcome=connection_error")
            raise SyncConnectionError("Unable to reach Django order-sync API") from exc
        return self._decode_http_response(response)

    def _http_post(self, url: str, payload: dict[str, Any]) -> dict[str, object]:
        self._check_enabled()
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"X-API-Key": self._api_key},
                timeout=self._http_timeout,
            )
        except requests.RequestException as exc:
            logger.warning("order_sync op=http_post outcome=connection_error")
            raise SyncConnectionError("Unable to reach Django order-sync API") from exc
        return self._decode_http_response(response)

    def _decode_http_response(self, response: requests.Response) -> dict[str, object]:
        if response.status_code in (401, 403):
            logger.warning(
                "order_sync op=http outcome=unauthorized status=%s",
                response.status_code,
            )
            raise SyncAuthenticationError("Django rejected the API key")
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.warning(
                "order_sync op=http outcome=http_error status=%s",
                response.status_code,
            )
            raise SyncConnectionError(
                f"Django order-sync API returned {response.status_code}"
            ) from exc
        if not response.content:
            return {}
        try:
            body = response.json()
        except ValueError as exc:
            raise SyncProtocolError("Response body was not valid JSON") from exc
        return _require_dict(body)


# -- Decoding helpers (never trust data from the network) --------------------


def _decode_ws_message(raw: str | bytes) -> dict[str, object]:
    if isinstance(raw, bytes):
        if len(raw) > _MAX_WS_MESSAGE_BYTES:
            raise SyncProtocolError("Message too large")
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SyncProtocolError("Message was not valid UTF-8") from exc
    if len(raw) > _MAX_WS_MESSAGE_BYTES:
        raise SyncProtocolError("Message too large")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SyncProtocolError("Message was not valid JSON") from exc
    return _require_dict(data)


def _require_dict(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise SyncProtocolError("Expected a JSON object")
    return cast(dict[str, object], data)


def _parse_event_fields(data: dict[str, object]) -> OrderSyncEvent:
    event_id = data.get("event_id")
    order_id = data.get("order_id")
    event_type_raw = data.get("event_type")
    created_at_raw = data.get("created_at")
    if not isinstance(event_id, int) or not isinstance(order_id, str):
        raise SyncProtocolError(
            "event_id must be an integer and order_id a UUID string"
        )
    try:
        parsed_order_id = uuid.UUID(order_id)
    except ValueError as exc:
        raise SyncProtocolError("order_id must be a UUID string") from exc
    if not isinstance(event_type_raw, str):
        raise SyncProtocolError("event_type must be a string")
    try:
        event_type = OrderEventType(event_type_raw)
    except ValueError as exc:
        raise SyncProtocolError(f"Unknown event_type: {event_type_raw!r}") from exc
    created_at = _parse_datetime(created_at_raw)
    return OrderSyncEvent(
        event_id=event_id,
        order_id=parsed_order_id,
        event_type=event_type,
        created_at=created_at,
    )


def _parse_order_detail(data: dict[str, object]) -> OrderSyncDetail:
    try:
        items_raw = data["items"]
        if not isinstance(items_raw, list):
            raise SyncProtocolError("items must be a list")
        items = [_parse_order_item(_require_dict(item)) for item in items_raw]
        return OrderSyncDetail(
            order_id=_require_uuid(data, "order_id"),
            order_number=_require_str(data, "order_number"),
            status=_require_str(data, "status"),
            customer_name=_require_str(data, "customer_name"),
            customer_phone=_require_str(data, "customer_phone"),
            customer_address=_require_str(data, "customer_address"),
            order_date=_parse_datetime(data.get("order_date")),
            subtotal=_require_decimal(data, "subtotal"),
            delivery_fee=_require_decimal(data, "delivery_fee"),
            discount=_require_decimal(data, "discount"),
            total=_require_decimal(data, "total"),
            items=items,
        )
    except KeyError as exc:
        raise SyncProtocolError(f"Order detail missing field: {exc}") from exc


def _parse_order_item(data: dict[str, object]) -> OrderSyncItemDetail:
    try:
        product_id_raw = data.get("product_id")
        if product_id_raw is not None and not isinstance(product_id_raw, str):
            raise SyncProtocolError("product_id must be a UUID string or null")
        return OrderSyncItemDetail(
            product_id=_parse_uuid(product_id_raw),
            product_name=_require_str(data, "product_name"),
            unit=_require_str(data, "unit"),
            quantity=_require_decimal(data, "quantity"),
            unit_price=_require_decimal(data, "unit_price"),
            subtotal=_require_decimal(data, "subtotal"),
        )
    except KeyError as exc:
        raise SyncProtocolError(f"Order item missing field: {exc}") from exc


def _parse_action_result(data: dict[str, object]) -> OrderSyncActionResult:
    return OrderSyncActionResult(
        order_id=_require_uuid(data, "order_id"),
        status=_require_str(data, "status"),
    )


def _require_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise SyncProtocolError(f"{key} must be a string")
    return value


def _require_int(data: dict[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise SyncProtocolError(f"{key} must be an integer")
    return value


def _require_uuid(data: dict[str, object], key: str) -> uuid.UUID:
    value = data.get(key)
    if not isinstance(value, str):
        raise SyncProtocolError(f"{key} must be a UUID string")
    parsed = _parse_uuid(value)
    if parsed is None:
        raise SyncProtocolError(f"{key} must be a UUID string")
    return parsed


def _parse_uuid(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SyncProtocolError("UUID value must be a string or null")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise SyncProtocolError("UUID value is invalid") from exc


def _require_decimal(data: dict[str, object], key: str) -> Decimal:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise SyncProtocolError(f"{key} must be a number or numeric string")
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as exc:
        raise SyncProtocolError(f"{key} is not a valid decimal") from exc
    if not decimal_value.is_finite():
        raise SyncProtocolError(f"{key} is not a finite number")
    return decimal_value


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise SyncProtocolError("created_at/order_date must be a string")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise SyncProtocolError(f"Invalid ISO8601 timestamp: {value!r}") from exc


def _to_ws_url(http_base_url: str) -> str:
    parts = urlsplit(http_base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, "", "", ""))
