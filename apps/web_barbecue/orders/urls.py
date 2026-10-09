from django.urls import path

from . import admin_api, views

app_name = "orders"

urlpatterns = [
    path("api/basket/", views.basket_detail, name="basket-detail"),
    path("api/basket/items/", views.basket_add, name="basket-add"),
    path(
        "api/basket/items/<uuid:product_id>/update/",
        views.basket_update,
        name="basket-update",
    ),
    path(
        "api/basket/items/<uuid:product_id>/remove/",
        views.basket_remove,
        name="basket-remove",
    ),
    path("orders/checkout/", views.checkout_submit, name="checkout"),
    # Admin-facing sync API (X-API-Key authenticated, consumed by
    # apps/admin's SyncService) - order matters: the static "sync/"
    # path must be registered before the <uuid:order_id>/ pattern so it
    # is never swallowed by it.
    path("api/admin/orders/sync/", admin_api.order_sync, name="admin-orders-sync"),
    path(
        "api/admin/orders/<uuid:order_id>/",
        admin_api.order_detail,
        name="admin-order-detail",
    ),
    path(
        "api/admin/orders/<uuid:order_id>/confirm/",
        admin_api.order_confirm,
        name="admin-order-confirm",
    ),
    path(
        "api/admin/orders/<uuid:order_id>/reject/",
        admin_api.order_reject,
        name="admin-order-reject",
    ),
    path(
        "api/admin/orders/<uuid:order_id>/acknowledge/",
        admin_api.order_acknowledge,
        name="admin-order-acknowledge",
    ),
]
