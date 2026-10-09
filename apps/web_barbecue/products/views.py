import json
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from orders.basket import Basket
from orders.forms import CustomerInfoForm

from .auth import require_api_key
from .models import Product


def build_product_list_context(request):
    """Shared context for the storefront page.

    Used both by the normal GET (product_list) and by
    orders.views.checkout_submit's error path, so a failed order
    submission re-renders the exact same page instead of duplicating
    the product/basket context building.
    """
    products = Product.objects.filter(is_active=True, is_visible=True)
    basket = Basket(request)
    return {
        "products": products,
        "basket_summary": basket.summary(),
        "customer_form": CustomerInfoForm(),
        "open_order_modal": False,
    }


def product_list(request):
    return render(request, "products/index.html", build_product_list_context(request))


# No session/cookie auth is ever used on this endpoint - it is authenticated
# purely by the X-API-Key header checked in require_api_key, so Django's
# CSRF protection (which guards cookie-authenticated browser requests)
# does not apply here.
@csrf_exempt
@require_POST
@require_api_key
def sync_products(request):
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    items = payload.get("products")
    if not isinstance(items, list):
        return JsonResponse(
            {"error": "invalid_payload", "detail": "'products' must be a list"},
            status=400,
        )

    created = 0
    updated = 0
    failed_items = []
    for item in items:
        outcome, error = _upsert_product(item)
        if outcome == "created":
            created += 1
        elif outcome == "updated":
            updated += 1
        else:
            failed_items.append({"item": item, "error": error})

    return JsonResponse(
        {
            "created": created,
            "updated": updated,
            "failed": len(failed_items),
            "failed_items": failed_items,
        }
    )


def _upsert_product(item):
    if not isinstance(item, dict):
        return "failed", "item_must_be_object"

    try:
        admin_product_id = item["admin_product_id"]
        name = item["name"]
        price = Decimal(str(item["selling_price"]))
        is_active = bool(item["is_active"])
    except (KeyError, InvalidOperation, TypeError):
        return "failed", "missing_or_invalid_field"

    obj, was_created = Product.objects.get_or_create(
        admin_product_id=admin_product_id,
        # display_name defaults to name only on first sync; later syncs
        # must never touch it, since it becomes web-owned once created.
        defaults={
            "name": name,
            "price": price,
            "is_active": is_active,
            "display_name": name,
        },
    )
    if was_created:
        return "created", None

    obj.name = name
    obj.price = price
    obj.is_active = is_active
    obj.save(update_fields=["name", "price", "is_active", "updated_at"])
    return "updated", None
