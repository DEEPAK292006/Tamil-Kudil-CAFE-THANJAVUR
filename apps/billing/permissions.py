from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from apps.accounts.models import User


def billing_staff_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser and request.user.role not in {
            User.Role.ADMIN, User.Role.MANAGER, User.Role.CASHIER,
        }:
            raise PermissionDenied("Your staff role cannot finalize bills.")
        return view_func(request, *args, **kwargs)

    return wrapped


def billing_manager_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser and request.user.role not in {
            User.Role.ADMIN, User.Role.MANAGER,
        }:
            raise PermissionDenied("Only a manager or administrator can remove a bill from active totals.")
        return view_func(request, *args, **kwargs)

    return wrapped
