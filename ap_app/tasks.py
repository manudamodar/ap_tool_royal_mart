import os
import time
import logging
import json
import re
import requests
import uuid
from decimal import Decimal, InvalidOperation # For accurate monetary comparisons
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient, AnalysisFeature

from .models import (
    OCRBatch,
    DocumentResult,
    BatchStatus,
    ReconciliationStatus,
    DueReportInvoiceWise,
    VendorMaster,
)
from .due_report_service import extract_gst_from_supplier_name
from .master_data_utils import get_cash_discount_details
from .reconciliation_service import build_bill_lookup, match_bill, apply_reconciliation

logger = logging.getLogger(__name__)

GSTIN_REGEX = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]\b", re.IGNORECASE)
HSN_SAC_CODE_REGEX = re.compile(r"\b\d{4,8}\b")


def _normalize_whitespace(value):
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", str(value)).strip(" :.-")
    return normalized or None


def _find_labeled_value(text, patterns):
    if not text:
        return None

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _normalize_whitespace(match.group(1))
    return None


def _normalize_bank_label(value):
    if not value:
        return None
    value = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
    return value or None


def _clean_account_number(value):
    if not value:
        return None
    cleaned = re.sub(r"[^0-9Xx*]", "", str(value)).upper()
    digit_count = sum(ch.isdigit() for ch in cleaned)
    if digit_count < 8 or digit_count > 18:
        return None
    return cleaned


def _clean_ifsc(value):
    if not value:
        return None
    match = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", str(value).upper())
    return match.group(1) if match else None


def _extract_vendor_bank_details(key_value_pairs):
    if not key_value_pairs:
        logger.info("No Azure key-value pairs available for bank extraction.")
        return {}

    bank_data = {}
    bank_candidates = []

    for pair in key_value_pairs:
        key = _normalize_whitespace(pair.key.content if getattr(pair, "key", None) else None)
        value = _normalize_whitespace(pair.value.content if getattr(pair, "value", None) else None)
        confidence = getattr(pair, "confidence", 0) or 0

        if not key or not value or confidence < 0.7:
            continue

        normalized_key = _normalize_bank_label(key)
        if not normalized_key:
            continue

        bank_candidates.append({
            "key": key,
            "value": value,
            "confidence": confidence,
        })

        if normalized_key in {"bank name", "name of bank", "beneficiary bank", "vendor bank"}:
            bank_data["bank_name"] = value
        elif normalized_key in {"ifsc", "ifsc code", "ifs code"}:
            cleaned_ifsc = _clean_ifsc(value)
            if cleaned_ifsc:
                bank_data["ifsc_code"] = cleaned_ifsc
        elif normalized_key in {"account no", "account number", "a c no", "a c number", "bank a c", "beneficiary account", "beneficiary account no"}:
            cleaned_account = _clean_account_number(value)
            if cleaned_account:
                bank_data["account_number"] = cleaned_account
        elif normalized_key in {"account holder", "account holder name", "beneficiary name", "name of beneficiary"}:
            bank_data["account_holder_name"] = value
        elif normalized_key in {"branch", "branch name", "bank branch"}:
            bank_data["branch_name"] = value
        elif normalized_key in {"micr", "micr code"}:
            bank_data["micr_code"] = value
        elif normalized_key in {"swift", "swift code"}:
            bank_data["swift_code"] = value

    has_reliable_bank_identity = any([
        bank_data.get("bank_name"),
        bank_data.get("ifsc_code"),
        bank_data.get("branch_name"),
        bank_data.get("micr_code"),
        bank_data.get("swift_code"),
    ])

    if not has_reliable_bank_identity:
        logger.info(
            "Discarded bank details from Azure key-value pairs due to missing reliable bank identity. Candidates=%s Parsed=%s",
            bank_candidates,
            bank_data,
        )
        return {}

    summary_parts = []
    for key, label in [
        ("bank_name", "Bank"),
        ("account_holder_name", "Account Holder"),
        ("account_number", "Account No"),
        ("ifsc_code", "IFSC"),
        ("branch_name", "Branch"),
        ("micr_code", "MICR"),
        ("swift_code", "SWIFT"),
    ]:
        value = _normalize_whitespace(bank_data.get(key))
        if value:
            summary_parts.append(f"{label}: {value}")

    if summary_parts:
        bank_data["vendor_bank"] = ", ".join(summary_parts)

    logger.info(
        "Accepted bank details from Azure key-value pairs. Candidates=%s Parsed=%s",
        bank_candidates,
        bank_data,
    )
    return bank_data


def _extract_hsn_or_sac(text):
    if not text:
        return None

    codes = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        if re.search(r"\b(?:hsn|sac)\b", line, flags=re.IGNORECASE):
            for match in HSN_SAC_CODE_REGEX.findall(line):
                if match not in codes:
                    codes.append(match)

    if not codes:
        for match in re.finditer(r"\b(?:hsn|sac)\s*(?:code)?\s*[:\-]?\s*([0-9 ,/]{4,200})", text, flags=re.IGNORECASE):
            for code in HSN_SAC_CODE_REGEX.findall(match.group(1)):
                if code not in codes:
                    codes.append(code)

    return ", ".join(codes) if codes else None


def _extract_gst_number(text, context_patterns):
    if not text:
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in context_patterns):
            window = " ".join(lines[max(0, index - 1): min(len(lines), index + 2)])
            match = GSTIN_REGEX.search(window)
            if match:
                return match.group(0).upper()

    return None


def _clean_vendor_name(value):
    """Normalize a vendor name and remove a GSTIN accidentally appended to it."""
    if not value:
        return None
    cleaned = GSTIN_REGEX.sub("", str(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,:.-/")
    return cleaned or None


def _extract_vendor_name_from_header(text):
    """Find the seller heading that Azure sometimes returns only partially."""
    if not text:
        return None

    lines = [_normalize_whitespace(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    noise = re.compile(
        r"^(?:tax invoice|invoice|original|duplicate|triplicate|e-?invoice|irn|"
        r"ack(?:nowledgement)?(?: no| date)?|dated|date|invoice no\.?|page\b)",
        flags=re.IGNORECASE,
    )

    # On standard tax invoices, the seller name is immediately before the
    # Invoice No./Dated heading. Search only a small window to avoid selecting
    # an address, buyer name, or item description.
    for index, line in enumerate(lines):
        if not re.fullmatch(r"invoice\s+no\.?", line, flags=re.IGNORECASE):
            continue
        for candidate in reversed(lines[max(0, index - 5):index]):
            if noise.search(candidate) or GSTIN_REGEX.search(candidate):
                continue
            if re.fullmatch(r"[0-9a-f-]{20,}", candidate, flags=re.IGNORECASE):
                continue
            if not re.search(r"[A-Za-z]", candidate):
                continue
            return _clean_vendor_name(candidate)
    return None


def _vendor_master_name(gst_number):
    if not gst_number:
        return None
    try:
        vendor = VendorMaster.objects.filter(
            gst_number__iexact=gst_number,
            is_active=True,
        ).first()
    except Exception:
        logger.exception("Could not look up vendor master for GST %s", gst_number)
        return None
    return _clean_vendor_name(vendor.supplier_name) if vendor else None


def _money_from_cell(value):
    if value in (None, ""):
        return None
    matches = re.findall(r"-?\d[\d,]*(?:\.\d+)?", str(value))
    if not matches:
        return None
    try:
        return sum(Decimal(match.replace(",", "")) for match in matches)
    except InvalidOperation:
        return None


def _calculate_total_tax_from_tables(tables):
    """Calculate total GST as CGST + SGST/UTGST + IGST from tax tables."""
    tax_label = re.compile(r"^(?:CGST|SGST|UTGST|SGST/UTGST|IGST)$", re.IGNORECASE)

    for table in tables or []:
        cells = table.get("cells", [])
        tax_headers = sorted(
            (
                (cell.get("column_index"), cell.get("row_index"))
                for cell in cells
                if tax_label.fullmatch(_normalize_whitespace(cell.get("content")) or "")
            ),
            key=lambda item: item[0],
        )
        if not tax_headers:
            continue

        max_column = max((cell.get("column_index", 0) for cell in cells), default=0)
        amount_columns = []
        amount_header_rows = []
        for position, (start_column, header_row) in enumerate(tax_headers):
            end_column = (
                tax_headers[position + 1][0] - 1
                if position + 1 < len(tax_headers)
                else max_column
            )
            amount_header = next((
                cell for cell in cells
                if header_row <= cell.get("row_index", -1) <= header_row + 2
                and start_column <= cell.get("column_index", -1) <= end_column
                and re.fullmatch(
                    r"(?:amount|tax\s*amt|tax\s*amount)",
                    _normalize_whitespace(cell.get("content")) or "",
                    re.IGNORECASE,
                )
            ), None)
            if amount_header:
                amount_columns.append(amount_header["column_index"])
                amount_header_rows.append(amount_header["row_index"])

        if not amount_columns:
            continue

        data_start_row = max(amount_header_rows) + 1
        total_rows = {
            cell.get("row_index")
            for cell in cells
            if cell.get("row_index", -1) >= data_start_row
            and
            re.fullmatch(r"(?:grand\s+)?total", _normalize_whitespace(cell.get("content")) or "", re.IGNORECASE)
        }

        # Prefer component totals, when present, so detail rows and their total
        # are not both counted. Otherwise sum every component detail amount.
        rows_to_use = total_rows or {
            cell.get("row_index") for cell in cells
            if cell.get("row_index", -1) >= data_start_row
        }
        component_values = []
        for row in rows_to_use:
            for column in amount_columns:
                cell = next((
                    item for item in cells
                    if item.get("row_index") == row and item.get("column_index") == column
                ), None)
                amount = _money_from_cell(cell.get("content")) if cell else None
                if amount is not None:
                    component_values.append(amount)

        if component_values:
            return sum(component_values, Decimal("0"))

    return None


def _extract_amount_below_table_header(tables, header_patterns):
    """Read the first monetary value below an exact summary-column header."""
    compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in header_patterns]
    for table in tables or []:
        cells = table.get("cells", [])
        headers = [
            cell for cell in cells
            if any(pattern.search(_normalize_whitespace(cell.get("content")) or "") for pattern in compiled_patterns)
        ]
        for header in headers:
            candidates = sorted(
                (
                    cell for cell in cells
                    if cell.get("column_index") == header.get("column_index")
                    and cell.get("row_index", -1) > header.get("row_index", -1)
                ),
                key=lambda cell: cell.get("row_index", 0),
            )
            for candidate in candidates:
                amount = _money_from_cell(candidate.get("content"))
                if amount is not None:
                    return amount
    return None


def enrich_invoice_fields(extracted_data, extracted_text, key_value_pairs=None):
    enriched_data = dict(extracted_data or {})
    text = extracted_text or ""

    enriched_data.update(_extract_vendor_bank_details(key_value_pairs))
    enriched_data["hsn_or_sac"] = _extract_hsn_or_sac(text)
    enriched_data["vendor_gst_number"] = _extract_gst_number(text, [
        r"\bvendor\b",
        r"\bsupplier\b",
        r"\bseller\b",
        r"\bfrom\b",
        r"\bconsignor\b",
        r"\bvendor gst\b",
        r"\bsupplier gst\b",
    ])
    enriched_data["customer_gst_number"] = _extract_gst_number(text, [
        r"\bcustomer\b",
        r"\bbuyer\b",
        r"\brecipient\b",
        r"\brcvr\b",
        r"\bbill to\b",
        r"\bship to\b",
        r"\bto\b",
        r"\broyal mart\b",
    ])

    if not enriched_data.get("vendor_gst_number"):
        gst_matches = [match.group(0).upper() for match in GSTIN_REGEX.finditer(text)]
        if len(gst_matches) == 1:
            enriched_data["vendor_gst_number"] = gst_matches[0]
        elif len(gst_matches) > 1 and not enriched_data.get("customer_gst_number"):
            enriched_data["vendor_gst_number"] = gst_matches[0]
            enriched_data["customer_gst_number"] = gst_matches[1]

    azure_name = _clean_vendor_name(enriched_data.get("vendor_name"))
    labeled_name = _find_labeled_value(text, [
        r"(?:vendor\s+name|supplier\s+name|seller\s+name)\s*[:\-]?\s*([A-Z0-9&.,()/ \-]{3,100})",
    ])
    header_name = _extract_vendor_name_from_header(text)
    master_name = _vendor_master_name(enriched_data.get("vendor_gst_number"))

    # GST master is canonical. Otherwise replace a truncated Azure result only
    # when the longer header/labeled value clearly contains that result.
    if master_name:
        enriched_data["vendor_name"] = master_name
    else:
        candidates = [_clean_vendor_name(labeled_name), header_name]
        better_name = next((
            candidate for candidate in candidates
            if candidate and (
                not azure_name
                or azure_name.casefold() in candidate.casefold()
            )
        ), None)
        enriched_data["vendor_name"] = better_name or azure_name

    return enriched_data

# Global list to store Azure credentials for round-robin
AZURE_CREDENTIALS = []
# Global counter for round-robin
AZURE_CREDENTIALS_INDEX = 0

def load_azure_credentials():
    """
    Loads Azure Form Recognizer endpoints and keys from environment variables
    (e.g., BPT_OCR1, BPT_OCR1_URL1, BPT_OCR2, BPT_OCR2_URL1)
    and prepares them for round-robin usage.
    """
    global AZURE_CREDENTIALS
    AZURE_CREDENTIALS = [] # Clear previous credentials if function is called again

    found_credentials = False
    for i in range(1, 4): # Check for up to 3 sets of credentials based on user's .env example
        key_var_name = f"BPT_OCR{i}"
        endpoint_var_name = f"BPT_OCR_URL{i}" # Corrected based on user's example BPT_OCR1_URL1 -> BPT_OCR_URL1

        key = os.environ.get(key_var_name)
        endpoint = os.environ.get(endpoint_var_name)

        if key and endpoint:
            AZURE_CREDENTIALS.append({'endpoint': endpoint.strip(), 'key': key.strip()})
            found_credentials = True
        elif key or endpoint: # One is present, but not the other
            logger.warning(f"Incomplete Azure Form Recognizer credential set found: {key_var_name} or {endpoint_var_name} is missing.")
            
    if not found_credentials:
        raise ValueError("No complete Azure Form Recognizer credential sets (e.g., BPT_OCR1 and BPT_OCR_URL1) found in environment variables.")

    logger.info(f"Loaded {len(AZURE_CREDENTIALS)} Azure Form Recognizer credential sets.")

def get_next_azure_credential():
    """
    Returns the next Azure credential set in a round-robin fashion.
    """
    global AZURE_CREDENTIALS_INDEX, AZURE_CREDENTIALS
    if not AZURE_CREDENTIALS:
        load_azure_credentials() # Attempt to load if not already loaded

    if not AZURE_CREDENTIALS: # If still empty after loading, something is wrong
        raise ValueError("No Azure Form Recognizer credentials available.")

    credential = AZURE_CREDENTIALS[AZURE_CREDENTIALS_INDEX]
    AZURE_CREDENTIALS_INDEX = (AZURE_CREDENTIALS_INDEX + 1) % len(AZURE_CREDENTIALS)
    return credential

def extract_data_from_image(file_path, endpoint, key):
    """
    Extracts invoice data using Azure Document Intelligence (Form Recognizer).
    """
    try:
        document_analysis_client = DocumentAnalysisClient(
            endpoint=endpoint, credential=AzureKeyCredential(key)
        )

        with open(file_path, "rb") as f:
            poller = document_analysis_client.begin_analyze_document(
                "prebuilt-invoice",
                document=f,
                features=[AnalysisFeature.KEY_VALUE_PAIRS],
            )
        result = poller.result()

        extracted_data = {}
        extracted_text = result.content

        # Assume we are processing the first invoice in the document
        if result.documents:
            invoice = result.documents[0]
            fields = invoice.fields

            extracted_data["invoice_number"] = fields.get("InvoiceId").value if fields.get("InvoiceId") else None
            extracted_data["vendor_name"] = fields.get("VendorName").value if fields.get("VendorName") else None
            
            # --- PRIORITY AMOUNT EXTRACTION LOGIC ---
            # 1. Try to get "AmountDue" (Net Payable) first
            if fields.get("AmountDue"):
                val = fields.get("AmountDue").value
                extracted_data["total_amount"] = val.amount if hasattr(val, 'amount') else val
            # 2. Fallback to "InvoiceTotal" if AmountDue is missing
            elif fields.get("InvoiceTotal"):
                val = fields.get("InvoiceTotal").value
                extracted_data["total_amount"] = val.amount if hasattr(val, 'amount') else val
            else:
                extracted_data["total_amount"] = None

            if fields.get("SubTotal"):
                val = fields.get("SubTotal").value
                extracted_data["goods_value"] = val.amount if hasattr(val, 'amount') else val
            else:
                extracted_data["goods_value"] = None

            if fields.get("TotalTax"):
                val = fields.get("TotalTax").value
                extracted_data["tax_amount"] = val.amount if hasattr(val, 'amount') else val
            else:
                extracted_data["tax_amount"] = None
                
            extracted_data["date"] = fields.get("InvoiceDate").value.isoformat() if fields.get("InvoiceDate") and fields.get("InvoiceDate").value else None

        # Extract Tables
        tables_data = []
        for table_idx, table in enumerate(result.tables):
            table_dict = {
                "table_id": table_idx,
                "row_count": table.row_count,
                "column_count": table.column_count,
                "cells": []
            }
            for cell in table.cells:
                table_dict["cells"].append({
                    "row_index": cell.row_index,
                    "column_index": cell.column_index,
                    "content": cell.content
                })
            tables_data.append(table_dict)

        if tables_data:
            extracted_data["tables"] = tables_data

        calculated_goods_value = _extract_amount_below_table_header(
            tables_data,
            [r"taxable\s+value", r"taxable\s+amt(?:ount)?"],
        )
        calculated_tax = _calculate_total_tax_from_tables(tables_data) or _extract_amount_below_table_header(
            tables_data,
            [r"tax\s+paid", r"total\s+tax"],
        )
        final_net_value = _extract_amount_below_table_header(
            tables_data,
            [r"net\s+value", r"net\s+payable"],
        )
        if calculated_goods_value is not None:
            extracted_data["goods_value"] = float(calculated_goods_value)
        if calculated_tax is not None:
            extracted_data["tax_amount"] = float(calculated_tax)
        if final_net_value is not None:
            extracted_data["total_amount"] = float(final_net_value)

        extracted_data = enrich_invoice_fields(extracted_data, extracted_text, result.key_value_pairs)

        return extracted_data, extracted_text
    except Exception as e:
        logger.error(f"Error in OCR extraction for {file_path} using endpoint {endpoint}: {e}")
        raise # Re-raise the exception to be caught by the calling task

def call_getbills_api(fin_year=None):
    """
    Calls the configured external getbills API.
    """
    api_url = getattr(settings, 'EXTERNAL_GETBILLS_URL', '').strip()
    if not api_url:
        logger.warning("External GETBILLS API is not configured. Returning empty bill list.")
        return None

    params = {}
    if fin_year:
        params["finYear"] = fin_year

    headers = {
        "Accept": "application/json",
        "X-Auth-Token": getattr(settings, 'EXTERNAL_GETBILLS_TOKEN', '').strip(),
    }

    timeout = (
        getattr(settings, 'EXTERNAL_GETBILLS_CONNECT_TIMEOUT_SECONDS', 15),
        getattr(settings, 'EXTERNAL_GETBILLS_READ_TIMEOUT_SECONDS', 600),
    )
    request_id = uuid.uuid4().hex[:12]
    started_at = timezone.now()
    started_clock = time.perf_counter()
    logger.info(
        '[THIRD_PARTY_API] ▶ START request_id=%s service=GoFrugal operation=GetBills '
        'method=GET fin_year=%s started_at=%s',
        request_id,
        fin_year or 'not-specified',
        started_at.isoformat(),
    )

    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        response_data = response.json()

        if isinstance(response_data, dict):
            if "data" in response_data:
                bills = response_data["data"]
            else:
                logger.error("GoFrugal response is missing the data field.")
                return None
        elif isinstance(response_data, list):
            bills = response_data
        else:
            logger.error(f"Unexpected GoFrugal response format: {type(response_data)}")
            return None

        if not isinstance(bills, list) or any(not isinstance(bill, dict) for bill in bills):
            logger.error("GoFrugal response data must be a list of bill objects.")
            return None

        logger.info(
            '[THIRD_PARTY_API] ✓ SUCCESS request_id=%s service=GoFrugal operation=GetBills '
            'http_status=%s rows=%s fin_year=%s completed_at=%s duration_ms=%.2f',
            request_id,
            response.status_code,
            len(bills),
            fin_year or 'not-specified',
            timezone.now().isoformat(),
            (time.perf_counter() - started_clock) * 1000,
        )
        return response_data, bills
    except requests.exceptions.ReadTimeout:
        logger.error(
            '[THIRD_PARTY_API] ✗ TIMEOUT request_id=%s service=GoFrugal operation=GetBills '
            'fin_year=%s timeout_seconds=%s failed_at=%s duration_ms=%.2f',
            request_id,
            fin_year or 'not-specified',
            timeout[1],
            timezone.now().isoformat(),
            (time.perf_counter() - started_clock) * 1000,
        )
        return None
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else 'unknown'
        logger.error(
            '[THIRD_PARTY_API] ✗ HTTP_ERROR request_id=%s service=GoFrugal operation=GetBills '
            'http_status=%s fin_year=%s failed_at=%s duration_ms=%.2f',
            request_id,
            status_code,
            fin_year or 'not-specified',
            timezone.now().isoformat(),
            (time.perf_counter() - started_clock) * 1000,
        )
        return None
    except requests.exceptions.RequestException as e:
        logger.error(
            '[THIRD_PARTY_API] ✗ NETWORK_ERROR request_id=%s service=GoFrugal operation=GetBills '
            'fin_year=%s error=%s failed_at=%s duration_ms=%.2f',
            request_id,
            fin_year or 'not-specified',
            str(e),
            timezone.now().isoformat(),
            (time.perf_counter() - started_clock) * 1000,
        )
        return None
    except json.JSONDecodeError as e:
        logger.error(
            '[THIRD_PARTY_API] ✗ INVALID_JSON request_id=%s service=GoFrugal operation=GetBills '
            'error=%s failed_at=%s duration_ms=%.2f',
            request_id,
            str(e),
            timezone.now().isoformat(),
            (time.perf_counter() - started_clock) * 1000,
        )
        return None
        return None

@shared_task
def process_ocr_batch(batch_id, folder_path):
    """
    Background task to process a batch of files, perform OCR, and reconcile with due report data.
    """
    logger.info(f"🚀 Started processing batch: {batch_id}. Looking for files in {folder_path}")
    
    reconciliation_summary = {
        ReconciliationStatus.VERIFIED: 0,
        ReconciliationStatus.MANUAL_REVIEW: 0,
        ReconciliationStatus.NO_MATCH: 0,
        "total_processed_for_reconciliation": 0,
        "errors_during_reconciliation": 0,
    }

    try:
        # Ensure credentials are loaded before starting processing
        load_azure_credentials()

        batch = OCRBatch.objects.get(pk=batch_id)
        batch.status = BatchStatus.PROCESSING
        batch.save()

        fetched_bills = [
            invoice_row_to_bill(row)
            for row in DueReportInvoiceWise.objects.all()
        ]
        if not fetched_bills:
            logger.warning(f"No bills fetched from the due report for batch {batch_id}. All documents will be marked as NO_MATCH or MANUAL_REVIEW.")

        bill_lookup = build_bill_lookup(fetched_bills)

        for root, _, files in os.walk(folder_path):
            total_in_folder = len(files)
            logger.info(f"📂 Found {total_in_folder} files to process for batch {batch_id}.")
            
            for index, file_name in enumerate(files, start=1):
                file_path = os.path.join(root, file_name)
                
                logger.info(f"⏳ [Batch {batch_id}] Processing file {index}/{total_in_folder}: {file_name}")
                
                document_result = None # Initialize document_result
                try:
                    # Get next credential set in round-robin
                    credential = get_next_azure_credential()
                    current_endpoint = credential['endpoint']
                    current_key = credential['key']
                    
                    # Perform actual OCR logic here using Azure Form Recognizer
                    extracted_data, extracted_text = extract_data_from_image(file_path, current_endpoint, current_key)

                    # Phase 3: Persistence & Cleanup
                    # 1. Save to DB (initially with PENDING reconciliation status)
                    document_result = DocumentResult.objects.create(
                        batch=batch,
                        original_filename=file_name,
                        extracted_text=extracted_text,
                        parsed_data=extracted_data,
                        reconciliation_status=ReconciliationStatus.PENDING # Set initial status
                    )
                    
                    # --- Reconciliation Logic ---
                    reconciliation_summary["total_processed_for_reconciliation"] += 1
                    matched_bill = match_bill(extracted_data, bill_lookup)
                    apply_reconciliation(document_result, extracted_data, matched_bill)
                    reconciliation_summary[document_result.reconciliation_status] += 1
                    # --- End Reconciliation Logic ---

                    # 2. Cleanup: delete the file from the VM disk
                    try:
                        os.remove(file_path)
                        logger.debug(f"🗑️ Deleted local temp file: {file_path}")
                    except Exception as e:
                        logger.error(f"❌ Failed to delete file {file_path}: {e}")
                    
                    # Update progress in DB (so frontend polling sees it)
                    batch.processed_files += 1
                    batch.save()
                    
                    # Log progress percentage
                    progress_pct = (batch.processed_files / batch.total_files) * 100 if batch.total_files > 0 else 0
                    logger.info(f"✅ [Batch {batch_id}] Progress: {batch.processed_files}/{batch.total_files} ({progress_pct:.1f}%)")
                except Exception as file_e:
                    logger.error(f"❌ Error processing file {file_name} in batch {batch_id}: {file_e}")
                    reconciliation_summary["errors_during_reconciliation"] += 1
                    if document_result:
                        document_result.reconciliation_status = ReconciliationStatus.MANUAL_REVIEW
                        document_result.reconciliation_details = {"error": str(file_e), "message": "Error during OCR or initial processing."}
                        document_result.save()
                    # Continue processing remaining files instead of failing the whole batch
                    batch.processed_files += 1
                    batch.save()
                    continue

        # Determine final batch status based on reconciliation results
        if reconciliation_summary[ReconciliationStatus.MANUAL_REVIEW] > 0 or \
           reconciliation_summary[ReconciliationStatus.NO_MATCH] > 0 or \
           reconciliation_summary["errors_during_reconciliation"] > 0:
            batch.status = BatchStatus.MANUAL_REVIEW
            logger.info(f"⚠️ Batch {batch_id} requires MANUAL_REVIEW due to discrepancies or errors.")
        else:
            batch.status = BatchStatus.COMPLETED
            logger.info(f"🎉 Batch {batch_id} COMPLETED. All documents VERIFIED.")
        batch.save()
        
        # Try to remove the empty directory
        try:
            os.rmdir(folder_path)
            logger.info(f"🧹 Cleaned up temporary directory: {folder_path}")
        except Exception as e:
            logger.warning(f"⚠️ Could not remove empty directory {folder_path}: {e}")

        completion_msg = f"🎉 Batch {batch_id} processing finished. Final Status: {batch.status}. Reconciliation Summary: {reconciliation_summary}"
        logger.info(completion_msg)
        return completion_msg

    except Exception as e:
        if 'batch' in locals():
            batch.status = BatchStatus.FAILED
            batch.save()
        error_msg = f"❌ Error processing batch {batch_id}: {e}"
        logger.error(error_msg)
        # Celery will mark the task as failed and store the exception
        raise # Re-raise the exception to propagate the error.

def _bill_to_invoice_row(bill):
    """Map a GetBills payload item to the invoice-wise due-report schema."""
    def first(*keys):
        for key in keys:
            value = bill.get(key)
            if value is not None and value != '':
                return value
        return None

    supplier_name = first('partyName', 'supplier_name')
    cleaned_supplier_name, embedded_gst = extract_gst_from_supplier_name(supplier_name)
    gst_number = str(embedded_gst or first('partyGSTNo', 'gst_number') or '').strip().upper() or None
    invoice_no = str(first('invoiceNo', 'invoice_no') or '').strip() or None
    return {
        'tran_year': first('tranYear', 'tran_year'),
        'branch_code': first('branchCode', 'branch_code'),
        'location_name': first('branchName', 'location_name'),
        'voucher_no': first('voucherNo', 'voucher_no'),
        'supplier_name': cleaned_supplier_name,
        'party_code': first('partyCode', 'party_code'),
        'gst_number': gst_number,
        'invoice_no': invoice_no,
        'ref_no': first('billRefNo', 'ref_no'),
        'bill_voucher_date': first('voucherDate', 'bill_voucher_date'),
        'bill_date': first('billDate', 'bill_date'),
        'invoice_date': first('invoiceDate', 'invoice_date'),
        'bill_amount': first('voucherAmount', 'bill_amount'),
        'payable': first('payable'),
        'expense_ledger': first('expenseLedger', 'expense_ledger'),
        'goods_value': first('goodsValue', 'goods_value'),
        'tax_amount': first('taxAmount', 'tax_amount'),
        'tax_code': first('taxCode', 'tax_code'),
        'tax_type': first('taxType', 'tax_type'),
        'tds_amount': first('tdsAmount', 'tds_amount'),
        'tds_section': first('tdsSection', 'tds_section'),
        'disc_amount': first('discAmount', 'disc_amount'),
        'amount_adjusted': first('amountAdjusted', 'amount_adjusted'),
        'balance_amount': first('payable', 'balanceAmount', 'balance_amount', 'voucherAmount'),
        'pending_adj_amt': first('pendingAdjAmt', 'pending_adj_amt'),
        'net_balance': first('netBalance', 'net_balance', 'payable'),
        'no_of_days': first('dueDays', 'no_of_days'),
        'due_date': first('dueDate', 'due_date'),
        'over_due_days': first('overDueDays', 'over_due_days'),
        'prior_date': first('priorDate', 'prior_date'),
        'group_name': first('groupName', 'group_name'),
        'voucher_type': first('voucherType', 'voucher_type'),
        'msme_type': first('msmeType', 'msme_type'),
        'party_contact': first('partyContact', 'party_contact'),
        'pay_mode': first('payMode', 'pay_mode'),
        'other_charges': first('otherCharges', 'other_charges'),
        'payment_status': first('paymentStatus', 'payment_status'),
        'transaction_link': first('transactionLink', 'transaction_link'),
        'email_id': first('emailId', 'email_id'),
        'bill_unique_id': first('billUniqueId', 'bill_unique_id'),
        'status': first('status') or 'PENDING',
    }


def invoice_row_to_bill(row):
    """Return the API-shaped bill used by reconciliation from a persisted row."""
    return {
        'id': row.id,
        'tranYear': row.tran_year,
        'branchCode': row.branch_code,
        'branchName': row.location_name,
        'voucherNo': row.voucher_no,
        'partyName': row.supplier_name,
        'partyCode': row.party_code,
        'partyGSTNo': row.gst_number,
        'invoiceNo': row.invoice_no,
        'billRefNo': row.ref_no,
        'voucherDate': row.bill_voucher_date,
        'billDate': row.bill_date,
        'invoiceDate': row.invoice_date,
        'voucherAmount': row.bill_amount,
        'payable': row.payable or row.balance_amount or row.net_balance or row.bill_amount,
        'expenseLedger': row.expense_ledger,
        'goodsValue': row.goods_value,
        'taxAmount': row.tax_amount,
        'taxCode': row.tax_code,
        'taxType': row.tax_type,
        'tdsAmount': row.tds_amount,
        'tdsSection': row.tds_section,
        'dueDays': row.no_of_days,
        'dueDate': row.due_date,
        'groupName': row.group_name,
        'voucherType': row.voucher_type,
        'paymentStatus': row.payment_status,
        'partyContact': row.party_contact,
        'payMode': row.pay_mode,
        'otherCharges': row.other_charges,
        'transactionLink': row.transaction_link,
        'emailId': row.email_id,
        'billUniqueId': row.bill_unique_id,
    }


def sync_bills_from_gofrugal(fin_year=None):
    """Fetch GoFrugal bills and upsert them into the invoice-wise table."""
    result = call_getbills_api(fin_year=fin_year)
    if result is None:
        return None

    response_data, bills = result
    mapped_rows = [_bill_to_invoice_row(bill) for bill in bills]
    valid_rows = [row for row in mapped_rows if row['invoice_no']]

    with transaction.atomic():
        current_keys = {(row['invoice_no'], row['gst_number']) for row in valid_rows}
        existing_rows = DueReportInvoiceWise.objects.only('id', 'invoice_no', 'gst_number')
        if fin_year:
            # A GetBills response is a snapshot of one financial year. Never
            # remove rows belonging to a different financial year.
            existing_rows = existing_rows.filter(tran_year=fin_year)
        stale_ids = [
            row.id
            for row in existing_rows
            if (row.invoice_no, row.gst_number) not in current_keys
        ]
        if stale_ids:
            DueReportInvoiceWise.objects.filter(id__in=stale_ids).delete()

        for row in valid_rows:
            DueReportInvoiceWise.objects.update_or_create(
                invoice_no=row['invoice_no'],
                gst_number=row['gst_number'],
                defaults=row,
            )

    return response_data, len(valid_rows)


def current_financial_year():
    """Return the current April-to-March financial year in TrueBooks format."""
    today = timezone.localdate()
    start_year = today.year if today.month >= 4 else today.year - 1
    return f'{start_year}_{start_year + 1}'


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
)
def sync_due_reports_task(self, fin_year=None):
    """Synchronize the latest due-report snapshot in a Celery worker."""
    target_fin_year = fin_year or current_financial_year()
    started_clock = time.perf_counter()
    logger.info(
        '[DUE_REPORT_SYNC] ▶ START task_id=%s fin_year=%s started_at=%s',
        self.request.id or 'direct-call',
        target_fin_year,
        timezone.now().isoformat(),
    )
    result = sync_bills_from_gofrugal(fin_year=target_fin_year)
    if result is None:
        logger.error(
            '[DUE_REPORT_SYNC] ✗ FAILED task_id=%s fin_year=%s failed_at=%s duration_ms=%.2f',
            self.request.id or 'direct-call',
            target_fin_year,
            timezone.now().isoformat(),
            (time.perf_counter() - started_clock) * 1000,
        )
        raise RuntimeError(f'Due-report synchronization failed for {target_fin_year}.')

    _, row_count = result
    logger.info(
        '[DUE_REPORT_SYNC] ✓ SUCCESS task_id=%s fin_year=%s rows=%s completed_at=%s duration_ms=%.2f',
        self.request.id or 'direct-call',
        target_fin_year,
        row_count,
        timezone.now().isoformat(),
        (time.perf_counter() - started_clock) * 1000,
    )
    return {'fin_year': target_fin_year, 'row_count': row_count}
