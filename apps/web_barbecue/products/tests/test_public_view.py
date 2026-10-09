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


@pytest.mark.django_db
def test_visible_active_product_is_listed():
    product = _make_product()
    response = Client().get(reverse("product-list"))
    assert response.status_code == 200
    assert product.name.encode() in response.content


@pytest.mark.django_db
def test_visible_product_price_uses_apostrophe_thousands_separator():
    _make_product(price=Decimal("30000.00"))
    response = Client().get(reverse("product-list"))
    assert b"30&#x27;000" in response.content


@pytest.mark.django_db
def test_inactive_product_is_excluded():
    product = _make_product(is_active=False)
    response = Client().get(reverse("product-list"))
    assert product.name.encode() not in response.content


@pytest.mark.django_db
def test_invisible_product_is_excluded():
    product = _make_product(is_visible=False)
    response = Client().get(reverse("product-list"))
    assert product.name.encode() not in response.content
