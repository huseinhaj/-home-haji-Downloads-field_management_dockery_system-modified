#!/bin/sh
set -e

# Load detected GDAL/GEOS paths
if [ -f /app/.geoenv ]; then
    export $(cat /app/.geoenv | xargs)
fi

echo "GDAL_LIBRARY_PATH=$GDAL_LIBRARY_PATH"
echo "GEOS_LIBRARY_PATH=$GEOS_LIBRARY_PATH"

# ═════════════════════════════════════════════════════════════════════════════
# TTC STUDENT PORTAL — separate Django project with its OWN database.
# Deployed inside this same container under /ttc/ via container nginx.
# Only active when TTC_PORTAL_ENABLED=true (set on Railway). When the flag is
# off (e.g. docker-compose on the VPS) field_management behaves exactly as
# before — the two projects never touch each other's data.
# ═════════════════════════════════════════════════════════════════════════════
TTC_READY=0
# Normalise the flag: accept true/True/TRUE/1/yes (trim + lowercase) so a
# copy-paste with different casing can never silently disable the portal.
TTC_FLAG="$(printf '%s' "$TTC_PORTAL_ENABLED" | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
echo "TTC_PORTAL_ENABLED='$TTC_PORTAL_ENABLED' → normalised='$TTC_FLAG' (TTC_DATABASE_URL set: $([ -n "$TTC_DATABASE_URL" ] && echo yes || echo no))"
if [ "$TTC_FLAG" = "true" ] || [ "$TTC_FLAG" = "1" ] || [ "$TTC_FLAG" = "yes" ]; then
    echo "🖥️  TTC Student Portal ENABLED — running its own migrations..."
    # Failure-tolerant: ikiwa TTC itashindwa (mf. TTC_DATABASE_URL mbovu),
    # field_management inaendelea kuanza bila TTC portal — haipotezi container.
    if (cd /app/ttc_portal && python manage.py migrate --noinput); then
        # Seed is fully idempotent (get_or_create) — run it every boot so a
        # partial/crashed seed heals itself. Demo accounts (admin/admin123)
        # are created ONLY when TTC_SEED_DEMO=true or DEBUG=true, so in
        # production no passwords are ever created or reset.
        echo "Seeding TTC data (vyuo, programu, ada)..."
        (cd /app/ttc_portal && python seed_data.py) || echo "⚠️  TTC seed failed — continuing."
        # Collect TTC static (incl. Django admin) so nginx serves /ttc/static/
        echo "Collecting TTC static files..."
        (cd /app/ttc_portal && python manage.py collectstatic --noinput) || echo "⚠️  TTC collectstatic failed."
        TTC_READY=1
    else
        echo "⚠️  TTC migrations FAILED (angalia TTC_DATABASE_URL) — field_management itaendelea bila TTC portal."
    fi
fi

# Run field_management migrations
echo "Running migrations..."
python manage.py migrate --noinput
python manage.py migrate --database=transfer --noinput
python manage.py migrate --database=results --noinput

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

# ── Start services ────────────────────────────────────────────────────────────
if [ "$TTC_READY" = "1" ]; then
    # TTC portal gunicorn on internal port 8001
    echo "Starting TTC portal gunicorn on 127.0.0.1:8001..."
    (cd /app/ttc_portal && exec gunicorn ttc_portal.wsgi:application \
        --bind "127.0.0.1:8001" \
        --workers "${TTC_WEB_CONCURRENCY:-1}" \
        --timeout 120 \
        --access-logfile - \
        --error-logfile -) &
    TTC_PID=$!

    # Container nginx — owns the public port, routes /ttc/ → TTC portal,
    # everything else → field_management (started below on 127.0.0.1:8000).
    PORT="${PORT:-8000}"
    echo "Starting container nginx on 0.0.0.0:${PORT}..."
    sed "s/\${PORT}/$PORT/g" /app/nginx-container.conf > /tmp/nginx.conf
    nginx -c /tmp/nginx.conf -g 'daemon off;' &
    NGINX_PID=$!

    # field_management gunicorn as a background job (NOT exec) so this shell
    # stays PID 1 and the trap below can kill ALL three on SIGTERM/SIGINT —
    # graceful shutdown ya TTC gunicorn na nginx pia.
    echo "Starting field_management gunicorn on 127.0.0.1:8000 (behind nginx)..."
    gunicorn field_management.wsgi:application \
        --bind "127.0.0.1:8000" \
        --workers "${WEB_CONCURRENCY:-2}" \
        --timeout 300 \
        --access-logfile - \
        --error-logfile - &
    FM_PID=$!

    cleanup() { kill "$FM_PID" "$TTC_PID" "$NGINX_PID" 2>/dev/null || true; }
    trap cleanup TERM INT EXIT

    # Wait for the main app; if it exits, the container stops and cleanup kills
    # the other two.
    wait "$FM_PID"
else
    # Original single-app behaviour (docker-compose / TTC not enabled)
    echo "Starting gunicorn on port ${PORT:-8000}..."
    exec gunicorn field_management.wsgi:application \
        --bind "0.0.0.0:${PORT:-8000}" \
        --workers "${WEB_CONCURRENCY:-2}" \
        --timeout 300 \
        --access-logfile - \
        --error-logfile -
fi
