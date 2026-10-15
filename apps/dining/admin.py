from django.contrib import admin

from .models import Reservation, RestaurantTable


@admin.register(RestaurantTable)
class RestaurantTableAdmin(admin.ModelAdmin):
    list_display = ("table_number", "capacity", "status", "is_active", "sort_order")
    list_filter = ("status", "is_active")
    search_fields = ("table_number",)
    ordering = ("sort_order", "table_number")
    readonly_fields = ("status",)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("guest_name", "table", "party_size", "reserved_for", "status")
    list_filter = ("status", "reserved_for")
    search_fields = ("guest_name", "contact_phone", "table__table_number")
    date_hierarchy = "reserved_for"
