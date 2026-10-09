import uuid

from django.db import models

from products.models import Product


class Order(models.Model):
    """A customer order submitted from the public storefront.

    total_amount is always computed server-side from the OrderItem
    snapshots at submission time (see views.checkout_submit) - the
    browser's computed total is never trusted.

    Status model (see migration 0002 for the reconciliation from the
    previous NEW/CONFIRMED/COMPLETED/CANCELLED choices): this is the
    *business* status the Desktop Admin's Online Selling page acts on.
    PENDING orders are awaiting an admin decision; CONFIRMED orders are
    converted into a Sale on the Admin side; REJECTED orders are a
    terminal negative outcome. Sync status (has the event reached
    Admin?) and sale-conversion status (has a Sale been created?) are
    tracked entirely on the Admin side per the spec's three-way status
    separation - Django only ever owns this one business-status field.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Սպասման մեջ"
        CONFIRMED = "CONFIRMED", "Հաստատված"
        REJECTED = "REJECTED", "Մերժված"

    class ActionSource(models.TextChoices):
        ADMIN_PANEL = "ADMIN_PANEL", "Admin Panel"
        TELEGRAM = "TELEGRAM", "Telegram"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    customer_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32)
    address = models.TextField()
    comment = models.TextField(blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.CharField(max_length=255, blank=True)
    confirmation_source = models.CharField(
        max_length=20, choices=ActionSource.choices, blank=True
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.CharField(max_length=255, blank=True)
    rejection_reason = models.TextField(blank=True)
    rejection_source = models.CharField(
        max_length=20, choices=ActionSource.choices, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order {self.id} ({self.customer_name})"


class OrderItem(models.Model):
    """A line item within an Order.

    product_name/unit_price are a snapshot taken at order time and must
    never be re-derived from the live Product - product prices/names can
    change later, but historical orders must keep showing what was
    actually charged.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.SET_NULL
    )

    product_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.product_name} x{self.quantity}"


class OrderStatusHistory(models.Model):
    """An audit trail row for every business-status transition.

    Written in the same transaction as the OrderEvent for that
    transition (see admin_api.py) so the two never drift apart.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order, related_name="status_history", on_delete=models.CASCADE
    )
    from_status = models.CharField(max_length=20, choices=Order.Status.choices)
    to_status = models.CharField(max_length=20, choices=Order.Status.choices)
    # The Desktop Admin device (or terminal) that performed the
    # transition, e.g. a machine/session identifier - never a display
    # name or credential, so this is safe to store and to log.
    actor_device_id = models.CharField(max_length=255)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "order status histories"

    def __str__(self) -> str:
        return f"{self.order_id}: {self.from_status} -> {self.to_status}"


class OrderEvent(models.Model):
    """Append-only sync log consumed by the Desktop Admin's SyncService.

    Never updated or deleted once written - both the WebSocket
    broadcast and the GET /api/admin/orders/sync/ HTTP-recovery path
    read from this table, and its auto-incrementing `id` is the
    `event_id` / `after_event_id` cursor the Admin side tracks.
    """

    class EventType(models.TextChoices):
        ORDER_CREATED = "order.created", "Order created"
        ORDER_CONFIRMED = "order.confirmed", "Order confirmed"
        ORDER_REJECTED = "order.rejected", "Order rejected"
        ORDER_UPDATED = "order.updated", "Order updated"

    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(Order, related_name="events", on_delete=models.CASCADE)
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    # A snapshot of what changed, e.g. {"from_status": ..., "to_status":
    # ..., "device_id": ..., "reason": ...} - deliberately small; the
    # full current order state is read live (not from this snapshot)
    # whenever a consumer needs to reconstruct state, so payload never
    # goes stale.
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"#{self.id} {self.event_type} ({self.order_id})"


class OrderEventAcknowledgement(models.Model):
    """Minimal ack-tracking row: which device has confirmed receipt of
    which event, via POST /api/admin/orders/<id>/acknowledge/.

    Exactly one Desktop Admin instance is in scope for this task (see
    task-plan.md), so a simple (event, device_id) uniqueness constraint
    is enough to make acknowledging idempotent - no need for a richer
    per-device cursor table.
    """

    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(
        OrderEvent, related_name="acknowledgements", on_delete=models.CASCADE
    )
    device_id = models.CharField(max_length=255)
    acknowledged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "device_id"], name="unique_ack_per_device"
            )
        ]

    def __str__(self) -> str:
        return f"ack event#{self.event_id} by {self.device_id}"
