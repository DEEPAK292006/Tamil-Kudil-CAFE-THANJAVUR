from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class RestaurantTable(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        OCCUPIED = "OCCUPIED", "Occupied"
        RESERVED = "RESERVED", "Reserved"

    table_number = models.CharField(max_length=20, unique=True)
    capacity = models.PositiveSmallIntegerField(default=2, validators=[MinValueValidator(1)])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.AVAILABLE)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "table_number")
        constraints = [
            models.CheckConstraint(condition=Q(capacity__gte=1), name="restaurant_table_capacity_positive"),
        ]

    def __str__(self):
        return f"Table {self.table_number}"


class Reservation(models.Model):
    class Status(models.TextChoices):
        BOOKED = "BOOKED", "Booked"
        SEATED = "SEATED", "Seated"
        CANCELLED = "CANCELLED", "Cancelled"
        NO_SHOW = "NO_SHOW", "No show"

    table = models.ForeignKey(RestaurantTable, on_delete=models.PROTECT, related_name="reservations")
    guest_name = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=24, blank=True)
    party_size = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    reserved_for = models.DateTimeField(db_index=True)
    notes = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.BOOKED)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_reservations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("reserved_for", "table__table_number")
        indexes = [models.Index(fields=("table", "status", "reserved_for"))]

    def __str__(self):
        label = self.guest_name or "Guest"
        return f"{label} - Table {self.table.table_number} at {self.reserved_for:%Y-%m-%d %H:%M}"
