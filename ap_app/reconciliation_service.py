import logging
from decimal import Decimal, InvalidOperation

from .models import DocumentResult, ReconciliationStatus
from .master_data_utils import get_cash_discount_details

logger = logging.getLogger(__name__)


class ReconciliationOutcome:
    VERIFIED = ReconciliationStatus.VERIFIED
    MANUAL_REVIEW = ReconciliationStatus.MANUAL_REVIEW
    NO_MATCH = ReconciliationStatus.NO_MATCH


def build_bill_lookup(fetched_bills):
    by_invoice = {}
    by_invoice_gst = {}

    for bill in fetched_bills:
        invoice_no = bill.get("invoiceNo")
        gst_number = bill.get("gst_number") or bill.get("GSTIN") or bill.get("GST Number")

        if invoice_no:
            by_invoice.setdefault(invoice_no, []).append(bill)

        if invoice_no and gst_number:
            by_invoice_gst.setdefault((invoice_no, gst_number), []).append(bill)

    return {
        "by_invoice": by_invoice,
        "by_invoice_gst": by_invoice_gst,
    }


def match_bill(extracted_data, fetched_bills_lookup):
    if not extracted_data:
        return None

    invoice_no = extracted_data.get("invoice_number")
    gst_number = extracted_data.get("gst_number")
    total_amount = extracted_data.get("total_amount")

    if invoice_no and gst_number:
        matched = fetched_bills_lookup["by_invoice_gst"].get((invoice_no, gst_number))
        if matched:
            return matched[0]

    if invoice_no:
        matched = fetched_bills_lookup["by_invoice"].get(invoice_no)
        if matched:
            return matched[0]

    return None


def apply_reconciliation(document_result, extracted_data, matched_bill):
    reconciliation_details = {}
    document_result.matched_bill_data = matched_bill

    ocr_total_amount = extracted_data.get("total_amount")
    api_payable_amount = matched_bill.get("payable") if matched_bill else None

    if matched_bill:
        reconciliation_details["cash_discount"] = get_cash_discount_details(
            parsed_data=extracted_data,
            matched_bill_data=matched_bill,
        )

        if ocr_total_amount is not None and api_payable_amount is not None:
            try:
                ocr_amount_decimal = Decimal(str(ocr_total_amount))
                api_amount_decimal = Decimal(str(api_payable_amount))
                if ocr_amount_decimal == api_amount_decimal:
                    document_result.reconciliation_status = ReconciliationOutcome.VERIFIED
                    reconciliation_details["message"] = "Invoice number and total amount matched."
                else:
                    document_result.reconciliation_status = ReconciliationOutcome.MANUAL_REVIEW
                    reconciliation_details["message"] = "Invoice number matched, but total amount differs."
                    reconciliation_details["ocr_amount"] = str(ocr_total_amount)
                    reconciliation_details["api_amount"] = str(api_payable_amount)
                    logger.warning("Invoice number matched, but total amount differs. OCR=%s API=%s", ocr_total_amount, api_payable_amount)
            except (InvalidOperation, TypeError):
                document_result.reconciliation_status = ReconciliationOutcome.MANUAL_REVIEW
                reconciliation_details["message"] = "Invoice number matched, but OCR amount could not be parsed for comparison."
                reconciliation_details["ocr_amount"] = str(ocr_total_amount)
                reconciliation_details["api_amount"] = str(api_payable_amount)
                logger.warning("Invoice amount parse failed for %s", ocr_total_amount)
        else:
            document_result.reconciliation_status = ReconciliationOutcome.MANUAL_REVIEW
            reconciliation_details["message"] = "Invoice number matched, but OCR or due report total amount was missing for comparison."
            reconciliation_details["ocr_amount"] = str(ocr_total_amount)
            reconciliation_details["api_amount"] = str(api_payable_amount)
            logger.warning("Incomplete amount data for invoice match: OCR=%s API=%s", ocr_total_amount, api_payable_amount)
    else:
        document_result.reconciliation_status = ReconciliationOutcome.NO_MATCH
        reconciliation_details["message"] = "No matching bill found in due report data for OCR invoice number."
        reconciliation_details["ocr_invoice_number"] = invoice_no
        reconciliation_details["ocr_total_amount"] = str(ocr_total_amount) if ocr_total_amount is not None else None
        logger.warning("No matching bill found for invoice: %s", invoice_no)

    document_result.reconciliation_details = reconciliation_details
    document_result.save()
    return document_result
