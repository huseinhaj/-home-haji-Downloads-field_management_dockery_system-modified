#!/bin/sh
set -e

# Load detected GDAL/GEOS paths
if [ -f /app/.geoenv ]; then
    export $(cat /app/.geoenv | xargs)
fi

echo "GDAL_LIBRARY_PATH=$GDAL_LIBRARY_PATH"
echo "GEOS_LIBRARY_PATH=$GEOS_LIBRARY_PATH"

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Create superuser if DJANGO_SUPERUSER_EMAIL is set
if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "Creating superuser..."
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
email = '$DJANGO_SUPERUSER_EMAIL'
password = '$DJANGO_SUPERUSER_PASSWORD'
if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(email=email, password=password)
    print('Superuser created.')
else:
    print('Superuser already exists.')
" || true
fi

# Load base data (regions, districts, subjects) - fast, skips if already exists
echo "Loading base data..."
python manage.py loaddata regions.json || true
python manage.py loaddata districts.json || true
python manage.py import_subjects data/subjects.csv || true

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Load schools in background after startup (slow - 21k records)
echo "Loading schools in background..."
(python manage.py loaddata schools.json && \
 python manage.py shell -c "from field_app.models import School; School.objects.update(current_students=0); print('Reset current_students to 0')" && \
 python manage.py import_schools_pdf --overwrite && \
 echo "Schools loaded OK") &

# Start gunicorn
echo "Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn field_management.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
