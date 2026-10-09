import json
import uuid
from decimal import Decimal

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from orders.models import Order, OrderEvent, OrderStatusHistory


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def auth_headers():
    return {"HTTP_X_API_KEY": settings.WEB_SYNC_API_KEY}


@pytest.fixture
def pending_order(db):
    return Order.objects.create(
        customer_name="Անի Հակոբյան",
        phone="+37499123456",
        address="Վանաձոր, Տիգրան Մեծի փող. 5",
        total_amount=Decimal("1000.00"),
    )


def _confirm_url(order_id):
    return reverse("orders:admin-order-confirm", args=[order_id])


def _reject_url(order_id):
    return reverse("orders:admin-order-reject", args=[order_id])


def _detail_url(order_id):
    return reverse("orders:admin-order-detail", args=[order_id])


def _ack_url(order_id):
    return reverse("orders:admin-order-acknowledge", args=[order_id])


@pytest.mark.django_db
def test_admin_endpoints_require_api_key(client, pending_order):
    response = client.get(_detail_url(pending_order.id))
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_endpoints_reject_wrong_api_key(client, pending_order):
    response = client.get(
        _detail_url(pending_order.id), HTTP_X_API_KEY="wrong-key"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_order_detail_returns_full_order(client, auth_headers, pending_order):
    response = client.get(_detail_url(pending_order.id), **auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(pending_order.id)
    assert body["customer_name"] == pending_order.customer_name
    assert body["phone"] == pending_order.phone
    assert body["address"] == pending_order.address
    assert body["status"] == Order.Status.PENDING


@pytest.mark.django_db
def test_confirm_transitions_pending_to_confirmed(client, auth_headers, pending_order):
    response = client.post(
        _confirm_url(pending_order.id),
        data=json.dumps({"device_id": "admin-desktop-1"}),
        content_type="application/json",
        **auth_headers,
    )
    assert response.status_code == 200
    assert response.json() == {
        "order_id": str(pending_order.id),
        "status": "CONFIRMED",
    }

    pending_order.refresh_from_db()
    assert pending_order.status == Order.Status.CONFIRMED
    assert OrderStatusHistory.objects.filter(order=pending_order).count() == 1
    assert (
        OrderEvent.objects.filter(
            order=pending_order, event_type=OrderEvent.EventType.ORDER_CONFIRMED
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_confirm_is_idempotent(client, auth_headers, pending_order):
    payload = json.dumps({"device_id": "admin-desktop-1"})
    client.post(
        _confirm_url(pending_order.id),
        data=payload,
        content_type="application/json",
        **auth_headers,
    )
    response = client.post(
        _confirm_url(pending_order.id),
        data=payload,
        content_type="application/json",
        **auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"
    # No second transition/event for the duplicate confirm.
    assert OrderStatusHistory.objects.filter(order=pending_order).count() == 1
    assert OrderEvent.objects.filter(
        order=pending_order, event_type=OrderEvent.EventType.ORDER_CONFIRMED
    ).count() == 1


@pytest.mark.django_db
def test_confirm_missing_device_id_is_rejected(client, auth_headers, pending_order):
    response = client.post(
        _confirm_url(pending_order.id),
        data=json.dumps({}),
        content_type="application/json",
        **auth_headers,
    )
    assert response.status_code == 400
    pending_order.refresh_from_db()
    assert pending_order.status == Order.Status.PENDING


@pytest.mark.django_db
def test_reject_transitions_pending_to_rejected_with_reason(
    client, auth_headers, pending_order
):
    response = client.post(
        _reject_url(pending_order.id),
        data=json.dumps({"device_id": "admin-desktop-1", "reason": "Ապրանքը չկա"}),
        content_type="application/json",
        **auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"

    pending_order.refresh_from_db()
    assert pending_order.status == Order.Status.REJECTED
    history = OrderStatusHistory.objects.get(order=pending_order)
    assert history.reason == "Ապրանքը չկա"


@pytest.mark.django_db
def test_reject_is_idempotent(client, auth_headers, pending_order):
    payload = json.dumps({"device_id": "admin-desktop-1", "reason": "no stock"})
    client.post(
        _reject_url(pending_order.id),
        data=payload,
        content_type="application/json",
        **auth_headers,
    )
    response = client.post(
        _reject_url(pending_order.id),
        data=payload,
        content_type="application/json",
        **auth_headers,
    )
    assert response.status_code == 200
    assert OrderEvent.objects.filter(
        order=pending_order, event_type=OrderEvent.EventType.ORDER_REJECTED
    ).count() == 1


@pytest.mark.django_db
def test_cannot_reject_an_already_confirmed_order(client, auth_headers, pending_order):
    client.post(
        _confirm_url(pending_order.id),
        data=json.dumps({"device_id": "admin-desktop-1"}),
        content_type="application/json",
        **auth_headers,
    )
    response = client.post(
        _reject_url(pending_order.id),
        data=json.dumps({"device_id": "admin-desktop-1", "reason": "changed mind"}),
        content_type="application/json",
        **auth_headers,
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_acknowledge_is_idempotent(client, auth_headers, pending_order):
    confirm_response = client.post(
        _confirm_url(pending_order.id),
        data=json.dumps({"device_id": "admin-desktop-1"}),
        content_type="application/json",
        **auth_headers,
    )
    assert confirm_response.status_code == 200
    event = OrderEvent.objects.get(
        order=pending_order, event_type=OrderEvent.EventType.ORDER_CONFIRMED
    )

    for _ in range(2):
        response = client.post(
            _ack_url(pending_order.id),
            data=json.dumps({"device_id": "admin-desktop-1", "event_id": event.id}),
            content_type="application/json",
            **auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == {"acknowledged": True, "event_id": event.id}

    assert event.acknowledgements.count() == 1


@pytest.mark.django_db
def test_sync_returns_events_after_cursor(client, auth_headers, pending_order):
    other_order = Order.objects.create(
        customer_name="Գագիկ",
        phone="+37499000000",
        address="Վանաձոր",
        total_amount=Decimal("500.00"),
    )
    event1 = OrderEvent.objects.create(
        order=pending_order, event_type=OrderEvent.EventType.ORDER_CREATED, payload={}
    )
    event2 = OrderEvent.objects.create(
        order=other_order, event_type=OrderEvent.EventType.ORDER_CREATED, payload={}
    )

    response = client.get(
        reverse("orders:admin-orders-sync"),
        {"device_id": "admin-desktop-1", "after_event_id": event1.id},
        **auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert [e["event_id"] for e in body["events"]] == [event2.id]
    assert body["events"][0]["order"]["id"] == str(other_order.id)


@pytest.mark.django_db
def test_sync_requires_device_id(client, auth_headers):
    response = client.get(reverse("orders:admin-orders-sync"), **auth_headers)
    assert response.status_code == 400


@pytest.mark.django_db
def test_checkout_creates_an_order_created_event(client):
    from products.models import Product

    product = Product.objects.create(
        admin_product_id=uuid.uuid4(),
        name="Խոզի խորոված",
        price=Decimal("3500.00"),
        is_active=True,
        is_visible=True,
    )
    client.post(
        reverse("orders:basket-add"),
        data=json.dumps({"product_id": str(product.id), "quantity": 1}),
        content_type="application/json",
    )
    client.post(
        reverse("orders:checkout"),
        data={
            "customer_name": "Անի Հակոբյան",
            "phone": "+37499123456",
            "address": "Վանաձոր, Տիգրան Մեծի փող. 5",
        },
    )

    order = Order.objects.get()
    assert OrderEvent.objects.filter(
        order=order, event_type=OrderEvent.EventType.ORDER_CREATED
    ).count() == 1
