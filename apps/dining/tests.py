from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditRecord
from apps.orders.models import Order

from .models import RestaurantTable
from .services import assign_dine_in_order, set_table_reserved


class TableManagementTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="manager", password="test-password-123", role=User.Role.MANAGER)
        self.cashier = User.objects.create_user(username="cashier", password="test-password-123", role=User.Role.CASHIER)
        self.table = RestaurantTable.objects.create(table_number="1", capacity=4)

    def make_order(self, **kwargs):
        defaults = {"order_type": Order.Type.DINE_IN, "opened_by": self.cashier}
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def test_manager_can_create_table_and_change_is_audited(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("dining:table_create"), {
            "table_number": "Patio A", "capacity": "4", "sort_order": "2", "is_active": "on",
        })
        self.assertRedirects(response, reverse("dining:table_list"))
        table = RestaurantTable.objects.get(table_number="Patio A")
        self.assertEqual(table.capacity, 4)
        self.assertTrue(AuditRecord.objects.filter(actor=self.manager, action="restaurant_table_created", object_id=str(table.pk)).exists())

    def test_cashier_can_view_tables_but_cannot_change_table_settings(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("dining:table_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dining:table_edit", args=(self.table.pk,))).status_code, 403)

    def test_order_assignment_occupies_table_and_completion_releases_it(self):
        order = self.make_order()
        assigned = assign_dine_in_order(order_id=order.pk, table_id=self.table.pk, actor=self.cashier)
        self.assertEqual(assigned.table_id, self.table.pk)
        self.assertTrue(AuditRecord.objects.filter(action="dine_in_order_table_assigned", object_id=str(order.pk)).exists())

        self.client.force_login(self.cashier)
        response = self.client.get(reverse("dining:table_list"))
        self.assertContains(response, "Occupied")
        self.assertContains(response, "Active order")

        order.status = Order.Status.COMPLETED
        order.save(update_fields=("status", "updated_at"))
        response = self.client.get(reverse("dining:table_list"))
        self.assertContains(response, "Available")
        self.assertNotContains(response, "Active order")
        order.refresh_from_db()
        self.assertEqual(order.table_id, self.table.pk, "Historical order-to-table relationship must be preserved.")

    def test_second_active_order_cannot_be_assigned_to_an_occupied_table(self):
        first = self.make_order()
        second = self.make_order()
        assign_dine_in_order(order_id=first.pk, table_id=self.table.pk, actor=self.cashier)
        with self.assertRaisesMessage(ValidationError, "This table already has an active dine-in order."):
            assign_dine_in_order(order_id=second.pk, table_id=self.table.pk, actor=self.cashier)
        second.refresh_from_db()
        self.assertIsNone(second.table_id)

    def test_reserved_table_rejects_assignment_and_unreserve_releases_it(self):
        set_table_reserved(table_id=self.table.pk, reserved=True, actor=self.manager)
        order = self.make_order()
        with self.assertRaisesMessage(ValidationError, "This table is reserved and cannot be assigned to a walk-in order."):
            assign_dine_in_order(order_id=order.pk, table_id=self.table.pk, actor=self.cashier)
        set_table_reserved(table_id=self.table.pk, reserved=False, actor=self.manager)
        assigned = assign_dine_in_order(order_id=order.pk, table_id=self.table.pk, actor=self.cashier)
        self.assertEqual(assigned.table_id, self.table.pk)

    def test_active_order_prevents_table_deactivation_without_losing_assignment(self):
        order = self.make_order()
        assign_dine_in_order(order_id=order.pk, table_id=self.table.pk, actor=self.cashier)
        self.client.force_login(self.manager)
        response = self.client.post(reverse("dining:table_edit", args=(self.table.pk,)), {
            "table_number": "1", "capacity": "4", "sort_order": "0",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "active dine-in order and cannot be deactivated")
        order.refresh_from_db()
        self.assertEqual(order.table_id, self.table.pk)
        self.table.refresh_from_db()
        self.assertTrue(self.table.is_active)
