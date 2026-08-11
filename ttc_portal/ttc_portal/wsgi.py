"""WSGI config for ttc_portal project."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ttc_portal.settings')

application = get_wsgi_application()
