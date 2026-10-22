import os
import json
import re
import msal
import logging
import requests
import base64
from django.conf import settings
from django.shortcuts import redirect
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
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
    DueReportInvoiceWise,
    PaymentFile,
    PaymentFileInvoice,
    PaymentFileReviewEvent,
)
from .tasks import invoice_row_to_bill, process_ocr_batch
from .payment_file_service import create_payment_file_record, build_payment_file_rows, generate_payment_file_content, generate_payment_file_xlsx
from .truebooks_payment_service import approve_bill, create_central_payment, TrueBooksPaymentError
from .ap_review_service import compare_bank_file
from .reconciliation_service import build_bill_lookup, match_bill, apply_reconciliation, sync_due_report_invoice_reconciliation

logger = logging.getLogger(__name__)

"""Due-report data is fetched from GetBills and stored invoice-wise."""

'''LEGACY_CODE_REMOVED
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

        if invoice_no and gst_number:
            key = (invoice_no, gst_number)
            existing_row = existing_map.get(key)
            if existing_row:
                for field_name, value in base_data.items():
                    setattr(existing_row, field_name, value)
                if existing_row not in update_candidates:
                    update_candidates.append(existing_row)
            else:
                invoice_wise_rows.append(DueReportInvoiceWise(**base_data))
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

LEGACY_CODE_REMOVED'''

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

    allowed_invoice_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}
    files = [
        uploaded_file for uploaded_file in request.FILES.getlist('files')
        if not os.path.basename(uploaded_file.name).startswith('.')
        and os.path.splitext(uploaded_file.name)[1].lower() in allowed_invoice_extensions
    ]
    if not files:
        return JsonResponse({"error": "No supported invoice files provided. Upload PDF or image files."}, status=400)

    if not DueReportInvoiceWise.objects.exists():
        return JsonResponse({"error": "Fetch the due report before uploading scanned bills."}, status=400)

    # 1. Create the Batch Database record
    batch = OCRBatch.objects.create(
        uploaded_by=request.user,
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

        editable_fields = {
            'invoice_number', 'date', 'vendor_name', 'vendor_gst_number',
            'customer_gst_number', 'total_amount', 'goods_value', 'tax_amount',
            'hsn_or_sac', 'vendor_bank', 'bank_name', 'account_holder_name',
            'account_number', 'ifsc_code', 'branch_name', 'micr_code', 'swift_code',
        }
        invalid_fields = sorted(set(updates) - editable_fields)
        if invalid_fields:
            return JsonResponse({
                "error": f"These fields cannot be manually edited: {', '.join(invalid_fields)}"
            }, status=400)

        # 1. Update the parsed data
        if document.parsed_data is None:
            document.parsed_data = {}
            
        old_data = document.parsed_data.copy()
        
        # We only want to log things that actually changed, and we NEVER want to log the giant tables array
        changed_details = []
        actual_changes = {}

        for key, value in updates.items():
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
            "timestamp": timezone.now().isoformat(),
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
        fetched_bills = [
            invoice_row_to_bill(row)
            for row in DueReportInvoiceWise.objects.all()
        ]
        
        bill_lookup = build_bill_lookup(fetched_bills)
        matched_bill = match_bill(document.parsed_data, bill_lookup)
        apply_reconciliation(document, document.parsed_data, matched_bill)
        if document.reconciliation_status == ReconciliationStatus.VERIFIED:
            document.reconciliation_status = ReconciliationStatus.MANUALLY_VERIFIED
            details = document.reconciliation_details or {}
            details['message'] = 'All reconciliation checks passed after manual correction.'
            document.reconciliation_details = details
            document.save(update_fields=['reconciliation_status', 'reconciliation_details'])
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
    if request.method != 'GET':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    base_invoice_rows = DueReportInvoiceWise.objects.all()
    store_options = list(
        base_invoice_rows.exclude(location_name__isnull=True).exclude(location_name='')
        .order_by('location_name').values_list('location_name', flat=True).distinct()
    )
    search_query = (request.GET.get('q') or '').strip()
    store_filter = (request.GET.get('store') or '').strip()
    reconciliation_status_filter = (request.GET.get('status') or '').strip().upper()
    if search_query:
        base_invoice_rows = base_invoice_rows.filter(
            Q(invoice_no__icontains=search_query)
            | Q(gst_number__icontains=search_query)
            | Q(supplier_name__icontains=search_query)
        )
    if store_filter:
        base_invoice_rows = base_invoice_rows.filter(location_name=store_filter)
    if reconciliation_status_filter:
        if reconciliation_status_filter == 'SCANNED':
            base_invoice_rows = base_invoice_rows.filter(invoice_scanned=True)
        elif reconciliation_status_filter == 'SCANNED_NOT_VERIFIED':
            base_invoice_rows = base_invoice_rows.filter(invoice_scanned=True).exclude(
                invoice_reconciliation_status__in=[
                    ReconciliationStatus.VERIFIED,
                    ReconciliationStatus.MANUALLY_VERIFIED,
                ]
            )
        elif reconciliation_status_filter == 'NOT_SCANNED':
            base_invoice_rows = base_invoice_rows.filter(invoice_scanned=False)
        else:
            base_invoice_rows = base_invoice_rows.filter(
                invoice_reconciliation_status=reconciliation_status_filter
            )

    invoice_rows = base_invoice_rows.annotate(
        reconciliation_priority=Case(
            When(invoice_scanned=True, invoice_reconciliation_status='VERIFIED', then=Value(0)),
            When(invoice_scanned=True, invoice_reconciliation_status='MANUALLY_VERIFIED', then=Value(1)),
            When(invoice_scanned=True, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
    ).order_by('reconciliation_priority', '-created_at', '-id')
    page_number = request.GET.get('page', 1)
    try:
        page_size = min(100, max(1, int(request.GET.get('page_size', 100))))
    except (TypeError, ValueError):
        page_size = 100
    return_all = request.GET.get('all', '').lower() in {'1', 'true', 'yes'}
    page_obj = None
    if not return_all:
        paginator = Paginator(invoice_rows, page_size)
        try:
            page_obj = paginator.page(page_number)
        except (EmptyPage, PageNotAnInteger):
            page_obj = paginator.page(1)
        invoice_rows = page_obj.object_list
    rejected_statuses = [
        PaymentFileInvoice.Status.MANAGER_REJECTED,
        PaymentFileInvoice.Status.AP_REJECTED,
    ]
    rejected_payment_file_ids = set(PaymentFileInvoice.objects.filter(
        status__in=rejected_statuses,
    ).values_list('payment_file_id', flat=True))
    # The normal generation pool may reuse only line items that were actually
    # rejected. Approved rows remain locked even when their containing file was
    # rejected. The dedicated regeneration screen may still select any source row.
    active_invoice_ids = set(PaymentFileInvoice.objects.exclude(
        status__in=rejected_statuses,
    ).values_list('invoice_id', flat=True))
    rejected_links = PaymentFileInvoice.objects.filter(
        payment_file_id__in=rejected_payment_file_ids,
        status__in=[
            PaymentFileInvoice.Status.MANAGER_REJECTED,
            PaymentFileInvoice.Status.AP_REJECTED,
        ],
    ).select_related('payment_file').order_by('updated_at')
    latest_rejection_by_invoice = {link.invoice_id: link for link in rejected_links}
    bills = []
    for row in invoice_rows:
        rejection_link = latest_rejection_by_invoice.get(row.id)
        bills.append({
                    'id': row.id,
                    'tran_year': row.tran_year,
                    'branch_code': row.branch_code,
                    'location_name': row.location_name,
                    'voucher_no': row.voucher_no,
                    'supplier_name': row.supplier_name,
                    'party_code': row.party_code,
                    'gst_number': row.gst_number,
                    'invoice_no': row.invoice_no,
                    'ref_no': row.ref_no,
                    'bill_voucher_date': row.bill_voucher_date,
                    'bill_date': row.bill_date,
                    'invoice_date': row.invoice_date,
                    'bill_amount': row.bill_amount,
                    'payable': row.payable,
                    'expense_ledger': row.expense_ledger,
                    'goods_value': row.goods_value,
                    'tax_amount': row.tax_amount,
                    'tax_code': row.tax_code,
                    'tax_type': row.tax_type,
                    'tds_amount': row.tds_amount,
                    'tds_section': row.tds_section,
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
                    'party_contact': row.party_contact,
                    'pay_mode': row.pay_mode,
                    'other_charges': row.other_charges,
                    'payment_status': row.payment_status,
                    'transaction_link': row.transaction_link,
                    'email_id': row.email_id,
                    'bill_unique_id': row.bill_unique_id,
                    'status': row.status,
                    'invoice_scanned': row.invoice_scanned,
                    'invoice_reconciliation_status': row.invoice_reconciliation_status,
                    'invoice_number_matches': row.invoice_number_matches,
                    'payable_amount_matches': row.payable_amount_matches,
                    'goods_value_matches': row.goods_value_matches,
                    'tax_amount_matches': row.tax_amount_matches,
                    'tax_type_matches': row.tax_type_matches,
                    'vendor_gst_matches': row.vendor_gst_matches,
                    'vendor_master_verified': row.vendor_master_verified,
                    'store_gst_matches': row.store_gst_matches,
                    'store_master_verified': row.store_master_verified,
                    'reconciliation_details': row.reconciliation_details,
                    'is_acknowledged': row.is_acknowledged,
                    'payment_reference_number': row.payment_reference_number,
                    'is_payment_file_created': row.id in active_invoice_ids,
                    'is_available_for_payment': row.id not in active_invoice_ids,
                    'payment_file_rejected': rejection_link is not None,
                    'payment_file_rejection_level': (
                        'AP' if rejection_link and (rejection_link.status == PaymentFileInvoice.Status.AP_REJECTED or rejection_link.ap_rejection_reason)
                        else 'MANAGER' if rejection_link else None
                    ),
                    'payment_file_rejection_reason': (
                        rejection_link.ap_rejection_reason or rejection_link.manager_rejection_reason
                        if rejection_link else None
                    ),
                    'rejected_payment_file_id': rejection_link.payment_file_id if rejection_link else None,
                    'manager_rejected': row.manager_rejected,
                    'manager_rejected_at': row.manager_rejected_at,
                    'manager_rejected_by': row.manager_rejected_by.username if row.manager_rejected_by else None,
                    'manager_rejection_reason': row.manager_rejection_reason,
        })

    return JsonResponse({
        "status": "success",
        "message": "success",
        "source": {"row_count": page_obj.paginator.count if page_obj else len(bills)},
        "pagination": ({
            "current_page": page_obj.number,
            "page_size": page_size,
            "total_pages": page_obj.paginator.num_pages,
            "total_items": page_obj.paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        } if page_obj else {
            "current_page": 1,
            "page_size": len(bills),
            "total_pages": 1,
            "total_items": len(bills),
            "has_next": False,
            "has_previous": False,
        }),
        "filters": {
            "q": search_query,
            "store": store_filter,
            "status": reconciliation_status_filter,
            "stores": store_options,
        },
        "data": bills,
    })


def _get_payment_file_status(payment_file):
    links = payment_file.invoice_links.all()
    if not links.exists():
        return 'PENDING'
    statuses = set(links.values_list('status', flat=True))
    if PaymentFileInvoice.Status.MANAGER_REJECTED in statuses:
        return 'REJECTED'
    if PaymentFileInvoice.Status.AP_REJECTED in statuses:
        # A single rejected line rejects the complete payment file. The link
        # statuses still preserve exactly which invoices AP rejected.
        return 'REJECTED'
    if statuses and statuses.issubset({PaymentFileInvoice.Status.AP_APPROVED, PaymentFileInvoice.Status.PAID}):
        if statuses == {PaymentFileInvoice.Status.PAID}:
            return 'PAID'
        return 'APPROVED'
    if statuses and statuses.issubset({
        PaymentFileInvoice.Status.MANAGER_APPROVED,
        PaymentFileInvoice.Status.PAID,
    }):
        if statuses == {PaymentFileInvoice.Status.PAID}:
            return 'PAID'
        return 'APPROVED'
    return 'PENDING'


def _get_manager_review_status(payment_file):
    statuses = set(payment_file.invoice_links.values_list('status', flat=True))
    if not statuses or PaymentFileInvoice.Status.PENDING_MANAGER_REVIEW in statuses:
        return 'PENDING'
    if PaymentFileInvoice.Status.MANAGER_REJECTED in statuses:
        return 'REJECTED'
    # AP statuses can only be assigned after manager approval, so they preserve
    # the manager-approved outcome even though the line status has advanced.
    return 'APPROVED'


def _get_ap_review_status(payment_file):
    if payment_file.is_ap_rejected:
        return 'REJECTED'
    if payment_file.is_ap_approved:
        return 'APPROVED'
    return 'PENDING'


def _get_payment_file_rejected_by(payment_file):
    """Return the user who performed the rejection that put the file in its current state."""
    event = payment_file.review_events.filter(
        event_type__in=[
            PaymentFileReviewEvent.EventType.MANAGER_REJECTED,
            PaymentFileReviewEvent.EventType.AP_REJECTED,
        ],
        actor__isnull=False,
    ).order_by('-created_at', '-id').first()
    return event.actor if event else None


def _can_regenerate_payment_file(payment_file, user):
    if not user.is_authenticated or _get_payment_file_status(payment_file) != 'REJECTED':
        return False
    rejected_by = _get_payment_file_rejected_by(payment_file)
    return rejected_by is not None and rejected_by.id == user.id


def _serialize_payment_file(payment_file, request):
    invoice_rows = list(payment_file.due_report_rows.order_by('id'))
    row_data = build_payment_file_rows(payment_file.payment_type, invoice_rows, overrides=payment_file.line_item_overrides or {})
    links_by_invoice_id = {
        link.invoice_id: link
        for link in payment_file.invoice_links.all()
    }

    for idx, row in enumerate(invoice_rows):
        link = links_by_invoice_id.get(row.id)
        review_status = link.status if link else PaymentFileInvoice.Status.PENDING_MANAGER_REVIEW
        row_data[idx].update({
            'review_status': review_status,
            'is_approved': review_status in [
                PaymentFileInvoice.Status.MANAGER_APPROVED,
                PaymentFileInvoice.Status.AP_APPROVED,
                PaymentFileInvoice.Status.PAID,
            ],
            'is_rejected': review_status in [
                PaymentFileInvoice.Status.MANAGER_REJECTED,
                PaymentFileInvoice.Status.AP_REJECTED,
            ],
            'review_reason': (link.ap_rejection_reason or link.manager_rejection_reason) if link else None,
            'ap_rejection_reason': link.ap_rejection_reason if link else None,
            'is_ap_approved': link.is_ap_approved if link else False,
            'is_ap_rejected': link.is_ap_rejected if link else False,
            'manager_rejected': row.manager_rejected,
            'manager_rejected_at': row.manager_rejected_at,
            'manager_rejected_by': row.manager_rejected_by.username if row.manager_rejected_by else None,
            'manager_rejection_reason': row.manager_rejection_reason,
        })

    history = [{
        'event_type': event.event_type,
        'actor': event.actor.username if event.actor else 'System',
        'actor_email': event.actor.email if event.actor else None,
        'comment': event.comment,
        'invoice_ids': event.invoice_ids or [],
        'metadata': event.metadata or {},
        'created_at': event.created_at,
    } for event in payment_file.review_events.select_related('actor').all()]

    return {
        "id": payment_file.id,
        "unique_id": payment_file.unique_id,
        "status": payment_file.status,
        "payment_status": _get_payment_file_status(payment_file),
        "manager_review_status": _get_manager_review_status(payment_file),
        "ap_review_status": _get_ap_review_status(payment_file),
        "is_payment_file_approved": payment_file.is_payment_file_approved,
        "is_ap_approved": payment_file.is_ap_approved,
        "is_ap_rejected": payment_file.is_ap_rejected,
        "bank_file_matches": payment_file.bank_file_matches,
        "bank_file_comparison": payment_file.bank_file_comparison or {},
        "bank_file_uploaded_at": payment_file.bank_file_uploaded_at,
        "ap_reviewed_at": payment_file.ap_reviewed_at,
        "payment_type": payment_file.payment_type,
        "total_files": payment_file.total_files,
        "processed_files": payment_file.processed_files,
        "download_url": request.build_absolute_uri(reverse('download_payment_file', args=[payment_file.id])),
        "file_name": f"{payment_file.id}_{payment_file.payment_type}.xlsx",
        "created_at": payment_file.created_at,
        "created_by": payment_file.created_by.username if payment_file.created_by else None,
        "created_by_id": payment_file.created_by.id if payment_file.created_by else None,
        "created_by_email": payment_file.created_by.email if payment_file.created_by else None,
        "line_item_overrides": payment_file.line_item_overrides or {},
        "rejected_due_report_row_ids": payment_file.rejected_due_report_row_ids or [],
        "source_payment_file_id": payment_file.source_payment_file_id,
        "regenerated_file_ids": list(payment_file.regenerated_files.values_list('id', flat=True)),
        "can_regenerate": _can_regenerate_payment_file(payment_file, request.user),
        "history": history,
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


def _require_ap_role(request):
    if request.user.is_staff:
        return True
    return UserProfile.objects.filter(user=request.user, role=UserRole.AP_TEAM).exists()


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

    if (
        not request.user.is_staff
        and payment_file.created_by != request.user
        and not _is_manager_of(request.user, payment_file.created_by)
        and not _require_ap_role(request)
    ):
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
    with transaction.atomic():
        for link in payment_file.invoice_links.select_for_update():
            is_rejected = link.invoice_id in valid_rejected_ids
            link.status = (
                PaymentFileInvoice.Status.MANAGER_REJECTED
                if is_rejected else PaymentFileInvoice.Status.MANAGER_APPROVED
            )
            link.manager_rejection_reason = payload.get('rejection_reason') if is_rejected else None
            link.save(update_fields=['status', 'manager_rejection_reason', 'updated_at'])

        rows_to_update = DueReportInvoiceWise.objects.filter(id__in=invoice_row_ids)
        for row in rows_to_update:
            is_rejected = row.id in valid_rejected_ids
            row.manager_rejected = is_rejected
            row.manager_rejected_at = now if is_rejected else None
            row.manager_rejected_by = request.user if is_rejected else None
            row.manager_rejection_reason = payload.get('rejection_reason') if is_rejected else None
            row.save(update_fields=[
                'manager_rejected', 'manager_rejected_at', 'manager_rejected_by',
                'manager_rejection_reason',
            ])

        payment_file.line_item_overrides = overrides
        payment_file.rejected_due_report_row_ids = sorted(valid_rejected_ids)
        payment_file.is_payment_file_approved = not valid_rejected_ids
        payment_file.status = BatchStatus.COMPLETED if not valid_rejected_ids else BatchStatus.REJECTED
        payment_file.modified_by = request.user
        payment_file.save(update_fields=[
            'line_item_overrides', 'rejected_due_report_row_ids',
            'is_payment_file_approved', 'status', 'modified_by', 'updated_at',
        ])
        PaymentFileReviewEvent.objects.create(
            payment_file=payment_file,
            event_type=(PaymentFileReviewEvent.EventType.MANAGER_REJECTED if valid_rejected_ids else PaymentFileReviewEvent.EventType.MANAGER_APPROVED),
            actor=request.user,
            comment=payload.get('rejection_reason') or None,
            invoice_ids=sorted(valid_rejected_ids),
            metadata={'approved_invoice_ids': sorted(invoice_row_ids - set(valid_rejected_ids))},
        )

    return JsonResponse({"payment_file": _serialize_payment_file(payment_file, request)})


@csrf_exempt
def regenerate_payment_file(request, payment_file_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        payment_file = PaymentFile.objects.get(pk=payment_file_id)
    except PaymentFile.DoesNotExist:
        return JsonResponse({"error": "Payment file not found."}, status=404)

    if _get_payment_file_status(payment_file) != 'REJECTED':
        return JsonResponse({"error": "Only rejected payment files can be regenerated."}, status=400)

    if not _can_regenerate_payment_file(payment_file, request.user):
        return JsonResponse({"error": "Only the user who rejected this payment file can regenerate it."}, status=403)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    invoice_ids = payload.get('invoice_ids')
    if not isinstance(invoice_ids, list) or not invoice_ids:
        return JsonResponse({"error": "Select at least one invoice from the rejected payment file."}, status=400)
    allowed_ids = set(payment_file.due_report_rows.values_list('id', flat=True))
    selected_ids = {int(row_id) for row_id in invoice_ids if str(row_id).isdigit()}
    if not selected_ids or selected_ids - allowed_ids:
        return JsonResponse({"error": "One or more selected invoices do not belong to this payment file."}, status=400)
    invoice_rows = list(payment_file.due_report_rows.filter(id__in=selected_ids).order_by('id'))

    if not invoice_rows:
        return JsonResponse({"error": "No valid invoice rows available for regeneration."}, status=400)

    source_overrides = payment_file.line_item_overrides or {}
    overrides_for_new_file = {
        key: value for key, value in source_overrides.items() if int(key) in [row.id for row in invoice_rows]
    }

    new_payment_file = create_payment_file_record(
        payment_type=payment_file.payment_type,
        invoice_rows=invoice_rows,
        created_by=payment_file.created_by or request.user,
        line_item_overrides=overrides_for_new_file,
        rejected_due_report_row_ids=[],
        source_payment_file=payment_file,
    )

    DueReportInvoiceWise.objects.filter(id__in=[row.id for row in invoice_rows]).update(
        manager_rejected=False,
        manager_rejected_at=None,
        manager_rejected_by=None,
        manager_rejection_reason=None,
    )
    PaymentFileReviewEvent.objects.create(
        payment_file=payment_file,
        event_type=PaymentFileReviewEvent.EventType.REGENERATED,
        actor=request.user,
        invoice_ids=[row.id for row in invoice_rows],
        metadata={'new_payment_file_id': new_payment_file.id},
    )

    return JsonResponse({
        "message": "New payment file generated successfully.",
        "payment_file": _serialize_payment_file(new_payment_file, request)
    }, status=201)


@csrf_exempt
def upload_bank_portal_file(request, payment_file_id):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    if not request.user.is_authenticated or not _require_ap_role(request):
        return JsonResponse({"error": "Only AP Team can upload bank portal files."}, status=403)

    try:
        payment_file = PaymentFile.objects.get(pk=payment_file_id)
    except PaymentFile.DoesNotExist:
        return JsonResponse({"error": "Payment file not found."}, status=404)
    if _get_payment_file_status(payment_file) != 'APPROVED':
        return JsonResponse({"error": "Only manager-approved files can be compared."}, status=400)

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({"error": "Bank portal file is required."}, status=400)
    try:
        comparison = compare_bank_file(payment_file, uploaded_file)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    uploaded_file.seek(0)
    payment_file.bank_portal_file.save(uploaded_file.name, uploaded_file, save=False)
    payment_file.bank_file_matches = comparison['matches']
    payment_file.bank_file_comparison = comparison
    payment_file.bank_file_uploaded_at = timezone.now()
    payment_file.bank_file_uploaded_by = request.user
    payment_file.save()
    PaymentFileReviewEvent.objects.create(
        payment_file=payment_file,
        event_type=PaymentFileReviewEvent.EventType.BANK_FILE_COMPARED,
        actor=request.user,
        invoice_ids=list(payment_file.due_report_rows.values_list('id', flat=True)),
        metadata=comparison,
    )
    return JsonResponse({"payment_file": _serialize_payment_file(payment_file, request)})


@csrf_exempt
def ap_review_payment_file(request, payment_file_id):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    if not request.user.is_authenticated or not _require_ap_role(request):
        return JsonResponse({"error": "Only AP Team can review these files."}, status=403)

    try:
        payment_file = PaymentFile.objects.get(pk=payment_file_id)
        payload = json.loads(request.body)
    except PaymentFile.DoesNotExist:
        return JsonResponse({"error": "Payment file not found."}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    action = str(payload.get('action', '')).lower()
    if action not in ['approve', 'reject']:
        return JsonResponse({"error": "action must be either 'approve' or 'reject'."}, status=400)
    rejected_items = payload.get('rejected_items', {})
    if not isinstance(rejected_items, dict):
        return JsonResponse({"error": "rejected_items must map invoice IDs to comments."}, status=400)
    rejected_items = {int(key): str(value).strip() for key, value in rejected_items.items() if str(key).isdigit()}
    if any(not comment for comment in rejected_items.values()):
        return JsonResponse({"error": "A comment is required for every AP-rejected line item."}, status=400)
    if action == 'approve' and rejected_items:
        return JsonResponse({"error": "An approval cannot contain rejected line items."}, status=400)
    if action == 'reject' and not rejected_items:
        return JsonResponse({"error": "Select at least one line item and enter a rejection comment."}, status=400)

    with transaction.atomic():
        links = list(payment_file.invoice_links.select_for_update())
        valid_ids = {link.invoice_id for link in links}
        if set(rejected_items) - valid_ids:
            return JsonResponse({"error": "One or more invoice IDs do not belong to this file."}, status=400)
        for link in links:
            rejected = link.invoice_id in rejected_items
            link.status = PaymentFileInvoice.Status.AP_REJECTED if rejected else PaymentFileInvoice.Status.AP_APPROVED
            link.ap_rejection_reason = rejected_items.get(link.invoice_id)
            link.is_ap_approved = not rejected
            link.is_ap_rejected = rejected
            link.save(update_fields=['status', 'ap_rejection_reason', 'is_ap_approved', 'is_ap_rejected', 'updated_at'])
            if rejected:
                row = link.invoice
                row.manager_rejected = True
                row.manager_rejection_reason = link.ap_rejection_reason
                row.manager_rejected_at = timezone.now()
                row.manager_rejected_by = request.user
                row.save(update_fields=['manager_rejected', 'manager_rejection_reason', 'manager_rejected_at', 'manager_rejected_by'])
        payment_file.ap_reviewed_at = timezone.now()
        payment_file.ap_reviewed_by = request.user
        payment_file.is_payment_file_approved = not rejected_items
        payment_file.is_ap_approved = action == 'approve'
        payment_file.is_ap_rejected = action == 'reject'
        payment_file.rejected_due_report_row_ids = sorted(rejected_items)
        payment_file.status = BatchStatus.REJECTED if rejected_items else BatchStatus.COMPLETED
        payment_file.modified_by = request.user
        payment_file.save(update_fields=[
            'ap_reviewed_at', 'ap_reviewed_by', 'is_payment_file_approved', 'is_ap_approved', 'is_ap_rejected',
            'rejected_due_report_row_ids', 'status', 'modified_by', 'updated_at',
        ])
        PaymentFileReviewEvent.objects.create(
            payment_file=payment_file,
            event_type=(PaymentFileReviewEvent.EventType.AP_REJECTED if rejected_items else PaymentFileReviewEvent.EventType.AP_APPROVED),
            actor=request.user,
            invoice_ids=sorted(rejected_items),
            metadata={
                'rejected_items': {str(key): value for key, value in rejected_items.items()},
                'approved_invoice_ids': sorted(valid_ids - set(rejected_items)),
                'bank_file_matches': payment_file.bank_file_matches,
            },
        )

    return JsonResponse({"payment_file": _serialize_payment_file(payment_file, request)})


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
        file_format = str(payload.get('file_format', 'xlsx')).lower()

        if not invoice_ids or not isinstance(invoice_ids, list):
            return JsonResponse({"error": "invoice_ids must be provided as a list."}, status=400)

        if payment_type not in ["ICICI", "SBI"]:
            return JsonResponse({"error": "payment_type must be either 'ICICI' or 'SBI'."}, status=400)

        if file_format not in ['xlsx', 'csv']:
            return JsonResponse({"error": "file_format must be either 'xlsx' or 'csv'."}, status=400)

        invoice_rows = list(DueReportInvoiceWise.objects.filter(id__in=invoice_ids).order_by('id'))
        if not invoice_rows:
            return JsonResponse({"error": "No due report invoice rows found for the provided IDs."}, status=404)

        active_invoice_ids = set(PaymentFileInvoice.objects.filter(
            invoice_id__in=invoice_ids,
        ).exclude(status__in=[
            PaymentFileInvoice.Status.MANAGER_REJECTED,
            PaymentFileInvoice.Status.AP_REJECTED,
        ]).values_list('invoice_id', flat=True))
        if active_invoice_ids:
            return JsonResponse({"error": "One or more selected invoices already belong to an active payment file."}, status=400)

        payable_invoice_rows = []
        failed_invoices = []
        for invoice_row in invoice_rows:
            try:
                # A stored central-payment reference implies acknowledgement
                # succeeded; repair reset/legacy rows without another API call.
                if invoice_row.payment_reference_number and not invoice_row.is_acknowledged:
                    DueReportInvoiceWise.objects.filter(pk=invoice_row.pk).update(is_acknowledged=True)
                    invoice_row.is_acknowledged = True

                # Persist acknowledgement independently so central-payment
                # failures do not cause duplicate acknowledgements on retry.
                if not invoice_row.is_acknowledged:
                    with transaction.atomic():
                        locked_row = DueReportInvoiceWise.objects.select_for_update().get(pk=invoice_row.pk)
                        if not locked_row.is_acknowledged:
                            approve_bill(locked_row)
                            locked_row.is_acknowledged = True
                            locked_row.save(update_fields=['is_acknowledged'])
                        invoice_row = locked_row

                # A stored hoVoucherNo proves central payment already succeeded.
                if not invoice_row.payment_reference_number:
                    with transaction.atomic():
                        locked_row = DueReportInvoiceWise.objects.select_for_update().get(pk=invoice_row.pk)
                        if not locked_row.payment_reference_number:
                            locked_row.payment_reference_number = create_central_payment(locked_row)
                            locked_row.save(update_fields=['payment_reference_number'])
                            logger.info(
                                'Stored TrueBooks payment reference: invoice_id=%s invoice_no=%s hoVoucherNo=%s',
                                locked_row.pk,
                                locked_row.invoice_no,
                                locked_row.payment_reference_number,
                            )
                        invoice_row = locked_row

                payable_invoice_rows.append(invoice_row)
            except TrueBooksPaymentError as exc:
                logger.warning('Invoice %s excluded from payment file: %s', invoice_row.pk, exc)
                failed_invoices.append({
                    'id': invoice_row.pk,
                    'invoice_no': invoice_row.invoice_no,
                    'error': str(exc),
                })

        if not payable_invoice_rows:
            return JsonResponse({
                "error": "No invoices completed TrueBooks acknowledgement and central payment.",
                "failed_invoices": failed_invoices,
            }, status=502)

        payment_file = create_payment_file_record(
            payment_type=payment_type,
            invoice_rows=payable_invoice_rows,
            created_by=request.user,
        )

        download_url = request.build_absolute_uri(reverse('download_payment_file', args=[payment_file.id]))
        download_url = f"{download_url}?format={file_format}"
        return JsonResponse({
            "message": "Payment file created successfully.",
            "failed_invoices": failed_invoices,
            "processed_invoice_ids": [row.id for row in payable_invoice_rows],
            "payment_file": {
                "id": payment_file.id,
                "unique_id": payment_file.unique_id,
                "status": payment_file.status,
                "payment_status": _get_payment_file_status(payment_file),
                "payment_type": payment_file.payment_type,
                "total_files": payment_file.total_files,
                "processed_files": payment_file.processed_files,
                "download_url": download_url,
                "file_name": f"{payment_file.id}_{payment_file.payment_type}.{file_format}",
                "file_format": file_format,
                "file_url": None,
            }
        }, status=201)

    if request.method == 'GET':
        is_ap_team = UserProfile.objects.filter(user=request.user, role=UserRole.AP_TEAM).exists()
        if request.user.is_staff:
            payment_files = PaymentFile.objects.order_by('-created_at')
        elif is_ap_team:
            payment_files = PaymentFile.objects.filter(
                invoice_links__status__in=[
                    PaymentFileInvoice.Status.MANAGER_APPROVED,
                    PaymentFileInvoice.Status.AP_APPROVED,
                    PaymentFileInvoice.Status.AP_REJECTED,
                    PaymentFileInvoice.Status.PAID,
                ]
            ).distinct().order_by('-created_at')
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
                    "manager_review_status": _get_manager_review_status(payment_file),
                    "ap_review_status": _get_ap_review_status(payment_file),
                    "is_ap_approved": payment_file.is_ap_approved,
                    "is_ap_rejected": payment_file.is_ap_rejected,
                    "payment_type": payment_file.payment_type,
                    "total_files": payment_file.total_files,
                    "processed_files": payment_file.processed_files,
                    "download_url": request.build_absolute_uri(reverse('download_payment_file', args=[payment_file.id])),
                    "file_name": f"{payment_file.id}_{payment_file.payment_type}.xlsx",
                    "file_url": None,
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

    if (
        payment_file.created_by
        and payment_file.created_by != request.user
        and not request.user.is_staff
        and not _is_manager_of(request.user, payment_file.created_by)
        and not _require_ap_role(request)
    ):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    invoice_rows = list(payment_file.due_report_rows.all())
    if not invoice_rows:
        return JsonResponse({"error": "No invoice rows available for this payment file."}, status=404)

    file_format = request.GET.get('format', 'xlsx').lower()
    if file_format not in ['xlsx', 'csv']:
        return JsonResponse({"error": "format must be either 'xlsx' or 'csv'."}, status=400)

    rows_data = build_payment_file_rows(payment_file.payment_type, invoice_rows, overrides=payment_file.line_item_overrides or {})
    if file_format == 'csv':
        file_content = generate_payment_file_content(payment_file.payment_type, rows_data)
        content_type = 'text/csv; charset=utf-8'
    else:
        file_content = generate_payment_file_xlsx(payment_file.payment_type, rows_data)
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    filename = f"{payment_file.id}_{payment_file.payment_type}.{file_format}"

    response = HttpResponse(file_content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
