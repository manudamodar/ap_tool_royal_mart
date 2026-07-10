import logging
from decimal import Decimal, InvalidOperation

from .models import DocumentResult, DueReportInvoiceWise, ReconciliationStatus
from .master_data_utils import get_cash_discount_details

logger = logging.getLogger(__name__)


class ReconciliationOutcome:
    VERIFIED = ReconciliationStatus.VERIFIED
    MANUAL_REVIEW = ReconciliationStatus.MANUAL_REVIEW
    NO_MATCH = ReconciliationStatus.NO_MATCH


def _normalize_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_invoice_no(value):
    text = _normalize_text(value)
    if not text:
        return None
    compact = "".join(text.split()).upper()
    if compact.endswith('.0'):
        try:
            numeric_value = Decimal(compact)
            if numeric_value == numeric_value.to_integral_value():
                compact = str(int(numeric_value))
        except (InvalidOperation, TypeError):
            pass
    return compact


def _normalize_gst(value):
    text = _normalize_text(value)
    return text.upper() if text else None


def _map_document_to_due_report_reco_status(document_reconciliation_status):
    if document_reconciliation_status == ReconciliationStatus.VERIFIED:
        return 'VERIFIED'
    if document_reconciliation_status == ReconciliationStatus.MANUALLY_VERIFIED:
        return 'MANUALLY_VERIFIED'
    return 'UNVERIFIED'


def sync_due_report_invoice_reconciliation(document_result, matched_bill=None):
    due_report = getattr(getattr(document_result, 'batch', None), 'due_report', None)
    if not due_report:
        return

    parsed_data = document_result.parsed_data or {}
    invoice_no = _normalize_invoice_no((matched_bill or {}).get('invoiceNo') or parsed_data.get('invoice_number'))
    if not invoice_no:
        logger.warning("Skipping due-report invoice sync for document %s: missing invoice number", document_result.id)
        return

    gst_candidates = [
        (matched_bill or {}).get('gst_number'),
        (matched_bill or {}).get('GSTIN'),
        (matched_bill or {}).get('GST Number'),
        parsed_data.get('gst_number'),
        parsed_data.get('vendor_gst_number'),
    ]
    gst_candidates = [_normalize_gst(gst) for gst in gst_candidates]
    gst_candidates = [gst for gst in gst_candidates if gst]

    invoice_candidates = [
        row for row in DueReportInvoiceWise.objects.filter(due_report=due_report).order_by('-created_at')
        if _normalize_invoice_no(row.invoice_no) == invoice_no
    ]

    target_row = None
    for gst in gst_candidates:
        for row in invoice_candidates:
            if _normalize_gst(row.gst_number) == gst:
                target_row = row
                break
        if target_row:
            break

    if not target_row:
        target_row = invoice_candidates[0] if invoice_candidates else None

    if not target_row:
        logger.warning(
            "Could not locate due-report invoice row for document %s (due_report=%s, invoice_no=%s)",
            document_result.id,
            due_report.id,
            invoice_no,
        )
        return

    target_row.invoice_scanned = True
    target_row.invoice_reconciliation_status = _map_document_to_due_report_reco_status(document_result.reconciliation_status)
    target_row.save(update_fields=['invoice_scanned', 'invoice_reconciliation_status'])


def build_bill_lookup(fetched_bills):
    by_invoice = {}
    by_invoice_gst = {}

    for bill in fetched_bills:
        invoice_no = _normalize_invoice_no(bill.get("invoiceNo"))
        gst_number = _normalize_gst(bill.get("gst_number") or bill.get("GSTIN") or bill.get("GST Number"))

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

    invoice_no = _normalize_invoice_no(extracted_data.get("invoice_number"))
    gst_number = _normalize_gst(extracted_data.get("gst_number") or extracted_data.get("vendor_gst_number"))
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

    invoice_no = _normalize_invoice_no(extracted_data.get("invoice_number")) if extracted_data else None
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
    sync_due_report_invoice_reconciliation(document_result, matched_bill=matched_bill)
    return document_result
