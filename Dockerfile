# ── Stage 1: Builder ───────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build-time system dependencies (compilers + dev headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    binutils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages into an isolated prefix so we can copy them cleanly
COPY requirements.txt /tmp/requirements.txt
RUN pip install --prefix=/install --no-cache-dir -r /tmp/requirements.txt


# ── Stage 2: Runtime ───────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Runtime-only system libraries (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    gdal-bin \
    libgdal36 \
    libgeos-c1v5 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Pull in the pip packages compiled in builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Detect actual GDAL/GEOS versioned library paths at build time.
# We search for the versioned .so (e.g. libgdal.so.36) under the main
# multiarch lib dir only, explicitly excluding the ogdi sub-directory
# which ships its own incompatible libgdal.so that lacks GDALVersionInfo.
RUN GDAL_PATH=$(find /usr/lib/x86_64-linux-gnu -maxdepth 1 -name 'libgdal.so.*' | sort -V | tail -1) && \
    GEOS_PATH=$(find /usr/lib/x86_64-linux-gnu -maxdepth 1 -name 'libgeos_c.so.*' | sort -V | tail -1) && \
    echo "Detected GDAL_LIBRARY_PATH=$GDAL_PATH" && \
    echo "Detected GEOS_LIBRARY_PATH=$GEOS_PATH" && \
    printf "GDAL_LIBRARY_PATH=%s\nGEOS_LIBRARY_PATH=%s\n" "$GDAL_PATH" "$GEOS_PATH" > /app/.geoenv

# ── Application code ───────────────────────────────────────────────────────────
COPY . .

# ── Non-root user for security ────────────────────────────────────────────────
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appgroup /app

# ── Startup script ─────────────────────────────────────────────────────────────
COPY --chown=appuser:appgroup docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

USER appuser

EXPOSE 8000

CMD ["/app/docker-entrypoint.sh"]
