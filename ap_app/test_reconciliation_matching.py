from decimal import Decimal

from django.test import SimpleTestCase

from .reconciliation_service import (
    _decimal_equal,
    _invoice_numbers_ocr_equivalent,
    build_bill_lookup,
    match_bill,
)


class ReconciliationMatchingTests(SimpleTestCase):
    def setUp(self):
        self.vendor_gst = "29AACFU9772B1ZV"
        self.other_vendor_gst = "29AAACX0000A1Z5"

    def test_same_invoice_number_selects_only_exact_vendor_gst(self):
        bills = [
            {"invoiceNo": "INV-100", "partyGSTNo": self.other_vendor_gst, "payable": "500.00"},
            {"invoiceNo": "INV-100", "partyGSTNo": self.vendor_gst, "payable": "500.00"},
        ]

        matched = match_bill(
            {
                "invoice_number": "INV-100",
                "vendor_gst_number": self.vendor_gst,
                "total_amount": "500.00",
            },
            build_bill_lookup(bills),
        )

        self.assertEqual(matched["partyGSTNo"], self.vendor_gst)

    def test_unique_invoice_without_vendor_gst_is_found_for_manual_review(self):
        bills = [
            {"invoiceNo": "INV-100", "partyGSTNo": self.vendor_gst, "payable": "500.00"},
        ]

        matched = match_bill(
            {"invoice_number": "INV-100", "total_amount": "500.00"},
            build_bill_lookup(bills),
        )

        self.assertEqual(matched["invoiceNo"], "INV-100")

    def test_i_and_one_ocr_confusion_requires_same_gst_and_payable(self):
        bills = [
            {"invoiceNo": "I/26-27/004198", "partyGSTNo": self.vendor_gst, "payable": "46251.00"},
        ]

        matched = match_bill(
            {
                "invoice_number": "1/26-27/004198",
                "vendor_gst_number": self.vendor_gst,
                "total_amount": "46251.00",
            },
            build_bill_lookup(bills),
        )

        self.assertEqual(matched["invoiceNo"], "I/26-27/004198")

    def test_i_and_one_ocr_confusion_rejects_wrong_payable(self):
        bills = [
            {"invoiceNo": "I/26-27/004198", "partyGSTNo": self.vendor_gst, "payable": "46251.00"},
        ]

        matched = match_bill(
            {
                "invoice_number": "1/26-27/004198",
                "vendor_gst_number": self.vendor_gst,
                "total_amount": "46252.00",
            },
            build_bill_lookup(bills),
        )

        self.assertIsNone(matched)

    def test_ambiguous_exact_invoice_and_gst_is_not_auto_selected(self):
        duplicate = {"invoiceNo": "INV-100", "partyGSTNo": self.vendor_gst, "payable": "500.00"}

        matched = match_bill(
            {
                "invoice_number": "INV-100",
                "vendor_gst_number": self.vendor_gst,
                "total_amount": "500.00",
            },
            build_bill_lookup([duplicate, dict(duplicate)]),
        )

        self.assertIsNone(matched)

    def test_duplicate_invoice_without_gst_uses_unique_payable(self):
        bills = [
            {"invoiceNo": "INV-100", "partyGSTNo": self.vendor_gst, "payable": "500.00"},
            {"invoiceNo": "INV-100", "partyGSTNo": self.other_vendor_gst, "payable": "750.00"},
        ]

        matched = match_bill(
            {"invoice_number": "INV-100", "total_amount": "750.00"},
            build_bill_lookup(bills),
        )

        self.assertEqual(matched["partyGSTNo"], self.other_vendor_gst)

    def test_duplicate_invoice_and_gst_uses_unique_payable(self):
        bills = [
            {"invoiceNo": "INV-100", "partyGSTNo": self.vendor_gst, "payable": "500.00"},
            {"invoiceNo": "INV-100", "partyGSTNo": self.vendor_gst, "payable": "750.00"},
        ]

        matched = match_bill(
            {
                "invoice_number": "INV-100",
                "vendor_gst_number": self.vendor_gst,
                "total_amount": "750.00",
            },
            build_bill_lookup(bills),
        )

        self.assertEqual(matched["payable"], "750.00")

    def test_amount_tolerance_remains_one_paisa(self):
        self.assertTrue(_decimal_equal("100.00", "100.01"))
        self.assertFalse(_decimal_equal("100.00", Decimal("100.02")))

    def test_invoice_number_check_is_independent_of_amount(self):
        self.assertTrue(_invoice_numbers_ocr_equivalent("INV-100", "INV-100"))

