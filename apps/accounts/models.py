from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        MANAGER = "MANAGER", "Manager"
        CASHIER = "CASHIER", "Cashier"
        KITCHEN = "KITCHEN", "Kitchen"
        SERVER = "SERVER", "Server"

    display_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=24, blank=True)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.CASHIER)

    def __str__(self):
        return self.display_name or self.username
