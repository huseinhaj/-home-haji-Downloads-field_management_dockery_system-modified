# ── Base image ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ── System dependencies ────────────────────────────────────────────────────────
# gcc + libpq-dev  : psycopg2 compilation
# gdal-bin + libgdal-dev + libgeos-dev : django.contrib.gis (Point/Distance)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    binutils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Auto-detect GDAL/GEOS paths so image works on both amd64 and arm64
RUN echo "GDAL_LIBRARY_PATH=$(find /usr/lib -name 'libgdal.so*' | head -1)" >> /etc/environment && \
    echo "GEOS_LIBRARY_PATH=$(find /usr/lib -name 'libgeos_c.so*' | head -1)" >> /etc/environment

ENV GDAL_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgdal.so
ENV GEOS_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgeos_c.so.2

# ── Python dependencies (cached layer) ────────────────────────────────────────
COPY requirements.txt .
RUN pip install -r requirements.txt

# ── Application code ───────────────────────────────────────────────────────────
COPY . .

# ── Non-root user for security ────────────────────────────────────────────────
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appgroup /app

USER appuser

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000

# migrate + collectstatic run at startup (not build) so no secret key needed at build time
CMD ["sh", "-c", \
    "python manage.py migrate --noinput && \
     python manage.py collectstatic --noinput && \
     gunicorn field_management.wsgi:application \
       --bind 0.0.0.0:${PORT:-8000} \
       --workers ${WEB_CONCURRENCY:-2} \
       --timeout 120 \
       --access-logfile - \
       --error-logfile -"]
