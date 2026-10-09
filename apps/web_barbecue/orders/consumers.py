"""WebSocket consumer for the Desktop Admin's live order sync channel.

Authentication mirrors products.auth.require_api_key: the same
X-API-Key shared secret, read here from the WebSocket handshake
headers instead of a Django request. There is exactly one connected
Admin instance in scope for this task (see task-plan.md), so this
consumer does not attempt any multi-admin fan-out beyond the single
"admin_orders" group.

Never logs the raw API key, and only logs operation + outcome (no
request/response bodies), per CLAUDE.md / .claude/rules/security.md.
"""
import json
import logging

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .events import ADMIN_ORDERS_GROUP
from .models import OrderEvent
from .serializers import serialize_order

logger = logging.getLogger(__name__)

# Non-standard private-use close codes (RFC 6455 reserves 4000-4999 for
# applications) so the Admin-side client can distinguish "you sent bad
# auth" from a generic network failure.
CLOSE_MISSING_API_KEY = 4401
CLOSE_INVALID_API_KEY = 4403


class AdminOrdersConsumer(AsyncWebsocketConsumer):
    group_name = ADMIN_ORDERS_GROUP

    async def connect(self):
        headers = dict(self.scope.get("headers") or [])
        api_key = headers.get(b"x-api-key")

        if not api_key:
            logger.warning("admin_orders_ws_rejected reason=missing_api_key")
            await self.close(code=CLOSE_MISSING_API_KEY)
            return

        if api_key.decode("utf-8", errors="strict") != settings.WEB_SYNC_API_KEY:
            logger.warning("admin_orders_ws_rejected reason=invalid_api_key")
            await self.close(code=CLOSE_INVALID_API_KEY)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info("admin_orders_ws_connected")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info("admin_orders_ws_disconnected code=%s", close_code)

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is None:
            return

        try:
            message = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(json.dumps({"type": "error", "detail": "invalid_json"}))
            return

        if not isinstance(message, dict) or message.get("type") != "connect":
            await self.send(
                json.dumps({"type": "error", "detail": "expected_connect_message"})
            )
            return

        device_id = message.get("device_id")
        last_event_id = message.get("last_event_id", 0)
        if last_event_id is None:
            last_event_id = 0
        if not isinstance(device_id, str) or not isinstance(last_event_id, int):
            await self.send(
                json.dumps({"type": "error", "detail": "invalid_connect_payload"})
            )
            return

        logger.info(
            "admin_orders_ws_sync_start device_id=%s last_event_id=%s",
            device_id,
            last_event_id,
        )
        await self.send(json.dumps({"type": "connection.ready"}))
        await self._replay_missed_events(last_event_id)

    async def _replay_missed_events(self, last_event_id: int) -> None:
        events = await self._fetch_events_after(last_event_id)
        for event in events:
            await self.send(json.dumps({**event, "type": "event"}))

    @staticmethod
    @sync_to_async
    def _fetch_events_after(last_event_id: int) -> list[dict]:
        queryset = (
            OrderEvent.objects.filter(id__gt=last_event_id)
            .select_related("order")
            .prefetch_related("order__items")
            .order_by("id")
        )
        return [
            {
                "event_id": event.id,
                "order_id": str(event.order_id),
                "event_type": event.event_type,
                "payload": event.payload,
                "order": serialize_order(event.order),
                "created_at": event.created_at.isoformat(),
            }
            for event in queryset
        ]

    # --- group broadcast handlers -------------------------------------
    # Channels dispatches a group_send message to `type.replace(".", "_")`
    # - these three names correspond to OrderEvent.EventType.ORDER_CREATED
    # / ORDER_CONFIRMED / ORDER_REJECTED as sent by events.broadcast_order_event.

    async def order_created(self, event: dict) -> None:
        await self._send_live_event(event)

    async def order_confirmed(self, event: dict) -> None:
        await self._send_live_event(event)

    async def order_rejected(self, event: dict) -> None:
        await self._send_live_event(event)

    async def order_updated(self, event: dict) -> None:
        await self._send_live_event(event)

    async def _send_live_event(self, event: dict) -> None:
        message = {
            **event,
            "type": "event",
            "event_type": event.get("type"),
        }
        await self.send(json.dumps(message))
