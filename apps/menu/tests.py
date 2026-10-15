from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import MenuCategory, MenuItem


class MenuModelTests(TestCase):
    def test_same_item_name_is_allowed_in_different_categories(self):
        snacks = MenuCategory.objects.create(name="Healthy Snacks")
        chaat = MenuCategory.objects.create(name="Chaat & Samosa")
        MenuItem.objects.create(category=snacks, name="Sprouts Chaat", price=Decimal("80.00"))
        MenuItem.objects.create(category=chaat, name="Sprouts Chaat", price=Decimal("80.00"))

        self.assertEqual(MenuItem.objects.filter(name="Sprouts Chaat").count(), 2)

    def test_duplicate_item_in_one_category_is_rejected(self):
        category = MenuCategory.objects.create(name="Tea Varieties")
        MenuItem.objects.create(category=category, name="Tea", price=Decimal("15.00"))

        with self.assertRaises(IntegrityError), transaction.atomic():
            MenuItem.objects.create(category=category, name="Tea", price=Decimal("20.00"))
