from django.urls import path

from . import views

app_name = "menu"

urlpatterns = [
    path("", views.menu_list, name="list"),
    path("items/new/", views.item_create, name="item_create"),
    path("items/<int:pk>/edit/", views.item_edit, name="item_edit"),
    path("items/<int:pk>/availability/", views.item_availability, name="item_availability"),
    path("categories/new/", views.category_create, name="category_create"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/toggle/", views.category_toggle, name="category_toggle"),
]
