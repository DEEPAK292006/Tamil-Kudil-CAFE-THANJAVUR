from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
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
    sales_today = Invoice.objects.filter(
        status=Invoice.Status.ISSUED,
        issued_at__date=today,
    ).aggregate(count=Count("pk"), total=Sum("total_amount"))

    recent_orders = list(
        Order.objects.all()
        .select_related("table")
        .prefetch_related("items")[:5]
    )
    for order in recent_orders:
        order.subtotal_preview = order_subtotal(order)

    return render(request, "dashboard/index.html", {
        "today": today,
        "sales_count": sales_today["count"],
        "sales_total": sales_today["total"] or 0,
        "open_order_count": Order.objects.filter(status=Order.Status.OPEN).count(),
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
