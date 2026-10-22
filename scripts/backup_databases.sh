#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  Backup ya database zote (local docker + Railway production)
#  Tumia:  ./scripts/backup_databases.sh
#  Hufanya kila siku kwa cron (tazama crontab).
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/home/haji/backups/databases}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
LOG_FILE="/home/haji/backups/backup.log"
mkdir -p "$BACKUP_ROOT"

# ── Sifa za database ───────────────────────────────────────────────────────
# REPO HII NI PUBLIC — URLs za database (zina passwords) zisingeweza
# kukuwa ndani ya script hii. Tunazisoma kutoka kwenye .env (ambayo
# .gitignore inaficha) au kutoka kwenye mazingira, hivyo script inaweza
# kufanya kazi bila kuwa na sifa yoyote ya pesa ndani yake.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/../.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

STAMP="$(date '+%Y%m%d_%H%M%S')"
DAY_DIR="$BACKUP_ROOT/$STAMP"
mkdir -p "$DAY_DIR"

# ── Majukumu ────────────────────────────────────────────────────────────────
# pg_dump inapatikana ndani ya container ya postgres; tunatumia hii ili
# tusihitaji pg_dump kwenye host.
PSQL_CONTAINER="field_management_dockery_system-modifiedied-db-1"
# Railway inatumia PostgreSQL 18 — lazima tutumie pg_dump ya 18 (sio 16).
PG18_IMAGE="${PG18_IMAGE:-postgres:18-alpine}"

# Jina | DATABASE_URL | schema (--schema-only inahitaji kama DB ni schema-based)
# 1) LOCAL — docker compose (postgres)
LOCAL_DB="${LOCAL_DB:-postgresql://field_user:field_pass@db:5432/field_db}"
# 2) RAILWAY — database kuu ya field_management
RAILWAY_MAIN="${RAILWAY_MAIN:-${DATABASE_URL:-}}"
# 3) RAILWAY — database ya matokeo (results)
RAILWAY_RESULTS="${RAILWAY_RESULTS:-${RESULTS_DATABASE_URL:-}}"

dump_local() {
    local label="$1" url="$2" out="$3"
    log "⇄ Ina-dump $label (pg_dump 16 ndani ya container) ..."
    docker exec "$PSQL_CONTAINER" pg_dump "$url" > "$out" 2>"$out.err"
    finish_dump "$label" "$out"
}

dump_remote() {
    local label="$1" url="$2" out="$3" image="$4"
    if [ -z "$url" ]; then
        log "✗ $label — hakuna DATABASE_URL. Weka DATABASE_URL / RESULTS_DATABASE_URL kwenye $ENV_FILE au kwenye mazingira."
        return 1
    fi
    log "⇄ Ina-dump $label (pg_dump ${image##*:}) ..."
    # Railway inatumia PostgreSQL 18 — pg_dump 16 inakataa ("server version mismatch").
    # Tunatumia image inayolingana na server.
    docker run --rm "$image" pg_dump "$url" > "$out" 2>"$out.err"
    finish_dump "$label" "$out"
}

finish_dump() {
    local label="$1" out="$2"
    if [ -s "$out" ]; then
        log "✓ $label — $(du -h "$out" | cut -f1) → $out"
        rm -f "$out.err"
        return 0
    fi
    log "✗ $label — pg_dump imeshindwa: $(tail -1 "$out.err" 2>/dev/null)"
    rm -f "$out" "$out.err"
    return 1
}

FAILED=0

dump_local "local/field_db"   "$LOCAL_DB"        "$DAY_DIR/local_field_db.sql"              || FAILED=1
dump_remote "railway/main"    "$RAILWAY_MAIN"    "$DAY_DIR/railway_main.sql"     "$PG18_IMAGE" || FAILED=1
dump_remote "railway/results" "$RAILWAY_RESULTS" "$DAY_DIR/railway_results.sql"  "$PG18_IMAGE" || FAILED=1

# ── Ukatwa wa backup ya ppgump ──────────────────────────────────────────────
find "$BACKUP_ROOT" -maxdepth 1 -type d -name '20*' -mtime "+$RETENTION_DAYS" -exec rm -rf {} + 2>/dev/null
find "$BACKUP_ROOT" -maxdepth 1 -type d -name '20*' -empty -exec rmdir {} + 2>/dev/null

# ── Ukurugaji wa backup ya volume ya postgres (kwa uoko wa hatari) ─────────
# Bei ya 1GB — tunafanya kila wiki tu.
if [ "$(date +%u)" = "7" ]; then
    VOL="field_management_dockery_system-modifiedied_postgres_data"
    log "⇄ Ina-tar volume $VOL (backup ya wiki) ..."
    docker run --rm -v "$VOL":/data:ro -v "$BACKUP_ROOT":/out postgres:16-alpine \
        tar czf "/out/pgvolume_${STAMP}.tar.gz" --exclude=./core -C /data . \
        && log "✓ volume tar iko: $BACKUP_ROOT/pgvolume_${STAMP}.tar.gz" \
        || { log "✗ volume tar imeshindwa"; FAILED=1; }
fi

if [ "$FAILED" -eq 0 ]; then
    log "═══ Backup yote imekamilika ═══"
else
    log "!!! Baadhi ya backup zilishindwa — angalia taarifa hapo juu !!!"
fi
exit $FAILED
