"""
Test settings — SQLite local kwa ajili ya tests haraka (bila DB za mbali za
Railway). Django test runner inahitaji kuunda/kuharibu test DB; kwenye
Postgres za mbali hilo linafikia timeout au linauliza confirm.

All other settings inherit from field_management.settings.
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_test_default.sqlite3',
    },
    'transfer': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_test_transfer.sqlite3',
    },
    'results': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_test_results.sqlite3',
    },
}

# Tests hazihitaji AI wala billing
CELERY_TASK_ALWAYS_EAGER = True
