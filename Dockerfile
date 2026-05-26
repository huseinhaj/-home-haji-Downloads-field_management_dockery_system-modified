# ── Base image ────────────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ── System dependencies ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    binutils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Detect actual GDAL/GEOS paths at build time and bake into ENV
RUN GDAL_PATH=$(find /usr/lib -name 'libgdal.so' | head -1) && \
    GEOS_PATH=$(find /usr/lib -name 'libgeos_c.so' | head -1) && \
    echo "GDAL_LIBRARY_PATH=$GDAL_PATH" && \
    echo "GEOS_LIBRARY_PATH=$GEOS_PATH" && \
    echo "export GDAL_LIBRARY_PATH=$GDAL_PATH" >> /etc/profile.d/geodjango.sh && \
    echo "export GEOS_LIBRARY_PATH=$GEOS_PATH" >> /etc/profile.d/geodjango.sh

# Set them as ENV using the detected values
RUN GDAL_PATH=$(find /usr/lib -name 'libgdal.so' | head -1) && \
    GEOS_PATH=$(find /usr/lib -name 'libgeos_c.so' | head -1) && \
    printf "GDAL_LIBRARY_PATH=%s\nGEOS_LIBRARY_PATH=%s\n" "$GDAL_PATH" "$GEOS_PATH" > /app/.geoenv

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

# ── Startup script ─────────────────────────────────────────────────────────────
COPY --chown=appuser:appgroup docker-entrypoint.sh /app/docker-entrypoint.sh

EXPOSE 8000

CMD ["/app/docker-entrypoint.sh"]
