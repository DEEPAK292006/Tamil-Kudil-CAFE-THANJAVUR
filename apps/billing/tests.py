from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditRecord
from apps.menu.models import MenuCategory, MenuItem
from apps.orders.models import Order, OrderItem

from .models import BusinessTaxProfile, Invoice, InvoiceLine, TaxConfiguration
from .services import finalize_order


class BillingFinalizationTests(TestCase):
    def setUp(self):
        self.cashier = get_user_model().objects.create_user(
            username="billing-cashier", password="test-only-password", role="CASHIER",
        )
        self.category = MenuCategory.objects.create(name="Billing Test")
        BusinessTaxProfile.objects.create(
            registration_status=BusinessTaxProfile.RegistrationStatus.REGISTERED,
            supplier_state_code="33",
            premises_type=BusinessTaxProfile.PremisesType.STANDALONE,
            accountant_confirmed=True,
        )
        self.tax = TaxConfiguration.objects.create(
            name="Test taxable inclusive", classification_code="TEST", treatment=TaxConfiguration.Treatment.TAXABLE,
            rate_percent=Decimal("5.00"), price_mode=TaxConfiguration.PriceMode.TAX_INCLUSIVE, is_active=True,
        )
        self.item = MenuItem.objects.create(category=self.category, name="Pongal", price=Decimal("85.00"), tax_configuration=self.tax)
        self.order = Order.objects.create(order_type=Order.Type.TAKEAWAY, opened_by=self.cashier)
        self.line = OrderItem.objects.create(
            order=self.order,
            menu_item=self.item,
            item_name_snapshot=self.item.name,
            unit_price=self.item.price,
            quantity=2,
        )

    def test_finalize_calculates_totals_from_saved_order_and_snapshots_lines(self):
        invoice = finalize_order(order_id=self.order.pk, discount_amount=Decimal("10.00"), issued_by=self.cashier, place_of_supply_state_code="33")
        self.order.refresh_from_db()
        line = invoice.lines.get()

        self.assertEqual(invoice.status, Invoice.Status.ISSUED)
        self.assertRegex(invoice.invoice_number, r"^TK-\d{8}-\d{6,}$")
        self.assertEqual(invoice.subtotal, Decimal("170.00"))
        self.assertEqual(invoice.discount_amount, Decimal("10.00"))
        self.assertEqual(line.discount_amount, Decimal("10.00"))
        self.assertEqual(line.taxable_amount, Decimal("152.38"))
        self.assertEqual(line.line_total, Decimal("160.00"))
        self.assertEqual(invoice.taxable_amount, Decimal("152.38"))
        self.assertEqual(invoice.cgst_amount, Decimal("3.81"))
        self.assertEqual(invoice.sgst_amount, Decimal("3.81"))
        self.assertEqual(invoice.total_amount, Decimal("160.00"))
        self.assertEqual(invoice.rounding_adjustment, Decimal("0.00"))
        self.assertEqual(invoice.cgst_amount + invoice.sgst_amount + invoice.igst_amount, Decimal("7.62"))
        self.assertEqual(self.order.status, Order.Status.COMPLETED)
        self.assertIsNotNone(self.order.completed_at)
        self.assertTrue(AuditRecord.objects.filter(action="invoice_issued", object_id=str(invoice.pk)).exists())

        self.item.name = "Renamed Pongal"
        self.item.price = Decimal("95.00")
        self.item.save()
        line.refresh_from_db()
        self.assertEqual(line.item_name_snapshot, "Pongal")
        self.assertEqual(line.unit_price, Decimal("85.00"))

    def test_discount_cannot_be_negative_or_greater_than_subtotal(self):
        for discount in (Decimal("-0.01"), Decimal("170.01")):
            with self.subTest(discount=discount), self.assertRaises(ValidationError):
                finalize_order(order_id=self.order.pk, discount_amount=discount, issued_by=self.cashier, place_of_supply_state_code="33")
        self.assertFalse(Invoice.objects.filter(order=self.order).exists())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.OPEN)

    def test_tax_billing_is_blocked_when_an_item_has_no_confirmed_classification(self):
        self.item.tax_configuration = None
        self.item.save(update_fields=("tax_configuration", "updated_at"))
        with self.assertRaisesMessage(ValidationError, "Configure an active, accountant-confirmed tax treatment"):
            finalize_order(order_id=self.order.pk, discount_amount=Decimal("0.00"), issued_by=self.cashier, place_of_supply_state_code="33")
        self.assertFalse(Invoice.objects.filter(order=self.order).exists())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.OPEN)

    def test_interstate_place_of_supply_uses_igst(self):
        invoice = finalize_order(order_id=self.order.pk, discount_amount=Decimal("0.00"), issued_by=self.cashier, place_of_supply_state_code="29")
        line = invoice.lines.get()
        self.assertEqual(invoice.tax_mode_snapshot, "IGST")
        self.assertEqual(invoice.cgst_amount, Decimal("0.00"))
        self.assertEqual(invoice.sgst_amount, Decimal("0.00"))
        self.assertEqual(invoice.igst_amount, Decimal("8.10"))
        self.assertEqual(line.igst_amount, Decimal("8.10"))
        self.assertEqual(invoice.total_amount, Decimal("170.00"))

    def test_exclusive_price_adds_cgst_and_sgst_after_discounted_base(self):
        self.tax.price_mode = TaxConfiguration.PriceMode.TAX_EXCLUSIVE
        self.tax.save(update_fields=("price_mode",))
        self.line.unit_price = Decimal("100.00")
        self.line.quantity = 1
        self.line.save(update_fields=("unit_price", "quantity"))
        invoice = finalize_order(order_id=self.order.pk, discount_amount=Decimal("0.00"), issued_by=self.cashier, place_of_supply_state_code="33")
        self.assertEqual(invoice.taxable_amount, Decimal("100.00"))
        self.assertEqual(invoice.cgst_amount, Decimal("2.50"))
        self.assertEqual(invoice.sgst_amount, Decimal("2.50"))
        self.assertEqual(invoice.total_amount, Decimal("105.00"))

    def test_exempt_and_non_taxable_values_remain_separate(self):
        self.tax.treatment = TaxConfiguration.Treatment.EXEMPT
        self.tax.rate_percent = Decimal("0.00")
        self.tax.classification_code = "EXEMPT-TEST"
        self.tax.save()
        other_tax = TaxConfiguration.objects.create(
            name="Test non-taxable", classification_code="NON-TAX-TEST",
            treatment=TaxConfiguration.Treatment.NON_TAXABLE, rate_percent=Decimal("0.00"),
            price_mode=TaxConfiguration.PriceMode.TAX_INCLUSIVE, is_active=True,
        )
        item = MenuItem.objects.create(category=self.category, name="Water", price=Decimal("85.00"), tax_configuration=other_tax)
        OrderItem.objects.create(order=self.order, menu_item=item, item_name_snapshot="Water", unit_price=Decimal("85.00"), quantity=1)
        invoice = finalize_order(order_id=self.order.pk, discount_amount=Decimal("0.00"), issued_by=self.cashier, place_of_supply_state_code="33")
        self.assertEqual(invoice.exempt_amount, Decimal("170.00"))
        self.assertEqual(invoice.non_taxable_amount, Decimal("85.00"))
        self.assertEqual(invoice.taxable_amount, Decimal("0.00"))
        self.assertEqual(invoice.total_amount, Decimal("255.00"))

    def test_empty_order_cannot_be_finalized(self):
        self.order.items.all().delete()
        with self.assertRaisesMessage(ValidationError, "Add at least one item before billing this order."):
            finalize_order(order_id=self.order.pk, discount_amount=Decimal("0.00"), issued_by=self.cashier, place_of_supply_state_code="33")
        self.assertFalse(Invoice.objects.filter(order=self.order).exists())

    def test_discount_allocation_uses_paise_precision_and_sums_exactly(self):
        self.order.items.all().delete()
        for name, price in (("A", "0.33"), ("B", "0.33"), ("C", "0.34")):
            item = MenuItem.objects.create(category=self.category, name=name, price=Decimal(price), tax_configuration=self.tax)
            OrderItem.objects.create(
                order=self.order, menu_item=item, item_name_snapshot=name,
                unit_price=Decimal(price), quantity=1,
            )

        invoice = finalize_order(order_id=self.order.pk, discount_amount=Decimal("0.01"), issued_by=self.cashier, place_of_supply_state_code="33")
        self.assertEqual(sum(invoice.lines.values_list("discount_amount", flat=True), Decimal("0.00")), Decimal("0.01"))
        self.assertEqual(invoice.lines.get(item_name_snapshot="C").discount_amount, Decimal("0.01"))
        self.assertEqual(invoice.total_amount, Decimal("0.99"))

    def test_repeated_finalization_returns_same_invoice_without_duplicate_lines(self):
        first = finalize_order(order_id=self.order.pk, discount_amount=Decimal("5.00"), issued_by=self.cashier, place_of_supply_state_code="33")
        second = finalize_order(order_id=self.order.pk, discount_amount=Decimal("99.00"), issued_by=self.cashier, place_of_supply_state_code="33")
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.discount_amount, Decimal("5.00"))
        self.assertEqual(Invoice.objects.filter(order=self.order).count(), 1)
        self.assertEqual(InvoiceLine.objects.filter(invoice=first).count(), 1)

    def test_issued_invoice_and_lines_are_immutable_but_payment_status_can_advance(self):
        invoice = finalize_order(order_id=self.order.pk, discount_amount=Decimal("0.00"), issued_by=self.cashier, place_of_supply_state_code="33")
        invoice.total_amount = Decimal("1.00")
        with self.assertRaises(ValidationError):
            invoice.save()

        line = invoice.lines.get()
        line.quantity = 3
        with self.assertRaises(ValidationError):
            line.save()
        with self.assertRaises(ValidationError):
            line.delete()
        with self.assertRaises(ValidationError):
            InvoiceLine.objects.create(
                invoice=invoice,
                menu_item=self.item,
                item_name_snapshot="Extra item",
                unit_price=Decimal("1.00"),
                quantity=1,
                line_total=Decimal("1.00"),
            )
        with self.assertRaises(ValidationError):
            invoice.delete()

        invoice.refresh_from_db()
        invoice.payment_status = Invoice.PaymentStatus.PARTIAL
        invoice.save(update_fields=("payment_status",))
        invoice.refresh_from_db()
        self.assertEqual(invoice.payment_status, Invoice.PaymentStatus.PARTIAL)

    def test_cashier_can_finalize_from_review_page_and_invoice_is_read_only(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse("billing:finalize_order", args=(self.order.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "₹170.00")
        self.assertContains(response, "GST profile and item classifications are configured")
        response = self.client.post(reverse("billing:finalize_order", args=(self.order.pk,)), {"discount_amount": "20.00", "place_of_supply_state_code": "33"})
        invoice = Invoice.objects.get(order=self.order)
        self.assertRedirects(response, reverse("billing:invoice_detail", args=(invoice.pk,)))
        response = self.client.get(reverse("billing:invoice_detail", args=(invoice.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, invoice.invoice_number)
        self.assertContains(response, "Finalized bill · financial details are locked")
        self.assertContains(response, "CGST")

    def test_kitchen_role_cannot_finalize_bills(self):
        kitchen = get_user_model().objects.create_user(username="billing-kitchen", password="test-only-password", role="KITCHEN")
        self.client.force_login(kitchen)
        self.assertEqual(self.client.get(reverse("billing:finalize_order", args=(self.order.pk,))).status_code, 403)
