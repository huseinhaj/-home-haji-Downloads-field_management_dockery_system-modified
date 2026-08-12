# TTC Student Portal — Mfumo wa Vyuo vya Ualimu

Mfumo wa **kujitegemea** (standalone Django project, database yake tofauti) kwa
**wanafunzi wa vyuo vya ualimu (Teacher Training Colleges)** wanaosoma
**Diploma in Education**. Flow ya mfumo inafuata mtindo wa **UDOM SR2** na
malipo ya **GePG**:

1. Mwanafunzi anaona **vyuo vyote** na anachagua chuo chake.
2. Anajiandikisha — bili zake (Ada + Mchango wa Chuo) zinaundwa **moja kwa moja**.
3. Anabofya **Generate Control Number** → namba ya malipo inatoka kwa **GePG halisi**
   (au simulated ikiwa GePG bado haijasanidiwa).
4. Analipa kupitia benki / simu ya mkonomi / GePG channels akitaja namba ya malipo.
5. **GePG inatuma webhook** → malipo yanathibitishwa **kiotomatiki** (reconciliation).
6. Mwanafunzi anaona **alicholipa** na **anachodaiwa** kwa wakati halisi.

> **Hakuna akaunti za demo!** Super admin inaundwa tu kwa `TTC_SUPERUSER_EMAIL`
> + `TTC_SUPERUSER_PASSWORD` env vars (au `python manage.py createsuperuser`).

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

# 2. Migrations + Seed (vyuo 33, programu, ada — HAKUNA akaunti za demo)
python3 manage.py migrate --noinput
python3 seed_data.py

# 3. Unda super admin
python3 manage.py createsuperuser

# 4. Endesha server (badilisha port kutoka 8000 ya field_management)
python3 manage.py runserver 8001
```

Fungua: http://localhost:8001

## Kujaribu Flow Kamili (SR2-style)

1. Fungua `/` — tafuta **Kasulu** → bofya chuo → `Jiandikishe Hapa`.
2. Jiandikishe kama mwanafunzi mpya (usajili unaunda bili otomatiki).
3. Kwenye **Dashboard**: bofya **Generate Control No.** kwenye "Ada ya Mwaka".
4. Bofya **Wasilisha Malipo** → jaza kiasi, njia na kumbukumbu.
5. **Ikiwa GePG iko halisi** → malipo yanathibitishwa yenyewe kupitia webhook.
   **Ikiwa simulated** → Msimamizi wa Chuo anathibitisha (Jopo la Chuo → Malipo).
6. Rudi kwenye dashboard — deni limepungua, historia inaonekana.

## Super Admin — Kusimamia Vyuo na Wasimamizi

Kupitia Django Admin (`/admin/`):
- **Vyuo** — ongeza/hariri chuo kipya (Django Admin → Colleges).
- **Programu** — ongeza programu kwa kila chuo.
- **Wasimamizi wa Chuo** — unda user wa `college_admin` na umuunganishe na chuo
  (Django Admin → Colleges → College admins). Ukitengeneza kupitia
  `CollegeAdmin` form, role inawekwa `college_admin` moja kwa moja.

## 💳 GePG HALISI — Malipo ya Serikali

Mfumo una **moduli kamili ya GePG** (`ttc_portal/fees/gepg.py`) kwa mtindo wa
GePG v2 (imethibitishwa dhidi ya reference library ya `watabelabs/gepg-java`):

```
1. BILL SUBMISSION   gepgBillSubReq (XML iliyotiwa sahihi ya RSA) → GePG
                     GePG inarudisha gepgBillSubResp + ControlNum (tarakimu 10)
2. PAYMENT           Mwanafunzi analipa kwa namba ya malipo (benki/simu/GePG)
3. CONFIRMATION      GePG inatuma webhook → /ttc/api/gepg/notification/
                     → malipo yanathibitishwa kiotomatiki (idempotent)
```

### Jinsi ya kupata credentials za GePG

GePG **haitoi credentials kiotomatiki** — unahitaji kuwa PSP/SP:

1. **Wasiliana na GePG** (gepg.go.tz) au benki yako (NMB/CRDB/NBC — wao ni PSPs
   waliosajiliwa) ili kusajili chuo chako kama **Service Provider (SP)**.
2. Utapokea:
   - **`GEPG_CODE`** — SP code (mf. `SP023`)
   - **`SUB_SP_CODE`** + **`SP_SYS_ID`** — vitambulisho vya mfumo wako
   - **`GFS_CODE`** — Government Fiscal code (ada/elimu, mf. `140100`)
   - **Private key** (PKCS#12 `.pfx` au PEM) + **client certificate** (mTLS)
   - **`API_URL`** ya GePG (test/uat kwanza, kisha production)
3. GePG inakusajilisha kwenye **test environment** ili ujaribu kabla ya go-live.

### Env variables za GePG (Railway)

| Variable | Maelezo |
|---|---|
| `TTC_GEPG_ENABLED` | `true` kuwasha GePG halisi |
| `TTC_GEPG_CODE` | SP code (mf. `SP023`) |
| `TTC_GEPG_SUB_SP_CODE` | Sub-SP code |
| `TTC_GEPG_SP_SYS_ID` | System ID yako (mf. `SYSTT000`) |
| `TTC_GEPG_GFS_CODE` | GFS code ya ada/elimu |
| `TTC_GEPG_API_URL` | Base URL ya GePG gateway (https, mTLS) |
| `TTC_GEPG_PRIVATE_KEY_PATH` | Path ya private key kwenye container (PEM au PKCS#12) |
| `TTC_GEPG_PRIVATE_KEY_PASSWORD` | Password ya private key |
| `TTC_GEPG_CLIENT_CERT` / `TTC_GEPG_CLIENT_KEY` | PEM cert + key kwa mTLS (alternative ya keystore) |
| `TTC_GEPG_SIGNATURE_ALGORITHM` | `SHA1withRSA` (default) au SHA256withRSA |
| `TTC_GEPG_API_USER` / `TTC_GEPG_API_PASSWORD` | Basic auth ikiwa inahitajika |
| `TTC_GEPG_NOTIFICATION_TOKEN` | Token ya kuthibitisha webhook calls (GePG inaituma kwenye header `X-GEPG-Token`) |

> **Ikiwa hazijawekwa**, mfumo unatumia **simulated control numbers** kiotomatiki —
> portal inaendelea kufanya kazi hadi GePG iko tayari.

### Kupima webhook (sandbox)

```bash
curl -X POST https://domain.railway.app/ttc/api/gepg/notification/ \
  -H 'Content-Type: Application/xml' \
  -d '<Gepg><gepgPmtSpInfo><PspCode>NMB</PspCode><ControlNum>9911223344</ControlNum><PyrAmt>300000.00</PyrAmt><ReceiptNumber>RX12345</ReceiptNumber></gepgPmtSpInfo></Gepg>'
# → <Gepg><gepgPaymentAck><StsCode>7101</StsCode>...  (malipo yanathibitishwa moja kwa moja)
```

> **MUHIMU kwa onboarding:** muundo halisi wa webhook/status messages wa GePG
> unathibitishwa na timu ya GePG wakati wa onboarding. Moduli hii ina-tafuta
> majina ya kawaida ya elementi (`ControlNum`, `PyrAmt`, `ReceiptNumber` n.k.)
> — kama schema yako inatofautiana, ni kubadilisha tu `handle_payment_notification`.

## Deployment (Railway — ndani ya field_management, database tofauti)

TTC portal inadeploy **ndani ya container ile ile ya field_management** (Railway
service moja), chini ya njia `/ttc/`, lakini inatumia **database yake tofauti**
(`TTC_DATABASE_URL`, Postgres yake yenyewe ya Railway). Topolojia:

```
Railway container (PORT)
   └─ nginx (container.conf)
        ├─ /ttc/*        → TTC gunicorn 127.0.0.1:8001  (DB: TTC_DATABASE_URL)
        ├─ /ttc/static/  → ttc_portal/staticfiles (moja kwa moja)
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
TTC_SUPERUSER_EMAIL=<yako@chuo.ac.tz>             # super admin (inahitajika)
TTC_SUPERUSER_PASSWORD=<nywila imara>
# ── GePG halisi (hiari — ukiiweka, malipo yanaenda GePG) ──
TTC_GEPG_ENABLED=true
TTC_GEPG_CODE=SP023
TTC_GEPG_SUB_SP_CODE=1001
TTC_GEPG_SP_SYS_ID=SYSTT000
TTC_GEPG_GFS_CODE=140100
TTC_GEPG_API_URL=https://gepg-gateway.example
TTC_GEPG_PRIVATE_KEY_PATH=/app/keys/gepg-private.pfx
TTC_GEPG_PRIVATE_KEY_PASSWORD=...
TTC_GEPG_CLIENT_CERT=/app/keys/client.crt
TTC_GEPG_CLIENT_KEY=/app/keys/client.key
TTC_GEPG_NOTIFICATION_TOKEN=<token imara>
```

3. Push kwenye `main` → inadeploy → fungua **`https://domain/ttc/`**.

Mara ya kwanza `docker-entrypoint.sh` inafanya `migrate` + `seed_data.py` za TTC
kiotomatiki (vyuo 33 + programu + ada; super admin kutoka env vars).
**MUHIMU:** TTC inasoma `TTC_DATABASE_URL` TU — haigusi kamwe `DATABASE_URL`
ya field_management.

## Muundo wa Apps

```
accounts/  → CustomUser (super_admin / college_admin / student), login/logout
colleges/  → College (TTC), Program, CollegeAdmin + orodha ya vyuo
students/  → Student (student teacher), usajili, dashboard, jopo la chuo
fees/      → FeeItem, FeeBill (control number), Payment, gepg.py (GePG integration)
```
