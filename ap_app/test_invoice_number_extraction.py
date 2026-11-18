from django.test import SimpleTestCase

from .tasks import _extract_invoice_number


class InvoiceNumberExtractionTests(SimpleTestCase):
    def test_cash_bill_title_is_replaced_by_labelled_number(self):
        text = "CASH BILL\nSAS ENTERPRISES\nNo. 5689\nDate: 26/4/26"

        self.assertEqual(
            _extract_invoice_number(text, "CASH BILL", "SAS ENTERPRISES INV NO 5689.pdf"),
            "5689",
        )

    def test_estimate_title_uses_leading_filename_number(self):
        text = "SRI SAI FOODS\nESTIMATE\nRMM Super Market LA 21551"

        self.assertEqual(
            _extract_invoice_number(text, "ESTIMATE", "21551 SAI FOODS.pdf"),
            "21551",
        )

    def test_filename_number_seen_in_ocr_beats_date_selected_by_llm(self):
        text = "SRI SAI FOODS\nESTIMATE\nR mer Super Market LA 21551\nDate 24/466"

        self.assertEqual(
            _extract_invoice_number(text, "24/466", "21551 SAI FOODS.pdf"),
            "21551",
        )

    def test_filename_inv_no_is_used_when_ocr_has_no_label(self):
        self.assertEqual(
            _extract_invoice_number("SAS ENTERPRISES\nCASH BILL", "CASH BILL", "SAS ENTERPRISES INV NO 5689.pdf"),
            "5689",
        )

    def test_serial_number_label_is_not_used_as_invoice_number(self):
        text = "Sy. No. 42/1\nSRI SAI FOODS\nESTIMATE"

        self.assertEqual(
            _extract_invoice_number(text, "ESTIMATE", "21551 SAI FOODS.pdf"),
            "21551",
        )

    def test_valid_llm_invoice_number_is_preserved(self):
        self.assertEqual(
            _extract_invoice_number("TAX INVOICE", "SOBP/25-26/2071", "invoice.pdf"),
            "SOBP/25-26/2071",
        )

    def test_structured_bill_number_beats_manager_code_and_short_filename(self):
        text = """Bill No
:
Bill Date
:
15/04/26 02:08:50 PM
RPHMNGR1
Credit Bill
26/3412/0000736
"""

        self.assertEqual(
            _extract_invoice_number(
                text,
                "RPHMNGR1",
                "RPH RFA HYPERMARKET LLP INV NO 0736.pdf",
            ),
            "26/3412/0000736",
        )

