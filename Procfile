web: /app/docker-entrypoint.sh
worker: celery -A field_management worker --loglevel=info --concurrency=2 --queues=default,emails
worker_fill: celery -A field_management worker --loglevel=info --concurrency=${ESS_FILL_CONCURRENCY:-4} --queues=essfill --max-tasks-per-child=20
beat: celery -A field_management beat --loglevel=info
