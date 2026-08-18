import csv
import io
import re
from decimal import Decimal, InvalidOperation

import pandas as pd

from .payment_file_service import build_payment_file_rows


def _header(value):
    return re.sub(r'[^a-z0-9]+', '', str(value or '').lower())


def _text(value):
    return re.sub(r'[^A-Z0-9]+', '', str(value or '').upper())


def _amount(value):
    try:
        return Decimal(re.sub(r'[^0-9.\-]', '', str(value or '0'))).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return Decimal('0.00')


def _read_rows(uploaded_file):
    name = (uploaded_file.name or '').lower()
    uploaded_file.seek(0)
    if name.endswith('.csv'):
        return list(csv.DictReader(io.StringIO(uploaded_file.read().decode('utf-8-sig'))))
    if name.endswith(('.xlsx', '.xls', '.xlsm')):
        uploaded_file.seek(0)
        return pd.read_excel(uploaded_file).fillna('').to_dict(orient='records')
    raise ValueError('Upload a CSV or Excel bank portal file.')


def _value(row, aliases):
    normalized = {_header(key): value for key, value in row.items()}
    for alias in aliases:
        if _header(alias) in normalized:
            return normalized[_header(alias)]
    return None


def compare_bank_file(payment_file, uploaded_file):
    expected = build_payment_file_rows(
        payment_file.payment_type,
        list(payment_file.due_report_rows.order_by('id')),
        overrides=payment_file.line_item_overrides or {},
    )
    actual = _read_rows(uploaded_file)

    actual_keys = set()
    for row in actual:
        account = _value(row, ['BENE_ACC_NO', 'BEN.ACCOU', 'beneficiary account', 'account number'])
        amount = _value(row, ['AMOUNT', 'AMT'])
        name = _value(row, ['BNF_NAME', 'BEN.NAME', 'beneficiary name'])
        actual_keys.add((_text(account), _amount(amount), _text(name)))

    # The beneficiary-name column is bank specific. SBI files contain the plain
    # supplier name in BEN.NAME, whereas ICICI files contain the generated
    # supplier-name + GST value in BNF_NAME.
    if payment_file.payment_type == 'SBI':
        expected_name = lambda row: row.get('supplier_name')
    else:
        expected_name = lambda row: row.get('bnf_name') or row.get('supplier_name')

    expected_keys = {
        (_text(row.get('account_number')), _amount(row.get('amount')), _text(expected_name(row)))
        for row in expected
    }
    missing = expected_keys - actual_keys
    unexpected = actual_keys - expected_keys
    return {
        'matches': not missing and not unexpected and len(expected) == len(actual),
        'expected_rows': len(expected),
        'uploaded_rows': len(actual),
        'missing_rows': len(missing),
        'unexpected_rows': len(unexpected),
    }
