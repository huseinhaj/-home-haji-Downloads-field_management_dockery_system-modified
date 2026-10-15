# ESS e-Tendaji — Ufafanuzi & Kutatua Matatizo

## 1. Muhtasari
Mfumo wa e-Tendaji (ESS) katika repo hii unasaidia walimu:
- Kuandaa/kuangalia "sub-tasks" (maazimio, nukuu, maandalio, zana, vipindi, tathmini, majaribio) na kuongeza maendeleo wiki-wiki.
- Kujaza (fill) maendeleo haya kiotomatiki kwenye ESS (e-Tendaji) kwa kutumia Playwright (Chromium).
- Kuidhinisha (approve/verify) "description zilizowasilishwa" (SUBMITTED) na walimu walio chini ya mkuu/kiongozi.
- Kufanya kujaza kiotomatiki na kuidhinisha kiotomatiki kwa ratiba (beat au embedded scheduler).

## 2. Miundo Muhimu

### Models
- `TeacherProfile` (`ess_tracker/models.py:35`): wasifu wa mwalimu. Uga muhimu:
  - `ess_username`, `ess_password` (nywila iliyosimbwa na Fernet), `ess_ready`
  - `approver_enabled`, `auto_approve_weeks` (1 au 2) — hatua ya mwisho (commit db31fc4e/c899918a)
  - `auto_subtasks` (IDs za sub-tasks kwa kujaza kiotomatiki), `auto_fill_enabled`, `entries_per_week`, `school_open/close`, `holidays`, `user`, `school`, `full_name`, `phone`
  - `set_ess_password(raw)` — simbua na hifadhi; `ess_password_plain` (mambo ya debug)
- `Task` / `SubTask` (`135, 158`): kazi na sub-tasks zenye maeneo (somo, kidato, n.k.), position, description, mode/target.
- `WeekEntry` (`192`): maandishi ya wiki (actual, date, week_no) kwa profile+subtask.
- `EssFillRun` (`217`): rekodi ya run (fill/sync/push/read/approve), status (queued/running/done/error), timestamps, counts (saved/skipped/not_found), kind/source.
- `PushSubscription`, `AcademicCalendar`, `MonthlyTarget`, `WeeklyTarget`, `Holiday`.

### Kufanya kazi (Fill)
Kituo: `ess_tracker/essfill.py` — Playwright sync, inafungua ESS, ingia, kwenda "subtasks", kusoma majina ya mwaka, kutafuta sub-task inayolingana, kufungua View/Implementation, kusoma entries zilizopo (official map), kuchagua status/pct inayolingana, Save/Submit kulingana na hali. Pia:
- `run_fill(profile_id, run_id)` — kujaza zilizochaguliwa kwa subtask_id ama kiotomatiki.
- `run_sync` — kuvuta majina/task/subtask kutoka ESS.
- `run_push` — kusawazisha majina kwenda ESS.
- `run_read` — kusoma asilimia halisi (official) kutoka ESS.
- `_open_ess`, `_auto_login`, `_goto_subtasks`, `_panel_is_entries`, `_submit_panel_or_view`, n.k.

### Kuidhinisha (Approve)
Kituo: `ess_tracker/essapprove.py` — login, nenda department report ya mkuu, fungua rows "SUBMITTED", **Verify** kwenye kila moja.
- `run_approve(profile_id, run_id, dry_run=False)` — mchakato mkuu.
- `_wait_for_main_rows` — subiri Angular/i18n iliyo na data (kuzuia "no data to display" kwenye HTML ghali).
- `_row_cells` — safi: puuza safu tupu / "no data to display" / "hakuna data".
- `_verify_submitted_in_details` — tegemea "Verify"/"Verified" badges; hurudi `(verified, remaining)`. Ana `MAX_ROUNDS=500` kuzuia loop isiyoisha.
- `_process_main_row` — hukubali "Approve"/"Approve Progress" (vitenzi tofauti kwa lugha/UPD).
- `_next_page` — inajaribu selectors nyingi ili kuzunguka kurasa.

### Tasks na Scheduler
`ess_tracker/tasks.py`:
- `run_ess_fill/run_ess_sync/run_ess_push/run_ess_read/run_ess_approve` — async (queue='essfill', timeouts).
- `approve_interval_days`, `approve_last_auto`, `approve_due_for` (si kurudia siku moja, na kizingiti), `approve_next_due`.
- `approve_due` — chagua approvers `approver_enabled=True, ess_ready=True` walio `due_for`.
- `run_approve_inline(profiles=None, only_due=False)` — "humuhumu ndani ya process" (inline); sasa na **thread concurrency** (`_approve_concurrency`, env `ESS_APPROVE_CONCURRENCY`, default 3, max 8), kila profile kwenye thread yake, `connection.close()` mwisho.
- `auto_fill_due`, `run_auto_fill_inline`.

Management commands:
- `ess_approve_scheduler --hour 18 --catch-up` — embedded inline approver, default saa 18 (EAT).
- `ess_scheduler` — embedded auto-fill inline (default 06:30).
- `ess_approve`, `ess_auto_fill` — CLI.
- `ess_key_check`, `ess_set_password`, `ess_enc_key`.

### Admin
- Imewekwa kwenye `field_app.admin.custom_admin_site` (URL `/admin/`). `ess_tracker/admin.py` inasajili pia kwenye custom site ili ESS ionekane ("ESS e-Tendaji Tracker").
- `TeacherProfileAdmin`: `new_ess_password` (kubadilisha password ya ESS bila kuedit token), `actions = ('enable_approver','disable_approver')` — kuwawasha approvers wengi kwa mkupuo.

## 3. Jinsi ya Kutatua Matatizo (Problems Solved)

| Tatizo | Suluhisho | Commit(s) |
|---|---|---|
| Build "Deployment failed to build" (Debian 13/trixie): majina ya packages yalibadilika | `Dockerfile` — `libgeos-c1v5`→`libgeos-c1t64`, `libatk1.0-0`→`libatk1.0-0t64`, `libatk-bridge2.0-0`→`libatk-bridge2.0-0t64`, `libcups2`→`libcups2t64`, `libasound2`→`libasound2t64`. `python:3.12-slim` (mirror AWS) kwenye trixie. | `e2d472d8` |
| ESS login "haisomiki" (password haiwezi kusomwa) | `crypto.py`: `_key()` hubadilisha base64 → bytes kwa usahihi, `effective_key()` hutumia `DJANGO_SECRET_KEY`. Ujumbe mpya wa login kuhusu "Weka password upya". | `9605e78b` |
| Kujisaidia "Weka password upya" (recover) | `ess_recover` view + `_password_readable`, URL `recover/`, template `ess_recover.html`, kiungo kwenye login. Command `ess_key_check` na `ess_set_password`. | `f26342ee`, `4eff25fb`, `bbb4e1ce` |
| Approve ikionyesha "no data to display" ingawa kuna data | `essapprove.py`: `_row_cells` hupunguza HTML tupu na puuza "no data to display"/"hakuna data"; `_wait_for_main_rows` husubiri Angular ili data ionekane (subiri rows count > 0). | `1b97944e` |
| Verify/approve haikuhesabu kwa usahihi, loop isiyoisha au hazijatambuliwa | `_verify_submitted_in_details` hurudi `(verified, remaining)`, `MAX_ROUNDS=500`; `_process_main_row` hukubali 'Approve'/'Approve Progress'; `_next_page` imeboresha selectors; log inaonyesha `HAZIJATHIBITISHWA (N)`. | `9087a4c0` |
| ESS models hazionekani kwenye `/admin/` (custom admin site) | Kusajili TeacherProfile/Task/SubTask/WeekEntry/EssFillRun/AcademicCalendar pia kwenye `field_app.admin.custom_admin_site` (katika `ess_tracker/admin.py`). | `c899918a` |
| Hitaji: auto-approve kila wiki 1 au 2, kila siku 18:00 EAT | Model `auto_approve_weeks`, migration 0019, helpers (`approve_interval_days`, `approve_last_auto`, `approve_due_for`, `approve_next_due`), `approve_due` inatumia interval per-profile na kizingiti (si kurudia siku moja), scheduler default hour 18, beat `ess-approve-daily` hour 18, UI form kwenye approve page + `ess_approve_schedule` view, docker-entrypoint ujumbe. | `db31fc4e` |
| Kasi kwa wakuu wengi | `run_approve_inline` inatumia `ThreadPoolExecutor` (concurrency configurable), `_approve_one` kwa kila mkuu, `connection.close()` kwa thread, env `ESS_APPROVE_CONCURRENCY` (default 3, max 8). Aggregation sahihi ya verified/processed/failed. | `976d83f1` |
| UI ilikuwa na vitu vingi inakera watumiaji | Mpangilio upya wa `ess_home.html` na `ess_approve.html`: vichwa wazi (Hali, Hatua kuu, Maendeleo, Zana za ziada, Uhidhinishaji), kitufe kikuu mbele, zana za hiari zimepangika vizuri. Kila kipengele kimebaki. | `d21adac4` |
| Django multi-line `{# #}` comment inaonekana kwenye header | Badilisha kwenda `{% comment %}...{% endcomment %}` kwenye `_ess_install.html` (Django 5.2 haitupi multi-line `{# #}`). | `1c2f7af1` |
| Kalenda ililazimisha asilimia ya kila sub-task (kila sub-task = kalenda %) — si sahihi | Kalenda ni "total score" ya mwaka. Ondoa matangazo ya kalenda kwenye `expected_pct` na `pct_auto_for`; sub-task sasa hufuata **ratiba yake** (`schedule`). Ongeza `profile_calendar_status` (jumla ya maendeleo ya mwalimu vs lengo la kalenda) na kuionyesha kwenye `ess_home`. | `5feebbfc` |

### Mantiki ya Kalenda vs Sub-task (muhimu)

- **Sub-task** hujazwa kulingana na **ratiba yake** (mstari mnyoofu: wiki zilizopita / wiki zote). Sub-task ya mwaka (annual) = 100%. Chanzo: `schedule` | `annual` | `topics`.
- **Kalenda** (asilimia lengwa ya mwezi/wiki) ni **"total score"** ya mwaka — hulinganishwa na **JUMLA ya maendeleo ya mwalimu** (`profile_progress_pct` = wastani wa sub-task zote), si kila sub-task.
- `profile_calendar_status(profile)` hurudisha `{'target','progress','gap','status'}`; inaonyeshwa kwenye nyumbani kama "Jumla ya maendeleo" (behind/ontrack). Pia `notify_calendar_targets` inatumia jumla hii kwa arifa.
- Mwalimu anaweza kuwa na **task nyingi** (3, 4, ...) kila moja na sub-tasks zake; `built_wanted` na `ess_home` huzunguka task zote.
- `school_open/close` za kalenda bado zinafafanua **mwaka wa shule kwa wote** (`_window`, `compute.py:319`) — hii imeamuliwa kukaa hivi (si la kila task).

## 4. Uendeshaji, Deployment & ENV

### Env vars muhimu (ESS)
- `ESS_ENC_KEY` — Fernet key (base64-urlsafe). Ikiwa haipo, inatumia `DJANGO_SECRET_KEY` (fallback).
- `ESS_APPROVE_CONCURRENCY` — idadi ya approvers sambamba (default 3, range 1-8).
- `ESS_FILL_CONCURRENCY` — concurrency kwa fill workers (queue essfill).
- `ESS_EMBED_SCHEDULER`, `ESS_EMBED_APPROVER` — wa ON kwenye Railway (embedded inline), OFF kwenye docker-compose (beat/worker).
- `ESS_LOGIN_URL`, `ESS_PROFILE_LOCK_SECONDS`, `ESS_RUN_STALE_SECONDS`, `ESS_FILL_RATE_LIMIT`.

### Beat (Celery)
`field_management/settings.py:CELERY_BEAT_SCHEDULE`:
- `ess-auto-fill-daily` — 06:30 EAT (crontab)
- `ess-approve-daily` — 18:00 EAT (crontab) — **imebadilishwa saa 18**.

### Embedded schedulers
- `ess_scheduler` (mgmt cmd) — inline auto-fill kila siku 06:30.
- `ess_approve_scheduler` (mgmt cmd) — inline approve kila siku 18:00, `--hour`, `--catch-up`, `--once`. Hupitisha `only_due=True`.

### Docker
- Multi-stage (builder/runtime), Playwright Chromium pre-installed.
- Entrypoint huanzisha TTC portal (optional), migrations, collectstatic, seeds, background jobs, embedded schedulers (kulingana na `SERVICE_ROLE` na Railway env), kisha gunicorn/nginx.

### Management Commands (zilizo muhimu)
`ess_approve`, `ess_approve_scheduler`, `ess_auto_fill`, `ess_scheduler`, `ess_key_check`, `ess_set_password`, `ess_enc_key`, `import_academic_calendar.py`, `data/`, n.k.

## 5. Njia ya Kufanya Kazi (Overview Flow)

1. **Usajili (ESS):** `/ess/register/` — mkuu/mwalimu anajisajili na username/password ya e-Tendaji. `ess_register` huunda User + TeacherProfile.
2. **Wasifu:** `/ess/profile/` — kuweka ess_username/ess_password, kalenda shule, entries_per_week, holidays.
3. **Kujaza:** `/ess/` (nyumbani) — bofya **"Jaza ESS sasa"**. Hutoa POST `/ess/fill/` → `ess_fill` view au `run_ess_fill` (queue). Huangalia sub-tasks zilizochaguliwa au zote, inasoma hali kutoka ESS na kuwasilisha.
4. **Kuidhinisha (mkono):** `/ess/approve/run/` (POST) → `ess_approve_now` → `run_ess_approve` (queue) au inline. Inapata approvers na kufungua ESS.
5. **Auto-approve:** kila siku **18:00 EAT** — beat au embedded scheduler inaita `approve_due` → kwa approvers walio `due_for` hutoa `run_ess_approve` (queue). Concurrency inline (ThreadPool) kwa embedded.
6. **Onboarding approver:** admin (custom `/admin/`) → ESS e-Tendaji Tracker → Teacher profiles → chagua → action **"Washa kuidhinisha kwa waliochaguliwa"**. Kitufe kinaonekana kwenye nyumbani/approve.

## 6. Hitimisho
Tumeunda mfumo imara wa ESS (fill + approve) na kuiratibu vizuri (mpangilio wa UI msafi kwa walimu), tumeongeza automation yenye kipindi (wiki 1/2) na trigger wa kila siku 18:00 EAT, tukaboresha kasi kwa concurrency, tukarekesha matatizo ya Docker/trixie, key ya crypto, approve selectors/data detection, na admin registration. Hivi karibuni tume**tenganisha kalenda na sub-task**: kalenda sasa ni "total score" tu (inayokua kwa miezi/wiki, ikilinganishwa na jumla ya maendeleo kwenye nyumbani + arifa 07:15), huku kila sub-task ikifuata ratiba yake mwenyewe. Documentation hii inasambaza muundo, suluhisho na namna ya kuendeshwa kwa usahihi.
