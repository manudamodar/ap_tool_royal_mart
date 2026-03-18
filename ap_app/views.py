import msal
import logging
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
        redirect_uri=settings.MSAL_REDIRECT_URI
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

    # No explicit role assignment here; it will use the model's default (UNASSIGNED)
    
    profile.msal_data = user_info
    profile.save()
    logger.info(f"UserProfile for {user.username} saved successfully.")

    login(request, user)
    logger.info(f"User {user.username} logged into Django session.")
    
    return redirect('/')

@csrf_exempt
def msal_logout(request):
    logout(request)
    return JsonResponse({"status": "logged_out"})

def get_user_info(request):
    if request.user.is_authenticated:
        try:
            profile = UserProfile.objects.get(user=request.user)
            role = profile.role
            msal_data = profile.msal_data
        except UserProfile.DoesNotExist:
            # If for some reason a UserProfile doesn't exist, default to UNASSIGNED
            role = UserRole.UNASSIGNED
            msal_data = {}
            
        return JsonResponse({
            "authenticated": True,
            "username": request.user.username,
            "role": role,
            "email": request.user.email,
            "first_name": request.user.first_name,
            "msal_data": msal_data,
        })
    else:
        return JsonResponse({"authenticated": False})
