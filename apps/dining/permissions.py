from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from apps.accounts.models import User


def table_manager_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser and request.user.role not in {User.Role.ADMIN, User.Role.MANAGER}:
            raise PermissionDenied("Only administrators and managers can change table settings.")
        return view_func(request, *args, **kwargs)

    return wrapped


def table_service_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser and request.user.role not in {
            User.Role.ADMIN, User.Role.MANAGER, User.Role.CASHIER, User.Role.SERVER,
        }:
            raise PermissionDenied("Your staff role cannot manage table service.")
        return view_func(request, *args, **kwargs)

    return wrapped
