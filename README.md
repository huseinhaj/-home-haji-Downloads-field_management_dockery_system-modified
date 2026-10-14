# Field Management System — Railway Deployment

> **Trigger deploy:** push kwenye `main` → GitHub Action (`deploy.yml`) → `railway up --detach`.

## 🖥️ TTC Student Portal (imefungwa ndani ya container hii, database yake tofauti)

Kuanzia sasa, container hii ya Railway inaweza kuendesha **mfumo mbili kwa wakati mmoja**:

| Mfumo | URL | Database | Projekt |
|---|---|---|---|
| Field Management (kama zamani) | `https://domain.railway.app/` | `DATABASE_URL` | `field_management/` |
| **TTC Student Portal** (vyuo vya ualimu, SR2 flow) | `https://domain.railway.app/ttc/` | `TTC_DATABASE_URL` (**tofauti!**) | `ttc_portal/` |

**Ni lazy-in-enabled:** mfumo wa field_management unafanya kazi kama zamani kabisa —
TTC portal inaanzishwa TU wakati env variable `TTC_PORTAL_ENABLED=true` imewekwa.

### ⚙️ Env variables zinazohitajika (Railway)

Katika Railway service hii (hazigusi mipangilio iliyopo):

| Variable | Thamani | Maelezo |
|---|---|---|
| `TTC_PORTAL_ENABLED` | `true` | Anzisha TTC portal + nginx ya container |
| `TTC_DATABASE_URL` | `postgresql://...` | **Postgres yake tofauti kabisa** (undaa DB mpya kwenye Railway) |
| `TTC_SECRET_KEY` | `...` | Secret key ya TTC |
| `TTC_SUPERUSER_EMAIL` | `yako@chuo.ac.tz` | Super admin ya TTC (pamoja na `TTC_SUPERUSER_PASSWORD`) — **hakuna demo accounts!** |
| `TTC_SUPERUSER_PASSWORD` | `...` | Nywila ya super admin ya TTC |
| `TTC_GEPG_*` | *(hiari)* | Credentials za **GePG halisi** (control numbers halisi + malipo otomatiki) — tazama `ttc_portal/README.md` |

> **MUHIMU:** TTC inasoma `TTC_DATABASE_URL` TU — haigusi kamwe `DATABASE_URL`
> yako ya field_management. Postgres ya TTC ni **service tofauti** kwenye Railway.
> **Hakuna akaunti za demo** — super admin inaundwa kwa `TTC_SUPERUSER_EMAIL` +
> `TTC_SUPERUSER_PASSWORD` (au `createsuperuser`).

### 🚀 Hatua za kuset up kwenye Railway

1. **Undaa database mpya ya Postgres** kwenye Railway (si ile ya field_management!)
   → `Railway → New → Database → PostgreSQL` → nakili connection URL.
2. Weka variable zilizo hapo juu kwenye **service ya field_management**:
   - `TTC_PORTAL_ENABLED=true`
   - `TTC_DATABASE_URL=<postgres mpya>`
   - `TTC_SECRET_KEY=<random string>`
3. Push kwenye `main` → inadeploy → fungua **`https://domain/ttc/`**.

Mara ya kwanza container inafanya **migrations + seed** za TTC kiotomatiki
(vyuo 33 + programu + ada) kabla ya kuanza nginx. Super admin inaundwa kutoka
`TTC_SUPERUSER_EMAIL`/`TTC_SUPERUSER_PASSWORD` — **hakuna akaunti za demo**.

💳 **GePG halisi:** weka `TTC_GEPG_ENABLED=true` + credentials (SP code, private
key, mTLS cert, API URL) — basi control numbers zinakuja kutoka GePG na malipo
yanathibitishwa kiotomatiki kupitia webhook `/ttc/api/gepg/notification/`.
Maelezo kamili (pamoja na jinsi ya kusajiliwa na GePG) yamo kwenye
`ttc_portal/README.md`. Credentials zisipokuwepo, simulated mode inatumika.

### 🧪 Kujaribu locally

```bash
# 1. Anzisha TTC portal (port 8001)
cd ttc_portal && python3 manage.py migrate --noinput && python3 seed_data.py
python3 manage.py runserver 8001

# 2. Anzisha field_management (port 8000) kama kawaida
python3 manage.py runserver 8000
```

Kwa topology kamili ya production (nginx → /ttc/ → TTC, / → field_management),
weka `TTC_PORTAL_ENABLED=true` na tumia Dockerfile + `docker-entrypoint.sh`
(majadiliano kamili yamo kwenye `ttc_portal/README.md`).

## 📱 e-Tendaji (ESS) — app ya walimu

App ya kujaza maendeleo ya **e-Utendaji (ESS)** iko chini ya `/ess/` (PWA).
Walimu wanajiandikisha mara moja, wanachagua sub-task na kubonyeza **Jaza**.

### Env variables (Railway)
| Variable | Maelezo |
|---|---|
| `ESS_ENC_KEY` | Fernet key ya kusimba password za ESS. Tengeneza: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | Web Push (arifa). Tengeneza: `python manage.py gen_vapid_keys` |
| `VAPID_ADMIN_EMAIL` | Barua pepe ya mawasiliano ya VAPID (mf. `support@utumishi.go.tz`) |
| `ESS_FILL_CONCURRENCY` | Idadi ya workers wa foleni `essfill` (walimu wanaojazwa kwa wakati mmoja; default 8). Kila worker = Chromium moja (~200–400MB RAM) |

> **MUHIMU:** Kazi za ESS zinatumia foleni **`essfill`**. Hakikisha worker wa foleni
> hii anaendesha, la sivyo kazi zitasubiri milele:
> ```bash
> celery -A field_management worker --loglevel=info \
>   --concurrency=8 --queues=essfill --max-tasks-per-child=20
> ```
> `ESS_FILL_CONCURRENCY` huamua walimu wangapi hujazwa **sambamba** (default 8).
> Ongeza tu ikiwa host ina RAM ya kutosha: kila slot ~200–400MB (8 ≈ 2–3GB).
> Idadi ya walimu wanaotumia mfumo haina kikomo — ni foleni.
> Beat hutuma kumbukumbu Jumatatu–Ijumaa 07:00 EAT (`ess-notify-due`) na kujaza
> kiotomatiki kila siku (`ess-auto-fill-daily`).

### 📅 Mtaala na Kalenda ya mwaka (admin)

**Asilimia hutokana na MTAALA, sio mwalimu.** Idadi ya vipindi kwa wiki kwa kila
somo (`SUBJECT_PERIODS_WEEK`, Mtaala Mpya 2023, TIE, Kidato I–IV) huamua jinsi
asilimia inapanda (kiingilio kimoja = `100 / (wiki za somo × vipindi/wiki)`).
Somo lisilojulikana hutumia `entries_per_week` ya mwalimu kama fallback.

**Kalenda ya mwaka.** Admin anaweka kalenda (tarehe za kufungua/kufunga +
asilimia lengwa ya kila mwezi) kwenye **Django admin** → *ESS → Kalenda za miaka*
(`/admin/ess_tracker/academiccalendar/`), au kwa amri:

```bash
python manage.py import_academic_calendar 2026 \
    --csv kalenda.csv --open 2026-01-06 --close 2026-12-04 --activate
# CSV: safu mbili (mwezi, asilimia), mwezi = namba 1–12 au jina (Septemba/September)
```

Kalenda **moja** tu huwa `is_active=True`; ikiwa active, mfumo hutumia dirisha
lake la mwaka na asilimia zake kwa **walimu wote** — hivyo admin akibadilisha,
mabadiliko hujituma kiotomatiki (asilimia, ratiba, na alerts). Beat hutuma arifa
kwa walio **nyuma ya asilimia ya mwezi** kila siku 07:15 EAT (`ess-notify-calendar`).

**Kujaza kiotomatiki kunapangwa vipi.** Beat huamsha `auto_fill_due` kila siku
06:30 EAT; inajaza mwalimu ikiwa leo: (1) yuko ndani ya dirisha la kalenda,
(2) ni siku ya kujaza kulingana na `entries_per_week` aliyochagua mwalimu
(mf. 3 = Jumatatu/Jumatano/Ijumaa), (3) hajajaza leo, na (4) hakuna lock.
Wasifu wenye `auto_fill_enabled=True` + ESS username/password.

> **Siku vs. vipindi.** Vipindi vya mtaala (`SUBJECT_PERIODS_WEEK`) hutumika kwa
> **asilimia/increment** pekee (≈ `100 / (vipindi/wiki × wiki za dirisha)`), SIO
> kwa ratiba ya siku. Siku za kujaza hutoka `entries_per_week` ya mwalimu.

> **MUHIMU — foleni ya beat.** Task za beat (auto-fill/notify) zinapaswa kwenda
> foleni **`default`** (`options={"queue": "default"}` kwenye
> `CELERY_BEAT_SCHEDULE`). Bila hivyo, Celery huzituma kwenye foleni yake ya
> default (`celery`) ambayo **hakuna worker anayeisikiliza** — kazi hukaa
> brokerni na hazifanyiki. Workers huendesha `--queues=default,emails`.

**Kuchunguza kujaza kiotomatiki** (bila kusubiri beat):
```bash
python manage.py ess_auto_fill               # onyesho: nani yuko tayari leo + sababu
python manage.py ess_auto_fill --profile 12  # mwalimu mmoja pekee
python manage.py ess_auto_fill --execute     # weka foleni (essfill) — inahitaji worker
python manage.py ess_auto_fill --execute --inline  # endesha HUMU (bila worker/beat)
```

> **Njia rahisi: Railway Cron Job** (bila beat/worker). Unda service ya aina
> **Cron Job** kwenye Railway, start command:
> ```sh
> sh -c 'export $(cat /app/.geoenv 2>/dev/null | xargs); python manage.py ess_auto_fill --execute --inline'
> ```
> Schedule (UTC; sisi tunatumia EAT=UTC+3): `30 3 * * *` = **06:30 EAT** kila
> siku. `--inline` hujaza moja kwa moja ndani ya cron, hivyo huhitaji `beat`
> wala `worker`.

> **Njia inayojipanga yenyewe — embedded scheduler (mapendekezo kwa Railway).**
> Railway hudeploy **service moja (web)** kwa `railway up`; Procfile
> (`worker`/`beat`) **hupuuzwa**, hivyo beat huwa haifanyi kazi. Kipanga-saa
> **`ess_scheduler`** hupachikwa kwenye container ya **web** na kujaza kila siku
> **06:30 EAT** (hutumia hukumu zile zile za `auto_fill_due`, bila broker/worker).
> - Hupachikwa **kiotomatiki** kwenye Railway (hugundua `RAILWAY_*` env) —
>   hakuna service ya ziada wala Cron Job.
> - Huzimwa kwenye docker-compose (yenye `celery-beat` yake).
> - Kulazimisha: weka `ESS_EMBED_SCHEDULER=1` (washa) au `=0` (zima); kwa
>   docker-compose unaweza `=1` ili kuiendesha badala ya celery-beat.
> - **Usiweke `beat`/`worker` services pia** — kujaza ni kilekile; hata hivyo
>   `auto_fill_decision` huruka mwalimu aliyejaza leo (kizuizi cha mara-moja).
> - Kukagua: `python manage.py ess_scheduler --once` (endesha mara moja), au
>   angalia log `/tmp/ess_scheduler.log` kwenye container.

**Historia ya kujaza** (`/ess/fill/log/`) inaonyesha kila run ikiwa na safu
**Aina** (`kind`: Kujaza/Sawazisha/Tuma/Soma) na **Chanzo** (`source`:
**Kiotomatiki** kwa beat, **Mwenyewe** kwa kubofya). Run za **kujaza**
(`kind=fill`) pekee zinaathiri kuzuia/kujaza; run nyingine ni za kusawazisha
majina, kusoma asilimia, n.k.

> **Runs zilizokwama.** Run iliyoanza zaidi ya `ESS_RUN_STALE_SECONDS`
> (default 1800s) bado `running` hufungwa kama `error` kiotomatiki
> (`ess_tracker/runstate.reap_stale_runs`) ili **isizuie** kitufe cha "Jaza"
> milele. Usafi huu hufanyika unapofungua historia, unapobofya "Jaza", na
> mwanzoni mwa `auto_fill_due`.

### 🛠️ Background services (workers + beat)

Web service haitoshelezi ESS/resources peke yake — inahitaji **worker**, **worker
wa foleni `essfill`**, na **beat**. Image moja inaendesha roles zote: kubadilisha
env var **`SERVICE_ROLE`** (`web` | `worker` | `worker_fill` | `beat`) ndiyo
inayoamua container inafanya nini (tazama `docker-entrypoint.sh`). Hakuna haja ya
kubadilisha start command.

**A) VPS / docker-compose** (tayari imewekwa kwenye `docker-compose.yml`):
`web` + `celery` (worker), `celery-fill` (worker_fill), `celery-beat` (beat).
Weka `VAPID_*` kwenye `.env.docker` kisha:
```bash
docker compose build --no-cache web celery celery-fill celery-beat
docker compose up -d
```

**B) Railway** — undaa **services tatu za ziada** kutoka repo hii hii; kwenye
kila moja weka variable `SERVICE_ROLE` pekee:

| Service | Variable |
|---|---|
| worker | `SERVICE_ROLE=worker` |
| worker-fill | `SERVICE_ROLE=worker_fill` |
| beat | `SERVICE_ROLE=beat` |

Au endesha helper (inaunda services + variables + deploy):
```bash
./scripts/setup_railway_workers.sh
```

> Weka `VAPID_*`, `ESS_ENC_KEY`, `DATABASE_URL` na `REDIS_URL` kwenye **kila**
> service (au kama Shared Variables za project). Beat iwe **replica 1 pekee**.
> Workers/beat **hawafungui HTTP port** — kama zinasimama kwa "healthcheck
> failed", futa **Healthcheck Path** kwenye Settings → Deploy za service husika.
