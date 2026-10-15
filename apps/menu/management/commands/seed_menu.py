from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.menu.models import MenuCategory, MenuItem


# This is the supplied café menu. Prices are INR; an empty description means
# that no description was supplied.
MENU = (
    ("Tea Varieties", (
        ("Tea", "15", ""), ("Ginger Tea", "20", ""), ("Sukku Tea", "25", ""),
        ("Green Tea", "25", ""), ("Masala Tea", "25", ""),
    )),
    ("Coffee Varieties", (
        ("Filter Coffee", "25", ""), ("Degree Coffee", "35", ""),
        ("Sukku Malli Coffee", "40", ""), ("Palm Jaggery Coffee", "40", ""),
        ("Ragi Malt", "50", ""), ("Kambu Koozh", "50", ""),
    )),
    ("Fresh Juices", (
        ("Lemon Juice", "40", ""), ("Lemon Mint Cooler", "50", ""),
        ("Watermelon Juice", "60", ""), ("Sweet Lime Juice", "70", ""),
        ("Muskmelon Juice", "70", ""), ("Pineapple Juice", "80", ""),
        ("Orange Juice", "90", ""), ("Carrot Ginger Juice", "90", ""),
        ("Pomegranate Juice", "110", ""), ("Apple Beetroot Carrot Juice", "120", ""),
    )),
    ("Ice Cream", (
        ("Vanilla Ice Cream", "60", ""), ("Chocolate Ice Cream", "70", ""),
        ("Strawberry Ice Cream", "70", ""), ("Butterscotch Ice Cream", "70", ""),
        ("Kulfi (Traditional)", "80", ""), ("Seasonal Fruit Ice Cream", "80", ""),
    )),
    ("Health Drinks", (
        ("Millet Health Drink", "60", ""), ("Badam Milk", "70", ""),
        ("Turmeric Milk", "60", ""),
    )),
    ("Sundal Specials", (
        ("Green Peas Sundal", "50", "High protein, high fiber"),
        ("Green Gram Sundal", "50", "Protein, fiber, low GI"),
        ("Sweet Corn Sundal", "50", "Fiber, vitamin B"),
        ("White Cholam Sundal", "55", "Gluten-free, high fiber"),
        ("Peanut Sundal", "60", "High protein, healthy fats"),
        ("White Chickpea Sundal", "65", "Protein, fiber"),
        ("Brown Channa Sundal", "65", "Protein, fiber, low GI"),
        ("Navadhanya Sundal", "75", "Protein, fiber, minerals"),
    )),
    ("Millet Kozhukattai", (
        ("Ragi Kara Kozhukattai", "65", "Calcium, fiber"),
        ("Pearl Millet Kozhukattai", "70", "Fiber, low GI"),
        ("Foxtail Millet Kozhukattai", "75", "Fiber, sustained energy"),
        ("Little Millet Kozhukattai", "75", "Fiber, easy digestion"),
        ("Mixed Millet Kozhukattai", "70", "Fiber, minerals"),
    )),
    ("Healthy Snacks", (
        ("Banana Stem Bhel Puri", "75", "High fiber"),
        ("Banana Flower Vadai", "70", "Iron, fiber"),
        ("Chana Dal Keerai Vadai", "70", "Protein, iron"),
        ("Drumstick Leaf Vadai", "70", "Calcium, vitamins"),
        ("Sprouts Chaat", "80", "High protein, high fiber"),
        ("Banana Stem Chaat", "80", "High fiber"),
    )),
    ("Paniyaram", (
        ("Kara Paniyaram", "70", "Fermented"),
        ("Onion Paniyaram", "75", "Fermented"),
        ("Pepper Paniyaram", "75", "Digestive spices"),
        ("Chettinad Kuzhi Paniyaram", "80", "Fermented"),
    )),
    ("Puttu", (
        ("Red Rice Puttu", "80", "Benefits not specified"),
        ("Whole Wheat Puttu", "80", "High fiber"),
        ("Ragi Puttu", "85", "Calcium, high fiber"),
        ("Kambu Puttu", "85", "High fiber, low GI"),
        ("Mixed Millet Puttu", "95", "Fiber, minerals"),
        ("Banana & Palm Jaggery Puttu", "120", "Natural energy"),
    )),
    ("65 Specials", (
        ("Gobi 65", "120", "Fiber source"), ("Mushroom 65", "130", "Minerals"),
        ("Baby Corn 65", "130", "Fiber source"), ("Crispy Corn", "140", "Energy snack"),
        ("Paneer 65", "160", "High protein, calcium"),
    )),
    ("Chaat & Samosa", (
        ("Pani Puri", "50", "Street snack"), ("Masala Puri", "60", "Flavor packed"),
        ("Dahi Puri", "70", "Curd based"), ("Bhel Puri", "70", "Light snack"),
        ("Corn Chaat", "80", "Fiber source"), ("Sprouts Chaat", "80", "Protein, fiber"),
        ("Onion Samosa", "20", "Crispy snack"), ("Potato Samosa", "25", "Classic snack"),
        ("Vegetable Samosa", "30", "Vegetable filling"),
        ("Keerai Samosa", "35", "Iron, fiber"),
        ("Paneer Samosa", "45", "Protein source"),
    )),
)


class Command(BaseCommand):
    help = "Import the supplied Tamil Kudil Café menu without overwriting staff prices or availability."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-existing",
            action="store_true",
            help="Reset seeded prices, descriptions, ordering, availability, and category active states to this source list.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options["reset_existing"]
        category_counts = {"created": 0, "existing": 0, "updated": 0}
        item_counts = {"created": 0, "existing": 0, "updated": 0}

        for category_order, (category_name, entries) in enumerate(MENU, start=1):
            category, created = MenuCategory.objects.get_or_create(
                name=category_name,
                defaults={"sort_order": category_order, "is_active": True},
            )
            if created:
                category_counts["created"] += 1
            else:
                category_changes = {}
                desired_category = {"sort_order": category_order, "is_active": True}
                for field, value in desired_category.items():
                    if reset and getattr(category, field) != value:
                        category_changes[field] = value
                if category_changes:
                    for field, value in category_changes.items():
                        setattr(category, field, value)
                    category.save(update_fields=(*category_changes.keys(), "updated_at"))
                    category_counts["updated"] += 1
                else:
                    category_counts["existing"] += 1

            for item_order, (item_name, raw_price, description) in enumerate(entries, start=1):
                price = Decimal(raw_price).quantize(Decimal("0.01"))
                item, created = MenuItem.objects.get_or_create(
                    category=category,
                    name=item_name,
                    defaults={
                        "price": price,
                        "description": description,
                        "sort_order": item_order,
                        "is_available": True,
                    },
                )
                if created:
                    item_counts["created"] += 1
                    continue

                desired_item = {"description": description, "sort_order": item_order}
                if reset:
                    desired_item.update(price=price, is_available=True)
                changes = {
                    field: value
                    for field, value in desired_item.items()
                    if getattr(item, field) != value
                }
                if changes:
                    for field, value in changes.items():
                        setattr(item, field, value)
                    item.save(update_fields=(*changes.keys(), "updated_at"))
                    item_counts["updated"] += 1
                else:
                    item_counts["existing"] += 1

        self.stdout.write(self.style.SUCCESS("Tamil Kudil Café menu import finished."))
        self.stdout.write(
            f"Categories: {category_counts['created']} created, {category_counts['existing']} existing, "
            f"{category_counts['updated']} updated."
        )
        self.stdout.write(
            f"Items: {item_counts['created']} created, {item_counts['existing']} existing, "
            f"{item_counts['updated']} updated."
        )
        if reset:
            self.stdout.write(self.style.WARNING(
                "Reset mode was used: seeded prices and availability were reset; category states and seeded ordering were reset."
            ))
