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
from .models import UserProfile, UserRole

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
    # We update the msal_data dictionary but we preserve the old MSAL data and just update it
    # so we don't lose information if MSAL gives less info next time.
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
                    "invoiceNo": "234343",
                    "invoiceDate": "2026-03-02 00:00:00",
                    "voucherAmount": 400,
                    "expenseLedger": "Interstate GST28% Purchase",
                    "goodsValue": 285.71,
                    "taxAmount": 114.29,
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
                    "payable": 400,
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
                    "invoiceNo": "3ewe3",
                    "invoiceDate": "2026-02-03 00:00:00",
                    "voucherAmount": 100,
                    "expenseLedger": "Interstate GST28% Purchase",
                    "goodsValue": 34.72,
                    "taxAmount": 65.28,
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
                    "payable": 100,
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
