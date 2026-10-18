from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from apps.billing.models import Invoice
from apps.dining.models import RestaurantTable
from apps.menu.models import MenuCategory, MenuItem
from apps.orders.models import Order
from apps.orders.services import order_subtotal


@login_required
def dashboard(request):
    today = timezone.localdate()
    issued_invoices = Invoice.objects.filter(status=Invoice.Status.ISSUED)
    bill_totals = issued_invoices.aggregate(count=Count("pk"), total=Sum("total_amount"))
    order_totals = Order.objects.aggregate(
        count=Count("pk"),
        open_count=Count("pk", filter=Q(status=Order.Status.OPEN)),
        completed_count=Count("pk", filter=Q(status=Order.Status.COMPLETED)),
        cancelled_count=Count("pk", filter=Q(status=Order.Status.CANCELLED)),
    )

    recent_orders = list(
        Order.objects.all()
        .select_related("table", "invoice")
        .prefetch_related("items")[:5]
    )
    for order in recent_orders:
        order.subtotal_preview = order_subtotal(order)
        invoice = getattr(order, "invoice", None)
        order.has_issued_invoice = bool(invoice and invoice.status == Invoice.Status.ISSUED)
        order.display_total = invoice.total_amount if order.has_issued_invoice else order.subtotal_preview

    return render(request, "dashboard/index.html", {
        "today": today,
        "order_count": order_totals["count"],
        "open_order_count": order_totals["open_count"],
        "completed_order_count": order_totals["completed_count"],
        "cancelled_order_count": order_totals["cancelled_count"],
        "issued_bill_count": bill_totals["count"],
        "billed_total": bill_totals["total"] or 0,
        "recent_orders": recent_orders,
        "available_menu_count": MenuItem.objects.filter(
            is_available=True,
            category__is_active=True,
        ).count(),
        "active_table_count": RestaurantTable.objects.filter(is_active=True).count(),
        "active_category_count": MenuCategory.objects.filter(is_active=True).count(),
    })


def health(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "tamil-kudil-pos",
        }
    )
