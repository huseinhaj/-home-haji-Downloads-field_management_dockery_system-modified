web: /app/docker-entrypoint.sh
worker: celery -A field_management worker --loglevel=info --concurrency=2 --queues=default,emails
beat: celery -A field_management beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
