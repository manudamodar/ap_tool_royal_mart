from django.urls import path
from . import views

urlpatterns = [
    path('auth/login/', views.msal_login, name='msal_login'),
    path('auth/callback', views.msal_callback, name='msal_callback'),  # Removed trailing slash
    path('auth/logout/', views.msal_logout, name='msal_logout'),
    path('auth/user/', views.get_user_info, name='get_user_info'),
    path('rest/payable/getbills', views.get_bills, name='get_bills'),
    path('rest/central-payment', views.central_payment, name='central_payment'),
]
