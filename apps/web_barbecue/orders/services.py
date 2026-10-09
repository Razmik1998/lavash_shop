"""Canonical, transaction-safe order transitions.

Admin Panel and Telegram are transports only. This service owns lifecycle
validation, audit fields, history, and the durable sync event.
"""
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from .events import broadcast_order_event
from .models import Order, OrderEvent, OrderStatusHistory

MAX_REASON_LENGTH = 2000


class OrderTransitionError(Exception):
    """A requested transition cannot be applied to the current order."""


@dataclass(frozen=True)
class TransitionResult:
    order_id: str
    status: str
    changed: bool


def _validate_actor(actor: str) -> str:
    value = actor.strip()
    if not value or len(value) > 255:
        raise ValueError("actor must be a non-empty string of at most 255 characters")
    return value


def _record_transition(
    order: Order,
    *,
    actor: str,
    source: str,
    to_status: str,
    reason: str,
    event_type: str,
    now: datetime,
) -> None:
    from_status = order.status
    order.status = to_status
    if to_status == Order.Status.CONFIRMED:
        order.confirmed_at = now
        order.confirmed_by = actor
        order.confirmation_source = source
    else:
        order.rejected_at = now
        order.rejected_by = actor
        order.rejection_reason = reason
        order.rejection_source = source
    order.save(
        update_fields=[
            "status",
            "confirmed_at",
            "confirmed_by",
            "confirmation_source",
            "rejected_at",
            "rejected_by",
            "rejection_reason",
            "rejection_source",
            "updated_at",
        ]
    )
    OrderStatusHistory.objects.create(
        order=order,
        from_status=from_status,
        to_status=to_status,
        actor_device_id=actor,
        reason=reason,
    )
    event = OrderEvent.objects.create(
        order=order,
        event_type=event_type,
        payload={
            "from_status": from_status,
            "to_status": to_status,
            "actor": actor,
            "source": source,
            "reason": reason,
        },
    )
    transaction.on_commit(lambda: broadcast_order_event(event))


class OrderService:
    """Shared order application service for every processing interface."""

    @staticmethod
    def confirm_order(order_id, *, source: str, actor: str) -> TransitionResult:
        actor = _validate_actor(actor)
        if source not in Order.ActionSource.values:
            raise ValueError("invalid order action source")
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order_id)
            if order.status == Order.Status.CONFIRMED:
                return TransitionResult(str(order.id), order.status, False)
            if order.status != Order.Status.PENDING:
                raise OrderTransitionError(
                    f"cannot confirm an order in status {order.status}"
                )
            _record_transition(
                order,
                actor=actor,
                source=source,
                to_status=Order.Status.CONFIRMED,
                reason="",
                event_type=OrderEvent.EventType.ORDER_CONFIRMED,
                now=timezone.now(),
            )
        return TransitionResult(str(order.id), order.status, True)

    @staticmethod
    def reject_order(
        order_id, *, source: str, actor: str, reason: str
    ) -> TransitionResult:
        actor = _validate_actor(actor)
        if source not in Order.ActionSource.values:
            raise ValueError("invalid order action source")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("rejection reason is required")
        reason = reason.strip()
        if len(reason) > MAX_REASON_LENGTH:
            raise ValueError("rejection reason is too long")
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order_id)
            if order.status == Order.Status.REJECTED:
                return TransitionResult(str(order.id), order.status, False)
            if order.status != Order.Status.PENDING:
                raise OrderTransitionError(
                    f"cannot reject an order in status {order.status}"
                )
            _record_transition(
                order,
                actor=actor,
                source=source,
                to_status=Order.Status.REJECTED,
                reason=reason,
                event_type=OrderEvent.EventType.ORDER_REJECTED,
                now=timezone.now(),
            )
        return TransitionResult(str(order.id), order.status, True)
