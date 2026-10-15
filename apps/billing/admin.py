from django.contrib import admin

from .models import BusinessTaxProfile, Invoice, InvoiceLine, Payment, TaxConfiguration


@admin.register(TaxConfiguration)
class TaxConfigurationAdmin(admin.ModelAdmin):
    list_display = ("name", "treatment", "classification_code", "rate_percent", "price_mode", "is_active")
    list_filter = ("treatment", "price_mode", "is_active")
    search_fields = ("name", "classification_code")


@admin.register(BusinessTaxProfile)
class BusinessTaxProfileAdmin(admin.ModelAdmin):
    list_display = ("registration_status", "supplier_state_code", "premises_type", "accountant_confirmed", "updated_at")

    def has_add_permission(self, request):
        return not BusinessTaxProfile.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Invoice)
admin.site.register(InvoiceLine)
admin.site.register(Payment)
