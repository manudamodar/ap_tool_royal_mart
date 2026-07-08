import math
import re
from datetime import datetime

import pandas as pd

GET_BILLS_DEFAULTS = {
    "tranYear": "",
    "branchCode": None,
    "branchName": "",
    "voucherNo": "",
    "voucherDate": "",
    "billRefNo": "",
    "billDate": "",
    "partyCode": None,
    "partyName": "",
    "voucherType": "",
    "invoiceNo": "",
    "invoiceDate": "",
    "voucherAmount": 0,
    "expenseLedger": "",
    "goodsValue": 0,
    "taxAmount": 0,
    "taxCode": "",
    "taxType": "",
    "tdsAmount": 0,
    "tdsSection": " ",
    "dueDays": 0,
    "dueDate": "",
    "payMode": "",
    "otherCharges": 0,
    "paymentStatus": "NOT PAID",
    "transactionLink": "",
    "payable": 0,
    "groupName": "",
    "billUniqueId": "",
}

DATE_KEYS = {"voucherDate", "invoiceDate", "dueDate", "billDate"}
NUMERIC_KEYS = {"voucherAmount", "goodsValue", "taxAmount", "payable", "otherCharges", "dueDays"}

COLUMN_ALIASES = {
    "tranyear": "tranYear",
    "branchcode": "branchCode",
    "branchname": "branchName",
    "locationname": "branchName",
    "voucherno": "voucherNo",
    "voucherdate": "voucherDate",
    "billvoucherdate": "voucherDate",
    "billrefno": "billRefNo",
    "refno": "billRefNo",
    "billdate": "billDate",
    "partycode": "partyCode",
    "partyname": "partyName",
    "suppliername": "partyName",
    "vouchertype": "voucherType",
    "invoiceno": "invoiceNo",
    "invoicedate": "invoiceDate",
    "voucheramount": "voucherAmount",
    "billamount": "voucherAmount",
    "expenseledger": "expenseLedger",
    "goodsvalue": "goodsValue",
    "taxamount": "taxAmount",
    "taxcode": "taxCode",
    "taxtype": "taxType",
    "msmetype": "taxType",
    "payable": "payable",
    "groupname": "groupName",
    "billuniqueid": "billUniqueId",
    "balanceamount": "payable",
    "netbalance": "payable",
    "discamount": "otherCharges",
    "amountadjusted": "otherCharges",
    "pendingadjamt": "otherCharges",
    "noofdays": "dueDays",
    "duedate": "dueDate",
    "overduedays": "dueDays",
    "priordate": "dueDate",
}

DUE_REPORT_STORAGE_COLUMN_ALIASES = {
    "locationname": "location_name",
    "suppliername": "supplier_name",
    "partyname": "supplier_name",
    "supplier": "supplier_name",
    "vendorname": "supplier_name",
    "vendor": "supplier_name",
    "gstin": "gst_number",
    "gstnumber": "gst_number",
    "suppliergstnumber": "gst_number",
    "suppliergstno": "gst_number",
    "invoiceno": "invoice_no",
    "refno": "ref_no",
    "billvoucherdate": "bill_voucher_date",
    "voucherdate": "bill_voucher_date",
    "invoicedate": "invoice_date",
    "billamount": "bill_amount",
    "discamount": "disc_amount",
    "amountadjusted": "amount_adjusted",
    "balanceamount": "balance_amount",
    "pendingadjamt": "pending_adj_amt",
    "netbalance": "net_balance",
    "noofdays": "no_of_days",
    "duedate": "due_date",
    "overduedays": "over_due_days",
    "priordate": "prior_date",
    "groupname": "group_name",
    "vouchertype": "voucher_type",
    "msmetype": "msme_type",
}

DUE_REPORT_STORAGE_FIELDS = (
    "location_name",
    "supplier_name",
    "gst_number",
    "invoice_no",
    "ref_no",
    "bill_voucher_date",
    "invoice_date",
    "bill_amount",
    "disc_amount",
    "amount_adjusted",
    "balance_amount",
    "pending_adj_amt",
    "net_balance",
    "no_of_days",
    "due_date",
    "over_due_days",
    "prior_date",
    "group_name",
    "voucher_type",
    "msme_type",
)

GSTIN_PATTERN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", re.IGNORECASE)


def _normalize_header_name(value):
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _json_safe_excel_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d 00:00:00")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d 00:00:00")
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 3)
    return value


def _normalize_numeric_value(value):
    safe_value = _json_safe_excel_value(value)
    if safe_value is None:
        return None
    if isinstance(safe_value, str):
        cleaned = safe_value.strip().replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return safe_value
    if isinstance(safe_value, (int, float)):
        return float(safe_value)
    return safe_value


def _normalize_date_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d 00:00:00")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d 00:00:00")
    if isinstance(value, (int, float)):
        if math.isnan(value) or math.isinf(value):
            return None
        try:
            return pd.to_datetime(value, unit="D").strftime("%Y-%m-%d 00:00:00")
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = pd.to_datetime(text, errors="coerce")
            if pd.notna(parsed):
                return parsed.strftime("%Y-%m-%d 00:00:00")
        except Exception:
            pass
        for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y"):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.strftime("%Y-%m-%d 00:00:00")
            except ValueError:
                continue
    return _json_safe_excel_value(value)


def _excel_value_to_text(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        if value.is_integer():
            return str(int(value))
    return str(value).strip()


def _extract_gst_from_supplier_name(supplier_name):
    if not supplier_name:
        return supplier_name, ""

    supplier_text = str(supplier_name).strip()
    match = GSTIN_PATTERN.search(supplier_text)
    if not match:
        return supplier_text, ""

    gst_number = match.group(0).upper()
    cleaned_supplier_name = f"{supplier_text[:match.start()]} {supplier_text[match.end():]}"
    cleaned_supplier_name = re.sub(r"\s+", " ", cleaned_supplier_name).strip()
    return cleaned_supplier_name, gst_number


def parse_due_report(file_obj):
    file_obj.seek(0)
    df = pd.read_excel(file_obj)
    df = df.dropna(how="all")

    rows = []
    storage_rows = []

    for _, row in df.iterrows():
        bill = GET_BILLS_DEFAULTS.copy()
        stored_row = {field: None for field in DUE_REPORT_STORAGE_FIELDS}

        for column, value in row.items():
            normalized_header = _normalize_header_name(column)
            api_key = COLUMN_ALIASES.get(normalized_header)
            storage_key = DUE_REPORT_STORAGE_COLUMN_ALIASES.get(normalized_header)

            if api_key:
                if api_key in DATE_KEYS:
                    bill[api_key] = _normalize_date_value(value)
                elif api_key in NUMERIC_KEYS:
                    bill[api_key] = _normalize_numeric_value(value)
                else:
                    bill[api_key] = _json_safe_excel_value(value)

            if storage_key:
                stored_row[storage_key] = _excel_value_to_text(value)

        if not bill.get("dueDate") and bill.get("invoiceDate"):
            bill["dueDate"] = bill["invoiceDate"]

        if isinstance(bill.get("invoiceNo"), str):
            bill["invoiceNo"] = bill["invoiceNo"].strip()

        if bill.get("invoiceNo"):
            rows.append(bill)

        if any(value not in (None, "") for value in stored_row.values()):
            storage_rows.append(stored_row)

    return rows, storage_rows


def extract_gst_from_supplier_name(supplier_name):
    return _extract_gst_from_supplier_name(supplier_name)
