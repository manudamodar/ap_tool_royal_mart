import logging
from decimal import Decimal, InvalidOperation

from .models import (
    DocumentResult,
    DueReportInvoiceWise,
    ReconciliationStatus,
    RoyalMartStoreMaster,
    VendorMaster,
)
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


def _decimal_equal(left, right, tolerance=Decimal('0.01')):
    if left in (None, '') or right in (None, ''):
        return False
    try:
        return abs(Decimal(str(left).replace(',', '')) - Decimal(str(right).replace(',', ''))) <= tolerance
    except (InvalidOperation, TypeError, ValueError):
        return False


def _expected_tax_type(vendor_gst, customer_gst):
    vendor_gst = _normalize_gst(vendor_gst)
    customer_gst = _normalize_gst(customer_gst)
    if not vendor_gst or not customer_gst or len(vendor_gst) < 2 or len(customer_gst) < 2:
        return None
    return 'CGST/SGST' if vendor_gst[:2] == customer_gst[:2] else 'IGST'


def _normalize_tax_type(value):
    text = (_normalize_text(value) or '').upper().replace(' ', '')
    if 'IGST' in text and 'CGST' not in text:
        return 'IGST'
    if 'CGST' in text or 'SGST' in text:
        return 'CGST/SGST'
    return text or None


def _map_document_to_due_report_reco_status(document_reconciliation_status):
    if document_reconciliation_status == ReconciliationStatus.VERIFIED:
        return 'VERIFIED'
    if document_reconciliation_status == ReconciliationStatus.MANUALLY_VERIFIED:
        return 'MANUALLY_VERIFIED'
    if document_reconciliation_status == ReconciliationStatus.MANUAL_REVIEW:
        return 'MANUAL_REVIEW'
    if document_reconciliation_status == ReconciliationStatus.NO_MATCH:
        return 'NO_MATCH'
    return 'UNVERIFIED'


def sync_due_report_invoice_reconciliation(document_result, matched_bill=None):
    parsed_data = document_result.parsed_data or {}
    invoice_no = _normalize_invoice_no((matched_bill or {}).get('invoiceNo') or parsed_data.get('invoice_number'))
    if not invoice_no:
        logger.warning("Skipping due-report invoice sync for document %s: missing invoice number", document_result.id)
        return

    gst_candidates = [
        (matched_bill or {}).get('partyGSTNo'),
        (matched_bill or {}).get('gst_number'),
        (matched_bill or {}).get('GSTIN'),
        (matched_bill or {}).get('GST Number'),
        parsed_data.get('gst_number'),
        parsed_data.get('vendor_gst_number'),
    ]
    gst_candidates = [_normalize_gst(gst) for gst in gst_candidates]
    gst_candidates = [gst for gst in gst_candidates if gst]

    invoice_candidates = [
        row for row in DueReportInvoiceWise.objects.order_by('-created_at')
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
            "Could not locate invoice-wise row for document %s (invoice_no=%s)",
            document_result.id,
            invoice_no,
        )
        return

    target_row.invoice_scanned = True
    target_row.invoice_reconciliation_status = _map_document_to_due_report_reco_status(document_result.reconciliation_status)
    target_row.reconciliation_details = document_result.reconciliation_details or {}
    reconciliation_flag_fields = (
        'invoice_number_matches', 'payable_amount_matches', 'goods_value_matches',
        'tax_amount_matches', 'tax_type_matches', 'vendor_gst_matches',
        'vendor_master_verified', 'store_gst_matches', 'store_master_verified',
    )
    detail_checks = (document_result.reconciliation_details or {}).get('checks') or {}
    detail_check_names = {
        'invoice_number_matches': 'invoice_number',
        'payable_amount_matches': 'payable_amount',
        'goods_value_matches': 'goods_value',
        'tax_amount_matches': 'tax_amount',
        'tax_type_matches': 'tax_type',
        'vendor_gst_matches': 'vendor_gst',
        'vendor_master_verified': 'vendor_master',
        'store_gst_matches': 'store_gst',
        'store_master_verified': 'store_master',
    }
    for field_name in reconciliation_flag_fields:
        flag_value = getattr(document_result, field_name, None)
        if flag_value is None:
            flag_value = detail_checks.get(detail_check_names[field_name])
        setattr(target_row, field_name, flag_value)
    target_row.save(update_fields=[
        'invoice_scanned', 'invoice_reconciliation_status', 'reconciliation_details', *reconciliation_flag_fields,
    ])


def build_bill_lookup(fetched_bills):
    by_invoice = {}
    by_invoice_gst = {}

    for bill in fetched_bills:
        invoice_no = _normalize_invoice_no(bill.get("invoiceNo"))
        gst_number = _normalize_gst(
            bill.get("partyGSTNo") or bill.get("gst_number") or bill.get("GSTIN") or bill.get("GST Number")
        )

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
    extracted_data = extracted_data or {}
    scanned_invoice_fields = (
        'date', 'vendor_name', 'vendor_bank', 'bank_name', 'account_holder_name',
        'account_number', 'ifsc_code', 'branch_name', 'micr_code', 'swift_code',
        'hsn_or_sac', 'vendor_gst_number', 'gst_number', 'customer_gst_number',
        'total_amount', 'goods_value', 'tax_amount', 'invoice_number',
    )
    reconciliation_details = {
        'checks': {},
        'scanned_invoice': {
            key: extracted_data.get(key)
            for key in scanned_invoice_fields
            if extracted_data.get(key) not in (None, '')
        },
        'scanned_filename': document_result.original_filename,
    }
    document_result.matched_bill_data = matched_bill

    invoice_no = _normalize_invoice_no(extracted_data.get("invoice_number"))
    ocr_total_amount = extracted_data.get("total_amount")
    api_payable_amount = matched_bill.get("payable") if matched_bill else None

    if matched_bill:
        reconciliation_details["cash_discount"] = get_cash_discount_details(
            parsed_data=extracted_data,
            matched_bill_data=matched_bill,
        )

        vendor_gst = _normalize_gst(extracted_data.get('vendor_gst_number') or extracted_data.get('gst_number'))
        customer_gst = _normalize_gst(extracted_data.get('customer_gst_number'))
        due_vendor_gst = _normalize_gst(matched_bill.get('partyGSTNo'))
        expected_tax_type = _expected_tax_type(vendor_gst, customer_gst)

        checks = {
            'invoice_number': _normalize_invoice_no(matched_bill.get('invoiceNo')) == invoice_no,
            'payable_amount': _decimal_equal(ocr_total_amount, api_payable_amount),
            'goods_value': _decimal_equal(extracted_data.get('goods_value'), matched_bill.get('goodsValue')),
            'tax_amount': _decimal_equal(extracted_data.get('tax_amount'), matched_bill.get('taxAmount')),
            'vendor_gst': bool(vendor_gst and vendor_gst == due_vendor_gst),
            'vendor_master': bool(vendor_gst and VendorMaster.objects.filter(gst_number__iexact=vendor_gst, is_active=True).exists()),
            'store_master': bool(customer_gst and RoyalMartStoreMaster.objects.filter(gst_number__iexact=customer_gst, is_active=True).exists()),
            'tax_type': bool(expected_tax_type and expected_tax_type == _normalize_tax_type(matched_bill.get('taxType'))),
        }
        checks['store_gst'] = checks['store_master']
        values = {
            'ocr': {
                'invoice_number': extracted_data.get('invoice_number'), 'payable_amount': ocr_total_amount,
                'goods_value': extracted_data.get('goods_value'), 'tax_amount': extracted_data.get('tax_amount'),
                'vendor_gst': vendor_gst, 'customer_gst': customer_gst,
            },
            'due_report': {
                'invoice_number': matched_bill.get('invoiceNo'), 'payable_amount': api_payable_amount,
                'goods_value': matched_bill.get('goodsValue'), 'tax_amount': matched_bill.get('taxAmount'),
                'vendor_gst': due_vendor_gst, 'tax_type': matched_bill.get('taxType'),
            },
            'expected_tax_type': expected_tax_type,
        }
        reconciliation_details.update({'checks': checks, 'values': values})

        document_result.invoice_number_matches = checks['invoice_number']
        document_result.payable_amount_matches = checks['payable_amount']
        document_result.goods_value_matches = checks['goods_value']
        document_result.tax_amount_matches = checks['tax_amount']
        document_result.tax_type_matches = checks['tax_type']
        document_result.vendor_gst_matches = checks['vendor_gst']
        document_result.vendor_master_verified = checks['vendor_master']
        document_result.store_gst_matches = checks['store_gst']
        document_result.store_master_verified = checks['store_master']

        failed_checks = [name for name, passed in checks.items() if not passed]
        if not failed_checks:
            document_result.reconciliation_status = ReconciliationOutcome.VERIFIED
            reconciliation_details['message'] = 'Invoice, amounts, tax, vendor and Royal Mart store checks matched.'
        else:
            document_result.reconciliation_status = ReconciliationOutcome.MANUAL_REVIEW
            reconciliation_details['failed_checks'] = failed_checks
            reconciliation_details['message'] = 'Manual review required: ' + ', '.join(name.replace('_', ' ') for name in failed_checks) + '.'
            reconciliation_details['ocr_amount'] = str(ocr_total_amount) if ocr_total_amount is not None else None
            reconciliation_details['api_amount'] = str(api_payable_amount) if api_payable_amount is not None else None
    else:
        document_result.reconciliation_status = ReconciliationOutcome.NO_MATCH
        reconciliation_details["message"] = "No matching bill found in due report data for OCR invoice number."
        reconciliation_details["ocr_invoice_number"] = invoice_no
        reconciliation_details["ocr_total_amount"] = str(ocr_total_amount) if ocr_total_amount is not None else None
        logger.warning("No matching bill found for invoice: %s", invoice_no)
        for field_name in (
            'invoice_number_matches', 'payable_amount_matches', 'goods_value_matches',
            'tax_amount_matches', 'tax_type_matches', 'vendor_gst_matches',
            'vendor_master_verified', 'store_gst_matches', 'store_master_verified',
        ):
            setattr(document_result, field_name, False)

    document_result.reconciliation_details = reconciliation_details
    document_result.save()
    sync_due_report_invoice_reconciliation(document_result, matched_bill=matched_bill)
    return document_result
