import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.dining.models import RestaurantTable
from apps.menu.models import MenuItem


class Order(models.Model):
    class Type(models.TextChoices):
        DINE_IN = "DINE_IN", "Dine in"
        TAKEAWAY = "TAKEAWAY", "Takeaway"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class KitchenStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        READY = "READY", "Ready"
        SERVED = "SERVED", "Served"

    public_reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    order_type = models.CharField(max_length=12, choices=Type.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True)
    kitchen_status = models.CharField(
        max_length=12,
        choices=KitchenStatus.choices,
        default=KitchenStatus.PENDING,
        db_index=True,
    )
    table = models.ForeignKey(
        RestaurantTable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
    )
    notes = models.CharField(max_length=500, blank=True)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="opened_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("kitchen_status", "created_at")),
        ]

    def __str__(self):
        return f"{self.order_type} order {self.public_reference}"


class OrderItem(models.Model):
    class KitchenStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        READY = "READY", "Ready"
        SERVED = "SERVED", "Served"
        CANCELLED = "CANCELLED", "Cancelled"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="order_items")
    item_name_snapshot = models.CharField(max_length=140)
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    notes = models.CharField(max_length=300, blank=True)
    kitchen_status = models.CharField(
        max_length=12,
        choices=KitchenStatus.choices,
        default=KitchenStatus.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="order_item_quantity_positive"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="order_item_price_nonnegative"),
        ]
        indexes = [models.Index(fields=("order", "kitchen_status"))]

    @property
    def line_subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.item_name_snapshot}"
