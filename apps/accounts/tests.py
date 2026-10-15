from django.contrib.auth import get_user_model
from django.test import SimpleTestCase


class UserModelTests(SimpleTestCase):
    def test_pos_roles_are_defined(self):
        user_model = get_user_model()
        role_values = {value for value, _label in user_model._meta.get_field("role").choices}

        self.assertEqual(role_values, {"ADMIN", "MANAGER", "CASHIER", "KITCHEN", "SERVER"})
        self.assertTrue(user_model._meta.get_field("display_name"))
        self.assertTrue(user_model._meta.get_field("phone"))
