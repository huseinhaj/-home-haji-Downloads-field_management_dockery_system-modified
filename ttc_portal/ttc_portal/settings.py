"""
Django settings for the TTC Student Portal (Mfumo wa Vyuo vya Ualimu).

Standalone project with its OWN separate, self-contained database.
Linked with the field_management project only at the repository level.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present (allows DATABASE_URL override for deployment)
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('TTC_SECRET_KEY', 'dev-only-insecure-key-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production
DEBUG = os.environ.get('TTC_DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = os.environ.get(
    'TTC_ALLOWED_HOSTS',
    'localhost,127.0.0.1,0.0.0.0,.railway.app,.up.railway.app,'
    'home-haji-downloads-fieldmanagementdockerysy-production.up.railway.app,'
    'internshipmanagementsystem.online,www.internshipmanagementsystem.online',
).split(',')

CSRF_TRUSTED_ORIGINS = os.environ.get(
    'TTC_CSRF_TRUSTED_ORIGINS',
    'https://*.railway.app,https://*.up.railway.app,'
    'https://home-haji-downloads-fieldmanagementdockerysy-production.up.railway.app,'
    'https://internshipmanagementsystem.online,https://www.internshipmanagementsystem.online,'
    'http://localhost,http://localhost:8001,http://127.0.0.1:8001',
).split(',')

# ── Deployed INSIDE the field_management container under /ttc/ ──
# The nginx proxy strips nothing (passes the full URI); Django uses this to
# build all reversed URLs with the /ttc/ prefix.
FORCE_SCRIPT_NAME = '/ttc'

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = os.environ.get('TTC_SSL_REDIRECT', 'False').lower() == 'true'

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Local apps
    'accounts',
    'colleges',
    'students',
    'fees',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'ttc_portal.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ttc_portal.wsgi.application'

# ── Database: SEPARATE, self-contained database for this project ──
import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        env='TTC_DATABASE_URL',          # ← ONLY this var; never pick up the
        default='sqlite:///ttc_db.sqlite3',  #   field_management DATABASE_URL!
        conn_max_age=600,
        conn_health_checks=True,
    ),
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization — Swahili-first like SR2/GePG portals in Tanzania
LANGUAGE_CODE = 'sw'
TIME_ZONE = 'Africa/Dar_es_Salaam'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# Served by the container nginx straight from disk under /ttc/static/
STATIC_URL = '/ttc/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
# No manifest hashing: nginx serves the raw files directly.
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Media files
MEDIA_URL = '/ttc/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Keep TTC session/csrf cookies scoped to /ttc/ so they never collide with
# the field_management cookies served at the root path.
SESSION_COOKIE_PATH = '/ttc/'
CSRF_COOKIE_PATH = '/ttc/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Custom user model ──
AUTH_USER_MODEL = 'accounts.CustomUser'

AUTHENTICATION_BACKENDS = [
    'accounts.backends.IdentifierBackend',   # login by registration number OR email
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'home'

# Email — console backend by default (dev)
EMAIL_BACKEND = os.environ.get(
    'TTC_EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend'
)
DEFAULT_FROM_EMAIL = os.environ.get('TTC_FROM_EMAIL', 'TTC Portal <noreply@ttcportal.ac.tz>')

# Simulated GePG-style payment configuration
TTC_CONTROL_NUMBER_PREFIX = os.environ.get('TTC_CONTROL_NUMBER_PREFIX', '99')
TTC_CONTROL_NUMBER_LIFETIME_DAYS = int(os.environ.get('TTC_CONTROL_NUMBER_LIFETIME_DAYS', '30'))
TTC_SYSTEM_NAME = os.environ.get('TTC_SYSTEM_NAME', 'TTC Student Portal')

# ── Real GePG (Government e-Payment Gateway) integration ──────────────────
# Credentials hizi zinapatikana baada ya PSP registration na GePG (kupitia
# benki yako au GePG moja kwa moja) — tazama README sehemu ya GePG.
# Zikiwa hazijawekwa, mfumo unatumia simulated control numbers kiotomatiki.
TTC_GEPG_ENABLED = os.environ.get('TTC_GEPG_ENABLED', 'False').lower() == 'true'
TTC_GEPG_CODE = os.environ.get('TTC_GEPG_CODE', '')            # mf. SP023 — SP code
TTC_GEPG_SUB_SP_CODE = os.environ.get('TTC_GEPG_SUB_SP_CODE', '')
TTC_GEPG_SP_SYS_ID = os.environ.get('TTC_GEPG_SP_SYS_ID', '')  # mf. SYSTT000
TTC_GEPG_GFS_CODE = os.environ.get('TTC_GEPG_GFS_CODE', '')    # mf. 140100 (tuition fees)
TTC_GEPG_API_URL = os.environ.get('TTC_GEPG_API_URL', '')      # GePG gateway base URL (HTTPS/mTLS)
TTC_GEPG_API_USER = os.environ.get('TTC_GEPG_API_USER', '')
TTC_GEPG_API_PASSWORD = os.environ.get('TTC_GEPG_API_PASSWORD', '')
TTC_GEPG_PRIVATE_KEY_PATH = os.environ.get('TTC_GEPG_PRIVATE_KEY_PATH', '')  # PKCS#8 PEM au PKCS#12 (.pfx)
TTC_GEPG_PRIVATE_KEY_PASSWORD = os.environ.get('TTC_GEPG_PRIVATE_KEY_PASSWORD', '')
TTC_GEPG_CLIENT_CERT = os.environ.get('TTC_GEPG_CLIENT_CERT', '')  # PEM cert chain (mTLS)
TTC_GEPG_CLIENT_KEY = os.environ.get('TTC_GEPG_CLIENT_KEY', '')    # PEM private key (mTLS)
TTC_GEPG_SIGNATURE_ALGORITHM = os.environ.get('TTC_GEPG_SIGNATURE_ALGORITHM', 'SHA1withRSA')
TTC_GEPG_NOTIFICATION_TOKEN = os.environ.get('TTC_GEPG_NOTIFICATION_TOKEN', '')
TTC_GEPG_TIMEOUT = int(os.environ.get('TTC_GEPG_TIMEOUT', '30'))
