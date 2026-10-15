from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "display_name", "role", "is_active", "is_staff")
    list_filter = (*DjangoUserAdmin.list_filter, "role")
    fieldsets = (*DjangoUserAdmin.fieldsets, ("Café staff", {"fields": ("display_name", "phone", "role")}))
    add_fieldsets = (*DjangoUserAdmin.add_fieldsets, ("Café staff", {"fields": ("display_name", "phone", "role")}))
