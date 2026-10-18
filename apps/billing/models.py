import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.orders.models import Order


INDIAN_STATE_CHOICES = (
    ("01", "Jammu and Kashmir"), ("02", "Himachal Pradesh"), ("03", "Punjab"),
    ("04", "Chandigarh"), ("05", "Uttarakhand"), ("06", "Haryana"),
    ("07", "Delhi"), ("08", "Rajasthan"), ("09", "Uttar Pradesh"),
    ("10", "Bihar"), ("11", "Sikkim"), ("12", "Arunachal Pradesh"),
    ("13", "Nagaland"), ("14", "Manipur"), ("15", "Mizoram"),
    ("16", "Tripura"), ("17", "Meghalaya"), ("18", "Assam"),
    ("19", "West Bengal"), ("20", "Jharkhand"), ("21", "Odisha"),
    ("22", "Chhattisgarh"), ("23", "Madhya Pradesh"), ("24", "Gujarat"),
    ("26", "Dadra and Nagar Haveli and Daman and Diu"), ("27", "Maharashtra"),
    ("28", "Andhra Pradesh"), ("29", "Karnataka"), ("30", "Goa"),
    ("31", "Lakshadweep"), ("32", "Kerala"), ("33", "Tamil Nadu"),
    ("34", "Puducherry"), ("35", "Andaman and Nicobar Islands"),
    ("36", "Telangana"), ("37", "Andhra Pradesh"), ("38", "Ladakh"),
)


class BusinessTaxProfile(models.Model):
    class RegistrationStatus(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Not confirmed"
        REGISTERED = "REGISTERED", "GST registered"
        UNREGISTERED = "UNREGISTERED", "Not GST registered"

    class PremisesType(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Not confirmed"
        STANDALONE = "STANDALONE", "Standalone restaurant/café"
        SPECIFIED = "SPECIFIED", "Specified premises / hotel premises"
        OTHER = "OTHER", "Other / requires review"

    registration_status = models.CharField(max_length=12, choices=RegistrationStatus.choices, default=RegistrationStatus.UNKNOWN)
    supplier_state_code = models.CharField(max_length=2, choices=INDIAN_STATE_CHOICES, blank=True)
    premises_type = models.CharField(max_length=12, choices=PremisesType.choices, default=PremisesType.UNKNOWN)
    accountant_confirmed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "business GST profile"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Keep the single business tax profile; clear or update its fields instead.")

    def __str__(self):
        return "Business GST profile"


class TaxConfiguration(models.Model):
    class Treatment(models.TextChoices):
        TAXABLE = "TAXABLE", "Taxable"
        EXEMPT = "EXEMPT", "Exempt"
        NON_TAXABLE = "NON_TAXABLE", "Non-taxable"

    class PriceMode(models.TextChoices):
        TAX_EXCLUSIVE = "EXCLUSIVE", "Tax exclusive"
        TAX_INCLUSIVE = "INCLUSIVE", "Tax inclusive"

    name = models.CharField(max_length=100, unique=True)
    classification_code = models.CharField(max_length=32, blank=True)
    treatment = models.CharField(max_length=12, choices=Treatment.choices, default=Treatment.TAXABLE)
    rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    price_mode = models.CharField(
        max_length=10,
        choices=PriceMode.choices,
        default=PriceMode.TAX_INCLUSIVE,
    )
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.CheckConstraint(
                condition=Q(rate_percent__gte=0) & Q(rate_percent__lte=100),
                name="tax_rate_percent_range",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.rate_percent}%)"

    def clean(self):
        super().clean()
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "End date cannot be before start date."})
        if self.treatment in {self.Treatment.EXEMPT, self.Treatment.NON_TAXABLE} and self.rate_percent != 0:
            raise ValidationError({"rate_percent": "Exempt and non-taxable classifications must have a zero rate."})
        if self.treatment == self.Treatment.TAXABLE and not self.classification_code.strip():
            raise ValidationError({"classification_code": "Enter the classification confirmed for this taxable service/item."})


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"
        VOID = "VOID", "Void"

    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        PARTIAL = "PARTIAL", "Partially paid"
        PAID = "PAID", "Paid"
        REFUNDED = "REFUNDED", "Refunded"

    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="invoice")
    invoice_number = models.CharField(max_length=32, unique=True, null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT, db_index=True)
    payment_status = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        db_index=True,
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    exempt_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    non_taxable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_mode_snapshot = models.CharField(max_length=12, blank=True)
    supplier_state_code_snapshot = models.CharField(max_length=2, blank=True)
    place_of_supply_state_code_snapshot = models.CharField(max_length=2, blank=True)
    rounding_adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_invoices",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(condition=Q(subtotal__gte=0), name="invoice_subtotal_nonnegative"),
            models.CheckConstraint(condition=Q(discount_amount__gte=0), name="invoice_discount_nonnegative"),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="invoice_total_nonnegative"),
        ]

    def __str__(self):
        return self.invoice_number or f"Draft invoice {self.pk}"

    def save(self, *args, **kwargs):
        if self.pk:
            existing = type(self).objects.filter(pk=self.pk).first()
            if existing and existing.status in {self.Status.ISSUED, self.Status.VOID}:
                protected_fields = (
                    "order_id", "invoice_number", "subtotal", "discount_amount", "taxable_amount",
                    "exempt_amount", "non_taxable_amount", "tax_mode_snapshot",
                    "supplier_state_code_snapshot", "place_of_supply_state_code_snapshot",
                    "cgst_amount", "sgst_amount", "igst_amount", "rounding_adjustment", "total_amount",
                    "issued_at", "issued_by_id", "status",
                )
                changed = [field for field in protected_fields if getattr(existing, field) != getattr(self, field)]
                if changed:
                    raise ValidationError("Issued invoice financial details are locked; use a controlled correction workflow.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != self.Status.DRAFT:
            raise ValidationError("Issued or voided bills cannot be deleted; preserve their financial history.")
        return super().delete(*args, **kwargs)


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_lines",
    )
    item_name_snapshot = models.CharField(max_length=140)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_classification_snapshot = models.CharField(max_length=32, blank=True)
    tax_treatment_snapshot = models.CharField(max_length=12, choices=TaxConfiguration.Treatment.choices, blank=True)
    tax_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_price_mode_snapshot = models.CharField(max_length=10, blank=True)
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="invoice_line_price_nonnegative"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="invoice_line_quantity_positive"),
        ]

    def __str__(self):
        return f"{self.item_name_snapshot} x {self.quantity}"

    def save(self, *args, **kwargs):
        if Invoice.objects.filter(pk=self.invoice_id, status__in=(Invoice.Status.ISSUED, Invoice.Status.VOID)).exists():
            raise ValidationError("Lines on an issued invoice cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.invoice.status in {Invoice.Status.ISSUED, Invoice.Status.VOID}:
            raise ValidationError("Lines on an issued or voided bill cannot be removed.")
        return super().delete(*args, **kwargs)


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"
        CARD = "CARD", "Card"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SETTLED = "SETTLED", "Settled"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"
        REVERSED = "REVERSED", "Reversed"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    method = models.CharField(max_length=8, choices=Method.choices, default=Method.CASH)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    tendered_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    applied_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    change_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    external_reference = models.CharField(max_length=100, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_payments",
    )
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-received_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(tendered_amount__gte=0),
                name="payment_tendered_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(applied_amount__gte=0),
                name="payment_applied_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(change_amount__gte=0),
                name="payment_change_nonnegative",
            ),
        ]
        indexes = [models.Index(fields=("status", "received_at"))]

    def __str__(self):
        return f"{self.method} payment for {self.invoice}"
