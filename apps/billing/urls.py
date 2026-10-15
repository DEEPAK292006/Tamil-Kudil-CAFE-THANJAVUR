from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("orders/<int:order_id>/finalize/", views.finalize_order_view, name="finalize_order"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
]
