from django.urls import path

from . import views

app_name = "dining"

urlpatterns = [
    path("", views.table_list, name="table_list"),
    path("new/", views.table_create, name="table_create"),
    path("<int:pk>/edit/", views.table_edit, name="table_edit"),
    path("<int:pk>/delete/", views.table_delete, name="table_delete"),
    path("<int:pk>/reservation/", views.table_reservation_toggle, name="table_reservation_toggle"),
    path("<int:pk>/assign-order/", views.table_assign_order, name="table_assign_order"),
]
