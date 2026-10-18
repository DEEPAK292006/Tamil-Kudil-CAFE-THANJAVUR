from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit.models import AuditRecord
from apps.orders.models import Order

from .forms import RestaurantTableForm
from .models import Reservation, RestaurantTable
from .permissions import table_manager_required, table_service_required
from .services import assign_dine_in_order, set_table_reserved


@table_service_required
def table_list(request):
    tables = list(RestaurantTable.objects.all())
    table_ids = [table.pk for table in tables]
    active_orders = Order.objects.filter(
        table_id__in=table_ids,
        order_type=Order.Type.DINE_IN,
        status=Order.Status.OPEN,
    ).order_by("created_at")
    active_order_by_table = {}
    for order in active_orders:
        active_order_by_table.setdefault(order.table_id, order)

    for table in tables:
        table.active_order = active_order_by_table.get(table.pk)
        table.current_status = (
            RestaurantTable.Status.OCCUPIED if table.active_order else
            RestaurantTable.Status.RESERVED if table.status == RestaurantTable.Status.RESERVED else
            RestaurantTable.Status.AVAILABLE
        )
        table.can_delete = not table.orders.exists() and not table.reservations.exists()

    assignable_orders = Order.objects.filter(
        order_type=Order.Type.DINE_IN,
        status=Order.Status.OPEN,
        table__isnull=True,
    ).order_by("created_at")
    return render(request, "dining/table_list.html", {
        "tables": tables,
        "assignable_orders": assignable_orders,
        "can_manage_tables": request.user.is_superuser or request.user.role in {"ADMIN", "MANAGER"},
    })


@table_manager_required
def table_create(request):
    return _table_form(request)


@table_manager_required
def table_edit(request, pk):
    table = get_object_or_404(RestaurantTable, pk=pk)
    return _table_form(request, table)


@table_manager_required
@require_POST
def table_delete(request, pk):
    with transaction.atomic():
        table = get_object_or_404(RestaurantTable.objects.select_for_update(), pk=pk)
        if table.orders.exists() or table.reservations.exists():
            messages.error(request, "This table is linked to order or reservation history. Rename or deactivate it to keep that history.")
            return redirect("dining:table_list")
        label = table.table_number
        AuditRecord.objects.create(
            actor=request.user,
            action="restaurant_table_deleted",
            object_type=RestaurantTable._meta.label,
            object_id=str(table.pk),
            changes={"table_number": table.table_number, "capacity": table.capacity, "is_active": table.is_active},
        )
        table.delete()
    messages.success(request, f"Table {label} deleted.")
    return redirect("dining:table_list")


def _table_form(request, table=None):
    creating = table is None
    if request.method == "POST":
        saved = None
        try:
            with transaction.atomic():
                if table:
                    table = get_object_or_404(RestaurantTable.objects.select_for_update(), pk=table.pk)
                form = RestaurantTableForm(request.POST, instance=table)
                if form.is_valid():
                    before = {"table_number": table.table_number, "capacity": table.capacity, "is_active": table.is_active} if table else {}
                    saved = form.save()
                    after = {"table_number": saved.table_number, "capacity": saved.capacity, "is_active": saved.is_active}
                    AuditRecord.objects.create(
                        actor=request.user,
                        action="restaurant_table_created" if creating else "restaurant_table_updated",
                        object_type=RestaurantTable._meta.label,
                        object_id=str(saved.pk),
                        changes={"before": before, "after": after},
                    )
                else:
                    saved = None
        except IntegrityError:
            form.add_error("table_number", "A table with this number already exists.")
        if saved:
            messages.success(request, f'Table {saved.table_number} {"added" if creating else "updated"}.')
            return redirect("dining:table_list")
    else:
        form = RestaurantTableForm(instance=table)
    return render(request, "dining/table_form.html", {"form": form, "table": table, "creating": creating})


@table_service_required
@require_POST
def table_reservation_toggle(request, pk):
    reserved = request.POST.get("action") == "reserve"
    try:
        table = set_table_reserved(table_id=pk, reserved=reserved, actor=request.user)
    except (RestaurantTable.DoesNotExist, ValidationError) as exc:
        if isinstance(exc, RestaurantTable.DoesNotExist):
            messages.error(request, "That table no longer exists.")
        else:
            messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, f'Table {table.table_number} is now {"reserved" if reserved else "available for seating"}.')
    return redirect("dining:table_list")


@table_service_required
@require_POST
def table_assign_order(request, pk):
    try:
        order = assign_dine_in_order(order_id=request.POST.get("order_id"), table_id=pk, actor=request.user)
    except (Order.DoesNotExist, RestaurantTable.DoesNotExist, ValidationError, ValueError, TypeError) as exc:
        if isinstance(exc, ValidationError):
            error = "; ".join(exc.messages)
        elif isinstance(exc, (ValueError, TypeError)):
            error = "Choose a valid unassigned dine-in order."
        else:
            error = "The order or table no longer exists. Refresh and try again."
        messages.error(request, error)
    else:
        messages.success(request, f"Order {str(order.public_reference)[:8]} assigned to table {order.table.table_number}.")
    return redirect("dining:table_list")
