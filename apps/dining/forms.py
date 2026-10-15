from django import forms
from django.db.models import Q
from django.utils import timezone

from .models import Reservation, RestaurantTable


class RestaurantTableForm(forms.ModelForm):
    class Meta:
        model = RestaurantTable
        fields = ("table_number", "capacity", "sort_order", "is_active")
        widgets = {
            "table_number": forms.TextInput(attrs={"maxlength": 20, "placeholder": "e.g. 1 or Patio A"}),
            "capacity": forms.NumberInput(attrs={"min": 1, "step": 1}),
            "sort_order": forms.NumberInput(attrs={"min": 0, "step": 1}),
        }

    def clean_table_number(self):
        return self.cleaned_data["table_number"].strip()

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and not cleaned.get("is_active", True):
            if self.instance.status == RestaurantTable.Status.RESERVED:
                self.add_error("is_active", "Release this table’s reservation before deactivating it.")
            if self.instance.orders.filter(order_type="DINE_IN", status="OPEN").exists():
                self.add_error("is_active", "This table has an active dine-in order and cannot be deactivated yet.")
            if self.instance.reservations.filter(status__in=(Reservation.Status.BOOKED, Reservation.Status.SEATED)).filter(
                Q(status=Reservation.Status.SEATED)
                | Q(status=Reservation.Status.BOOKED, reserved_for__gte=timezone.now())
            ).exists():
                self.add_error("is_active", "This table has a current or upcoming reservation and cannot be deactivated.")
        return cleaned
