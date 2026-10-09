"""Plain-dict serialization for the admin-facing order API/WebSocket.

No DRF in this app (see products/auth.py's docstring / task-plan.md) -
these are hand-written dict builders, matching the existing
products/views.sync_products style.
"""
from .models import Order, OrderItem


def serialize_order_item(item: OrderItem) -> dict:
    return {
        "id": str(item.id),
        "product_id": (
            str(item.product.admin_product_id)
            if item.product is not None
            else None
        ),
        "product_name": item.product_name,
        "unit": "piece",
        "quantity": item.quantity,
        "unit_price": str(item.unit_price),
        "subtotal": str(item.total_price),
    }


def serialize_order(order: Order) -> dict:
    """Full order detail: customer, address, phone, items, financials -
    per spec section 4, everything the Online Selling detail view needs
    to render without a follow-up request."""
    return {
        "id": str(order.id),
        "order_id": str(order.id),
        "order_number": str(order.id),
        "status": order.status,
        "customer_name": order.customer_name,
        "phone": order.phone,
        "customer_phone": order.phone,
        "address": order.address,
        "customer_address": order.address,
        "comment": order.comment,
        "total_amount": str(order.total_amount),
        "subtotal": str(order.total_amount),
        "delivery_fee": "0",
        "discount": "0",
        "total": str(order.total_amount),
        "order_date": order.created_at.isoformat(),
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
        "confirmed_by": order.confirmed_by,
        "confirmation_source": order.confirmation_source,
        "rejected_at": order.rejected_at.isoformat() if order.rejected_at else None,
        "rejected_by": order.rejected_by,
        "rejection_reason": order.rejection_reason,
        "rejection_source": order.rejection_source,
        "items": [serialize_order_item(item) for item in order.items.all()],
    }
