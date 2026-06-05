"""
Django settings for field_management project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file so all environment variables are available
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-only-insecure-key-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production
DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() == 'true'

# ALLOWED_HOSTS for Railway
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.railway.app',  # Inaruhusu subdomain zote za railway.app
    '.up.railway.app',  # Alternative railway domain
    'home-haji-downloads-fieldmanagementdockerysy-production.up.railway.app',
]

# CSRF Trusted Origins - Muhimu kwa Railway!
CSRF_TRUSTED_ORIGINS = [
    'https://*.railway.app',
    'https://*.up.railway.app',
    'https://home-haji-downloads-fieldmanagementdockerysy-production.up.railway.app',
    'http://localhost',
    'http://localhost:8000',
    'http://127.0.0.1',
    'http://127.0.0.1:8000',
]

# SSL/HTTPS settings
# Railway handles SSL termination — tell Django to trust X-Forwarded-Proto header
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Sessions — use db backend (simpler, avoids per-worker cache sync issues on Railway)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# CSRF cookie security
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'

# Click-jacking protection — zuia ukurasa kuwekwa kwenye iframe ya tovuti nyingine
X_FRAME_OPTIONS = 'SAMEORIGIN'

# Browser security headers
SECURE_CONTENT_TYPE_NOSNIFF = True     # Zuia browser kubadilisha aina ya faili
SECURE_BROWSER_XSS_FILTER = True       # XSS filter kwenye browser za zamani

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
    'field_app',
    'import_export',
    'widget_tweaks',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.gzip.GZipMiddleware',          # Compress responses - punguza bandwidth 70%
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'field_app.middleware.NoCacheAuthMiddleware',
]

ROOT_URLCONF = 'field_management.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),
            os.path.join(BASE_DIR, 'field_app/templates/field_app'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'field_app.context_processors.language',
            ],
        },
    },
]

WSGI_APPLICATION = 'field_management.wsgi.application'

# Database - Tumia DATABASE_URL kutoka Railway
import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL', 'sqlite:///db.sqlite3'),
        conn_max_age=600,        # Weka connections wazi 10 min - punguza overhead
        conn_health_checks=True, # Kagua connection kabla kutumia
    )
}

# Password validation
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

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'field_app/static'),
]

# WhiteNoise compression
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom user model
AUTH_USER_MODEL = 'field_app.CustomUser'

# Authentication backends
AUTHENTICATION_BACKENDS = [
    'field_app.backends.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Login URLs
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# Email configuration - Tumia environment variables
EMAIL_HOST_USER = (
    os.environ.get('EMAIL_HOST_USER') or
    os.environ.get('DJANGO_HOST_USER') or
    'huseinhaj09@gmail.com'
)
EMAIL_HOST_PASSWORD = (
    os.environ.get('EMAIL_HOST_PASSWORD') or
    os.environ.get('DJANGO_HOST_PASSWORD') or
    ''
)

# Tumia Gmail SMTP - force IPv4 ili kuepuka tatizo la Railway
if EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = '74.125.133.108'  # smtp.gmail.com IPv4 (force IPv4)
    EMAIL_PORT = 465
    EMAIL_USE_TLS = False
    EMAIL_USE_SSL = True
else:
    # Kama password haijawekwa - andika kwenye logs badala ya kutuma
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = f'IMS System <{EMAIL_HOST_USER}>'
SERVER_EMAIL = EMAIL_HOST_USER
EMAIL_TIMEOUT = 30

# GDAL Configuration for GeoDjango
GDAL_LIBRARY_PATH = os.environ.get('GDAL_LIBRARY_PATH', '/usr/lib/x86_64-linux-gnu/libgdal.so')
GEOS_LIBRARY_PATH = os.environ.get('GEOS_LIBRARY_PATH', '/usr/lib/x86_64-linux-gnu/libgeos_c.so')

# Cache configuration - Redis (Railway/production) au LocMem (development)
_REDIS_URL = os.environ.get('REDIS_URL') or os.environ.get('REDISCLOUD_URL')
if _REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': _REDIS_URL,
            'TIMEOUT': 300,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_KWARGS': {'max_connections': 20},
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
                'IGNORE_EXCEPTIONS': True,  # Mfumo uendelee hata Redis ikishindwa
            },
            'KEY_PREFIX': 'ims',
        }
    }
    # Session kwenye Redis - haraka zaidi kuliko database
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'ims-cache',
            'TIMEOUT': 300,
            'OPTIONS': {'MAX_ENTRIES': 2000},
        }
    }

# Internal IPs for debugging
INTERNAL_IPS = ['127.0.0.1']

# Media files (User uploaded content)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
