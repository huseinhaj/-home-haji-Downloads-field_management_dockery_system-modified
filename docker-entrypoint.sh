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
" || true
fi

# Load base data (regions, districts, subjects) - fast, skips if already exists
echo "Loading base data..."
python manage.py loaddata regions.json || true
python manage.py loaddata districts.json || true
python manage.py import_subjects data/subjects.csv || true
python manage.py loaddata education_levels.json || true

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Load schools + link subjects + mark special needs in background
echo "Loading schools in background..."
(python manage.py loaddata schools.json || true; \
 python manage.py loaddata missing_schools.json || true; \
 python manage.py loaddata zanzibar_schools.json || true; \
 python manage.py loaddata mainland_private_schools.json || true; \
 python manage.py setup_school_subjects || true; \
 python manage.py shell -c "from field_app.models import School; School.objects.update(current_students=0); print('Reset current_students to 0')" || true; \
 python manage.py import_schools_pdf --overwrite || true; \
 python manage.py mark_special_needs_schools || true) &

# Trigger initial HESLB knowledge fetch in background (first boot only)
echo "Scheduling initial HESLB knowledge fetch..."
(python manage.py shell -c "
from field_app.heslb_knowledge import get_knowledge, scrape_and_update
if not get_knowledge():
    print('HESLB cache empty — fetching now...')
    r = scrape_and_update()
    print('HESLB fetch:', r.get('ok'), r.get('updated_at',''), r.get('error',''))
else:
    print('HESLB knowledge already cached.')
" 2>&1 || true) &

# Start gunicorn
echo "Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn field_management.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
