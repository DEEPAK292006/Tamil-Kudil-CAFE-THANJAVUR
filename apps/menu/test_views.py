from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditRecord

from .models import MenuCategory, MenuItem


class MenuManagementViewTests(TestCase):
    def setUp(self):
        self.category = MenuCategory.objects.create(name="Tiffin")

    def make_user(self, role):
        return User.objects.create_user(username=role.lower(), password="test-password-123", role=role)

    def test_staff_must_sign_in_to_view_menu(self):
        response = self.client.get(reverse("menu:list"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('menu:list')}")

    def test_cashier_can_view_but_cannot_edit_menu(self):
        cashier = self.make_user(User.Role.CASHIER)
        item = MenuItem.objects.create(category=self.category, name="Idli", price=Decimal("40.00"))
        self.client.force_login(cashier)

        self.assertEqual(self.client.get(reverse("menu:list")).status_code, 200)
        response = self.client.get(reverse("menu:item_edit", args=(item.pk,)))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_item_and_change_is_audited(self):
        manager = self.make_user(User.Role.MANAGER)
        self.client.force_login(manager)
        response = self.client.post(reverse("menu:item_create"), {
            "category": self.category.pk,
            "name": "Ghee Pongal",
            "description": "",
            "price": "85.00",
            "sort_order": "0",
            "is_available": "on",
        })
        self.assertRedirects(response, reverse("menu:list"))
        item = MenuItem.objects.get(name="Ghee Pongal")
        self.assertEqual(item.price, Decimal("85.00"))
        self.assertEqual(AuditRecord.objects.filter(actor=manager, action="menu_item_created", object_id=str(item.pk)).count(), 1)

        response = self.client.post(reverse("menu:item_availability", args=(item.pk,)), {"next": reverse("menu:list")})
        self.assertRedirects(response, reverse("menu:list"))
        item.refresh_from_db()
        self.assertFalse(item.is_available)
        audit = AuditRecord.objects.filter(actor=manager, action="menu_item_availability_changed", object_id=str(item.pk)).get()
        self.assertEqual(audit.changes["is_available"], {"before": True, "after": False})

    def test_negative_price_is_rejected(self):
        manager = self.make_user(User.Role.MANAGER)
        self.client.force_login(manager)
        response = self.client.post(reverse("menu:item_create"), {
            "category": self.category.pk,
            "name": "Invalid Item",
            "price": "-1.00",
            "sort_order": "0",
            "is_available": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MenuItem.objects.filter(name="Invalid Item").exists())
        self.assertContains(response, "Ensure this value is greater than or equal to 0")

    def test_search_and_category_filter_work(self):
        manager = self.make_user(User.Role.MANAGER)
        MenuItem.objects.create(category=self.category, name="Masala Dosa", price=Decimal("110.00"))
        MenuItem.objects.create(category=self.category, name="Filter Coffee", price=Decimal("30.00"))
        self.client.force_login(manager)
        response = self.client.get(reverse("menu:list"), {"category": self.category.pk, "q": "dosa"})
        self.assertContains(response, "Masala Dosa")
        self.assertNotContains(response, "Filter Coffee")
