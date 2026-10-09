import json
import uuid
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

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


@pytest.mark.django_db
def test_add_to_basket_creates_line(client):
    product = _make_product()
    response = client.post(
        reverse("orders:basket-add"),
        data=json.dumps({"product_id": str(product.id), "quantity": 2}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["total"] == "7000.00"
    assert body["items"][0]["product_id"] == str(product.id)


@pytest.mark.django_db
def test_add_twice_accumulates_quantity(client):
    product = _make_product()
    url = reverse("orders:basket-add")
    payload = json.dumps({"product_id": str(product.id), "quantity": 1})
    client.post(url, data=payload, content_type="application/json")
    response = client.post(url, data=payload, content_type="application/json")
    assert response.json()["count"] == 2


@pytest.mark.django_db
def test_update_quantity(client):
    product = _make_product()
    client.post(
        reverse("orders:basket-add"),
        data=json.dumps({"product_id": str(product.id), "quantity": 1}),
        content_type="application/json",
    )
    response = client.post(
        reverse("orders:basket-update", args=[product.id]),
        data=json.dumps({"quantity": 5}),
        content_type="application/json",
    )
    assert response.json()["count"] == 5


@pytest.mark.django_db
def test_update_quantity_to_zero_removes_line(client):
    product = _make_product()
    client.post(
        reverse("orders:basket-add"),
        data=json.dumps({"product_id": str(product.id), "quantity": 1}),
        content_type="application/json",
    )
    response = client.post(
        reverse("orders:basket-update", args=[product.id]),
        data=json.dumps({"quantity": 0}),
        content_type="application/json",
    )
    body = response.json()
    assert body["count"] == 0
    assert body["items"] == []


@pytest.mark.django_db
def test_remove_from_basket(client):
    product = _make_product()
    client.post(
        reverse("orders:basket-add"),
        data=json.dumps({"product_id": str(product.id), "quantity": 3}),
        content_type="application/json",
    )
    response = client.post(reverse("orders:basket-remove", args=[product.id]))
    body = response.json()
    assert body["count"] == 0


@pytest.mark.django_db
def test_stale_product_is_pruned_from_basket(client):
    product = _make_product()
    client.post(
        reverse("orders:basket-add"),
        data=json.dumps({"product_id": str(product.id), "quantity": 1}),
        content_type="application/json",
    )
    product.is_visible = False
    product.save(update_fields=["is_visible"])

    response = client.get(reverse("orders:basket-detail"))
    body = response.json()
    assert body["items"] == []
    assert body["count"] == 0


@pytest.mark.django_db
def test_add_with_invalid_quantity_is_rejected(client):
    product = _make_product()
    response = client.post(
        reverse("orders:basket-add"),
        data=json.dumps({"product_id": str(product.id), "quantity": -1}),
        content_type="application/json",
    )
    assert response.status_code == 400
