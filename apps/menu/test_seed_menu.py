from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from .management.commands.seed_menu import MENU
from .models import MenuCategory, MenuItem


class SeedMenuCommandTests(TestCase):
    def run_seed(self, *args):
        output = StringIO()
        call_command("seed_menu", *args, stdout=output)
        return output.getvalue()

    def test_seed_has_12_categories_and_75_items_with_exact_data(self):
        self.assertEqual(len(MENU), 12)
        self.assertEqual(sum(len(items) for _, items in MENU), 75)

        output = self.run_seed()
        self.assertIn("Categories: 12 created, 0 existing, 0 updated.", output)
        self.assertIn("Items: 75 created, 0 existing, 0 updated.", output)
        self.assertEqual(MenuCategory.objects.count(), 12)
        self.assertEqual(MenuItem.objects.count(), 75)

        for category_order, (category_name, entries) in enumerate(MENU, start=1):
            category = MenuCategory.objects.get(name=category_name)
            self.assertEqual(category.sort_order, category_order)
            self.assertEqual(list(category.items.order_by("sort_order").values_list("name", flat=True)), [entry[0] for entry in entries])
            for item_order, (name, raw_price, description) in enumerate(entries, start=1):
                item = MenuItem.objects.get(category=category, name=name)
                self.assertEqual(item.price, Decimal(raw_price).quantize(Decimal("0.01")))
                self.assertEqual(item.description, description)
                self.assertEqual(item.sort_order, item_order)

        sprouts = MenuItem.objects.filter(name="Sprouts Chaat").select_related("category")
        self.assertEqual(sprouts.count(), 2)
        self.assertSetEqual(set(sprouts.values_list("category__name", flat=True)), {"Healthy Snacks", "Chaat & Samosa"})

    def test_repeat_run_is_idempotent_and_preserves_staff_price_and_availability_edits(self):
        self.run_seed()
        item = MenuItem.objects.get(category__name="Tea Varieties", name="Tea")
        item.price = Decimal("99.00")
        item.is_available = False
        item.save(update_fields=("price", "is_available", "updated_at"))

        output = self.run_seed()

        self.assertIn("Categories: 0 created, 12 existing, 0 updated.", output)
        self.assertIn("Items: 0 created, 75 existing, 0 updated.", output)
        self.assertEqual(MenuCategory.objects.count(), 12)
        self.assertEqual(MenuItem.objects.count(), 75)
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal("99.00"))
        self.assertFalse(item.is_available)

    def test_reset_existing_restores_supplied_seed_values_explicitly(self):
        self.run_seed()
        item = MenuItem.objects.get(category__name="Tea Varieties", name="Tea")
        item.price = Decimal("99.00")
        item.is_available = False
        item.save(update_fields=("price", "is_available", "updated_at"))

        output = self.run_seed("--reset-existing")

        self.assertIn("Items: 0 created, 74 existing, 1 updated.", output)
        self.assertIn("Reset mode was used", output)
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal("15.00"))
        self.assertTrue(item.is_available)
