import json
import uuid
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from orders.models import Order, OrderItem
from products.models import Product


def _make_product(**kwargs):
    defaults = {
        "admin_product_id": uuid.uuid4(),
        "name": "Խոզի խորոված",
        "price": Decimal("3500.00"),
        "is_active": True,
        "is_visible": True,
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


@pytest.fixture
def client():
    return Client()


def _add_to_basket(client, product, quantity=1):
    client.post(
        reverse("orders:basket-add"),
        data=json.dumps({"product_id": str(product.id), "quantity": quantity}),
        content_type="application/json",
    )


@pytest.mark.django_db
def test_successful_checkout_creates_order_and_items(client):
    product = _make_product()
    _add_to_basket(client, product, quantity=2)

    response = client.post(
        reverse("orders:checkout"),
        data={
            "customer_name": "Անի Հակոբյան",
            "phone": "+37499123456",
            "address": "Վանաձոր, Տիգրան Մեծի փող. 5",
            "comment": "",
        },
    )

    assert response.status_code == 200
    assert response.context["order_success"] is True

    order = Order.objects.get()
    assert order.customer_name == "Անի Հակոբյան"
    assert order.status == Order.Status.PENDING
    assert order.total_amount == Decimal("7000.00")

    items = list(OrderItem.objects.filter(order=order))
    assert len(items) == 1
    assert items[0].product_name == product.name
    assert items[0].quantity == 2
    assert items[0].unit_price == Decimal("3500.00")
    assert items[0].total_price == Decimal("7000.00")


@pytest.mark.django_db
def test_checkout_clears_the_basket(client):
    product = _make_product()
    _add_to_basket(client, product)

    client.post(
        reverse("orders:checkout"),
        data={
            "customer_name": "Անի Հակոբյան",
            "phone": "+37499123456",
            "address": "Վանաձոր, Տիգրան Մեծի փող. 5",
        },
    )

    basket_response = client.get(reverse("orders:basket-detail"))
    assert basket_response.json()["count"] == 0


@pytest.mark.django_db
def test_checkout_with_empty_basket_does_not_create_order(client):
    response = client.post(
        reverse("orders:checkout"),
        data={
            "customer_name": "Անի Հակոբյան",
            "phone": "+37499123456",
            "address": "Վանաձոր, Տիգրան Մեծի փող. 5",
        },
    )
    assert response.status_code == 400
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_checkout_without_customer_name_is_rejected(client):
    product = _make_product()
    _add_to_basket(client, product)

    response = client.post(
        reverse("orders:checkout"),
        data={
            "customer_name": "",
            "phone": "+37499123456",
            "address": "Վանաձոր, Տիգրան Մեծի փող. 5",
        },
    )
    assert response.status_code == 400
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_checkout_without_address_is_rejected(client):
    product = _make_product()
    _add_to_basket(client, product)

    response = client.post(
        reverse("orders:checkout"),
        data={
            "customer_name": "Անի Հակոբյան",
            "phone": "+37499123456",
        },
    )

    assert response.status_code == 400
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_checkout_rejects_an_address_outside_vanadzor(client):
    product = _make_product()
    _add_to_basket(client, product)

    response = client.post(
        reverse("orders:checkout"),
        data={
            "customer_name": "Անի Հակոբյան",
            "phone": "+37499123456",
            "address": "Երևան, Կենտրոն",
        },
    )
    assert response.status_code == 400
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_checkout_accepts_the_historical_city_name(client):
    """Vanadzor was called Kirovakan under the Soviet era; some
    long-time residents still write it that way, so an address using
    the historical name must not be rejected as 'wrong city'."""
    product = _make_product()
    _add_to_basket(client, product)

    response = client.post(
        reverse("orders:checkout"),
        data={
            "customer_name": "Անի Հակոբյան",
            "phone": "+37499123456",
            "address": "Կիրովական, Կենտրոնական փող. 5",
        },
    )
    assert response.status_code == 200
    assert Order.objects.count() == 1


@pytest.mark.django_db
def test_checkout_never_trusts_a_client_supplied_total(client):
    """The order form has no total field at all - the server always
    derives total_amount/unit_price from the *current* Product price,
    regardless of what the price looked like when it was added to the
    basket or anything a malicious client might try to inject."""
    product = _make_product(price=Decimal("3500.00"))
    _add_to_basket(client, product, quantity=1)

    # Price changes after the item was added to the basket but before
    # checkout is submitted.
    product.price = Decimal("5000.00")
    product.save(update_fields=["price"])

    client.post(
        reverse("orders:checkout"),
        data={
            "customer_name": "Անի Հակոբյան",
            "phone": "+37499123456",
            "address": "Վանաձոր, Տիգրան Մեծի փող. 5",
            # Not a real form field, but even if it were, it must be ignored.
            "total_amount": "1.00",
        },
    )

    order = Order.objects.get()
    assert order.total_amount == Decimal("5000.00")
    assert order.items.get().unit_price == Decimal("5000.00")
