import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'field_management.settings')
app = Celery('field_management')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
