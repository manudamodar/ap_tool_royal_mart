import logging
import time
import uuid
from datetime import date, datetime

import requests
from django.conf import settings
from django.utils import timezone

from .payment_file_service import _select_amount


logger = logging.getLogger(__name__)


class TrueBooksPaymentError(Exception):
    pass


def _endpoint(setting_name, path):
    explicit_url = getattr(settings, setting_name, '').strip()
    if explicit_url:
        return explicit_url

    base_url = getattr(settings, 'EXTERNAL_TRUEBOOKS_BASE_URL', '').strip().rstrip('/')
    if not base_url:
        getbills_url = getattr(settings, 'EXTERNAL_GETBILLS_URL', '').strip()
        marker = '/TrueBooks/'
        if marker in getbills_url:
            base_url = getbills_url.split(marker, 1)[0]
    if not base_url:
        raise TrueBooksPaymentError('TrueBooks payment API is not configured.')
    return f"{base_url}{path}"


def _headers():
    return {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Auth-Token': getattr(settings, 'EXTERNAL_GETBILLS_TOKEN', '').strip(),
    }


def _timeout():
    return (
        getattr(settings, 'EXTERNAL_GETBILLS_CONNECT_TIMEOUT_SECONDS', 15),
        getattr(settings, 'EXTERNAL_GETBILLS_READ_TIMEOUT_SECONDS', 600),
    )


def _post(setting_name, path, payload):
    url = _endpoint(setting_name, path)
    operation = 'AcknowledgeBill' if path.endswith('/approvebills') else 'CentralPayment'
    request_id = uuid.uuid4().hex[:12]
    started_clock = time.perf_counter()
    logger.info(
        '[THIRD_PARTY_API] ▶ START request_id=%s service=TrueBooks operation=%s '
        'method=POST started_at=%s',
        request_id,
        operation,
        timezone.now().isoformat(),
    )
    try:
        response = requests.post(url, headers=_headers(), json=payload, timeout=_timeout())
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        status_code = getattr(getattr(exc, 'response', None), 'status_code', 'unavailable')
        logger.exception(
            '[THIRD_PARTY_API] ✗ FAILED request_id=%s service=TrueBooks operation=%s '
            'http_status=%s error=%s failed_at=%s duration_ms=%.2f',
            request_id,
            operation,
            status_code,
            str(exc),
            timezone.now().isoformat(),
            (time.perf_counter() - started_clock) * 1000,
        )
        raise TrueBooksPaymentError(f'TrueBooks request failed: {exc}') from exc
    if not isinstance(data, dict):
        logger.error(
            '[THIRD_PARTY_API] ✗ INVALID_RESPONSE request_id=%s service=TrueBooks operation=%s '
            'http_status=%s failed_at=%s duration_ms=%.2f',
            request_id,
            operation,
            response.status_code,
            timezone.now().isoformat(),
            (time.perf_counter() - started_clock) * 1000,
        )
        raise TrueBooksPaymentError('TrueBooks returned an invalid response.')
    logger.info(
        '[THIRD_PARTY_API] ✓ SUCCESS request_id=%s service=TrueBooks operation=%s '
        'http_status=%s result=%s completed_at=%s duration_ms=%.2f',
        request_id,
        operation,
        response.status_code,
        data.get('status') or data.get('result') or 'not-provided',
        timezone.now().isoformat(),
        (time.perf_counter() - started_clock) * 1000,
    )
    return data


def approve_bill(invoice):
    approval_id = (invoice.voucher_no or '').strip()
    if not approval_id:
        raise TrueBooksPaymentError('Invoice has no TrueBooks voucher number.')
    data = _post(
        'EXTERNAL_TRUEBOOKS_APPROVEBILLS_URL',
        '/TrueBooks/rest/payable/approvebills',
        [{'approvalId': approval_id, 'approvalStatus': 'C'}],
    )
    top_status = str(data.get('status') or data.get('result') or '').strip().lower()
    top_message = str(data.get('message') or '').strip()
    result_data = data.get('data')

    # TrueBooks deployments return either the documented list, a single result
    # object, or only a top-level success response. Because this request contains
    # exactly one bill, a sole result object/row belongs to this approval even if
    # approvalId is omitted or serialized differently.
    if isinstance(result_data, dict):
        result_rows = [result_data]
    elif isinstance(result_data, list):
        result_rows = [row for row in result_data if isinstance(row, dict)]
    else:
        result_rows = []

    matched = next(
        (row for row in result_rows if str(row.get('approvalId') or '').strip() == approval_id),
        result_rows[0] if len(result_rows) == 1 else None,
    )
    item_status = str((matched or {}).get('status') or '').strip().lower()
    explicit_item_failure = matched is not None and item_status not in ('', 'success')
    top_success = top_status == 'success' or top_message.lower() == 'success'

    if not top_success or explicit_item_failure:
        failure_message = (
            (matched or {}).get('message')
            or (matched or {}).get('status')
            or top_message
            or 'Bill acknowledgement failed.'
        )
        raise TrueBooksPaymentError(failure_message)


def _voucher_date(invoice):
    for value in (invoice.bill_voucher_date, invoice.bill_date, invoice.invoice_date):
        text = str(value or '').strip()
        if not text:
            continue
        for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
            try:
                return datetime.strptime(text, fmt).strftime('%d-%m-%Y')
            except ValueError:
                pass
    return date.today().strftime('%d-%m-%Y')


def create_central_payment(invoice):
    bill_id = (invoice.voucher_no or '').strip()
    if not bill_id:
        raise TrueBooksPaymentError('Invoice has no TrueBooks voucher number.')
    amount = _select_amount(invoice)
    party_code = str(invoice.party_code or '')
    payload = {
        'tranYear': invoice.tran_year or '',
        'partyCode': party_code,
        'voucherDate': _voucher_date(invoice),
        'remarks': f'Payment for invoice {invoice.invoice_no or ""}'.strip(),
        'paidAmount': float(amount),
        'bankName': getattr(settings, 'TRUEBOOKS_PAYMENT_BANK_NAME', '') or '',
        'bankCode': getattr(settings, 'TRUEBOOKS_PAYMENT_BANK_CODE', '') or party_code,
        'mode': getattr(settings, 'TRUEBOOKS_PAYMENT_MODE', 'C') or 'C',
        'chequeNo': getattr(settings, 'TRUEBOOKS_PAYMENT_CHEQUE_NO', '') or '',
        'branchName': invoice.location_name or '',
        'chequeName': ' '.join(filter(None, [invoice.supplier_name, invoice.gst_number])),
        'billList': [{'billId': bill_id, 'amount': float(amount)}],
    }
    data = _post(
        'EXTERNAL_TRUEBOOKS_CENTRAL_PAYMENT_URL',
        '/TrueBooks/rest/central-payment',
        payload,
    )
    reference = str(data.get('hoVoucherNo') or '').strip()
    if str(data.get('result', '')).lower() != 'success' or not reference:
        raise TrueBooksPaymentError(data.get('message') or 'Central payment failed.')
    return reference
