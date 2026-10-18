from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.orders.models import Order
from apps.orders.services import order_subtotal

from .forms import FinalizeInvoiceForm
from .models import BusinessTaxProfile, Invoice
from .permissions import billing_manager_required, billing_staff_required
from .services import finalize_order, void_invoice


@billing_staff_required
def finalize_order_view(request, order_id):
    order = get_object_or_404(Order.objects.select_related("table").prefetch_related("items"), pk=order_id)
    existing = Invoice.objects.filter(order=order).first()
    if existing and existing.status == Invoice.Status.ISSUED:
        return redirect("billing:invoice_detail", pk=existing.pk)
    if order.status != Order.Status.OPEN:
        messages.error(request, "Only an open order can be finalized for billing.")
        return redirect("orders:detail", pk=order.pk)
    subtotal = order_subtotal(order)
    if request.method == "POST":
        form = FinalizeInvoiceForm(request.POST, subtotal=subtotal)
        if form.is_valid():
            try:
                invoice = finalize_order(
                    order_id=order.pk,
                    discount_amount=form.cleaned_data["discount_amount"],
                    issued_by=request.user,
                )
            except (Order.DoesNotExist, ValidationError) as exc:
                if isinstance(exc, ValidationError):
                    message = "; ".join(exc.messages)
                else:
                    message = "This order no longer exists. Refresh and try again."
                messages.error(request, message)
            else:
                messages.success(request, f"Bill {invoice.invoice_number} finalized.")
                invoice_url = reverse("billing:invoice_detail", kwargs={"pk": invoice.pk})
                return redirect(f"{invoice_url}?print=1")
    else:
        form = FinalizeInvoiceForm(subtotal=subtotal)
    discount_preview = form.cleaned_data["discount_amount"] if form.is_bound and form.is_valid() else Decimal("0.00")
    profile = BusinessTaxProfile.objects.first()
    tax_setup_ready = bool(
        profile
        and profile.registration_status == BusinessTaxProfile.RegistrationStatus.REGISTERED
        and profile.accountant_confirmed
        and profile.supplier_state_code
        and all(line.menu_item_id and line.menu_item.tax_configuration_id and line.menu_item.tax_configuration.is_active for line in order.items.select_related("menu_item__tax_configuration"))
    )
    return render(request, "billing/finalize_order.html", {
        "order": order,
        "lines": order.items.all(),
        "subtotal": subtotal,
        "discount_preview": discount_preview,
        "amount_due_preview": subtotal - discount_preview,
        "tax_setup_ready": tax_setup_ready,
        "business_tax_profile": profile,
        "form": form,
    })


@billing_staff_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("order", "order__table", "issued_by").prefetch_related("lines"),
        pk=pk,
    )
    tax_total = invoice.cgst_amount + invoice.sgst_amount + invoice.igst_amount
    return render(request, "billing/invoice_detail.html", {
        "invoice": invoice,
        "lines": invoice.lines.all(),
        "tax_total": tax_total,
        "auto_print": request.GET.get("print") == "1",
        "can_void_invoice": request.user.is_superuser or request.user.role in {"ADMIN", "MANAGER"},
    })


@require_POST
@billing_manager_required
def void_invoice_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    try:
        void_invoice(invoice_id=invoice.pk, voided_by=request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, f"Bill {invoice.invoice_number} was removed from active bill totals. Its record remains in history.")
    return redirect("billing:invoice_detail", pk=invoice.pk)
