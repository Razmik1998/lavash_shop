import json
from decimal import Decimal

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from products.views import build_product_list_context

from .basket import Basket
from .events import broadcast_order_event
from .forms import CustomerInfoForm
from .models import Order, OrderEvent, OrderItem
from .telegram import schedule_order_notification


def _parse_json_body(request):
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


@require_GET
def basket_detail(request):
    return JsonResponse(Basket(request).summary())


@require_POST
def basket_add(request):
    payload = _parse_json_body(request)
    if payload is None:
        return JsonResponse({"error": "invalid_json"}, status=400)

    product_id = payload.get("product_id")
    quantity = payload.get("quantity", 1)
    if not product_id or not isinstance(quantity, int) or quantity <= 0:
        return JsonResponse({"error": "invalid_payload"}, status=400)

    basket = Basket(request)
    basket.add(product_id, quantity)
    return JsonResponse(basket.summary())


@require_POST
def basket_update(request, product_id):
    payload = _parse_json_body(request)
    if payload is None:
        return JsonResponse({"error": "invalid_json"}, status=400)

    quantity = payload.get("quantity")
    if not isinstance(quantity, int):
        return JsonResponse({"error": "invalid_payload"}, status=400)

    basket = Basket(request)
    basket.set_quantity(product_id, quantity)
    return JsonResponse(basket.summary())


@require_POST
def basket_remove(request, product_id):
    basket = Basket(request)
    basket.remove(product_id)
    return JsonResponse(basket.summary())


@require_POST
def checkout_submit(request):
    basket = Basket(request)
    form = CustomerInfoForm(request.POST)
    lines = basket.lines()

    form_valid = form.is_valid()
    if not lines:
        form.add_error(None, "Զամբյուղը դատարկ է։ Խնդրում ենք ընտրել ապրանք։")

    if not form_valid or not lines:
        context = build_product_list_context(request)
        context.update({"customer_form": form, "open_order_modal": True})
        return render(request, "products/index.html", context, status=400)

    with transaction.atomic():
        total = sum((line.line_total for line in lines), Decimal("0"))
        order = Order.objects.create(
            customer_name=form.cleaned_data["customer_name"],
            phone=form.cleaned_data["phone"],
            address=form.cleaned_data["address"],
            comment=form.cleaned_data["comment"],
            total_amount=total,
        )
        OrderItem.objects.bulk_create(
            OrderItem(
                order=order,
                product=line.product,
                product_name=line.product.display_name or line.product.name,
                quantity=line.quantity,
                unit_price=line.unit_price,
                total_price=line.line_total,
            )
            for line in lines
        )
        event = OrderEvent.objects.create(
            order=order,
            event_type=OrderEvent.EventType.ORDER_CREATED,
            payload={"total_amount": str(total)},
        )
        transaction.on_commit(lambda: broadcast_order_event(event))
        transaction.on_commit(lambda: schedule_order_notification(order.id))

    basket.clear()

    context = build_product_list_context(request)
    context["order_success"] = True
    return render(request, "products/index.html", context)
