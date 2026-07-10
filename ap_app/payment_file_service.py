import csv
import io
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

from .models import BatchStatus, MasterDataFile, PaymentFile, PaymentFileInvoice, DueReportInvoiceWise, Vendor

GST_FIELDS = {
    'supplier gst number', 'suppliergstnumber', 'gst number', 'gstnumber', 'gstin', 'gst'
}

SUPPLIER_FIELDS = {
    'supplier name', 'suppliername', 'party name', 'partyname', 'vendor name', 'vendorname', 'beneficiary name', 'beneficiaryname'
}

BANK_FIELDS = {
    'bank name', 'nameofbank', 'beneficiary bank', 'beneficiarybank', 'vendor bank', 'vendorbank',
}

IFSC_FIELDS = {
    'ifsc', 'ifsc code', 'ifsccode', 'ifsccode', 'ifsc_code', 'ifsccode'
}

ACCOUNT_FIELDS = {
    'account number', 'accountnumber', 'account no', 'accountno', 'bank account', 'bankaccount', 'beneficiary account', 'beneficiaryaccount'
}

ACCOUNT_HOLDER_FIELDS = {
    'account holder', 'account holder name', 'beneficiary name', 'beneficiaryname', 'name of beneficiary', 'payee name', 'payeename'
}

BRANCH_FIELDS = {
    'branch', 'branch name', 'branchname', 'bank branch', 'bankbranch'
}

PHONE_FIELDS = {
    'phone', 'phone number', 'phonenumber', 'mobile', 'mobile number', 'mobilenumber',
    'contact', 'contact number', 'contactnumber', 'phone no', 'phoneno',
}

EMAIL_FIELDS = {
    'email', 'email id', 'emailid', 'email address', 'emailaddress',
    'mail', 'mail id', 'mailid',
}

ADDRESS_FIELDS = {
    'address', 'beneficiary address', 'beneficiaryaddress', 'vendor address',
    'vendoraddress', 'city', 'location',
}

VENDOR_BANK_FIELDS = (
    BANK_FIELDS | IFSC_FIELDS | ACCOUNT_FIELDS | ACCOUNT_HOLDER_FIELDS
    | BRANCH_FIELDS | PHONE_FIELDS | EMAIL_FIELDS | ADDRESS_FIELDS
)

PAYMENT_FILE_HEADERS = {
    'SBI': [
        'TYPE',
        'AMT',
        'DATE',
        'DEBIT ACCOUNT NUMBER',
        'BEN.NAME',
        'PHONE NUMB',
        'BEN.ACCOU',
        'IFSC CODE',
        'PAYMENT INSTRCUCTION',
        'COR.REF NO (UNIQUE) PV NUMBER',
        'PAYABLE CURRENCY',
        'BENEFICIARY ADDRESS',
        'EMAIL',
        'BENEFICIARY ADVISE DISPATCH',
    ],
    'ICICI': [
        'PYMT_PROD_TYPE_CODE',
        'PYMT_MODE',
        'DEBIT_ACC_NO',
        'BNF_NAME',
        'BENE_ACC_NO',
        'BENE_IFSC',
        'AMOUNT',
        'DEBIT_NARR',
        'CREDIT_NARR',
        'MOBILE_NUM',
        'EMAIL_ID',
        'REMARK',
        'PYMT_DATE',
        'REF_NO',
        'ADDL_INFO1',
        'ADDL_INFO2',
        'ADDL_INFO3',
        'ADDL_INFO4',
        'ADDL_INFO5',
    ],
}


def _normalize_text(value):
    if value is None:
        return ""
    return re.sub(r'[^A-Z0-9]+', '', str(value).upper()).strip()


def _normalize_header(value):
    if value is None:
        return ""
    return re.sub(r'[^A-Za-z0-9]+', ' ', str(value).strip()).strip().lower()


def _get_master_field_value(row, candidate_keys):
    for key, value in row.items():
        if key is None:
            continue
        normalized_key = _normalize_header(key)
        if normalized_key in candidate_keys and value not in (None, ''):
            return str(value).strip()
    return None


_GST_PATTERN = re.compile(r'\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]\b')


def _extract_gst_from_text(text):
    """Extract an Indian GST number embedded anywhere in a text string."""
    if not text:
        return None
    match = _GST_PATTERN.search(text.upper())
    return match.group(0) if match else None


def _match_master_row(master_row, gst_number, supplier_name):
    if not master_row:
        return False

    n_gst = _normalize_text(gst_number) if gst_number else None

    # 1. Dedicated GST column
    gst_candidate = _get_master_field_value(master_row, GST_FIELDS)
    if n_gst and gst_candidate:
        if _normalize_text(gst_candidate) == n_gst:
            return True

    # 2. GST embedded inside the supplier/beneficiary name column
    #    e.g. "M B R MARKETING  29ALAPB8140P1ZV"
    supplier_candidate = _get_master_field_value(master_row, SUPPLIER_FIELDS)
    if n_gst and supplier_candidate:
        embedded_gst = _extract_gst_from_text(supplier_candidate)
        if embedded_gst and _normalize_text(embedded_gst) == n_gst:
            return True

    # 3. Fall back to name similarity
    if supplier_name and supplier_candidate:
        n_supplier = _normalize_text(supplier_name)
        n_candidate = _normalize_text(supplier_candidate)
        if n_supplier and n_candidate and (
            n_supplier == n_candidate
            or n_supplier in n_candidate
            or n_candidate in n_supplier
        ):
            return True

    return False


def _extract_bank_details(master_row):
    details = {
        'bank_name': None,
        'ifsc_code': None,
        'account_number': None,
        'account_holder_name': None,
        'branch_name': None,
        'phone': None,
        'email': None,
        'address': None,
        'vendor_bank': None,
    }

    for key, value in master_row.items():
        if value is None:
            continue
        normalized_key = _normalize_header(key)
        clean_value = str(value).strip()
        if not clean_value:
            continue

        if normalized_key in BANK_FIELDS:
            details['bank_name'] = clean_value
        elif normalized_key in IFSC_FIELDS:
            details['ifsc_code'] = clean_value
        elif normalized_key in ACCOUNT_FIELDS:
            details['account_number'] = clean_value
        elif normalized_key in ACCOUNT_HOLDER_FIELDS:
            details['account_holder_name'] = clean_value
        elif normalized_key in BRANCH_FIELDS:
            details['branch_name'] = clean_value
        elif normalized_key in PHONE_FIELDS:
            details['phone'] = clean_value
        elif normalized_key in EMAIL_FIELDS:
            details['email'] = clean_value
        elif normalized_key in ADDRESS_FIELDS:
            details['address'] = clean_value

    if any(details[f] for f in ['bank_name', 'ifsc_code', 'account_number', 'account_holder_name', 'branch_name']):
        parts = []
        if details['bank_name']:
            parts.append(f"Bank: {details['bank_name']}")
        if details['branch_name']:
            parts.append(f"Branch: {details['branch_name']}")
        if details['account_holder_name']:
            parts.append(f"Beneficiary: {details['account_holder_name']}")
        if details['account_number']:
            parts.append(f"A/C No: {details['account_number']}")
        if details['ifsc_code']:
            parts.append(f"IFSC: {details['ifsc_code']}")
        details['vendor_bank'] = ", ".join(parts)

    return details


def lookup_vendor_bank_details(due_report_row):
    if due_report_row is None:
        return {}

    gst_number = getattr(due_report_row, 'gst_number', None)
    supplier_name = getattr(due_report_row, 'supplier_name', None)

    # 1. Try MasterDataFile — preferred name first, then any active file with bank columns
    try:
        master_records = list(
            MasterDataFile.objects.filter(is_active=True).order_by(
                # preferred name sorts first
                '-document_name',
                '-uploaded_at',
            )
        )
        # prioritise the canonical bank-details file if present
        master_records.sort(
            key=lambda r: 0 if r.document_name == 'Vendor_Cash_Discount_Bank_Details' else 1
        )
    except Exception:
        master_records = []

    for master_record in master_records:
        parsed = getattr(master_record, 'parsed_data', None)
        if not parsed:
            logger.debug("[BankLookup] MasterDataFile '%s' has no parsed_data, skipping.", master_record.document_name)
            continue
        for master_row in parsed:
            if not master_row:
                continue
            # only use rows that actually carry bank details
            has_bank = any(
                _normalize_header(k) in VENDOR_BANK_FIELDS
                for k in master_row
                if k is not None
            )
            if not has_bank:
                continue
            if _match_master_row(master_row, gst_number, supplier_name):
                result = _extract_bank_details(master_row)
                logger.info(
                    "[BankLookup] Matched row in '%s' for GST=%s supplier=%s | raw_row=%s | extracted=%s",
                    master_record.document_name,
                    gst_number,
                    supplier_name,
                    {k: v for k, v in master_row.items() if _normalize_header(k) in VENDOR_BANK_FIELDS or _normalize_header(k) in GST_FIELDS or _normalize_header(k) in SUPPLIER_FIELDS},
                    result,
                )
                if any(result[f] for f in ['bank_name', 'ifsc_code', 'account_number', 'branch_name']):
                    return result
                logger.warning(
                    "[BankLookup] Row matched but no usable bank fields extracted for GST=%s. Full raw row: %s",
                    gst_number,
                    master_row,
                )

    # 2. Fallback: Vendor model by GST
    logger.warning(
        "[BankLookup] No master data match found for GST=%s supplier=%s. Tried %d master file(s).",
        gst_number,
        supplier_name,
        len(master_records),
    )

    # 2. Fallback: Vendor model by GST
    if gst_number:
        try:
            vendor = Vendor.objects.filter(gstin__iexact=gst_number).first()
            if vendor:
                details = {
                    'bank_name': vendor.bank_name or None,
                    'ifsc_code': None,
                    'account_number': vendor.account_number or None,
                    'account_holder_name': supplier_name,
                    'branch_name': None,
                    'vendor_bank': None,
                }
                parts = []
                if details['bank_name']:
                    parts.append(f"Bank: {details['bank_name']}")
                if details['account_holder_name']:
                    parts.append(f"Beneficiary: {details['account_holder_name']}")
                if details['account_number']:
                    parts.append(f"A/C No: {details['account_number']}")
                details['vendor_bank'] = ", ".join(parts)
                return details
        except Exception:
            pass

    # 3. Fallback: due report raw data (the JSON field may contain bank columns)
    try:
        due_report = getattr(due_report_row, 'due_report', None)
        if due_report and due_report.data:
            for raw_row in due_report.data:
                raw_gst = _normalize_text(raw_row.get('gst_number') or raw_row.get('GST Number') or raw_row.get('GSTIN') or '')
                raw_inv = _normalize_text(raw_row.get('invoice_no') or raw_row.get('Invoice No') or '')
                row_inv = _normalize_text(getattr(due_report_row, 'invoice_no', None) or '')
                if raw_gst and gst_number and raw_gst == _normalize_text(gst_number):
                    details = _extract_bank_details(raw_row)
                    if any(details[field] for field in ['bank_name', 'ifsc_code', 'account_number', 'branch_name']):
                        return details
                if raw_inv and row_inv and raw_inv == row_inv:
                    details = _extract_bank_details(raw_row)
                    if any(details[field] for field in ['bank_name', 'ifsc_code', 'account_number', 'branch_name']):
                        return details
    except Exception:
        pass

    return {}


def _coerce_decimal(value):
    if value is None:
        return Decimal('0.00')
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value))
    text = str(value).strip()
    if not text:
        return Decimal('0.00')
    cleaned = re.sub(r'[^0-9.\-]', '', text)
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal('0.00')


def _select_amount(row):
    candidates = [
        getattr(row, 'balance_amount', None),
        getattr(row, 'bill_amount', None),
        getattr(row, 'net_balance', None),
        getattr(row, 'amount_adjusted', None),
    ]
    for amount in candidates:
        if amount not in (None, ''):
            return _coerce_decimal(amount)
    return Decimal('0.00')


def build_payment_file_rows(payment_type, invoice_rows, overrides=None):
    rows = []
    overrides = overrides or {}

    for row in invoice_rows:
        bank_details = lookup_vendor_bank_details(row)
        row_override = overrides.get(str(row.id), {})
        amount = _select_amount(row)

        if 'amount' in row_override and row_override['amount'] not in (None, ''):
            amount = _coerce_decimal(row_override['amount'])

        gst = row_override.get('gst_number', row.gst_number) or ''
        name = row_override.get('supplier_name', row.supplier_name) or ''
        rows.append({
            'id': row.id,
            'invoice_no': row_override.get('invoice_no', row.invoice_no),
            'gst_number': gst,
            'supplier_name': name,
            'beneficiary_name': row_override.get('beneficiary_name', bank_details.get('account_holder_name') or name),
            'bank_name': row_override.get('bank_name', bank_details.get('bank_name')),
            'account_number': row_override.get('account_number', bank_details.get('account_number')),
            'ifsc_code': row_override.get('ifsc_code', bank_details.get('ifsc_code')),
            'branch_name': row_override.get('branch_name', bank_details.get('branch_name')),
            'vendor_bank': row_override.get('vendor_bank', bank_details.get('vendor_bank')),
            'phone': row_override.get('phone', bank_details.get('phone')),
            'email': row_override.get('email', bank_details.get('email')),
            'address': row_override.get('address', bank_details.get('address')),
            # BNF_NAME for ICICI: supplier name + GST (e.g. "M B R MARKETING  29ALAPB8140P1ZV")
            'bnf_name': f"{name}  {gst}".strip() if gst else name,
            'amount': amount.quantize(Decimal('0.01')) if isinstance(amount, Decimal) else _coerce_decimal(amount),
            'remarks': row_override.get('remarks', f"Invoice {row.invoice_no} / {gst or 'GST N/A'}"),
        })

    return rows


def _build_row_values(payment_type, invoice_row, debit_account, payment_ref, date_str):
    """Return an ordered list of cell values for one row in the bank file."""
    r = invoice_row
    amount_str = f"{float(r.get('amount') or 0):,.2f}"
    amount_num = float(r.get('amount') or 0)

    if payment_type == 'SBI':
        return [
            'NEFT',                                    # TYPE
            amount_num,                                # AMT
            date_str,                                  # DATE
            debit_account,                             # DEBIT ACCOUNT NUMBER
            r.get('supplier_name') or '',              # BEN.NAME
            r.get('phone') or '',                      # PHONE NUMB
            r.get('account_number') or '',             # BEN.ACCOU
            r.get('ifsc_code') or '',                  # IFSC CODE
            'VENDOR PAYMENT',                          # PAYMENT INSTRCUCTION
            payment_ref,                               # COR.REF NO (UNIQUE) PV NUMBER
            'INR',                                     # PAYABLE CURRENCY
            r.get('address') or '',                    # BENEFICIARY ADDRESS
            r.get('email') or '',                      # EMAIL
            'E',                                       # BENEFICIARY ADVISE DISPATCH
        ]
    else:  # ICICI
        return [
            'PAB_VENDOR',                              # PYMT_PROD_TYPE_CODE
            'NEFT',                                    # PYMT_MODE
            debit_account,                             # DEBIT_ACC_NO
            r.get('bnf_name') or r.get('supplier_name') or '',  # BNF_NAME
            r.get('account_number') or '',             # BENE_ACC_NO
            r.get('ifsc_code') or '',                  # BENE_IFSC
            amount_str,                                # AMOUNT
            '',                                        # DEBIT_NARR
            '',                                        # CREDIT_NARR
            r.get('phone') or '',                      # MOBILE_NUM
            r.get('email') or '',                      # EMAIL_ID
            payment_ref,                               # REMARK
            date_str,                                  # PYMT_DATE
            '',                                        # REF_NO
            r.get('gst_number') or '',                 # ADDL_INFO1
            '',                                        # ADDL_INFO2
            '',                                        # ADDL_INFO3
            '',                                        # ADDL_INFO4
            '',                                        # ADDL_INFO5
        ]


def _get_debit_account(payment_type):
    if payment_type == 'SBI':
        return getattr(settings, 'STORE_DEBIT_ACCOUNT_SBI', '') or ''
    return getattr(settings, 'STORE_DEBIT_ACCOUNT_ICICI', '') or ''


def generate_payment_file_content(payment_type, invoice_rows, payment_ref=''):
    headers = PAYMENT_FILE_HEADERS.get(payment_type, PAYMENT_FILE_HEADERS['ICICI'])
    debit_account = _get_debit_account(payment_type)
    date_str = date.today().strftime('%d-%m-%Y')

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    for invoice_row in invoice_rows:
        row_values = _build_row_values(payment_type, invoice_row, debit_account, payment_ref, date_str)
        writer.writerow(['' if v is None else v for v in row_values])
    return output.getvalue().encode('utf-8')


def generate_payment_file_xlsx(payment_type, invoice_rows, payment_ref=''):
    headers = PAYMENT_FILE_HEADERS.get(payment_type, PAYMENT_FILE_HEADERS['ICICI'])
    debit_account = _get_debit_account(payment_type)
    date_str = date.today().strftime('%d-%m-%Y')

    rows = [
        _build_row_values(payment_type, r, debit_account, payment_ref, date_str)
        for r in invoice_rows
    ]
    # Coerce None → '' so Excel cells are never blank due to None
    rows = [['' if v is None else v for v in row] for row in rows]
    df = pd.DataFrame(rows, columns=headers)
    output = io.BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    return output.getvalue()


def create_payment_file_record(payment_type, invoice_rows, due_report, created_by, line_item_overrides=None, rejected_due_report_row_ids=None, force_selected_ids=None):
    payment_file = PaymentFile.objects.create(
        due_report=due_report,
        status=BatchStatus.COMPLETED,
        total_files=len(invoice_rows),
        processed_files=len(invoice_rows),
        payment_type=payment_type,
        created_by=created_by,
        modified_by=created_by,
        line_item_overrides=line_item_overrides or {},
        rejected_due_report_row_ids=rejected_due_report_row_ids or [],
        is_payment_file_approved=False,
        is_payment_done=False,
    )

    payment_file.due_report_rows.set([row.id for row in invoice_rows])
    invoice_ids = [row.id for row in invoice_rows]
    force_selected_ids = set(force_selected_ids or [])

    for row in invoice_rows:
        link, _ = PaymentFileInvoice.objects.get_or_create(
            payment_file=payment_file,
            invoice=row,
            defaults={
                'status': PaymentFileInvoice.Status.PENDING_MANAGER_REVIEW,
                'force_selected': row.id in force_selected_ids,
            },
        )
        if row.id in force_selected_ids:
            link.force_selected = True
            link.status = PaymentFileInvoice.Status.PENDING_MANAGER_REVIEW
            link.save()

    DueReportInvoiceWise.objects.filter(id__in=invoice_ids).update(
        is_payment_file_created=True,
        manager_rejected=False,

    )

    return payment_file
