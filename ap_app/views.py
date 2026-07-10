import os
import json
import re
import msal
import logging
import requests
import base64
import math
import pandas as pd
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.shortcuts import redirect
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import FileSystemStorage
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import (
    UserProfile,
    UserRole,
    OCRBatch,
    DocumentResult,
    BatchStatus,
    ReconciliationStatus,
    DueReportUpload,
    DueReportInvoiceWise,
    DueReportUnknown,
    PaymentFile,
    PaymentFileInvoice,
)
from .tasks import process_ocr_batch
from .due_report_service import parse_due_report, extract_gst_from_supplier_name
from .master_data_utils import get_cash_discount_details
from .payment_file_service import create_payment_file_record, build_payment_file_rows, generate_payment_file_xlsx
from .reconciliation_service import build_bill_lookup, match_bill, apply_reconciliation
from .reconciliation_service import sync_due_report_invoice_reconciliation

logger = logging.getLogger(__name__)

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
    # GST / tax identifiers
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


def _persist_due_report_rows(due_report, rows, uploaded_by):
    invoice_wise_rows = []
    unknown_rows = []
    update_candidates = []
    invoice_keys = []

    for row in rows:
        original_supplier_name = row.get("supplier_name")
        cleaned_supplier_name, gst_number = extract_gst_from_supplier_name(original_supplier_name)
        invoice_no = (row.get("invoice_no") or "").strip()

        if invoice_no and gst_number:
            invoice_keys.append((invoice_no, gst_number))

    existing_rows = []
    if invoice_keys:
        invoice_nos = [invoice_no for invoice_no, _ in invoice_keys]
        gst_numbers = [gst_number for _, gst_number in invoice_keys]
        existing_rows = DueReportInvoiceWise.objects.filter(
            invoice_no__in=invoice_nos,
            gst_number__in=gst_numbers,
        )

    existing_map = {(row.invoice_no, row.gst_number): row for row in existing_rows}

    invoice_wise_count = 0
    for row in rows:
        original_supplier_name = row.get("supplier_name")
        cleaned_supplier_name, gst_number = extract_gst_from_supplier_name(original_supplier_name)
        invoice_no = (row.get("invoice_no") or "").strip()

        row_data = row.copy()
        row_data["gst_number"] = gst_number or None
        row_data["supplier_name"] = cleaned_supplier_name

        base_data = {
            **row_data,
            "due_report": due_report,
            "uploaded_by": uploaded_by,
            "is_from_excel": True,
            "is_from_api": False,
        }
        invoice_row_data = {
            **base_data,
            "invoice_scanned": False,
            "invoice_reconciliation_status": 'UNVERIFIED',
        }

        if invoice_no and gst_number:
            key = (invoice_no, gst_number)
            existing_row = existing_map.get(key)
            if existing_row:
                for field_name, value in invoice_row_data.items():
                    setattr(existing_row, field_name, value)
                if existing_row not in update_candidates:
                    update_candidates.append(existing_row)
            else:
                invoice_wise_rows.append(DueReportInvoiceWise(**invoice_row_data))
            invoice_wise_count += 1
        else:
            unknown_rows.append(DueReportUnknown(
                **base_data,
                status="MANUAL_REVIEW",
            ))

    if invoice_wise_rows:
        DueReportInvoiceWise.objects.bulk_create(invoice_wise_rows)
    if update_candidates:
        DueReportInvoiceWise.objects.bulk_update(
            update_candidates,
            fields=[
                'due_report', 'uploaded_by', 'status', 'is_from_excel', 'is_from_api',
                'location_name', 'supplier_name', 'gst_number', 'invoice_no', 'ref_no',
                'bill_voucher_date', 'invoice_date', 'bill_amount', 'disc_amount',
                'amount_adjusted', 'balance_amount', 'pending_adj_amt', 'net_balance',
                'no_of_days', 'due_date', 'over_due_days', 'prior_date', 'group_name',
                'voucher_type', 'msme_type',
                'invoice_scanned', 'invoice_reconciliation_status',
            ],
        )
    if unknown_rows:
        DueReportUnknown.objects.bulk_create(unknown_rows)

    return invoice_wise_count, len(unknown_rows)


def _parse_due_report_excel(file_obj):
    df = pd.read_excel(file_obj)
    df = df.dropna(how="all")

    rows = []
    for _, row in df.iterrows():
        bill = GET_BILLS_DEFAULTS.copy()
        for column, value in row.items():
            target_key = COLUMN_ALIASES.get(_normalize_header_name(column))
            if not target_key:
                continue

            if target_key in {"voucherDate", "invoiceDate", "dueDate", "billDate"}:
                bill[target_key] = _normalize_date_value(value)
            elif target_key in {"voucherAmount", "goodsValue", "taxAmount", "payable", "otherCharges", "dueDays"}:
                bill[target_key] = _normalize_numeric_value(value)
            else:
                bill[target_key] = _json_safe_excel_value(value)

        if not bill.get("dueDate") and bill.get("invoiceDate"):
            bill["dueDate"] = bill["invoiceDate"]

        if isinstance(bill.get("invoiceNo"), str):
            bill["invoiceNo"] = bill["invoiceNo"].strip()

        if bill.get("invoiceNo"):
            rows.append(bill)

    return rows

def get_msal_app():
    return msal.ConfidentialClientApplication(
        settings.MSAL_CLIENT_ID,
        authority=settings.MSAL_AUTHORITY,
        client_credential=settings.MSAL_CLIENT_SECRET,
    )

def msal_login(request):
    msal_app = get_msal_app()
    auth_url = msal_app.get_authorization_request_url(
        settings.MSAL_SCOPES,
        redirect_uri=settings.MSAL_REDIRECT_URI,
        prompt="select_account"
    )
    return redirect(auth_url)

@csrf_exempt
def msal_callback(request):
    logger.info("MSAL callback initiated.")
    code = request.GET.get('code')
    if not code:
        logger.error("Authorization code not found in callback.")
        return JsonResponse({"error": "Authorization code not found"}, status=400)

    msal_app = get_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=settings.MSAL_SCOPES,
        redirect_uri=settings.MSAL_REDIRECT_URI
    )

    if "error" in result:
        logger.error(f"MSAL token acquisition error: {result.get('error_description')}")
        return JsonResponse({"error": result.get("error_description")}, status=400)

    # Now that we have an access token, fetch the user's photo using Graph API
    access_token = result.get('access_token')
    photo_data = None
    if access_token:
        try:
            logger.info("Attempting to fetch user photo from Microsoft Graph API.")
            headers = {'Authorization': f'Bearer {access_token}'}
            photo_response = requests.get('https://graph.microsoft.com/v1.0/me/photo/$value', headers=headers)
            
            if photo_response.status_code == 200:
                # Convert the raw image bytes to a base64 string for easy storage and frontend rendering
                image_bytes = photo_response.content
                content_type = photo_response.headers.get('Content-Type', 'image/jpeg')
                base64_encoded = base64.b64encode(image_bytes).decode('utf-8')
                photo_data = f"data:{content_type};base64,{base64_encoded}"
                logger.info("Successfully fetched and encoded user photo.")
            else:
                logger.warning(f"Could not fetch photo. Status code: {photo_response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching photo from Graph API: {e}")

    user_info = result.get('id_token_claims', {})
    logger.info(f"User info from MSAL: {user_info}")
    
    email = user_info.get('preferred_username') or user_info.get('email') or user_info.get('upn')
    name = user_info.get('name', 'Unknown User')
    
    if not email:
        logger.error("Could not extract email from MSAL payload.")
        return JsonResponse({"error": "Could not extract email from Microsoft payload. Check token claims.", "raw_claims": user_info}, status=400)
    
    # Role assignment logic removed. UserProfile will default to UNASSIGNED.
    logger.info(f"User {email} will be created/retrieved with an UNASSIGNED role.")

    # We can try to extract first and last name from 'name'
    first_name = name.split()[0] if name else ''
    last_name = " ".join(name.split()[1:]) if name and len(name.split()) > 1 else ''

    user, user_created = User.objects.get_or_create(username=email, defaults={'email': email, 'first_name': first_name, 'last_name': last_name})
    
    # If the user already existed, update their names if possible
    if not user_created:
        user.first_name = first_name
        user.last_name = last_name
        user.save()

    logger.info(f"User {'created' if user_created else 'retrieved'}: {user.username}")
    
    profile, profile_created = UserProfile.objects.get_or_create(user=user)
    logger.info(f"UserProfile {'created' if profile_created else 'retrieved'} for user {user.username}. Role is {profile.role}.")

    # Update MSAL data and photo.
    if profile.msal_data:
        updated_data = profile.msal_data.copy()
        updated_data.update(user_info)
        profile.msal_data = updated_data
    else:
        profile.msal_data = user_info

    if photo_data:
        profile.profile_photo = photo_data
    profile.save()
    logger.info(f"UserProfile for {user.username} saved successfully.")

    login(request, user)
    logger.info(f"User {user.username} logged into Django session.")
    
    return redirect('/')

@csrf_exempt
def msal_logout(request):
    logout(request)
    authority = settings.MSAL_AUTHORITY
    post_logout_redirect_uri = request.build_absolute_uri('/')
    logout_url = f"{authority}/oauth2/v2.0/logout?post_logout_redirect_uri={post_logout_redirect_uri}"
    return JsonResponse({"status": "logged_out", "logout_url": logout_url})

def get_user_info(request):
    if request.user.is_authenticated:
        try:
            profile = UserProfile.objects.get(user=request.user)
            role = profile.role
            msal_data = profile.msal_data
            photo = profile.profile_photo
            account_manager = profile.account_manager
        except UserProfile.DoesNotExist:
            role = UserRole.UNASSIGNED
            msal_data = {}
            photo = None
            account_manager = None
            
        account_manager_data = {
            'id': account_manager.id,
            'username': account_manager.username,
            'email': account_manager.email,
        } if account_manager else None

        full_name = f"{request.user.first_name} {request.user.last_name}".strip()
        if not full_name:
            full_name = request.user.username

        return JsonResponse({
            "authenticated": True,
            "username": request.user.username,
            "role": role,
            "email": request.user.email,
            "first_name": request.user.first_name,
            "full_name": full_name,
            "msal_data": msal_data,
            "photo": photo,
            "account_manager": account_manager_data,
        })
    else:
        return JsonResponse({"authenticated": False})


# --- FOR TESTING: User Type Allocation Change Feature (To be removed later) ---
@csrf_exempt
def change_user_role(request):
    """
    FOR TESTING ONLY: Allows a user to change their own role.
    TODO: REMOVE THIS ENDPOINT AND UI COMPONENT IN PRODUCTION.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
        
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_role = data.get('role')
            
            if new_role not in [role[0] for role in UserRole.choices]:
                return JsonResponse({"error": "Invalid role specified"}, status=400)
                
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            profile.role = new_role
            profile.save()
            
            return JsonResponse({"message": "Role updated successfully", "new_role": profile.role})
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
             return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Method not allowed"}, status=405)
# -----------------------------------------------------------------------------

# --- OCR Workflow Views ---

@csrf_exempt
def upload_due_report(request):
    """
    Uploads the due report workbook that becomes the source for GetBills
    reconciliation data.
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    report_file = request.FILES.get('file')
    if not report_file:
        return JsonResponse({"error": "No due report file provided"}, status=400)

    filename = os.path.basename(report_file.name)
    if not filename.lower().endswith(".xlsx"):
        return JsonResponse({"error": "Please upload an Excel due report file (.xlsx)."}, status=400)

    try:
        rows, storage_rows = parse_due_report(report_file)
    except Exception as e:
        logger.error(f"Failed to parse due report {filename}: {e}")
        return JsonResponse({"error": f"Unable to parse due report: {e}"}, status=400)

    if not rows and not storage_rows:
        return JsonResponse({"error": "No bill rows were found in the due report."}, status=400)

    with transaction.atomic():
        due_report = DueReportUpload.objects.create(
            original_filename=filename,
            uploaded_by=request.user,
            row_count=len(storage_rows),
            data=rows,
        )
        invoice_wise_count, unknown_count = _persist_due_report_rows(
            due_report=due_report,
            rows=storage_rows,
            uploaded_by=request.user,
        )

    # Debug logging controlled by settings.LOGGER_MODE_DEBUG
    if getattr(settings, 'LOGGER_MODE_DEBUG', False):
        logger.debug("Due report parsed: filename=%s, parsed_rows=%d, storage_rows=%d", filename, len(rows), len(storage_rows))
        try:
            logger.debug("Parsed rows sample: %s", rows[:10])
            logger.debug("Storage rows sample: %s", storage_rows[:10])
        except Exception:
            logger.debug("Parsed/storage rows contain non-serializable items; skipping sample output")

    return JsonResponse({
        "message": "Due report uploaded successfully",
        "due_report": {
            "id": due_report.id,
            "filename": due_report.original_filename,
            "uploaded_at": due_report.uploaded_at,
            "row_count": due_report.row_count,
            "invoice_wise_count": invoice_wise_count,
            "unknown_count": unknown_count,
        }
    }, status=201)


def get_current_due_report(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    due_report = DueReportUpload.objects.filter(uploaded_by=request.user).order_by('-uploaded_at').first()
    if not due_report:
        return JsonResponse({"due_report": None})

    return JsonResponse({
        "due_report": {
            "id": due_report.id,
            "filename": due_report.original_filename,
            "uploaded_at": due_report.uploaded_at,
            "row_count": due_report.row_count,
        }
    })


@csrf_exempt
def upload_batch(request):
    """
    Phase 1: API Ingestion
    Accepts multiple files (simulating a folder upload), saves them locally,
    creates a Batch record, triggers Celery, and returns 202 immediately.
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    files = request.FILES.getlist('files')
    if not files:
        return JsonResponse({"error": "No files provided"}, status=400)

    due_report = DueReportUpload.objects.filter(uploaded_by=request.user).order_by('-uploaded_at').first()
    if not due_report:
        return JsonResponse({"error": "Please upload the due report Excel file before uploading bills."}, status=400)

    # 1. Create the Batch Database record
    batch = OCRBatch.objects.create(
        uploaded_by=request.user,
        due_report=due_report,
        status=BatchStatus.PENDING,
        total_files=len(files)
    )

    # 2. Storage: Save files to temporary local directory
    # e.g., media/temp_ocr/[batch_id]/
    temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_ocr', str(batch.batch_id))
    os.makedirs(temp_dir, exist_ok=True)
    
    fs = FileSystemStorage(location=temp_dir)
    for f in files:
        safe_filename = os.path.basename(f.name)
        fs.save(safe_filename, f)
    
    # 3. Phase 2 Trigger: Call Celery worker (asynchronous)
    process_ocr_batch.delay(str(batch.batch_id), temp_dir)

    # 4. Return 202 Accepted immediately
    return JsonResponse({
        "message": "Batch accepted for processing",
        "batch_id": str(batch.batch_id),
        "total_files": len(files)
    }, status=202)


def check_batch_status(request, batch_id):
    """
    Phase 4: Result Retrieval
    Frontend polls this endpoint. Returns status. Always returns the current data we have so far.
    """
    if not request.user.is_authenticated:
         return JsonResponse({"error": "Unauthorized"}, status=401)
         
    try:
        batch = OCRBatch.objects.get(pk=batch_id)
        
        # Verify ownership (optional, depending on your auth model)
        if batch.uploaded_by != request.user:
            return JsonResponse({"error": "Forbidden"}, status=403)

        response_data = {
            "batch_id": str(batch.batch_id),
            "status": batch.status,
            "total_files": batch.total_files,
            "processed_files": batch.processed_files,
            "due_report": {
                "id": batch.due_report.id,
                "filename": batch.due_report.original_filename,
                "row_count": batch.due_report.row_count,
            } if batch.due_report else None,
        }

        # ALWAYS fetch and return all the parsed data we have so far, to allow real-time UI updates
        documents = DocumentResult.objects.filter(batch=batch).order_by('-processed_at')
        results = []
        for doc in documents:
            results.append({
                "id": doc.id,
                "filename": doc.original_filename,
                "extracted_text": doc.extracted_text,
                "processed_at": doc.processed_at,
                "reconciliation_status": doc.reconciliation_status,
                "reconciliation_details": doc.reconciliation_details,
                "matched_bill_data": doc.matched_bill_data,
                "audit_trail": doc.audit_trail
            })
        response_data["results"] = results
            
        return JsonResponse(response_data)

    except OCRBatch.DoesNotExist:
        return JsonResponse({"error": "Batch not found"}, status=404)


def get_user_batches(request):
    """
    Returns a paginated list of OCR batches uploaded by the current user.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
        
    try:
        batches = OCRBatch.objects.filter(uploaded_by=request.user).order_by('-created_at')
        
        # Implementing Pagination
        page = request.GET.get('page', 1)
        per_page = request.GET.get('limit', 5) # Default 5 items per page
        
        paginator = Paginator(batches, per_page)
        
        try:
            batches_page = paginator.page(1) if isinstance(page, str) and not page.isdigit() else paginator.page(page)
        except EmptyPage:
            batches_page = paginator.page(paginator.num_pages)

        batch_list = []
        for b in batches_page:
            first_doc_name = None
            if str(b.status) in [BatchStatus.COMPLETED, BatchStatus.MANUAL_REVIEW, BatchStatus.FAILED, 'INVOICES_SCANNED', 'MANUAL_REVIEW', 'FAILED']:
                first_doc = DocumentResult.objects.filter(batch=b).first()
                if first_doc:
                    first_doc_name = first_doc.original_filename

            batch_list.append({
                "batch_id": str(b.batch_id),
                "created_at": b.created_at,
                "status": b.status,
                "total_files": b.total_files,
                "processed_files": b.processed_files,
                "due_report_filename": b.due_report.original_filename if b.due_report else None,
                "representative_file": first_doc_name
            })
            
        return JsonResponse({
            "batches": batch_list,
            "pagination": {
                "current_page": batches_page.number,
                "total_pages": paginator.num_pages,
                "total_items": paginator.count,
                "has_next": batches_page.has_next(),
                "has_previous": batches_page.has_previous()
            }
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def get_document_ocr_data(request, document_id):
    """
    Returns the full OCR parsed data for a specific DocumentResult ID.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    
    try:
        document = DocumentResult.objects.get(pk=document_id)
        # Ensure the user owns the batch this document belongs to
        if document.batch.uploaded_by != request.user:
            return JsonResponse({"error": "Forbidden"}, status=403)
            
        return JsonResponse({
            "document_id": document.id,
            "original_filename": document.original_filename,
            "parsed_data": document.parsed_data,
            "extracted_text": document.extracted_text,
            "reconciliation_status": document.reconciliation_status,
            "reconciliation_details": document.reconciliation_details,
            "matched_bill_data": document.matched_bill_data,
            "audit_trail": document.audit_trail
        })
    except DocumentResult.DoesNotExist:
        return JsonResponse({"error": "Document not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def update_document_data(request, document_id):
    """
    Updates the parsed data of a document (e.g. manual correction of invoice number or amount)
    and re-triggers the reconciliation process.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
        
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        document = DocumentResult.objects.get(pk=document_id)
        
        # Verify ownership
        if document.batch.uploaded_by != request.user:
            return JsonResponse({"error": "Forbidden"}, status=403)

        data = json.loads(request.body)
        updates = data.get('updates', {})
        
        if not updates:
             return JsonResponse({"error": "No updates provided"}, status=400)

        # 1. Update the parsed data
        if document.parsed_data is None:
            document.parsed_data = {}
            
        old_data = document.parsed_data.copy()
        
        # We only want to log things that actually changed, and we NEVER want to log the giant tables array
        changed_details = []
        actual_changes = {}

        for key, value in updates.items():
            if key == 'tables':
                continue # Never log tables
            
            old_val = old_data.get(key)
            if str(old_val) != str(value): # Compare as strings to avoid type issues (e.g. "100" vs 100)
                actual_changes[key] = {"old": old_val, "new": value}
                changed_details.append(f"{key}: '{old_val}' -> '{value}'")
            
            # Apply the update
            document.parsed_data[key] = value

        if not actual_changes:
            return JsonResponse({"message": "No meaningful changes detected.", "document": {"document_id": document.id}}, status=200)

        # 2. Add an audit log entry
        # Provide more specific details by filtering out non-changes
        full_name = f"{request.user.first_name} {request.user.last_name}".strip()
        if not full_name:
            full_name = request.user.username

        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": "Manual Correction",
            "user_name": full_name,
            "user_email": request.user.email,
            "details": " | ".join(changed_details),
            "changes": actual_changes
        }
        
        # Ensure audit_trail is a list
        if not isinstance(document.audit_trail, list):
            document.audit_trail = []

        document.audit_trail.append(audit_entry)
        
        # 3. Re-run reconciliation
        fetched_bills = document.batch.due_report.data if document.batch.due_report else []
        
        ocr_invoice_number = document.parsed_data.get("invoice_number")
        ocr_total_amount = document.parsed_data.get("total_amount")

        matched_bill = None
        reconciliation_details = {}

        if ocr_invoice_number:
            for bill in fetched_bills:
                if bill.get("invoiceNo") == ocr_invoice_number:
                    matched_bill = bill
                    break
        
        if matched_bill:
            document.matched_bill_data = matched_bill
            api_payable_amount = matched_bill.get("payable")
            cash_discount_details = get_cash_discount_details(
                parsed_data=document.parsed_data,
                matched_bill_data=matched_bill,
            )
            reconciliation_details["cash_discount"] = cash_discount_details

            if ocr_total_amount is not None and api_payable_amount is not None:
                try:
                    ocr_amount_decimal = Decimal(str(ocr_total_amount))
                    api_amount_decimal = Decimal(str(api_payable_amount))

                    if ocr_amount_decimal == api_amount_decimal:
                        document.reconciliation_status = ReconciliationStatus.MANUALLY_VERIFIED
                        reconciliation_details["message"] = "Invoice number and total amount matched after manual correction."
                    else:
                        document.reconciliation_status = ReconciliationStatus.MANUAL_REVIEW
                        reconciliation_details["message"] = "Manual correction applied, but total amount still differs from the due report."
                        reconciliation_details["ocr_amount"] = str(ocr_total_amount)
                        reconciliation_details["api_amount"] = str(api_payable_amount)
                except InvalidOperation:
                    document.reconciliation_status = ReconciliationStatus.MANUAL_REVIEW
                    reconciliation_details["message"] = "Manual correction applied, but amount could not be parsed for due report comparison."
                    reconciliation_details["ocr_amount"] = str(ocr_total_amount)
                    reconciliation_details["api_amount"] = str(api_payable_amount)
            else:
                document.reconciliation_status = ReconciliationStatus.MANUAL_REVIEW
                reconciliation_details["message"] = "Manual correction applied, but amount is missing for due report comparison."
        else:
            document.reconciliation_status = ReconciliationStatus.NO_MATCH
            reconciliation_details["message"] = "Manual correction applied, but no matching bill found in the due report."
            reconciliation_details["ocr_invoice_number"] = ocr_invoice_number
            reconciliation_details["ocr_total_amount"] = str(ocr_total_amount) if ocr_total_amount is not None else None
            
        document.reconciliation_details = reconciliation_details
        document.save()
        sync_due_report_invoice_reconciliation(document, matched_bill=matched_bill)
        
        # 4. Check if the parent batch status needs to be updated
        batch = document.batch
        unverified_docs = DocumentResult.objects.filter(
            batch=batch
        ).exclude(
            reconciliation_status__in=[ReconciliationStatus.VERIFIED, ReconciliationStatus.MANUALLY_VERIFIED]
        ).count()
        
        if unverified_docs == 0:
            batch.status = BatchStatus.COMPLETED
            batch.save()
            logger.info(f"Batch {batch.batch_id} fully verified after manual correction.")
        else:
            # Revert back to manual review if there are still issues, just in case
            batch.status = BatchStatus.MANUAL_REVIEW
            batch.save()

        return JsonResponse({
            "message": "Document updated and reconciled successfully",
            "document": {
                "document_id": document.id,
                "parsed_data": document.parsed_data,
                "reconciliation_status": document.reconciliation_status,
                "reconciliation_details": document.reconciliation_details,
                "matched_bill_data": document.matched_bill_data,
                "audit_trail": document.audit_trail
            },
            "batch_status": batch.status
        })

    except DocumentResult.DoesNotExist:
        return JsonResponse({"error": "Document not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Error updating document {document_id}: {e}")
        return JsonResponse({"error": str(e)}, status=500)


#do not write below this line
@csrf_exempt
def get_bills(request):
    if request.method == 'GET':
        due_report = DueReportUpload.objects.order_by('-uploaded_at').first()
        if not due_report:
            return JsonResponse({
                "status": "success",
                "message": "No due report uploaded yet",
                "data": []
            })

        invoice_rows = DueReportInvoiceWise.objects.filter(due_report=due_report).order_by('created_at')
        if invoice_rows.exists():
            bills = []
            for row in invoice_rows:
                bills.append({
                    'id': row.id,
                    'location_name': row.location_name,
                    'supplier_name': row.supplier_name,
                    'gst_number': row.gst_number,
                    'invoice_no': row.invoice_no,
                    'ref_no': row.ref_no,
                    'bill_voucher_date': row.bill_voucher_date,
                    'invoice_date': row.invoice_date,
                    'bill_amount': row.bill_amount,
                    'disc_amount': row.disc_amount,
                    'amount_adjusted': row.amount_adjusted,
                    'balance_amount': row.balance_amount,
                    'pending_adj_amt': row.pending_adj_amt,
                    'net_balance': row.net_balance,
                    'no_of_days': row.no_of_days,
                    'due_date': row.due_date,
                    'over_due_days': row.over_due_days,
                    'prior_date': row.prior_date,
                    'group_name': row.group_name,
                    'voucher_type': row.voucher_type,
                    'msme_type': row.msme_type,
                    'status': row.status,
                    'invoice_scanned': row.invoice_scanned,
                    'invoice_reconciliation_status': row.invoice_reconciliation_status,
                    'is_payment_file_created': row.is_payment_file_created,
                    'manager_rejected': row.manager_rejected,
                    'manager_rejected_at': row.manager_rejected_at,
                    'manager_rejected_by': row.manager_rejected_by.username if row.manager_rejected_by else None,
                    'manager_rejection_reason': row.manager_rejection_reason,
                })
        else:
            fin_year = request.GET.get('finYear')
            bills = due_report.data or []
            if fin_year:
                bills = [bill for bill in bills if str(bill.get("tranYear")) == str(fin_year)]

        return JsonResponse({
            "status": "success",
            "message": "success",
            "source": {
                "due_report_id": due_report.id,
                "filename": due_report.original_filename,
                "uploaded_at": due_report.uploaded_at,
            },
            "data": bills
        })
    return JsonResponse({"error": "Method not allowed"}, status=405)


def _get_payment_file_status(payment_file):
    if payment_file.is_payment_done:
        return 'PAID'
    if payment_file.is_payment_file_approved:
        return 'APPROVED'
    if payment_file.rejected_due_report_row_ids:
        return 'REJECTED'
    return 'PENDING'


def _serialize_payment_file(payment_file, request):
    invoice_rows = list(payment_file.due_report_rows.order_by('id'))
    row_data = build_payment_file_rows(payment_file.payment_type, invoice_rows, overrides=payment_file.line_item_overrides or {})

    for idx, row in enumerate(invoice_rows):
        link = payment_file.invoice_links.filter(invoice=row).first()
        review_status = link.status if link else None
        review_reason = link.manager_rejection_reason if link else row.manager_rejection_reason
        row_data[idx].update({
            'manager_rejected': row.manager_rejected,
            'manager_rejected_at': row.manager_rejected_at,
            'manager_rejected_by': row.manager_rejected_by.username if row.manager_rejected_by else None,
            'manager_rejection_reason': row.manager_rejection_reason,
            'review_status': review_status,
            'review_reason': review_reason,
            'is_rejected': review_status == PaymentFileInvoice.Status.MANAGER_REJECTED,
            'is_approved': review_status == PaymentFileInvoice.Status.MANAGER_APPROVED,
            'is_pending_review': review_status == PaymentFileInvoice.Status.PENDING_MANAGER_REVIEW,
        })

    return {
        "id": payment_file.id,
        "unique_id": payment_file.unique_id,
        "status": payment_file.status,
        "payment_status": _get_payment_file_status(payment_file),
        "payment_type": payment_file.payment_type,
        "total_files": payment_file.total_files,
        "processed_files": payment_file.processed_files,
        "download_url": request.build_absolute_uri(reverse('download_payment_file', args=[payment_file.id])),
        "file_name": f"{payment_file.id}_{payment_file.payment_type}.xlsx",
        "due_report_id": payment_file.due_report.id if payment_file.due_report else None,
        "due_report_filename": payment_file.due_report.original_filename if payment_file.due_report else None,
        "created_at": payment_file.created_at,
        "created_by": payment_file.created_by.username if payment_file.created_by else None,
        "created_by_id": payment_file.created_by.id if payment_file.created_by else None,
        "created_by_email": payment_file.created_by.email if payment_file.created_by else None,
        "line_item_overrides": payment_file.line_item_overrides or {},
        "rejected_due_report_row_ids": payment_file.rejected_due_report_row_ids or [],
        "is_payment_file_approved": payment_file.is_payment_file_approved,
        "is_payment_done": payment_file.is_payment_done,
        "rows": row_data,
    }


def _require_manager_role(request):
    if request.user.is_staff:
        return True
    try:
        profile = UserProfile.objects.get(user=request.user)
        return profile.role == UserRole.STORE_MANAGER
    except UserProfile.DoesNotExist:
        return False


def _ensure_payment_file_invoice_links(payment_file):
    invoice_ids = set(payment_file.due_report_rows.values_list('id', flat=True))
    existing_ids = set(payment_file.invoice_links.values_list('invoice_id', flat=True))
    missing_ids = invoice_ids - existing_ids
    for invoice_id in missing_ids:
        invoice = DueReportInvoiceWise.objects.get(pk=invoice_id)
        PaymentFileInvoice.objects.get_or_create(
            payment_file=payment_file,
            invoice=invoice,
            defaults={'status': PaymentFileInvoice.Status.PENDING_MANAGER_REVIEW},
        )


def _is_invoice_eligible_for_new_payment_file(invoice):
    latest_link = PaymentFileInvoice.objects.filter(invoice=invoice).order_by('-created_at').first()
    if latest_link:
        if latest_link.status in {
            PaymentFileInvoice.Status.PENDING_MANAGER_REVIEW,
            PaymentFileInvoice.Status.MANAGER_APPROVED,
            PaymentFileInvoice.Status.PAID,
        }:
            return False
        if latest_link.status == PaymentFileInvoice.Status.MANAGER_REJECTED:
            return True

    if invoice.is_payment_file_created and not invoice.manager_rejected:
        return False
    return True


def _is_manager_of(manager_user, target_user):
    if manager_user == target_user:
        return False
    if not manager_user.is_authenticated:
        return False
    try:
        manager_profile = UserProfile.objects.get(user=manager_user)
    except UserProfile.DoesNotExist:
        return False
    if manager_profile.role != UserRole.STORE_MANAGER:
        return False
    try:
        target_profile = UserProfile.objects.get(user=target_user)
    except UserProfile.DoesNotExist:
        return False
    return target_profile.account_manager_id == manager_user.id


@csrf_exempt
def payment_file_detail(request, payment_file_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        payment_file = PaymentFile.objects.get(pk=payment_file_id)
    except PaymentFile.DoesNotExist:
        return JsonResponse({"error": "Payment file not found."}, status=404)

    if request.method != 'GET':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not request.user.is_staff and payment_file.created_by != request.user and not _is_manager_of(request.user, payment_file.created_by):
        return JsonResponse({"error": "Forbidden"}, status=403)

    return JsonResponse({"payment_file": _serialize_payment_file(payment_file, request)})


@csrf_exempt
def review_payment_file(request, payment_file_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not _require_manager_role(request):
        return JsonResponse({"error": "Forbidden"}, status=403)

    try:
        payment_file = PaymentFile.objects.get(pk=payment_file_id)
    except PaymentFile.DoesNotExist:
        return JsonResponse({"error": "Payment file not found."}, status=404)

    if not request.user.is_staff and payment_file.created_by != request.user and not _is_manager_of(request.user, payment_file.created_by):
        return JsonResponse({"error": "Forbidden"}, status=403)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    edits = payload.get('edits', {})
    rejected_ids = payload.get('rejected_ids', [])
    if not isinstance(edits, dict) or not isinstance(rejected_ids, list):
        return JsonResponse({"error": "Invalid payload format."}, status=400)

    allowed_fields = {
        'invoice_no', 'gst_number', 'supplier_name', 'beneficiary_name',
        'bank_name', 'account_number', 'ifsc_code', 'branch_name', 'amount', 'remarks'
    }

    overrides = payment_file.line_item_overrides or {}
    invoice_row_ids = {row.id for row in payment_file.due_report_rows.all()}
    _ensure_payment_file_invoice_links(payment_file)

    for row_id, update_data in edits.items():
        try:
            row_id_int = int(row_id)
        except (ValueError, TypeError):
            continue
        if row_id_int not in invoice_row_ids:
            continue
        if not isinstance(update_data, dict):
            continue

        filtered = {k: v for k, v in update_data.items() if k in allowed_fields}
        if not filtered:
            continue
        overrides[str(row_id_int)] = {**overrides.get(str(row_id_int), {}), **filtered}

    rejected_ids = [int(row_id) for row_id in rejected_ids if str(row_id).isdigit()]
    valid_rejected_ids = [row_id for row_id in rejected_ids if row_id in invoice_row_ids]

    now = timezone.now()
    for link in payment_file.invoice_links.all():
        if link.invoice_id in valid_rejected_ids:
            link.status = PaymentFileInvoice.Status.MANAGER_REJECTED
            link.manager_rejection_reason = payload.get('rejection_reason') or link.manager_rejection_reason
            link.save()

            row = link.invoice
            row.manager_rejected = True
            row.manager_rejected_at = now
            row.manager_rejected_by = request.user
            row.manager_rejection_reason = link.manager_rejection_reason
            row.save()
        else:
            link.status = PaymentFileInvoice.Status.MANAGER_APPROVED
            link.manager_rejection_reason = None
            link.save()

    payment_file.line_item_overrides = overrides
    payment_file.rejected_due_report_row_ids = sorted(set(list(payment_file.rejected_due_report_row_ids or []) + valid_rejected_ids))
    payment_file.modified_by = request.user
    if valid_rejected_ids:
        payment_file.status = BatchStatus.REJECTED
        payment_file.is_payment_file_approved = False
    else:
        payment_file.status = BatchStatus.COMPLETED
        payment_file.is_payment_file_approved = True
    payment_file.save()

    return JsonResponse({"payment_file": _serialize_payment_file(payment_file, request)})


@csrf_exempt
def regenerate_payment_file(request, payment_file_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not UserProfile.objects.filter(user=request.user, role=UserRole.STORE_ACCOUNTANT).exists():
        return JsonResponse({"error": "Only accountants can regenerate payment files."}, status=403)

    try:
        payment_file = PaymentFile.objects.get(pk=payment_file_id)
    except PaymentFile.DoesNotExist:
        return JsonResponse({"error": "Payment file not found."}, status=404)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    invoice_ids = payload.get('invoice_ids')
    if invoice_ids is not None and not isinstance(invoice_ids, list):
        return JsonResponse({"error": "invoice_ids must be a list if provided."}, status=400)

    if invoice_ids is None:
        invoice_rows = list(payment_file.due_report_rows.filter(manager_rejected=False))
    else:
        invoice_rows = list(DueReportInvoiceWise.objects.filter(
            id__in=invoice_ids,
            due_report=payment_file.due_report,
        ))

    if not invoice_rows:
        return JsonResponse({"error": "No valid invoice rows available for regeneration."}, status=400)

    source_overrides = payment_file.line_item_overrides or {}
    overrides_for_new_file = {
        key: value for key, value in source_overrides.items() if int(key) in [row.id for row in invoice_rows]
    }

    new_payment_file = create_payment_file_record(
        payment_type=payment_file.payment_type,
        invoice_rows=invoice_rows,
        due_report=payment_file.due_report,
        created_by=payment_file.created_by or request.user,
        line_item_overrides=overrides_for_new_file,
        rejected_due_report_row_ids=payment_file.rejected_due_report_row_ids or [],
    )

    payment_file.status = BatchStatus.PENDING
    payment_file.is_payment_file_approved = False
    payment_file.save()

    return JsonResponse({
        "message": "New payment file generated successfully.",
        "payment_file": _serialize_payment_file(new_payment_file, request)
    }, status=201)


@csrf_exempt
def central_payment(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        invoice_ids = payload.get('invoice_ids')
        payment_type = payload.get('payment_type', 'ICICI')

        if not invoice_ids or not isinstance(invoice_ids, list):
            return JsonResponse({"error": "invoice_ids must be provided as a list."}, status=400)

        if payment_type not in ["ICICI", "SBI"]:
            return JsonResponse({"error": "payment_type must be either 'ICICI' or 'SBI'."}, status=400)

        invoice_rows = list(DueReportInvoiceWise.objects.filter(id__in=invoice_ids))
        if not invoice_rows:
            return JsonResponse({"error": "No due report invoice rows found for the provided IDs."}, status=404)

        due_report = invoice_rows[0].due_report
        if any(row.due_report_id != due_report.id for row in invoice_rows):
            return JsonResponse({"error": "All selected invoice rows must belong to the same due report."}, status=400)

        ineligible_rows = [row for row in invoice_rows if not _is_invoice_eligible_for_new_payment_file(row)]
        if ineligible_rows:
            return JsonResponse({"error": "Only new invoices or invoices rejected by the manager can be selected for a new payment file."}, status=400)

        force_selected_ids = payload.get('force_selected_ids', [])
        if not isinstance(force_selected_ids, list):
            return JsonResponse({"error": "force_selected_ids must be a list if provided."}, status=400)

        force_selected_ids = [int(row_id) for row_id in force_selected_ids if str(row_id).isdigit()]
        if not set(force_selected_ids).issubset({row.id for row in invoice_rows}):
            return JsonResponse({"error": "force_selected_ids must reference the selected invoice rows."}, status=400)

        pending_links = PaymentFileInvoice.objects.filter(
            invoice__in=invoice_rows,
            status=PaymentFileInvoice.Status.PENDING_MANAGER_REVIEW,
        ).exclude(payment_file__status__in=[BatchStatus.COMPLETED, BatchStatus.REJECTED])
        if pending_links.exists():
            return JsonResponse({"error": "Some invoices are already pending manager review in another payment file."}, status=400)

        payment_file = create_payment_file_record(
            payment_type=payment_type,
            invoice_rows=invoice_rows,
            due_report=due_report,
            created_by=request.user,
            force_selected_ids=force_selected_ids,
        )

        download_url = request.build_absolute_uri(reverse('download_payment_file', args=[payment_file.id]))
        return JsonResponse({
            "message": "Payment file created successfully.",
            "payment_file": {
                "id": payment_file.id,
                "unique_id": payment_file.unique_id,
                "status": payment_file.status,
                "payment_status": _get_payment_file_status(payment_file),
                "payment_type": payment_file.payment_type,
                "total_files": payment_file.total_files,
                "processed_files": payment_file.processed_files,
                "download_url": download_url,
                "file_name": f"{payment_file.id}_{payment_file.payment_type}.xlsx",
                "file_url": None,
                "due_report_id": due_report.id,
                "due_report_filename": due_report.original_filename,
            }
        }, status=201)

    if request.method == 'GET':
        if request.user.is_staff:
            payment_files = PaymentFile.objects.order_by('-created_at')
        else:
            payment_files = PaymentFile.objects.filter(
                Q(created_by=request.user) |
                Q(created_by__userprofile__account_manager=request.user)
            ).order_by('-created_at')
        return JsonResponse({
            "payment_files": [
                {
                    "id": payment_file.id,
                    "unique_id": payment_file.unique_id,
                    "status": payment_file.status,
                    "payment_status": _get_payment_file_status(payment_file),
                    "payment_type": payment_file.payment_type,
                    "total_files": payment_file.total_files,
                    "processed_files": payment_file.processed_files,
                    "download_url": request.build_absolute_uri(reverse('download_payment_file', args=[payment_file.id])),
                    "file_name": f"{payment_file.id}_{payment_file.payment_type}.xlsx",
                    "file_url": None,
                    "due_report_id": payment_file.due_report.id if payment_file.due_report else None,
                    "due_report_filename": payment_file.due_report.original_filename if payment_file.due_report else None,
                    "created_at": payment_file.created_at,
                    "created_by": payment_file.created_by.username if payment_file.created_by else None,
                    "created_by_id": payment_file.created_by.id if payment_file.created_by else None,
                    "created_by_email": payment_file.created_by.email if payment_file.created_by else None,
                }
                for payment_file in payment_files
            ]
        })

    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def download_payment_file(request, payment_file_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        payment_file = PaymentFile.objects.get(pk=payment_file_id)
    except PaymentFile.DoesNotExist:
        return JsonResponse({"error": "Payment file not found."}, status=404)

    if payment_file.created_by and payment_file.created_by != request.user and not request.user.is_staff and not _is_manager_of(request.user, payment_file.created_by):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    invoice_rows = list(payment_file.due_report_rows.all())
    if not invoice_rows:
        return JsonResponse({"error": "No invoice rows available for this payment file."}, status=404)

    rows_data = build_payment_file_rows(payment_file.payment_type, invoice_rows, overrides=payment_file.line_item_overrides or {})
    xlsx_content = generate_payment_file_xlsx(
        payment_file.payment_type,
        rows_data,
        payment_ref=payment_file.unique_id or payment_file.id,
    )
    filename = f"{payment_file.id}_{payment_file.payment_type}.xlsx"

    response = HttpResponse(xlsx_content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
