import os
import json
import msal
import logging
import requests
import base64
from django.conf import settings
from django.shortcuts import redirect
from django.http import JsonResponse
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import FileSystemStorage
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import UserProfile, UserRole, OCRBatch, DocumentResult, BatchStatus, ReconciliationStatus
from .tasks import process_ocr_batch

logger = logging.getLogger(__name__)

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

    user, user_created = User.objects.get_or_create(username=email, defaults={'email': email, 'first_name': name})
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
        except UserProfile.DoesNotExist:
            role = UserRole.UNASSIGNED
            msal_data = {}
            photo = None
            
        return JsonResponse({
            "authenticated": True,
            "username": request.user.username,
            "role": role,
            "email": request.user.email,
            "first_name": request.user.first_name,
            "msal_data": msal_data,
            "photo": photo,
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

    files = request.FILES.getlist('files')
    if not files:
        return JsonResponse({"error": "No files provided"}, status=400)

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
        # Save the file using its original name
        # If the user uploaded a folder, the frontend sometimes passes the relative path as the filename
        # We need to sanitize it to just the filename to avoid directory traversal issues
        safe_filename = os.path.basename(f.name)
        fs.save(safe_filename, f)
    
    # 3. Phase 2 Trigger: Call Celery worker (asynchronous)
    # The .delay() method puts the task in the Redis queue for the Celery worker to pick up
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
    Frontend polls this endpoint. Returns status. If complete, returns data.
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

        # If completed, manual review, or failed, fetch and return all the parsed data we have so far
        if str(batch.status) in [BatchStatus.COMPLETED, BatchStatus.MANUAL_REVIEW, BatchStatus.FAILED, 'INVOICES_SCANNED', 'MANUAL_REVIEW', 'FAILED']:
            documents = DocumentResult.objects.filter(batch=batch)
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
        })
    except DocumentResult.DoesNotExist:
        return JsonResponse({"error": "Document not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


#do not write below this line
@csrf_exempt
def get_bills(request):
    if request.method == 'GET':
        # Contract API response for GetBills
        data = {
            "status": "success",
            "message": "success",
            "data": [
                {
                    "tranYear": "2025_2026",
                    "branchCode": 1,
                    "branchName": "AEOC RPOS6",
                    "voucherNo": "2025_2026_52_1_1",
                    "voucherDate": "2026-03-02 00:00:00",
                    "billRefNo": "HO-PU17",
                    "billDate": "2026-03-02 00:00:00",
                    "partyCode": 10060000046,
                    "partyName": "sup new approved",
                    "voucherType": "Purchase",
                    "invoiceNo": "IN18196526016011",
                    "invoiceDate": "2026-03-02 00:00:00",
                    "voucherAmount": 400,
                    "expenseLedger": "Interstate GST28% Purchase",
                    "goodsValue": 1083.20,
                    "taxAmount": 0,
                    "taxCode": "GST 28%+Cess 12%",
                    "taxType": "IGST",
                    "tdsAmount": 0,
                    "tdsSection": " ",
                    "dueDays": 0,
                    "dueDate": "2026-03-02 00:00:00",
                    "payMode": "Bank",
                    "otherCharges": 0,
                    "paymentStatus": "NOT PAID",
                    "transactionLink": "/TrueBooks/transactionRedirect.do?companyCode=1&tranYear=2025_2026&acType=1&divisionCode=1&locationCode=1&voucherNo=45&isVoucherScr=Y&voucherCode=3&ishqvoucher=1&isdelete=0&invoiceno=234343&operation=VIEW",
                    "payable": 1083.20,
                    "groupName": "Suppliers",
                    "billUniqueId": "45_1_1_1"
                },
                {
                    "tranYear": "2025_2026",
                    "branchCode": 1,
                    "branchName": "AEOC RPOS6",
                    "voucherNo": "2025_2026_53_1_1",
                    "voucherDate": "2026-03-02 00:00:00",
                    "billRefNo": "HO-PU18",
                    "billDate": "2026-03-02 00:00:00",
                    "partyCode": 10060000046,
                    "partyName": "sup new approved",
                    "voucherType": "Purchase",
                    "invoiceNo": "IN18196526016009",
                    "invoiceDate": "2026-02-03 00:00:00",
                    "voucherAmount": 11414.06,
                    "expenseLedger": "Interstate GST28% Purchase",
                    "goodsValue": 34.72,
                    "taxAmount": 538.39,
                    "taxCode": "GST 28%+Cess 160%",
                    "taxType": "IGST",
                    "tdsAmount": 0,
                    "tdsSection": " ",
                    "dueDays": 0,
                    "dueDate": "2026-02-03 00:00:00",
                    "payMode": "Bank",
                    "otherCharges": 0,
                    "paymentStatus": "NOT PAID",
                    "transactionLink": "/TrueBooks/transactionRedirect.do?companyCode=1&tranYear=2025_2026&acType=1&divisionCode=1&locationCode=1&voucherNo=46&isVoucherScr=Y&voucherCode=3&ishqvoucher=1&isdelete=0&invoiceno=3ewe3&operation=VIEW",
                    "payable": 1306.00,
                    "groupName": "Suppliers",
                    "billUniqueId": "46_1_1_1"
                }
            ]
        }
        return JsonResponse(data)
    return JsonResponse({"error": "Method not allowed"}, status=405)

@csrf_exempt
def central_payment(request):
    if request.method == 'POST':
        data = {
            "docNo": "HO-PY7",
            "hoVoucherNo": "1",
            "message": "Success"
        }
        return JsonResponse(data)
    return JsonResponse({"error": "Method not allowed"}, status=405)