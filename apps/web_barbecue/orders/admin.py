from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("product_name", "quantity", "unit_price", "total_price")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer_name",
        "phone",
        "total_amount",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("customer_name", "phone", "id")
    readonly_fields = (
        "id",
        "customer_name",
        "phone",
        "address",
        "comment",
        "total_amount",
        "created_at",
        "updated_at",
    )
    fields = (
        "id",
        "customer_name",
        "phone",
        "address",
        "comment",
        "status",
        "total_amount",
        "created_at",
        "updated_at",
    )
    inlines = [OrderItemInline]

    def has_add_permission(self, request):
        # Orders only ever arrive through the public checkout flow.
        return False
