import logging
import math
from decimal import Decimal, InvalidOperation

from .models import MasterDataFile

logger = logging.getLogger(__name__)


def _normalize_text(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def _parse_percentage(value):
    if value is None:
        return None

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric_value = float(value)
        if abs(numeric_value) <= 1:
            return numeric_value * 100
        return numeric_value

    text = str(value).strip()
    if not text:
        return None

    cleaned = text.replace('%', '').replace(' ', '')
    try:
        numeric_value = float(cleaned)
    except ValueError:
        return None

    if abs(numeric_value) <= 1 and '%' not in text:
        return numeric_value * 100
    return numeric_value


def get_cash_discount_details(parsed_data=None, matched_bill_data=None):
    """
    Lookup cash discount details from the active master data file named
    Vendor_Cash_Discount_Bank_Details and compute the amount after discount.
    """
    if parsed_data is None:
        parsed_data = {}
    if matched_bill_data is None:
        matched_bill_data = {}

    supplier_gst_number = None
    for candidate in [
        parsed_data.get('vendor_gst_number'),
        parsed_data.get('supplier_gst_number'),
        parsed_data.get('gst_number'),
        matched_bill_data.get('partyGst') if isinstance(matched_bill_data, dict) else None,
    ]:
        if candidate:
            supplier_gst_number = candidate
            break

    total_amount = parsed_data.get('total_amount')
    if total_amount is None and matched_bill_data.get('payable') is not None:
        total_amount = matched_bill_data.get('payable')

    master_record = None
    try:
        master_record = MasterDataFile.objects.filter(
            document_name='Vendor_Cash_Discount_Bank_Details',
            is_active=True,
        ).order_by('-uploaded_at').first()
    except Exception:
        master_record = None

    discount_percentage = None
    match_found = False
    if master_record and getattr(master_record, 'parsed_data', None):
        logger.info(
            "Cash discount lookup input: gst=%s total_amount=%s master_record=%s",
            supplier_gst_number,
            total_amount,
            master_record.document_name if master_record else None,
        )
        for row in master_record.parsed_data or []:
            if not row:
                continue
            gst_candidate = row.get('SUPPLIER GST NUMBER') or row.get('Supplier GST Number') or row.get('supplier_gst_number') or row.get('GST Number') or row.get('gst_number')
            if gst_candidate and supplier_gst_number:
                normalized_input = _normalize_text(str(supplier_gst_number))
                normalized_candidate = _normalize_text(str(gst_candidate))
                if normalized_input == normalized_candidate:
                    match_found = True
                    discount_percentage = _parse_percentage(
                        row.get('CASH DISCOUNT') or row.get('Cash Discount') or row.get('cash_discount')
                    )
                    logger.info(
                        "Cash discount matched: gst=%s matched_row=%s discount=%s",
                        supplier_gst_number,
                        row,
                        discount_percentage,
                    )
                    break
                logger.debug(
                    "Cash discount GST mismatch: input=%s candidate=%s",
                    normalized_input,
                    normalized_candidate,
                )

    amount_after_discount = None
    if discount_percentage is not None and total_amount is not None:
        try:
            total_decimal = Decimal(str(total_amount))
            discount_decimal = Decimal(str(discount_percentage)) / Decimal('100')
            amount_after_discount = total_decimal - (total_decimal * discount_decimal)
        except (InvalidOperation, ValueError):
            amount_after_discount = None

    return {
        'cash_discount_percentage': discount_percentage,
        'amount_after_discount': float(amount_after_discount) if amount_after_discount is not None else None,
        'supplier_gst_number': supplier_gst_number,
        'master_record_name': master_record.document_name if master_record else None,
        'match_found': match_found,
    }
