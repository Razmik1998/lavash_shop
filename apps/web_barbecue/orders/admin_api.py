"""Admin-facing order sync API consumed by apps/admin's SyncService.

Every view here is authenticated the same way as
products.views.sync_products - the X-API-Key shared secret via
products.auth.require_api_key - and is CSRF-exempt for the same reason
(no session/cookie auth is ever used on this machine-to-machine path).

Each state-changing view validates its payload, checks the order's
*current* status before transitioning it, and writes the
OrderStatusHistory + OrderEvent rows in the same transaction as the
status change, per task-plan.md's non-negotiable list. Confirm/reject
are idempotent: calling either again on an order already in that
terminal state returns success without a second transition or event,
so a duplicate/retried request from the Admin side (e.g. after a
network blip) can never double-fire.
"""
import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from products.auth import require_api_key

from .models import Order, OrderEvent, OrderEventAcknowledgement
from .serializers import serialize_order
from .services import OrderService, OrderTransitionError

logger = logging.getLogger(__name__)

MAX_REASON_LENGTH = 2000


def _parse_json_body(request) -> dict | None:
    try:
        payload = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


@require_GET
@require_api_key
def order_detail(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    return JsonResponse(serialize_order(order))


@csrf_exempt
@require_POST
@require_api_key
def order_confirm(request, order_id):
    payload = _parse_json_body(request)
    if payload is None:
        return JsonResponse({"error": "invalid_json"}, status=400)

    device_id = payload.get("device_id")
    if not device_id or not isinstance(device_id, str):
        return JsonResponse(
            {"error": "invalid_payload", "detail": "device_id is required"},
            status=400,
        )

    try:
        result = OrderService.confirm_order(
            order_id, source=Order.ActionSource.ADMIN_PANEL, actor=device_id
        )
    except OrderTransitionError as exc:
        return JsonResponse(
            {"error": "invalid_transition", "detail": str(exc)}, status=409
        )
    logger.info("order_confirmed order_id=%s device_id=%s", order_id, device_id)
    return JsonResponse({"order_id": result.order_id, "status": result.status})


@csrf_exempt
@require_POST
@require_api_key
def order_reject(request, order_id):
    payload = _parse_json_body(request)
    if payload is None:
        return JsonResponse({"error": "invalid_json"}, status=400)

    device_id = payload.get("device_id")
    reason = payload.get("reason", "")
    if not device_id or not isinstance(device_id, str):
        return JsonResponse(
            {"error": "invalid_payload", "detail": "device_id is required"},
            status=400,
        )
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > MAX_REASON_LENGTH
    ):
        return JsonResponse(
            {"error": "invalid_payload", "detail": "reason must be a short string"},
            status=400,
        )

    try:
        result = OrderService.reject_order(
            order_id,
            source=Order.ActionSource.ADMIN_PANEL,
            actor=device_id,
            reason=reason,
        )
    except OrderTransitionError as exc:
        return JsonResponse(
            {"error": "invalid_transition", "detail": str(exc)}, status=409
        )
    except ValueError as exc:
        return JsonResponse(
            {"error": "invalid_payload", "detail": str(exc)}, status=400
        )
    logger.info("order_rejected order_id=%s device_id=%s", order_id, device_id)
    return JsonResponse({"order_id": result.order_id, "status": result.status})


@csrf_exempt
@require_POST
@require_api_key
def order_acknowledge(request, order_id):
    payload = _parse_json_body(request)
    if payload is None:
        return JsonResponse({"error": "invalid_json"}, status=400)

    device_id = payload.get("device_id")
    event_id = payload.get("event_id")
    if not device_id or not isinstance(device_id, str):
        return JsonResponse(
            {"error": "invalid_payload", "detail": "device_id is required"},
            status=400,
        )
    if not isinstance(event_id, int):
        return JsonResponse(
            {"error": "invalid_payload", "detail": "event_id must be an integer"},
            status=400,
        )

    event = get_object_or_404(OrderEvent, pk=event_id, order_id=order_id)
    OrderEventAcknowledgement.objects.get_or_create(
        event=event, device_id=device_id
    )
    logger.info(
        "order_event_acknowledged order_id=%s event_id=%s device_id=%s",
        order_id,
        event_id,
        device_id,
    )
    return JsonResponse({"acknowledged": True, "event_id": event_id})


@require_GET
@require_api_key
def order_sync(request):
    device_id = request.GET.get("device_id")
    if not device_id:
        return JsonResponse(
            {"error": "invalid_payload", "detail": "device_id is required"},
            status=400,
        )

    after_event_id_raw = request.GET.get("after_event_id", "0")
    try:
        after_event_id = int(after_event_id_raw)
    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "invalid_payload", "detail": "after_event_id must be an integer"},
            status=400,
        )

    events = (
        OrderEvent.objects.filter(id__gt=after_event_id)
        .select_related("order")
        .prefetch_related("order__items")
        .order_by("id")
    )
    return JsonResponse(
        {
            "events": [
                {
                    "event_id": event.id,
                    "event_type": event.event_type,
                    "order_id": str(event.order_id),
                    "payload": event.payload,
                    "order": serialize_order(event.order),
                    "created_at": event.created_at.isoformat(),
                }
                for event in events
            ]
        }
    )
