import os
import time
import logging
import json
import re
import requests # Import requests for API calls
from decimal import Decimal, InvalidOperation # For accurate monetary comparisons
from celery import shared_task
from django.conf import settings
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient, AnalysisFeature

from .models import OCRBatch, DocumentResult, BatchStatus, ReconciliationStatus

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


def enrich_invoice_fields(extracted_data, extracted_text, key_value_pairs=None):
    enriched_data = dict(extracted_data or {})
    text = extracted_text or ""

    if not enriched_data.get("vendor_name"):
        enriched_data["vendor_name"] = _find_labeled_value(text, [
            r"(?:vendor\s+name|supplier\s+name|seller\s+name)\s*[:\-]?\s*([A-Z0-9&.,()/ \-]{3,100})",
        ])

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

        extracted_data = enrich_invoice_fields(extracted_data, extracted_text, result.key_value_pairs)

        return extracted_data, extracted_text
    except Exception as e:
        logger.error(f"Error in OCR extraction for {file_path} using endpoint {endpoint}: {e}")
        raise # Re-raise the exception to be caught by the calling task

def call_getbills_api(fin_year="2025_2026"):
    """
    Calls the local getbills API to fetch payable bills.
    """
    api_url = f"http://localhost:8000/api/rest/payable/getbills?finYear={fin_year}"
    try:
        response = requests.get(api_url)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        if data.get("status") == "success" and "data" in data:
            logger.info(f"Successfully fetched {len(data['data'])} bills from API for {fin_year}.")
            return data["data"]
        else:
            logger.error(f"API response indicates failure or missing data: {data}")
            return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling getbills API for {fin_year}: {e}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from getbills API response: {e}")
        return []

@shared_task
def process_ocr_batch(batch_id, folder_path):
    """
    Background task to process a batch of files, perform OCR, and reconcile with API data.
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

        # Fetch all bills from the API once for the entire batch
        # Assuming all invoices in a batch belong to the same financial year for now
        # You might need to pass fin_year as a parameter to the task if it varies per batch
        fetched_bills = call_getbills_api(fin_year="2025_2026")
        if not fetched_bills:
            logger.warning(f"No bills fetched from API for batch {batch_id}. All documents will be marked as NO_MATCH or MANUAL_REVIEW.")

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
                    ocr_invoice_number = extracted_data.get("invoice_number")
                    ocr_total_amount = extracted_data.get("total_amount")

                    matched_bill = None
                    reconciliation_details = {}

                    if ocr_invoice_number:
                        # Find a matching bill from the API data
                        for bill in fetched_bills:
                            if bill.get("invoiceNo") == ocr_invoice_number:
                                matched_bill = bill
                                break
                    
                    if matched_bill:
                        document_result.matched_bill_data = matched_bill
                        api_payable_amount = matched_bill.get("payable")

                        if ocr_total_amount is not None and api_payable_amount is not None:
                            try:
                                ocr_amount_decimal = Decimal(str(ocr_total_amount))
                                api_amount_decimal = Decimal(str(api_payable_amount))

                                if ocr_amount_decimal == api_amount_decimal:
                                    document_result.reconciliation_status = ReconciliationStatus.VERIFIED
                                    reconciliation_summary[ReconciliationStatus.VERIFIED] += 1
                                    reconciliation_details["message"] = "Invoice number and total amount matched."
                                else:
                                    document_result.reconciliation_status = ReconciliationStatus.MANUAL_REVIEW
                                    reconciliation_summary[ReconciliationStatus.MANUAL_REVIEW] += 1
                                    reconciliation_details["message"] = "Invoice number matched, but total amount differs."
                                    reconciliation_details["ocr_amount"] = str(ocr_total_amount)
                                    reconciliation_details["api_amount"] = str(api_payable_amount)
                                    logger.warning(f"File {file_name}: {reconciliation_details['message']} (OCR: {ocr_total_amount}, API: {api_payable_amount})")
                            except InvalidOperation:
                                document_result.reconciliation_status = ReconciliationStatus.MANUAL_REVIEW
                                reconciliation_summary[ReconciliationStatus.MANUAL_REVIEW] += 1
                                reconciliation_details["message"] = "Invoice number matched, but OCR amount could not be parsed for comparison."
                                reconciliation_details["ocr_amount"] = str(ocr_total_amount)
                                reconciliation_details["api_amount"] = str(api_payable_amount)
                                logger.warning(f"File {file_name}: {reconciliation_details['message']}")
                        else:
                            document_result.reconciliation_status = ReconciliationStatus.MANUAL_REVIEW
                            reconciliation_summary[ReconciliationStatus.MANUAL_REVIEW] += 1
                            reconciliation_details["message"] = "Invoice number matched, but OCR or API total amount was missing for comparison."
                            reconciliation_details["ocr_amount"] = str(ocr_total_amount)
                            reconciliation_details["api_amount"] = str(api_payable_amount)
                            logger.warning(f"File {file_name}: {reconciliation_details['message']}")
                    else:
                        document_result.reconciliation_status = ReconciliationStatus.NO_MATCH
                        reconciliation_summary[ReconciliationStatus.NO_MATCH] += 1
                        reconciliation_details["message"] = "No matching bill found in API data for OCR invoice number."
                        reconciliation_details["ocr_invoice_number"] = ocr_invoice_number
                        reconciliation_details["ocr_total_amount"] = str(ocr_total_amount) if ocr_total_amount is not None else None
                        logger.warning(f"File {file_name}: {reconciliation_details['message']} (OCR Invoice: {ocr_invoice_number})")
                        
                    document_result.reconciliation_details = reconciliation_details
                    document_result.save() # Save reconciliation results
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
                    # If document_result was created, mark it as manual review due to processing error
                    if document_result:
                        document_result.reconciliation_status = ReconciliationStatus.MANUAL_REVIEW
                        document_result.reconciliation_details = {"error": str(file_e), "message": "Error during OCR or initial processing."}
                        document_result.save()
                    # Re-raise to fail the entire batch if any file fails
                    raise 

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
