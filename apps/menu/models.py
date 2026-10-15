from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class MenuCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name_plural = "menu categories"
        constraints = [
            models.CheckConstraint(condition=Q(sort_order__gte=0), name="menu_category_sort_nonnegative"),
        ]

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(MenuCategory, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    tax_configuration = models.ForeignKey(
        "billing.TaxConfiguration",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="menu_items",
        help_text="Choose only a classification and rate confirmed for this item/service.",
    )
    is_available = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("category__sort_order", "sort_order", "name")
        constraints = [
            models.UniqueConstraint(fields=("category", "name"), name="menu_item_category_name_unique"),
            models.CheckConstraint(condition=Q(price__gte=0), name="menu_item_price_nonnegative"),
            models.CheckConstraint(condition=Q(sort_order__gte=0), name="menu_item_sort_nonnegative"),
        ]
        indexes = [
            models.Index(fields=("category", "is_available")),
            models.Index(fields=("name",)),
        ]

    def __str__(self):
        return f"{self.name} ({self.category.name})"
