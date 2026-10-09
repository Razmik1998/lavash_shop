import json
import uuid

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from products.models import Product

SYNC_URL_NAME = "products-sync"


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def auth_headers():
    return {"HTTP_X_API_KEY": settings.WEB_SYNC_API_KEY}


def _payload(*products):
    return json.dumps({"products": list(products)})


def _item(
    admin_product_id=None,
    name="Խոզի խորոված",
    selling_price="3500.00",
    is_active=True,
):
    return {
        "admin_product_id": str(admin_product_id or uuid.uuid4()),
        "name": name,
        "selling_price": selling_price,
        "is_active": is_active,
    }


@pytest.mark.django_db
def test_missing_api_key_returns_401(client):
    response = client.post(
        reverse(SYNC_URL_NAME), data=_payload(_item()), content_type="application/json"
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_wrong_api_key_returns_403(client):
    response = client.post(
        reverse(SYNC_URL_NAME),
        data=_payload(_item()),
        content_type="application/json",
        HTTP_X_API_KEY="wrong-key",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_first_sync_creates_product(client, auth_headers):
    admin_id = uuid.uuid4()
    response = client.post(
        reverse(SYNC_URL_NAME),
        data=_payload(_item(admin_id, name="Հավի խորոված", selling_price="3000.00")),
        content_type="application/json",
        **auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 1
    assert body["updated"] == 0
    assert body["failed"] == 0

    product = Product.objects.get(admin_product_id=admin_id)
    assert product.name == "Հավի խորոված"
    assert str(product.price) == "3000.00"
    assert product.is_active is True


@pytest.mark.django_db
def test_second_sync_updates_existing_product(client, auth_headers):
    admin_id = uuid.uuid4()
    client.post(
        reverse(SYNC_URL_NAME),
        data=_payload(_item(admin_id, name="Հին անուն", selling_price="1000.00")),
        content_type="application/json",
        **auth_headers,
    )

    response = client.post(
        reverse(SYNC_URL_NAME),
        data=_payload(_item(admin_id, name="Նոր անուն", selling_price="1500.00")),
        content_type="application/json",
        **auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 0
    assert body["updated"] == 1

    product = Product.objects.get(admin_product_id=admin_id)
    assert product.name == "Նոր անուն"
    assert str(product.price) == "1500.00"


@pytest.mark.django_db
def test_sync_is_idempotent(client, auth_headers):
    admin_id = uuid.uuid4()
    payload = _payload(_item(admin_id))
    kwargs = {"data": payload, "content_type": "application/json", **auth_headers}
    client.post(reverse(SYNC_URL_NAME), **kwargs)
    client.post(reverse(SYNC_URL_NAME), **kwargs)

    assert Product.objects.filter(admin_product_id=admin_id).count() == 1


@pytest.mark.django_db
def test_first_sync_defaults_display_name_to_name(client, auth_headers):
    admin_id = uuid.uuid4()
    client.post(
        reverse(SYNC_URL_NAME),
        data=_payload(_item(admin_id, name="Խոզի խորոված")),
        content_type="application/json",
        **auth_headers,
    )

    product = Product.objects.get(admin_product_id=admin_id)
    assert product.display_name == "Խոզի խորոված"


@pytest.mark.django_db
def test_sync_preserves_web_owned_fields(client, auth_headers):
    admin_id = uuid.uuid4()
    client.post(
        reverse(SYNC_URL_NAME),
        data=_payload(_item(admin_id, selling_price="1000.00")),
        content_type="application/json",
        **auth_headers,
    )

    product = Product.objects.get(admin_product_id=admin_id)
    product.display_name = "Հատուկ խորոված"
    product.web_price = "4000.00"
    product.is_visible = True
    product.save()

    client.post(
        reverse(SYNC_URL_NAME),
        data=_payload(_item(admin_id, name="Նոր անուն", selling_price="1200.00")),
        content_type="application/json",
        **auth_headers,
    )

    product.refresh_from_db()
    assert product.display_name == "Հատուկ խորոված"
    assert str(product.web_price) == "4000.00"
    assert product.is_visible is True
    assert str(product.price) == "1200.00"
    assert product.name == "Նոր անուն"


@pytest.mark.django_db
def test_malformed_json_returns_400(client, auth_headers):
    response = client.post(
        reverse(SYNC_URL_NAME),
        data="not json",
        content_type="application/json",
        **auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_products_not_a_list_returns_400(client, auth_headers):
    response = client.post(
        reverse(SYNC_URL_NAME),
        data=json.dumps({"products": "nope"}),
        content_type="application/json",
        **auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_partial_failure_reports_failed_item(client, auth_headers):
    good = _item()
    # missing selling_price/is_active
    bad = {"admin_product_id": str(uuid.uuid4()), "name": "Անվավեր"}

    response = client.post(
        reverse(SYNC_URL_NAME),
        data=_payload(good, bad),
        content_type="application/json",
        **auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 1
    assert body["failed"] == 1
    assert len(body["failed_items"]) == 1
