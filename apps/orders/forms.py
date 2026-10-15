from django import forms
from django.db.models import Exists, OuterRef

from apps.dining.models import RestaurantTable

from .models import Order, OrderItem

MAX_ORDER_ITEM_QUANTITY = 99


class StartOrderForm(forms.Form):
    order_type = forms.ChoiceField(choices=Order.Type.choices, label="Service type")
    table = forms.ModelChoiceField(queryset=RestaurantTable.objects.none(), required=False, empty_label="Assign a table later")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_order = Order.objects.filter(
            table_id=OuterRef("pk"),
            order_type=Order.Type.DINE_IN,
            status=Order.Status.OPEN,
        )
        self.fields["table"].queryset = RestaurantTable.objects.filter(
            is_active=True,
            status=RestaurantTable.Status.AVAILABLE,
        ).annotate(has_active_order=Exists(active_order)).filter(has_active_order=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("order_type") == Order.Type.TAKEAWAY and cleaned.get("table"):
            self.add_error("table", "Takeaway orders cannot be assigned to a dining table.")
        return cleaned


class AddOrderItemForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, max_value=MAX_ORDER_ITEM_QUANTITY, initial=1)
    notes = forms.CharField(required=False, max_length=300, widget=forms.TextInput(attrs={"placeholder": "Optional kitchen note"}))

    def clean_notes(self):
        return self.cleaned_data["notes"].strip()


class QuantityForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, max_value=MAX_ORDER_ITEM_QUANTITY)


class OrderNotesForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ("notes",)
        widgets = {"notes": forms.Textarea(attrs={"rows": 2, "maxlength": 500, "placeholder": "Optional order note"})}

    def clean_notes(self):
        return self.cleaned_data["notes"].strip()
