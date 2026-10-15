from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditRecord
from apps.dining.models import RestaurantTable
from apps.menu.models import MenuItem

from .forms import MAX_ORDER_ITEM_QUANTITY
from .models import Order, OrderItem


@transaction.atomic
def create_open_order(*, order_type, table_id, actor):
    table = None
    if order_type == Order.Type.DINE_IN and table_id:
        table = RestaurantTable.objects.select_for_update().get(pk=table_id)
        if not table.is_active:
            raise ValidationError("This table is inactive.")
        if table.status == RestaurantTable.Status.RESERVED:
            raise ValidationError("This table is reserved.")
        if Order.objects.filter(table=table, order_type=Order.Type.DINE_IN, status=Order.Status.OPEN).exists():
            raise ValidationError("This table already has an active dine-in order.")
    elif order_type == Order.Type.TAKEAWAY:
        if table_id:
            raise ValidationError("Takeaway orders cannot be assigned to a table.")
    elif order_type != Order.Type.DINE_IN:
        raise ValidationError("Choose dine-in or takeaway.")

    order = Order.objects.create(order_type=order_type, table=table, opened_by=actor)
    AuditRecord.objects.create(
        actor=actor,
        action="order_created",
        object_type=Order._meta.label,
        object_id=str(order.pk),
        changes={"order_type": order_type, "table": table.table_number if table else None},
    )
    return order


@transaction.atomic
def add_menu_item_to_order(*, order_id, menu_item_id, quantity, notes, actor):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.OPEN:
        raise ValidationError("This order is no longer open.")
    if not isinstance(quantity, int) or not 1 <= quantity <= MAX_ORDER_ITEM_QUANTITY:
        raise ValidationError(f"Quantity must be between 1 and {MAX_ORDER_ITEM_QUANTITY}.")
    menu_item = MenuItem.objects.select_for_update().select_related("category").get(pk=menu_item_id)
    if not menu_item.is_available or not menu_item.category.is_active:
        raise ValidationError("This menu item is currently unavailable.")
    line = OrderItem.objects.create(
        order=order,
        menu_item=menu_item,
        item_name_snapshot=menu_item.name,
        unit_price=menu_item.price,
        quantity=quantity,
        notes=notes.strip(),
    )
    AuditRecord.objects.create(
        actor=actor,
        action="order_item_added",
        object_type=OrderItem._meta.label,
        object_id=str(line.pk),
        changes={"order_id": order.pk, "name": line.item_name_snapshot, "price": str(line.unit_price), "quantity": quantity},
    )
    return line


@transaction.atomic
def update_order_item_quantity(*, order_id, line_id, quantity, actor):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.OPEN:
        raise ValidationError("This order is no longer open.")
    if not isinstance(quantity, int) or not 1 <= quantity <= MAX_ORDER_ITEM_QUANTITY:
        raise ValidationError(f"Quantity must be between 1 and {MAX_ORDER_ITEM_QUANTITY}.")
    line = OrderItem.objects.select_for_update().get(pk=line_id, order=order)
    old = line.quantity
    if old == quantity:
        return line
    line.quantity = quantity
    line.save(update_fields=("quantity",))
    AuditRecord.objects.create(
        actor=actor,
        action="order_item_quantity_changed",
        object_type=OrderItem._meta.label,
        object_id=str(line.pk),
        changes={"quantity": {"before": old, "after": quantity}, "order_id": order.pk},
    )
    return line


@transaction.atomic
def remove_order_item(*, order_id, line_id, actor):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.OPEN:
        raise ValidationError("Items can only be removed from an open order.")
    line = OrderItem.objects.select_for_update().get(pk=line_id, order=order)
    snapshot = {"name": line.item_name_snapshot, "price": str(line.unit_price), "quantity": line.quantity, "order_id": order.pk}
    line.delete()
    AuditRecord.objects.create(
        actor=actor,
        action="order_item_removed",
        object_type=OrderItem._meta.label,
        object_id=str(line_id),
        changes=snapshot,
    )


@transaction.atomic
def update_order_notes(*, order_id, notes, actor):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.OPEN:
        raise ValidationError("This order is no longer open.")
    old = order.notes
    order.notes = notes.strip()
    order.save(update_fields=("notes", "updated_at"))
    if old != order.notes:
        AuditRecord.objects.create(
            actor=actor,
            action="order_notes_changed",
            object_type=Order._meta.label,
            object_id=str(order.pk),
            changes={"notes": {"before": old, "after": order.notes}},
        )
    return order


@transaction.atomic
def cancel_open_order(*, order_id, actor):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.OPEN:
        raise ValidationError("Only open orders can be cancelled.")
    order.status = Order.Status.CANCELLED
    order.save(update_fields=("status", "updated_at"))
    AuditRecord.objects.create(
        actor=actor,
        action="order_cancelled",
        object_type=Order._meta.label,
        object_id=str(order.pk),
        changes={"status": {"before": Order.Status.OPEN, "after": Order.Status.CANCELLED}},
    )
    return order


def order_subtotal(order):
    """Preview only; billing will perform authoritative invoice calculations in Step 9."""
    return sum((line.line_subtotal for line in order.items.all()), Decimal("0.00"))
