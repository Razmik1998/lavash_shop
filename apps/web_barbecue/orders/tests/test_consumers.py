from decimal import Decimal

import pytest
from channels.testing import WebsocketCommunicator
from django.conf import settings

from orders.consumers import AdminOrdersConsumer
from orders.models import Order, OrderEvent


async def _connect(headers=None):
    application = AdminOrdersConsumer.as_asgi()
    communicator = WebsocketCommunicator(
        application, "/ws/admin/orders/", headers=headers or []
    )
    connected, _ = await communicator.connect()
    return communicator, connected


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_connect_without_api_key_is_rejected():
    communicator, connected = await _connect(headers=[])
    assert connected is False
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_connect_with_wrong_api_key_is_rejected():
    communicator, connected = await _connect(
        headers=[(b"x-api-key", b"wrong-key")]
    )
    assert connected is False
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_connect_with_valid_api_key_is_accepted():
    communicator, connected = await _connect(
        headers=[(b"x-api-key", settings.WEB_SYNC_API_KEY.encode())]
    )
    assert connected is True
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_connect_message_replays_missed_events_then_sync_completed():
    from asgiref.sync import sync_to_async

    order = await sync_to_async(Order.objects.create)(
        customer_name="Անի",
        phone="+37499123456",
        address="Վանաձոր",
        total_amount=Decimal("100.00"),
    )
    event = await sync_to_async(OrderEvent.objects.create)(
        order=order, event_type=OrderEvent.EventType.ORDER_CREATED, payload={}
    )

    communicator, connected = await _connect(
        headers=[(b"x-api-key", settings.WEB_SYNC_API_KEY.encode())]
    )
    assert connected is True

    await communicator.send_json_to(
        {"type": "connect", "device_id": "admin-desktop-1", "last_event_id": None}
    )

    ready = await communicator.receive_json_from()
    assert ready == {"type": "connection.ready"}

    replayed = await communicator.receive_json_from()
    assert replayed["type"] == "event"
    assert replayed["event_id"] == event.id
    assert replayed["event_type"] == OrderEvent.EventType.ORDER_CREATED
    assert replayed["order"]["id"] == str(order.id)

    await communicator.disconnect()
