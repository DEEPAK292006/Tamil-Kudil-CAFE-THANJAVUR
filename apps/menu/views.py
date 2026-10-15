from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.http import url_has_allowed_host_and_scheme
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit.models import AuditRecord

from .forms import MenuCategoryForm, MenuItemForm
from .models import MenuCategory, MenuItem
from .permissions import menu_manager_required


@login_required
def menu_list(request):
    categories = MenuCategory.objects.filter(is_active=True)
    can_manage_menu = request.user.is_superuser or request.user.role in {"ADMIN", "MANAGER"}
    inactive_categories = MenuCategory.objects.filter(is_active=False) if can_manage_menu else MenuCategory.objects.none()
    selected_category = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()
    items = MenuItem.objects.select_related("category").filter(category__is_active=True)
    if not request.user.is_authenticated or request.user.role not in {"ADMIN", "MANAGER"}:
        items = items.filter(is_available=True)
    if selected_category.isdigit():
        items = items.filter(category_id=int(selected_category))
    if query:
        items = items.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(category__name__icontains=query))
    return render(request, "menu/menu_list.html", {
        "categories": categories,
        "inactive_categories": inactive_categories,
        "items": items,
        "selected_category": selected_category,
        "query": query,
        "can_manage_menu": can_manage_menu,
    })


def _audit(actor, action, obj, changes):
    AuditRecord.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label,
        object_id=str(obj.pk),
        changes=changes,
    )


@menu_manager_required
def item_create(request):
    return _item_form(request)


@menu_manager_required
def item_edit(request, pk):
    item = get_object_or_404(MenuItem.objects.select_related("category"), pk=pk)
    return _item_form(request, item)


def _item_form(request, item=None):
    creating = item is None
    if request.method == "POST":
        form = MenuItemForm(request.POST, instance=item)
        if form.is_valid():
            before = {}
            if item:
                before = {"category": item.category.name, "name": item.name, "price": str(item.price), "is_available": item.is_available}
            try:
                with transaction.atomic():
                    saved = form.save()
                    after = {"category": saved.category.name, "name": saved.name, "price": str(saved.price), "is_available": saved.is_available}
                    _audit(request.user, "menu_item_created" if creating else "menu_item_updated", saved, {"before": before, "after": after})
            except IntegrityError:
                form.add_error("name", "An item with this name already exists in that category.")
            else:
                messages.success(request, f'{saved.name} {"added" if creating else "updated"}.')
                return redirect("menu:list")
    else:
        form = MenuItemForm(instance=item)
    return render(request, "menu/item_form.html", {"form": form, "item": item, "creating": creating})


@menu_manager_required
@require_POST
def item_availability(request, pk):
    with transaction.atomic():
        item = get_object_or_404(MenuItem.objects.select_for_update(), pk=pk)
        old = item.is_available
        item.is_available = not old
        item.save(update_fields=("is_available", "updated_at"))
        _audit(request.user, "menu_item_availability_changed", item, {"is_available": {"before": old, "after": item.is_available}})
    messages.success(request, f'{item.name} is now {"available" if item.is_available else "unavailable"}.')
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = ""
    return redirect(next_url or "menu:list")


@menu_manager_required
def category_create(request):
    return _category_form(request)


@menu_manager_required
def category_edit(request, pk):
    category = get_object_or_404(MenuCategory, pk=pk)
    return _category_form(request, category)


def _category_form(request, category=None):
    creating = category is None
    if request.method == "POST":
        form = MenuCategoryForm(request.POST, instance=category)
        if form.is_valid():
            before = {"name": category.name, "is_active": category.is_active} if category else {}
            try:
                with transaction.atomic():
                    saved = form.save()
                    _audit(request.user, "menu_category_created" if creating else "menu_category_updated", saved, {"before": before, "after": {"name": saved.name, "is_active": saved.is_active}})
            except IntegrityError:
                form.add_error("name", "A category with this name already exists.")
            else:
                messages.success(request, f'Category “{saved.name}” {"added" if creating else "updated"}.')
                return redirect("menu:list")
    else:
        form = MenuCategoryForm(instance=category)
    return render(request, "menu/category_form.html", {"form": form, "category": category, "creating": creating})


@menu_manager_required
@require_POST
def category_toggle(request, pk):
    with transaction.atomic():
        category = get_object_or_404(MenuCategory.objects.select_for_update(), pk=pk)
        old = category.is_active
        category.is_active = not old
        category.save(update_fields=("is_active", "updated_at"))
        _audit(request.user, "menu_category_status_changed", category, {"is_active": {"before": old, "after": category.is_active}})
    messages.success(request, f'Category “{category.name}” {"activated" if category.is_active else "deactivated"}.')
    return redirect("menu:list")
