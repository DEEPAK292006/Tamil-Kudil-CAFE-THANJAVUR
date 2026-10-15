from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditRecord
from apps.dining.models import RestaurantTable
from apps.menu.models import MenuCategory, MenuItem
from .services import add_menu_item_to_order, cancel_open_order, create_open_order, remove_order_item, update_order_item_quantity
from .models import Order, OrderItem


class OrderModelTests(TestCase):
    def test_order_item_keeps_historical_name_and_price(self):
        user = get_user_model().objects.create_user(username="cashier", password="test-only-password")
        category = MenuCategory.objects.create(name="Tea")
        menu_item = MenuItem.objects.create(
            category=category,
            name="Ginger Tea",
            price=Decimal("20.00"),
        )
        order = Order.objects.create(order_type=Order.Type.TAKEAWAY, opened_by=user)
        line = OrderItem.objects.create(
            order=order,
            menu_item=menu_item,
            item_name_snapshot=menu_item.name,
            unit_price=menu_item.price,
            quantity=2,
        )

        menu_item.name = "Updated Ginger Tea"
        menu_item.price = Decimal("25.00")
        menu_item.save()
        line.refresh_from_db()

        self.assertEqual(line.item_name_snapshot, "Ginger Tea")
        self.assertEqual(line.unit_price, Decimal("20.00"))
        self.assertEqual(line.line_subtotal, Decimal("40.00"))


class OrderWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="counter", password="test-only-password", role="CASHIER")
        self.category = MenuCategory.objects.create(name="Tiffin")
        self.item = MenuItem.objects.create(category=self.category, name="Ghee Pongal", price=Decimal("85.00"))
        self.unavailable_item = MenuItem.objects.create(category=self.category, name="Sold Out Idli", price=Decimal("35.00"), is_available=False)
        self.table = RestaurantTable.objects.create(table_number="A1", capacity=4)
        self.client.force_login(self.user)

    def test_start_order_supports_takeaway_and_dine_in_table_selection(self):
        response = self.client.post(reverse("orders:create"), {"order_type": Order.Type.TAKEAWAY})
        self.assertEqual(response.status_code, 302)
        takeaway = Order.objects.get(order_type=Order.Type.TAKEAWAY)
        self.assertIsNone(takeaway.table_id)

        response = self.client.post(reverse("orders:create"), {"order_type": Order.Type.DINE_IN, "table": self.table.pk})
        dine_in = Order.objects.get(order_type=Order.Type.DINE_IN)
        self.assertRedirects(response, reverse("orders:detail", args=(dine_in.pk,)))
        self.assertEqual(dine_in.table_id, self.table.pk)

    def test_cashier_can_add_item_and_order_detail_shows_preview_total(self):
        order = create_open_order(order_type=Order.Type.TAKEAWAY, table_id=None, actor=self.user)
        response = self.client.post(reverse("orders:item_add", args=(order.pk, self.item.pk)), {
            "quantity": "2", "notes": "No chilli",
        })
        self.assertRedirects(response, reverse("orders:detail", args=(order.pk,)))
        line = OrderItem.objects.get(order=order)
        self.assertEqual(line.item_name_snapshot, "Ghee Pongal")
        self.assertEqual(line.unit_price, Decimal("85.00"))
        self.assertEqual(line.quantity, 2)
        self.assertEqual(line.notes, "No chilli")
        self.assertTrue(AuditRecord.objects.filter(action="order_item_added", object_id=str(line.pk)).exists())

        response = self.client.get(reverse("orders:detail", args=(order.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "₹170.00")

    def test_unavailable_items_and_invalid_quantities_are_rejected(self):
        order = create_open_order(order_type=Order.Type.TAKEAWAY, table_id=None, actor=self.user)
        response = self.client.post(reverse("orders:item_add", args=(order.pk, self.unavailable_item.pk)), {"quantity": "1"})
        self.assertRedirects(response, reverse("orders:detail", args=(order.pk,)))
        self.assertFalse(OrderItem.objects.filter(order=order).exists())

        response = self.client.post(reverse("orders:item_add", args=(order.pk, self.item.pk)), {"quantity": "0"})
        self.assertFalse(OrderItem.objects.filter(order=order).exists())

    def test_quantity_update_and_removal_are_limited_to_open_order(self):
        order = create_open_order(order_type=Order.Type.TAKEAWAY, table_id=None, actor=self.user)
        line = add_menu_item_to_order(order_id=order.pk, menu_item_id=self.item.pk, quantity=1, notes="", actor=self.user)
        response = self.client.post(reverse("orders:item_quantity", args=(order.pk, line.pk)), {"quantity": "3"})
        self.assertRedirects(response, reverse("orders:detail", args=(order.pk,)))
        line.refresh_from_db()
        self.assertEqual(line.quantity, 3)
        self.assertEqual(line.line_subtotal, Decimal("255.00"))

        response = self.client.post(reverse("orders:item_remove", args=(order.pk, line.pk)))
        self.assertRedirects(response, reverse("orders:detail", args=(order.pk,)))
        self.assertFalse(OrderItem.objects.filter(pk=line.pk).exists())
        self.assertTrue(AuditRecord.objects.filter(action="order_item_removed", object_id=str(line.pk)).exists())

    def test_order_level_note_is_saved_and_audited(self):
        order = create_open_order(order_type=Order.Type.TAKEAWAY, table_id=None, actor=self.user)
        response = self.client.post(reverse("orders:notes_save", args=(order.pk,)), {"notes": "Pack separately"})
        self.assertRedirects(response, reverse("orders:detail", args=(order.pk,)))
        order.refresh_from_db()
        self.assertEqual(order.notes, "Pack separately")
        self.assertTrue(AuditRecord.objects.filter(actor=self.user, action="order_notes_changed", object_id=str(order.pk)).exists())

    def test_table_cannot_have_two_open_dine_in_orders_and_cancellation_releases_it(self):
        first = create_open_order(order_type=Order.Type.DINE_IN, table_id=self.table.pk, actor=self.user)
        with self.assertRaisesMessage(ValidationError, "This table already has an active dine-in order."):
            create_open_order(order_type=Order.Type.DINE_IN, table_id=self.table.pk, actor=self.user)

        second = create_open_order(order_type=Order.Type.DINE_IN, table_id=None, actor=self.user)
        response = self.client.post(reverse("dining:table_assign_order", args=(self.table.pk,)), {"order_id": second.pk})
        self.assertRedirects(response, reverse("dining:table_list"))
        second.refresh_from_db()
        self.assertIsNone(second.table_id)

        response = self.client.post(reverse("orders:cancel", args=(first.pk,)))
        self.assertRedirects(response, reverse("orders:list"))
        first.refresh_from_db()
        self.assertEqual(first.status, Order.Status.CANCELLED)
        self.assertEqual(first.table_id, self.table.pk)

        next_order = create_open_order(order_type=Order.Type.DINE_IN, table_id=self.table.pk, actor=self.user)
        self.assertEqual(next_order.table_id, self.table.pk)

    def test_kitchen_role_cannot_open_cashier_order_workspace(self):
        kitchen = get_user_model().objects.create_user(username="kitchen", password="test-only-password", role="KITCHEN")
        self.client.force_login(kitchen)
        self.assertEqual(self.client.get(reverse("orders:list")).status_code, 403)
