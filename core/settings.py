"""
Django settings for core project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-sf$t1)@cv4nh7k=t6+j(g-(m5okmns=icu4g86!mr(e92p2*c3'

DEBUG = True

# Toggle debug logging for runtime parsing/diagnostics. Can be set via env var:
# LOGGER_MODE_DEBUG=1 or LOGGER_MODE_DEBUG=true
LOGGER_MODE_DEBUG = os.environ.get('LOGGER_MODE_DEBUG', 'True').strip().lower() in ('1', 'true', 'yes')

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'ap_app',
    'import_export',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'frontend', 'build')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DEFAULT_DB_NAME', 'ap_tool'),
        'USER': os.environ.get('DEFAULT_DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DEFAULT_DB_PASSWORD', 'admin'),
        'HOST': os.environ.get('DEFAULT_DB_HOST', 'localhost'),
        'PORT': os.environ.get('DEFAULT_DB_PORT', '5433'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'frontend', 'build', 'static'),
    os.path.join(BASE_DIR, 'frontend', 'build'),
]

# Set the media root so uploaded files go to a specific local directory
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# MSAL Configuration
# Load these from the .env file instead of hardcoding dummy values
MSAL_CLIENT_ID = os.environ.get("MSAL_CLIENT_ID", "dummy_client_id")
MSAL_CLIENT_SECRET = os.environ.get("MSAL_CLIENT_SECRET", "dummy_client_secret")
# Use the common endpoint by default if no tenant ID is specified
MSAL_TENANT_ID = os.environ.get("MSAL_TENANT_ID", "common")
MSAL_AUTHORITY = f"https://login.microsoftonline.com/{MSAL_TENANT_ID}"
MSAL_REDIRECT_URI = "http://localhost:8000/api/auth/callback"
MSAL_SCOPES = ["User.ReadBasic.All"]

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG' if LOGGER_MODE_DEBUG else 'INFO',
    },
}

DATA_UPLOAD_MAX_NUMBER_FILES = 1000  # Allow uploading large folders (default is 100)

# Celery Configuration
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'