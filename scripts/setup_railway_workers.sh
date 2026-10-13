#!/usr/bin/env bash
# ═════════════════════════════════════════════════════════════════════════════
# setup_railway_workers.sh — unda services za background za ESS kwenye Railway
# (worker, worker-fill, beat) na uweke variables muhimu.
#
# Image moja inaendesha roles zote kwa kubadilisha env var SERVICE_ROLE
# (tazama docker-entrypoint.sh). Hakuna haja ya "Custom Start Command".
#
# MAHITAJI: Railway CLI + kuwa logged in na project linked:
#     npm i -g @railway/cli
#     railway login
#     railway link          # chagua project yako ya field_management
#
# MATUMIZI:
#     ./scripts/setup_railway_workers.sh
#
# Kama flags za CLI zako ni tofauti na version, fuata maelekezo ya mkono
# yanayochapishwa mwishoni (dashboard ni njia ya uhakika).
# ═════════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REPO="huseinhaj/-home-haji-Downloads-field_management_dockery_system-modified"

command -v railway >/dev/null 2>&1 || {
  echo "❌ Railway CLI haipo. Sakinisha: npm i -g @railway/cli"; exit 1; }
railway whoami >/dev/null 2>&1 || {
  echo "❌ Haujaingia. Endesha: railway login && railway link"; exit 1; }

# ── VAPID + ESS_ENC_KEY kutoka .env.docker (kama zipo) ──
VAPID_PUBLIC_KEY=""; VAPID_PRIVATE_KEY=""
VAPID_ADMIN_EMAIL="support@utumishi.go.tz"; ESS_ENC_KEY=""
if [ -f .env.docker ]; then
  VAPID_PUBLIC_KEY="$(grep -E '^VAPID_PUBLIC_KEY=' .env.docker | cut -d= -f2- || true)"
  VAPID_PRIVATE_KEY="$(grep -E '^VAPID_PRIVATE_KEY=' .env.docker | cut -d= -f2- || true)"
  VAPID_ADMIN_EMAIL="$(grep -E '^VAPID_ADMIN_EMAIL=' .env.docker | cut -d= -f2- || true)"
  ESS_ENC_KEY="$(grep -E '^ESS_ENC_KEY=' .env.docker | cut -d= -f2- || true)"
fi
[ -n "$VAPID_PUBLIC_KEY" ] || echo "⚠️  VAPID_PUBLIC_KEY haipo kwenye .env.docker — endesha: python manage.py gen_vapid_keys"

set_var () {  # service key value
  railway variable set -s "$1" "$2=$3" >/dev/null 2>&1
  echo "   • $2"
}

create_service () {  # name role
  local name="$1" role="$2"
  echo "── Service: $name  (SERVICE_ROLE=$role) ──"
  # Unda service kutoka GitHub repo (kama haipo). Kama ipo, inarukwa.
  railway add --repo "$REPO" -s "$name" >/dev/null 2>&1 \
    || railway add --service "$name" >/dev/null 2>&1 \
    || echo "   (service huenda ipo tayari au 'add' inahitaji dashboard)"
  echo "   Variables:"
  set_var "$name" SERVICE_ROLE "$role"
  [ -n "$VAPID_PUBLIC_KEY" ]   && set_var "$name" VAPID_PUBLIC_KEY "$VAPID_PUBLIC_KEY"
  [ -n "$VAPID_PRIVATE_KEY" ]  && set_var "$name" VAPID_PRIVATE_KEY "$VAPID_PRIVATE_KEY"
  [ -n "$VAPID_ADMIN_EMAIL" ]  && set_var "$name" VAPID_ADMIN_EMAIL "$VAPID_ADMIN_EMAIL"
  [ -n "$ESS_ENC_KEY" ]        && set_var "$name" ESS_ENC_KEY "$ESS_ENC_KEY"
  echo "   Deploy:"
  railway up -s "$name" --detach >/dev/null 2>&1 || echo "   ⚠️  'railway up' imeshindikana — tumia dashboard."
  echo
}

create_service "worker"      "worker"
create_service "worker-fill" "worker_fill"
create_service "beat"        "beat"

cat <<'EOF'
════════════════════════════════════════════════════════════════════════════
✅ Umekamilisha! BAKI (weka kwa mkono):

1. SHARED VARIABLES (project-level) — zitumike kwa services zote:
      DATABASE_URL, REDIS_URL, DJANGO_SECRET_KEY
   Railway → Project → Variables (Shared). Kama hazipo, ongeza kwenye kila
   service pia.

2. BEAT: hakikisha replica = 1 pekee (isijirudie):
      Railway → service 'beat' → Settings → Replicas = 1

3. HEALTHCHECK: worker/beat hawafungui HTTP port. Kama zinasimama kwa
   "healthcheck failed":
      Railway → service → Settings → Deploy → futa Healthcheck Path

4. THIBITISHA magogo:
      railway logs -s worker
      railway logs -s worker-fill
      railway logs -s beat
   Unapaswa kuona "SERVICE_ROLE=... " kwenye logs.

5. JARIBU arifa: simu → /ess/ → Wasifu → Washa arifa → Tuma jaribio.

MAELELEZO YA MKONO (dashboard) kama script haikufanya kazi:
   New → GitHub Repo (repo hii) kwa kila service, kisha Settings → Variables:
      SERVICE_ROLE = worker        (worker)
      SERVICE_ROLE = worker_fill   (worker-fill)
      SERVICE_ROLE = beat          (beat)
   Hakuna haja ya kubadilisha start command — entrypoint inajichagua.
════════════════════════════════════════════════════════════════════════════
EOF
