from decimal import Decimal

from django import forms

class FinalizeInvoiceForm(forms.Form):
    discount_amount = forms.DecimalField(
        label="Order discount (₹)",
        min_value=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
        initial=Decimal("0.00"),
        required=True,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01", "inputmode": "decimal"}),
    )

    def __init__(self, *args, subtotal=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.subtotal = subtotal

    def clean_discount_amount(self):
        discount = self.cleaned_data["discount_amount"]
        if self.subtotal is not None and discount > self.subtotal:
            raise forms.ValidationError("Discount cannot be greater than the order subtotal.")
        return discount
