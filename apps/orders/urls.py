from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.order_list, name="list"),
    path("new/", views.order_create, name="create"),
    path("<int:pk>/", views.order_detail, name="detail"),
    path("<int:pk>/items/<int:menu_item_id>/add/", views.order_item_add, name="item_add"),
    path("<int:pk>/lines/<int:line_id>/quantity/", views.order_item_quantity, name="item_quantity"),
    path("<int:pk>/lines/<int:line_id>/remove/", views.order_item_remove, name="item_remove"),
    path("<int:pk>/notes/", views.order_notes_save, name="notes_save"),
    path("<int:pk>/cancel/", views.order_cancel, name="cancel"),
    path("<int:pk>/delete/", views.order_delete, name="delete"),
]
