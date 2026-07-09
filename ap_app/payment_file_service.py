import csv
import io
import re
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.core.files.base import ContentFile

from .models import BatchStatus, MasterDataFile, PaymentFile, PaymentFileInvoice, DueReportInvoiceWise

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

VENDOR_BANK_FIELDS = BANK_FIELDS | IFSC_FIELDS | ACCOUNT_FIELDS | ACCOUNT_HOLDER_FIELDS | BRANCH_FIELDS

PAYMENT_FILE_HEADERS = {
    'ICICI': [
        'Invoice No',
        'GST Number',
        'Supplier Name',
        'Beneficiary Name',
        'Bank Name',
        'Account Number',
        'IFSC Code',
        'Branch Name',
        'Amount',
        'Remarks',
    ],
    'SBI': [
        'Invoice No',
        'GST Number',
        'Supplier Name',
        'Beneficiary Name',
        'Account Number',
        'IFSC Code',
        'Bank Name',
        'Branch Name',
        'Amount',
        'Remarks',
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


def _match_master_row(master_row, gst_number, supplier_name):
    if not master_row:
        return False

    gst_candidate = _get_master_field_value(master_row, GST_FIELDS)
    if gst_number and gst_candidate:
        if _normalize_text(gst_candidate) == _normalize_text(gst_number):
            return True

    supplier_candidate = _get_master_field_value(master_row, SUPPLIER_FIELDS)
    if supplier_name and supplier_candidate:
        n_supplier = _normalize_text(supplier_name)
        n_candidate = _normalize_text(supplier_candidate)
        if n_supplier and n_candidate and (n_supplier == n_candidate or n_supplier in n_candidate or n_candidate in n_supplier):
            return True

    return False


def _extract_bank_details(master_row):
    details = {
        'bank_name': None,
        'ifsc_code': None,
        'account_number': None,
        'account_holder_name': None,
        'branch_name': None,
        'vendor_bank': None,
    }

    for key, value in master_row.items():
        if value is None:
            continue
        normalized_key = _normalize_header(key)
        clean_value = str(value).strip()

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

    if any(details[field] for field in ['bank_name', 'ifsc_code', 'account_number', 'account_holder_name', 'branch_name']):
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

    try:
        master_record = MasterDataFile.objects.filter(
            document_name='Vendor_Cash_Discount_Bank_Details',
            is_active=True,
        ).order_by('-uploaded_at').first()
    except Exception:
        return {}

    if not master_record or not getattr(master_record, 'parsed_data', None):
        return {}

    gst_number = getattr(due_report_row, 'gst_number', None)
    supplier_name = getattr(due_report_row, 'supplier_name', None)

    for master_row in master_record.parsed_data or []:
        if not master_row:
            continue
        if _match_master_row(master_row, gst_number, supplier_name):
            return _extract_bank_details(master_row)

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

        rows.append({
            'id': row.id,
            'invoice_no': row_override.get('invoice_no', row.invoice_no),
            'gst_number': row_override.get('gst_number', row.gst_number),
            'supplier_name': row_override.get('supplier_name', row.supplier_name),
            'beneficiary_name': row_override.get('beneficiary_name', bank_details.get('account_holder_name') or row.supplier_name),
            'bank_name': row_override.get('bank_name', bank_details.get('bank_name')),
            'account_number': row_override.get('account_number', bank_details.get('account_number')),
            'ifsc_code': row_override.get('ifsc_code', bank_details.get('ifsc_code')),
            'branch_name': row_override.get('branch_name', bank_details.get('branch_name')),
            'vendor_bank': row_override.get('vendor_bank', bank_details.get('vendor_bank')),
            'amount': amount.quantize(Decimal('0.01')) if isinstance(amount, Decimal) else _coerce_decimal(amount),
            'remarks': row_override.get('remarks', f"Invoice {row.invoice_no} / {row.gst_number or 'GST N/A'}"),
        })

    return rows


def generate_payment_file_content(payment_type, invoice_rows):
    headers = PAYMENT_FILE_HEADERS.get(payment_type, PAYMENT_FILE_HEADERS['ICICI'])
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)

    for invoice_row in invoice_rows:
        if payment_type == 'SBI':
            row_values = [
                invoice_row['invoice_no'],
                invoice_row['gst_number'],
                invoice_row['supplier_name'],
                invoice_row['beneficiary_name'],
                invoice_row['account_number'],
                invoice_row['ifsc_code'],
                invoice_row['bank_name'],
                invoice_row['branch_name'],
                f"{invoice_row['amount']:.2f}",
                invoice_row['remarks'],
            ]
        else:
            row_values = [
                invoice_row['invoice_no'],
                invoice_row['gst_number'],
                invoice_row['supplier_name'],
                invoice_row['beneficiary_name'],
                invoice_row['bank_name'],
                invoice_row['account_number'],
                invoice_row['ifsc_code'],
                invoice_row['branch_name'],
                f"{invoice_row['amount']:.2f}",
                invoice_row['remarks'],
            ]
        writer.writerow([value or '' for value in row_values])

    return output.getvalue().encode('utf-8')


def generate_payment_file_xlsx(payment_type, invoice_rows):
    headers = PAYMENT_FILE_HEADERS.get(payment_type, PAYMENT_FILE_HEADERS['ICICI'])
    rows = []
    for invoice_row in invoice_rows:
        row_values = [
            invoice_row.get('invoice_no', ''),
            invoice_row.get('gst_number', ''),
            invoice_row.get('supplier_name', ''),
            invoice_row.get('beneficiary_name', ''),
            invoice_row.get('bank_name', ''),
            invoice_row.get('account_number', ''),
            invoice_row.get('ifsc_code', ''),
            invoice_row.get('branch_name', ''),
            float(invoice_row.get('amount') or 0),
            invoice_row.get('remarks', ''),
        ]
        rows.append(row_values)

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
