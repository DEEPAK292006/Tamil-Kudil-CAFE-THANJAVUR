from django import forms

from .models import MenuCategory, MenuItem


class MenuCategoryForm(forms.ModelForm):
    class Meta:
        model = MenuCategory
        fields = ("name", "description", "sort_order", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"maxlength": 100, "placeholder": "e.g. Tiffin"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class MenuItemForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tax_configuration"].queryset = self.fields["tax_configuration"].queryset.filter(is_active=True)
        self.fields["tax_configuration"].required = False
        self.fields["tax_configuration"].empty_label = "Not configured"

    class Meta:
        model = MenuItem
        fields = ("category", "name", "description", "price", "tax_configuration", "sort_order", "is_available")
        widgets = {
            "name": forms.TextInput(attrs={"maxlength": 140, "placeholder": "Item name"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional description"}),
            "price": forms.NumberInput(attrs={"min": "0", "step": "0.01", "inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = MenuCategory.objects.filter(is_active=True)

    def clean_name(self):
        return self.cleaned_data["name"].strip()
