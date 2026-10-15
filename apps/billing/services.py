from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.timezone import localdate

from apps.audit.models import AuditRecord
from apps.orders.models import Order, OrderItem

from .models import BusinessTaxProfile, Invoice, InvoiceLine, TaxConfiguration

CENT = Decimal("0.01")


def _money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _allocate_discount(lines, discount, subtotal):
    """Allocate a fixed discount by line gross using largest remainder at paise precision."""
    if not lines or discount == 0 or subtotal == 0:
        return {line.pk: Decimal("0.00") for line in lines}

    shares = {}
    remainders = []
    for line in lines:
        gross = _money(line.unit_price * line.quantity)
        exact_share = discount * gross / subtotal
        rounded_down = exact_share.quantize(CENT, rounding=ROUND_DOWN)
        shares[line.pk] = rounded_down
        remainders.append((exact_share - rounded_down, line.pk))

    remaining_paise = int(((discount - sum(shares.values(), Decimal("0.00"))) / CENT).to_integral_value())
    for _, line_id in sorted(remainders, key=lambda entry: (-entry[0], entry[1]))[:remaining_paise]:
        shares[line_id] += CENT
    return shares


def _tax_for_line(net_amount, config, *, interstate):
    """Return taxable base and tax components for an inclusive or exclusive menu price."""
    net_amount = _money(net_amount)
    if config.treatment != TaxConfiguration.Treatment.TAXABLE:
        return net_amount, Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), net_amount

    rate = config.rate_percent
    if config.price_mode == TaxConfiguration.PriceMode.TAX_INCLUSIVE:
        base = _money(net_amount * Decimal("100") / (Decimal("100") + rate))
        tax_total = _money(net_amount - base)
        line_total = net_amount
    else:
        base = net_amount
        tax_total = _money(base * rate / Decimal("100"))
        line_total = _money(base + tax_total)

    if interstate:
        return base, Decimal("0.00"), Decimal("0.00"), tax_total, line_total
    cgst = _money(tax_total / Decimal("2"))
    sgst = _money(tax_total - cgst)
    return base, cgst, sgst, Decimal("0.00"), line_total


@transaction.atomic
def finalize_order(*, order_id, discount_amount, issued_by, place_of_supply_state_code=None):
    """Create an immutable issued invoice and complete its open order atomically."""
    order = Order.objects.select_for_update().get(pk=order_id)
    existing_invoice = Invoice.objects.filter(order=order).first()
    if existing_invoice:
        if existing_invoice.status == Invoice.Status.ISSUED:
            return existing_invoice
        raise ValidationError("An invoice record already exists for this order and is not issued.")
    if order.status != Order.Status.OPEN:
        raise ValidationError("Only an open order can be billed.")

    profile = BusinessTaxProfile.objects.first()
    if not profile or profile.registration_status != BusinessTaxProfile.RegistrationStatus.REGISTERED:
        raise ValidationError("Complete the GST registration profile before issuing a GST bill.")
    if not profile.accountant_confirmed:
        raise ValidationError("Ask your accountant to confirm the café's classifications, rates, and GST conditions before enabling billing.")
    if not profile.supplier_state_code or profile.premises_type == BusinessTaxProfile.PremisesType.UNKNOWN:
        raise ValidationError("Complete the supplier state and premises type in the business GST profile.")
    # The café only supplies from its registered state in this standalone POS.
    # Keep the state on the invoice snapshot without asking the cashier each time.
    if place_of_supply_state_code is None:
        place_of_supply_state_code = profile.supplier_state_code
    if place_of_supply_state_code not in dict(BusinessTaxProfile._meta.get_field("supplier_state_code").choices):
        raise ValidationError("Choose a valid place-of-supply state.")

    order_items = list(
        OrderItem.objects.select_for_update().filter(order=order)
        .select_related("menu_item__tax_configuration").order_by("pk")
    )
    if not order_items:
        raise ValidationError("Add at least one item before billing this order.")

    subtotal = _money(sum((_money(line.unit_price * line.quantity) for line in order_items), Decimal("0.00")))
    discount = _money(Decimal(discount_amount))
    if discount < 0:
        raise ValidationError("Discount cannot be negative.")
    if discount > subtotal:
        raise ValidationError("Discount cannot be greater than the order subtotal.")

    today = localdate()
    for line in order_items:
        config = line.menu_item.tax_configuration if line.menu_item_id else None
        if not config or not config.is_active:
            raise ValidationError(f"Configure an active, accountant-confirmed tax treatment for {line.item_name_snapshot} before billing.")
        if (config.effective_from and config.effective_from > today) or (config.effective_to and config.effective_to < today):
            raise ValidationError(f"The tax configuration for {line.item_name_snapshot} is not effective today.")
        try:
            config.full_clean()
        except ValidationError as exc:
            raise ValidationError(f"The tax configuration for {line.item_name_snapshot} is incomplete: {exc.messages}") from exc

    allocated_discounts = _allocate_discount(order_items, discount, subtotal)
    invoice = Invoice.objects.create(
        order=order,
        subtotal=subtotal,
        discount_amount=discount,
        taxable_amount=Decimal("0.00"),
        exempt_amount=Decimal("0.00"),
        non_taxable_amount=Decimal("0.00"),
        cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"),
        igst_amount=Decimal("0.00"),
        tax_mode_snapshot="IGST" if place_of_supply_state_code != profile.supplier_state_code else "CGST_SGST",
        supplier_state_code_snapshot=profile.supplier_state_code,
        place_of_supply_state_code_snapshot=place_of_supply_state_code,
        rounding_adjustment=Decimal("0.00"),
        total_amount=Decimal("0.00"),
    )
    taxable_total = Decimal("0.00")
    exempt_total = Decimal("0.00")
    non_taxable_total = Decimal("0.00")
    cgst_total = Decimal("0.00")
    sgst_total = Decimal("0.00")
    igst_total = Decimal("0.00")
    invoice_total = Decimal("0.00")
    for order_line in order_items:
        gross = _money(order_line.unit_price * order_line.quantity)
        line_discount = allocated_discounts[order_line.pk]
        discounted_price = _money(gross - line_discount)
        config = order_line.menu_item.tax_configuration
        base, cgst, sgst, igst, line_total = _tax_for_line(
            discounted_price,
            config,
            interstate=place_of_supply_state_code != profile.supplier_state_code,
        )
        if config.treatment == TaxConfiguration.Treatment.TAXABLE:
            taxable_total += base
        elif config.treatment == TaxConfiguration.Treatment.EXEMPT:
            exempt_total += base
        else:
            non_taxable_total += base
        cgst_total += cgst
        sgst_total += sgst
        igst_total += igst
        invoice_total += line_total
        InvoiceLine.objects.create(
            invoice=invoice,
            menu_item=order_line.menu_item,
            item_name_snapshot=order_line.item_name_snapshot,
            unit_price=order_line.unit_price,
            quantity=order_line.quantity,
            discount_amount=line_discount,
            tax_classification_snapshot=config.classification_code,
            tax_treatment_snapshot=config.treatment,
            tax_rate_snapshot=config.rate_percent,
            tax_price_mode_snapshot=config.price_mode,
            taxable_amount=base if config.treatment == TaxConfiguration.Treatment.TAXABLE else Decimal("0.00"),
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            line_total=line_total,
        )

    taxable_total = _money(taxable_total)
    exempt_total = _money(exempt_total)
    non_taxable_total = _money(non_taxable_total)
    cgst_total, sgst_total, igst_total = map(_money, (cgst_total, sgst_total, igst_total))
    invoice_total = _money(invoice_total)
    issued_at = timezone.now()
    invoice.invoice_number = f"TK-{timezone.localdate(issued_at):%Y%m%d}-{invoice.pk:06d}"
    invoice.taxable_amount = taxable_total
    invoice.exempt_amount = exempt_total
    invoice.non_taxable_amount = non_taxable_total
    invoice.cgst_amount = cgst_total
    invoice.sgst_amount = sgst_total
    invoice.igst_amount = igst_total
    invoice.total_amount = invoice_total
    invoice.status = Invoice.Status.ISSUED
    invoice.issued_at = issued_at
    invoice.issued_by = issued_by
    invoice.save(update_fields=(
        "invoice_number", "taxable_amount", "exempt_amount", "non_taxable_amount",
        "cgst_amount", "sgst_amount", "igst_amount", "total_amount", "status", "issued_at", "issued_by",
    ))

    order.status = Order.Status.COMPLETED
    order.completed_at = issued_at
    order.save(update_fields=("status", "completed_at", "updated_at"))
    AuditRecord.objects.create(
        actor=issued_by,
        action="invoice_issued",
        object_type=Invoice._meta.label,
        object_id=str(invoice.pk),
        changes={
            "invoice_number": invoice.invoice_number,
            "order_id": order.pk,
            "subtotal": str(subtotal),
            "discount": str(discount),
            "total": str(invoice.total_amount),
            "tax_mode": invoice.tax_mode_snapshot,
            "line_count": len(order_items),
        },
    )
    return invoice
