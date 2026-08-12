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
