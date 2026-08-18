from django.urls import path
from . import go_frugal_views, views

urlpatterns = [
    path('auth/login/', views.msal_login, name='msal_login'),
    path('auth/callback', views.msal_callback, name='msal_callback'),
    path('auth/logout/', views.msal_logout, name='msal_logout'),
    path('auth/user/', views.get_user_info, name='get_user_info'),
    
    # FOR TESTING: User Type Allocation Change Feature (To be removed later)
    path('auth/change_role/', views.change_user_role, name='change_user_role'),

    # OCR Endpoints
    path('ocr/upload/', views.upload_batch, name='upload_batch'),
    # Changed from <uuid:batch_id> to <str:batch_id> to support our custom string format
    path('ocr/status/<str:batch_id>/', views.check_batch_status, name='check_batch_status'),
    path('ocr/batches/', views.get_user_batches, name='get_user_batches'),
    path('ocr/document/<int:document_id>/', views.get_document_ocr_data, name='get_document_ocr_data'),
    path('ocr/document/<int:document_id>/update/', views.update_document_data, name='update_document_data'),

    #do not write below this line
    path('rest/payable/getbills', views.get_bills, name='get_bills'),
    path('rest/payable/gofrugal/sync', go_frugal_views.sync_bills, name='sync_gofrugal_bills'),
    path('rest/central-payment', views.central_payment, name='central_payment'),
    path('rest/central-payment/<str:payment_file_id>/', views.payment_file_detail, name='payment_file_detail'),
    path('rest/central-payment/<str:payment_file_id>/review/', views.review_payment_file, name='review_payment_file'),
    path('rest/central-payment/<str:payment_file_id>/regenerate/', views.regenerate_payment_file, name='regenerate_payment_file'),
    path('rest/central-payment/<str:payment_file_id>/bank-file/', views.upload_bank_portal_file, name='upload_bank_portal_file'),
    path('rest/central-payment/<str:payment_file_id>/ap-review/', views.ap_review_payment_file, name='ap_review_payment_file'),
    path('rest/central-payment/download/<str:payment_file_id>/', views.download_payment_file, name='download_payment_file'),
    # do not write below this line

]
