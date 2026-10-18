from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.dining.models import RestaurantTable
from apps.menu.models import MenuCategory, MenuItem

from .forms import AddOrderItemForm, OrderNotesForm, QuantityForm, StartOrderForm
from .models import Order, OrderItem
from .permissions import order_manager_required, order_staff_required
from .services import (
    add_menu_item_to_order,
    cancel_open_order,
    create_open_order,
    delete_order_without_bill,
    order_subtotal,
    remove_order_item,
    update_order_item_quantity,
    update_order_notes,
)


def _handle_order_error(request, exc):
    if isinstance(exc, ValidationError):
        message = "; ".join(exc.messages)
    else:
        message = "The order or menu item no longer exists. Refresh the page and try again."
    messages.error(request, message)


@order_staff_required
def order_list(request):
    selected_status = request.GET.get("status", "all").upper()
    valid_statuses = {value for value, _label in Order.Status.choices}
    if selected_status not in valid_statuses | {"ALL"}:
        selected_status = "ALL"

    orders = Order.objects.select_related("table", "opened_by", "invoice").prefetch_related("items")
    if selected_status != "ALL":
        orders = orders.filter(status=selected_status)
    for order in orders:
        order.subtotal_preview = order_subtotal(order)
        invoice = getattr(order, "invoice", None)
        order.has_issued_invoice = bool(invoice and invoice.status == "ISSUED")
        order.display_total = invoice.total_amount if order.has_issued_invoice else order.subtotal_preview
    status_counts = {
        "ALL": Order.objects.count(),
        **{value: Order.objects.filter(status=value).count() for value in valid_statuses},
    }
    return render(request, "orders/order_list.html", {
        "orders": orders,
        "selected_status": selected_status,
        "status_counts": status_counts,
    })


@order_staff_required
def order_create(request):
    if request.method == "POST":
        form = StartOrderForm(request.POST)
        if form.is_valid():
            table = form.cleaned_data["table"]
            try:
                order = create_open_order(
                    order_type=form.cleaned_data["order_type"],
                    table_id=table.pk if table else None,
                    actor=request.user,
                )
            except (RestaurantTable.DoesNotExist, ValidationError) as exc:
                _handle_order_error(request, exc)
            else:
                messages.success(request, f"Order {str(order.public_reference)[:8]} started. Add items to save it.")
                return redirect("orders:detail", pk=order.pk)
    else:
        form = StartOrderForm(initial={"order_type": Order.Type.DINE_IN})
    return render(request, "orders/order_create.html", {"form": form})


@order_staff_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("table", "opened_by", "invoice").prefetch_related("items__menu_item"), pk=pk)
    categories = MenuCategory.objects.filter(is_active=True)
    query = request.GET.get("q", "").strip()
    selected_category = request.GET.get("category", "").strip()
    menu_items = MenuItem.objects.filter(is_available=True, category__is_active=True).select_related("category")
    if selected_category.isdigit():
        menu_items = menu_items.filter(category_id=int(selected_category))
    if query:
        menu_items = menu_items.filter(Q(name__icontains=query) | Q(category__name__icontains=query))
    lines = list(order.items.all())
    subtotal = sum((line.line_subtotal for line in lines), Decimal("0.00"))
    invoice = getattr(order, "invoice", None)
    has_issued_invoice = bool(invoice and invoice.status == "ISSUED")
    return render(request, "orders/order_detail.html", {
        "order": order,
        "lines": lines,
        "subtotal": subtotal,
        "display_total": invoice.total_amount if has_issued_invoice else subtotal,
        "has_issued_invoice": has_issued_invoice,
        "can_manage_orders": request.user.is_superuser or request.user.role in {"ADMIN", "MANAGER"},
        "can_delete_order": (request.user.is_superuser or request.user.role in {"ADMIN", "MANAGER"}) and invoice is None,
        "categories": categories,
        "menu_items": menu_items,
        "query": query,
        "selected_category": selected_category,
        "add_form": AddOrderItemForm(),
        "notes_form": OrderNotesForm(instance=order),
    })


@order_staff_required
@require_POST
def order_item_add(request, pk, menu_item_id):
    form = AddOrderItemForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a quantity from 1 to 99 and a valid item note.")
    else:
        try:
            line = add_menu_item_to_order(
                order_id=pk,
                menu_item_id=menu_item_id,
                quantity=form.cleaned_data["quantity"],
                notes=form.cleaned_data["notes"],
                actor=request.user,
            )
        except (Order.DoesNotExist, MenuItem.DoesNotExist, ValidationError) as exc:
            _handle_order_error(request, exc)
        else:
            messages.success(request, f"Added {line.quantity} × {line.item_name_snapshot}.")
    return redirect("orders:detail", pk=pk)


@order_staff_required
@require_POST
def order_item_quantity(request, pk, line_id):
    form = QuantityForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Quantity must be a whole number from 1 to 99.")
    else:
        try:
            update_order_item_quantity(order_id=pk, line_id=line_id, quantity=form.cleaned_data["quantity"], actor=request.user)
        except (Order.DoesNotExist, OrderItem.DoesNotExist, ValidationError) as exc:
            _handle_order_error(request, exc)
    return redirect("orders:detail", pk=pk)


@order_staff_required
@require_POST
def order_item_remove(request, pk, line_id):
    try:
        remove_order_item(order_id=pk, line_id=line_id, actor=request.user)
    except (Order.DoesNotExist, OrderItem.DoesNotExist, ValidationError) as exc:
        _handle_order_error(request, exc)
    else:
        messages.success(request, "Item removed from the open order.")
    return redirect("orders:detail", pk=pk)


@order_staff_required
@require_POST
def order_notes_save(request, pk):
    order = get_object_or_404(Order, pk=pk)
    form = OrderNotesForm(request.POST, instance=order)
    if form.is_valid():
        try:
            update_order_notes(order_id=pk, notes=form.cleaned_data["notes"], actor=request.user)
        except (Order.DoesNotExist, ValidationError) as exc:
            _handle_order_error(request, exc)
        else:
            messages.success(request, "Order note saved.")
    else:
        messages.error(request, "Order notes must be 500 characters or fewer.")
    return redirect("orders:detail", pk=pk)


@order_staff_required
@require_POST
def order_cancel(request, pk):
    try:
        cancel_open_order(order_id=pk, actor=request.user)
    except (Order.DoesNotExist, ValidationError) as exc:
        _handle_order_error(request, exc)
    else:
        messages.success(request, "Open order cancelled. Its dine-in table is available again.")
    return redirect("orders:list")


@order_manager_required
@require_POST
def order_delete(request, pk):
    try:
        reference = delete_order_without_bill(order_id=pk, actor=request.user)
    except (Order.DoesNotExist, ValidationError) as exc:
        _handle_order_error(request, exc)
    else:
        messages.success(request, f"Unbilled order {reference} was deleted.")
    return redirect("orders:list")


