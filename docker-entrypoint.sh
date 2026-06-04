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

# Create superuser and board member if DJANGO_SUPERUSER_EMAIL is set
if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "Creating superuser..."
    python manage.py shell -c "
from django.contrib.auth import get_user_model
from field_app.models import BoardMember
User = get_user_model()
email = '$DJANGO_SUPERUSER_EMAIL'
password = '$DJANGO_SUPERUSER_PASSWORD'
if not User.objects.filter(email=email).exists():
    user = User.objects.create_superuser(email=email, password=password)
    print('Superuser created.')
else:
    user = User.objects.get(email=email)
    print('Superuser already exists.')
if not BoardMember.objects.filter(user=user).exists():
    BoardMember.objects.create(user=user, full_name='Admin', role='chair', is_active=True)
    print('BoardMember created.')
else:
    print('BoardMember already exists.')
# Create board user (fixed credentials)
board_email = 'bodi@ims.tz'
board_password = 'bodi1234'
if not User.objects.filter(email=board_email).exists():
    board_user = User.objects.create_user(email=board_email, password=board_password)
    print('Board user created.')
else:
    board_user = User.objects.get(email=board_email)
    print('Board user already exists.')
if not BoardMember.objects.filter(user=board_user).exists():
    BoardMember.objects.create(user=board_user, full_name='Bodi ya Walimu', role='chair', is_active=True)
    print('Board member created.')
" || true
fi

# Load base data (regions, districts, subjects) - fast, skips if already exists
echo "Loading base data..."
python manage.py loaddata regions.json || true
python manage.py loaddata districts.json || true
python manage.py import_subjects data/subjects.csv || true
python manage.py loaddata education_levels.json || true

# Link schools with subjects (runs foreground - schools already in DB)
echo "Setting up school-subject links..."
python manage.py setup_school_subjects || true

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Load schools in background (skips if already loaded)
echo "Loading schools in background..."
(python manage.py loaddata schools.json || true; \
 python manage.py shell -c "from field_app.models import School; School.objects.update(current_students=0); print('Reset current_students to 0')" || true; \
 python manage.py import_schools_pdf --overwrite || true) &

# Start gunicorn
echo "Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn field_management.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
