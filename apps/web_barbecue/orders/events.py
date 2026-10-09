"""Broadcasting OrderEvent rows to connected Desktop Admin clients.

This is the only module allowed to know about the channel layer /
"admin_orders" group name outside of the consumer itself - views call
`broadcast_order_event`, never `get_channel_layer()` directly, so the
group name and message shape stay defined in one place.
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import OrderEvent
from .serializers import serialize_order

logger = logging.getLogger(__name__)

ADMIN_ORDERS_GROUP = "admin_orders"


def broadcast_order_event(event: OrderEvent) -> None:
    """Fan out an already-committed OrderEvent to the admin_orders group.

    Callers must invoke this from transaction.on_commit(...) so a
    connected Admin never receives a notification for an event it
    can't yet read back via GET .../sync/ (no ack-before-persist races).

    Never raises: a channel-layer outage (e.g. Redis down) must not
    break the HTTP request that created the event - the Admin's HTTP
    recovery path (GET /api/admin/orders/sync/) covers this case.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning(
            "order_event_broadcast_skipped: no channel layer configured "
            "event_id=%s event_type=%s",
            event.id,
            event.event_type,
        )
        return

    message = {
        "type": event.event_type,
        "event_id": event.id,
        "order_id": str(event.order_id),
        "payload": event.payload,
        "order": serialize_order(event.order),
        "created_at": event.created_at.isoformat(),
    }
    try:
        async_to_sync(channel_layer.group_send)(ADMIN_ORDERS_GROUP, message)
    except Exception:
        # Never let a broadcast failure surface as a 500 to the caller
        # (checkout / confirm / reject); the event row is already
        # durably committed and recoverable via HTTP sync.
        logger.exception(
            "order_event_broadcast_failed event_id=%s event_type=%s",
            event.id,
            event.event_type,
        )
