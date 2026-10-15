from django.contrib import admin

from .models import MenuCategory, MenuItem


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("sort_order", "name")


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "tax_configuration", "is_available", "updated_at")
    list_filter = ("category", "is_available")
    search_fields = ("name", "description", "category__name")
    ordering = ("category__sort_order", "sort_order", "name")
