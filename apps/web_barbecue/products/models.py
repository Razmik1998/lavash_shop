import uuid

from django.db import models


class Product(models.Model):
    """A barbecue product synchronized from the Admin application.

    Fields are split by ownership: admin_product_id/name/price/is_active
    are written only by the sync endpoint (see views.sync_products) and
    must never be edited from Django Admin, since the next sync would
    just overwrite manual changes. display_name/description/web_price/
    image/is_visible are owned by this app and must never be touched by
    sync.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin_product_id = models.UUIDField(unique=True, editable=False)

    # Admin-owned: set only by the sync endpoint.
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    # Web-owned: set only via Django Admin.
    display_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    web_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    image = models.ImageField(upload_to="products/", null=True, blank=True)
    is_visible = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.display_name or self.name

    def effective_price(self):
        return self.web_price if self.web_price is not None else self.price
