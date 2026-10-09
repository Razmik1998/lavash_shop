from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "price",
        "is_active",
        "display_name",
        "web_price",
        "is_visible",
        "updated_at",
    )
    list_filter = ("is_active", "is_visible")
    search_fields = ("name", "display_name", "admin_product_id")
    readonly_fields = (
        "admin_product_id",
        "name",
        "price",
        "is_active",
        "created_at",
        "updated_at",
    )
    fields = (
        "admin_product_id",
        "name",
        "price",
        "is_active",
        "display_name",
        "description",
        "web_price",
        "image",
        "is_visible",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        # Products only ever arrive via the sync endpoint (views.sync_products).
        return False
