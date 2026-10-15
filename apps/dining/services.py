from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.models import AuditRecord
from apps.orders.models import Order

from .models import RestaurantTable


@transaction.atomic
def assign_dine_in_order(*, order_id, table_id, actor):
    """Assign an unassigned open dine-in order while serializing on the table row."""
    table = RestaurantTable.objects.select_for_update().get(pk=table_id)
    order = Order.objects.select_for_update().get(pk=order_id)

    if not table.is_active:
        raise ValidationError("This table is inactive.")
    if order.order_type != Order.Type.DINE_IN or order.status != Order.Status.OPEN:
        raise ValidationError("Only an open dine-in order can be assigned to a table.")
    if order.table_id is not None:
        raise ValidationError("This order is already assigned to a table.")
    if table.status == RestaurantTable.Status.RESERVED:
        raise ValidationError("This table is reserved and cannot be assigned to a walk-in order.")
    if Order.objects.filter(
        table=table,
        order_type=Order.Type.DINE_IN,
        status=Order.Status.OPEN,
    ).exists():
        raise ValidationError("This table already has an active dine-in order.")

    order.table = table
    order.save(update_fields=("table", "updated_at"))
    AuditRecord.objects.create(
        actor=actor,
        action="dine_in_order_table_assigned",
        object_type=Order._meta.label,
        object_id=str(order.pk),
        changes={"table": {"before": None, "after": table.table_number}},
    )
    return order


@transaction.atomic
def set_table_reserved(*, table_id, reserved, actor):
    table = RestaurantTable.objects.select_for_update().get(pk=table_id)
    if not table.is_active:
        raise ValidationError("An inactive table cannot be reserved or released.")
    if reserved and Order.objects.filter(
        table=table,
        order_type=Order.Type.DINE_IN,
        status=Order.Status.OPEN,
    ).exists():
        raise ValidationError("This table has an active order and cannot be reserved yet.")
    old = table.status
    new = RestaurantTable.Status.RESERVED if reserved else RestaurantTable.Status.AVAILABLE
    if old == new:
        return table
    table.status = new
    table.save(update_fields=("status",))
    AuditRecord.objects.create(
        actor=actor,
        action="restaurant_table_status_changed",
        object_type=RestaurantTable._meta.label,
        object_id=str(table.pk),
        changes={"status": {"before": old, "after": new}},
    )
    return table
