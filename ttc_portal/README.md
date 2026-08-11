# TTC Student Portal — Mfumo wa Vyuo vya Ualimu

Mfumo wa **kujitegemea** (standalone Django project, database yake tofauti) kwa
**wanafunzi wa vyuo vya ualimu (Teacher Training Colleges)** wanaosoma
**Diploma in Education**. Flow ya mfumo inafuata mtindo wa **UDOM SR2**:

1. Mwanafunzi anaona **vyuo vyote** na anachagua chuo chake.
2. Anajiandikisha — bili zake (Ada + Mchango wa Chuo) zinaundwa **moja kwa moja**.
3. Anabofya **Generate Control Number** kupata namba ya malipo (kama GePG).
4. Analipa kupitia benki / simu ya mkonomi kwa kutumia namba ya malipo.
5. Anawasilisha malipo → **Msimamizi wa Chuo anathibitisha** (reconciliation).
6. Mwanafunzi anaona **alicholipa** na **anachodaiwa** kwa wakati halisi.

## Uhusiano na field_management project

- Mradi huu ni **projekt tofauti** iliyoko ndani ya repo ya
  `field_management_dockery_system-modifiedied`, lakini **inajitegemea kabisa**:
  - `ttc_portal/ttc_db.sqlite3` — database yake yenyewe (separate database).
  - `ttc_portal/ttc_portal/settings.py` — settings yake yenyewe.
  - Inasoma **`TTC_DATABASE_URL`** tu (haigusi `DATABASE_URL` ya field_management).
- Unaweza kuendesha **mradi wote kwa wakati mmoja** kwenye port tofauti.

## Kuendesha (Local)

```bash
cd ttc_portal

# 1. Sakinisha dependencies (au tumia venv iliyopo)
pip install -r requirements.txt

# 2. Migrations + Seed data (vyuo 33, wasimamizi, wanafunzi wa mfano)
python3 manage.py migrate --noinput
python3 seed_data.py

# 3. Endesha server (badilisha port kutoka 8000 ya field_management)
python3 manage.py runserver 8001
```

Fungua: http://localhost:8001

## Akaunti za Mfano (Demo)

| Wajibu | Username | Nywila |
|---|---|---|
| Super Admin | `admin` | `admin123` |
| Msimamizi wa Kasulu TC | `kasulu_admin` | `admin123` |
| Mwanafunzi (Kasulu TC) | `KAS/2026/014` | `juma2026` |
| Mwanafunzi (Butimba TC) | `BUT/2026/007` | `neema2026` |
| Mwanafunzi (Morogoro TC) | `MOR/2026/021` | `baraka2026` |

> Kuingia: weka **namba ya usajili** (mf. `KAS/2026/014`) **au barua pepe** + nywila.

## Kujaribu Flow Kamili (SR2-style)

1. Fungua `/` — tafuta **Kasulu** → bofya chuo → `Jiandikishe Hapa`.
2. Jiandikishe (au ingia kama `KAS/2026/014` / `juma2026`).
3. Kwenye **Dashboard**: bofya **Generate Control No.** kwenye "Ada ya Mwaka".
4. Bofya **Wasilisha Malipo** → jaza kiasi, njia na kumbukumbu.
5. Ingia kama **Msimamizi wa Chuo** (`kasulu_admin`) → `Malipo` → **Thibitisha**.
6. Rudi kwenye dashboard ya mwanafunzi — deni limepungua, historia inaonekana.
7. Kama **Super Admin** (`admin`) angalia `/super-admin/` na `/admin/` (Django admin).

## Super Admin — Kusimamia Vyuo na Wasimamizi

Kupitia Django Admin (`/admin/`):
- **Vyuo** — ongeza/hariri chuo kipya (Django Admin → Colleges).
- **Programu** — ongeza programu kwa kila chuo.
- **Wasimamizi wa Chuo** — unda user wa `college_admin` na umuunganishe na chuo
  (Django Admin → Colleges → College admins). Ukitengeneza kupitia
  `CollegeAdmin` form, role inawekwa `college_admin` moja kwa moja.

## Deployment (Railway — ndani ya field_management, database tofauti)

TTC portal inadeploy **ndani ya container ile ile ya field_management** (Railway
service moja), chini ya njia `/ttc/`, lakini inatumia **database yake tofauti**
(`TTC_DATABASE_URL`, Postgres yake yenyewe ya Railway). Topolojia:

```
Railway container (PORT)
   └─ nginx (container.conf)
        ├─ /ttc/*        → TTC gunicorn 127.0.0.1:8001  (DB: TTC_DATABASE_URL)
        ├─ /ttc/static/  → ttc_portal/static (moja kwa moja)
        └─ /*            → field_management gunicorn 127.0.0.1:8000 (DB: DATABASE_URL)
```

Inawasha TU ikiwa `TTC_PORTAL_ENABLED=true` (docker-entrypoint.sh). Hatua:

1. **Undaa Postgres mpya** kwenye Railway (si ile ya field_management!)
   → `Railway → New → Database → PostgreSQL` → nakili URL.
2. Weka env variables kwenye service ya field_management:

```
TTC_PORTAL_ENABLED=true
TTC_DATABASE_URL=postgresql://...:5432/ttc_db     # database yake yenyewe!
TTC_SECRET_KEY=<random string>
TTC_SEED_DEMO=true                                 # demo accounts tu kwa majaribio!
```

3. Push kwenye `main` → inadeploy → fungua **`https://domain/ttc/`**.

Mara ya kwanza `docker-entrypoint.sh` inafanya `migrate` + `seed_data.py` za TTC
kiotomatiki. Nginx ndani ya container inastrip prefix `/ttc/` (trailing slash kwenye
`proxy_pass`) na Django ina `FORCE_SCRIPT_NAME='/ttc'` — kwa hiyo URLs zote
zinatengenezwa kwa prefix sahihi. **MUHIMU:** TTC inasoma `TTC_DATABASE_URL` TU —
haigusi kamwe `DATABASE_URL` ya field_management.

## Muundo wa Apps

```
accounts/  → CustomUser (super_admin / college_admin / student), login/logout
colleges/  → College (TTC), Program, CollegeAdmin + orodha ya vyuo
students/  → Student (student teacher), usajili, dashboard, jopo la chuo
fees/      → FeeItem, FeeBill (control number), Payment + reconciliation
```

## Mambo ya Baadaye (Real GePG)

Mfumo umejengwa kwa muundo wa "simulated GePG": namba za malipo zinatengenezwa
ndani ya mfumo na uthibitisho unafanywa na msimamizi. Kwa **GePG halisi**,
badilisha `fees/services.py::generate_control_number` kutumia API ya GePG na
unganisha webhook ya malipo badala ya uthibitisho wa mwongozo.
