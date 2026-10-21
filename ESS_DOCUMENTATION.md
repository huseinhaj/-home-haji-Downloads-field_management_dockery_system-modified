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
  - `SubTask.mode` sasa ni: `annual`, `periods`, `manual`, **`events`** (ratiba ya jaribio/mtihani kwa tarehe), **`count`** (nukuu / idadi iliyokamilika). Sub-task ya **nukuu (nafasi 2)** huumbwa ikiwa `count` kwa default (autogen + sync kutoka ESS).
- `SubTaskEvent` (migration `0020`, `0021`): tukio moja la sub-task ya `events` — `index`, `due_date` (tarehe ILIYOHESABIWA), `label`, na **anchor** ya aina tatu:
  - `date` — tarehe maalum (mf. `2026-03-15`).
  - `month` — mwezi (mf. "Jaribio 1: Machi"); `day` ikiwepo → siku hiyo, vinginevyo **mwisho wa mwezi** (hakuna kudai kabla mwezi kuisha).
  - `term_week` — muhula + wiki (mf. "Muhula 1, wiki ya 6"); mfumo huresibu kutoka kufungua/kufunga kwa shule: Muhula 1 = tarehe ya kufungua, Muhula 2 = nusu ya mwaka; wiki N = mwanzo + 7×(N−1).
  - `resolve_event_date(ev, task)` hubadilisha anchor → `due_date`; `refresh_event_dates(st)` husasisha (huitwa kwenye `subtask_snapshot`); `event_anchor_text(ev)` hutoa maelezo ya binadamu kwa UI.
- `WeekEntry` (`192`): maandishi ya wiki (actual, date, week_no) kwa profile+subtask.
- `EssFillRun` (`217`): rekodi ya run (fill/sync/push/read/approve), status (queued/running/done/error), timestamps, counts (saved/skipped/not_found), kind/source.
- `PushSubscription`, `AcademicCalendar`, `MonthlyTarget`, `WeeklyTarget`, `Holiday`.

### Schedule Guard (Ratiba ya Matukio & Nukuu)
Kizuizi cha ratiba kinazuia sub-task kufikia 100% mapema. Jaribio la Novemba
halionyeshwi kama limekamilika Oktoba; nukuu hutumia idadi halisi ya mwalimu,
si kudhaniwa kwa muda (linear).

**Kilele (compute.py):**
- `subtask_events / events_total / events_completed / events_next / schedule_cap_pct / is_waiting / count_pct`
- `resolve_event_date / term_bounds / refresh_event_dates / event_anchor_text` — ratiba ya mwezi na muhula+wiki.
- `pct_auto_for` — hurudisha cap ya ratiba kwa `events` na `count`; kama bado hazina data (tarehe/target) hurudi kwenye `linear` (haivunji tabia ya zamani).
- `entry_from_values(..., max_pct=cap)` — `planned` haipaswi kupita cap (mf. jaribio 3 kati ya 5 = 60%, si 100%).

**Jinsi inavyofanya kazi:**
- **Ratiba ya matukio (`events`)**: mwalimu huchagua njia moja kati ya tatu — tarehe maalum, mwezi ("Jaribio 1: Machi" — bila siku hujahesabiwa mwisho wa mwezi), au muhula + wiki ("Muhula 1, wiki ya 6"). Mfumo huresibu `due_date` na hujaza tu matukio yenye `due_date <= leo`. Cap = `yaliyofika / jumla`. Sub-task huonyesha "inasubiri Jaribio 4 — Julai…" (mwezi/anchor kwa Kiswahili) bila kupanda juu.
- **Idadi ya nukuu (`count`)**: mwalimu hujaza "X kati ya Y" (ukurasa wa nyumbani — X na Y vyote); cap = `X / Y` (mf. 3/7 = 42.86%). Walimu wa kasi tofauti (mmoja anamaliza nukuu mwezi wa 5, mwingine wa 10) hutumia idadi yao halisi.
- **"Inasubiri" kwenye nyumbani**: chini ya maelezo ya sub-task huonyeshwa "inasubiri <tukio> — <anchor/tarehe> (siku N)" kwa events, na "inasubiri mwalimu ajaze idadi ya nukuu" kwa count. Badge ya "Chini ya ratiba" haionyeshwi wakati sub-task inasubiri.
- **Kujaza kiotomatiki**: sub-task yenye `is_waiting` na cap=0 HAIPITISHWI kwenye kujaza (log: "inasubiri … — haijazwi"); ikifika tukio, hujazwa hadi cap.
- **Mabadiliko**: kwenye ukurasa wa kuhariri (`ess_task_edit`), mwalimu huchagua aina (`events`) na aina ya anchor kwa kila tukio; `ess_subtask_count` (`/ess/subtask/<id>/count/`) husasisha X **na Y** ya nukuu.

**Vipengele vya UI (ess_home.html):** kila sub-task ya `events` huonyesha badge
"Matukio X/Y" na ujumbe "inasubiri …"; kila `count` huonyesha kisanduku cha
kusasisha nukuu.

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
- `approve_interval_days` (0=kila siku, wiki 1=7, wiki 2=14), `approve_last_auto` (**hupuuzwa dry-runs** — jaribio la [DRY-RUN] halihesabiwi), `approve_due_for` (si kurudia siku moja, na kizingiti), `approve_next_due`.
- `approve_due` — chagua approvers `approver_enabled=True, ess_ready=True` walio `due_for`.
- `run_approve_inline(profiles=None, only_due=False)` — "humuhumu ndani ya process" (inline); sasa na **thread concurrency** (`_approve_concurrency`, env `ESS_APPROVE_CONCURRENCY`, default 3, max 8), kila profile kwenye thread yake, `connection.close()` mwisho.
- `auto_fill_due`, `run_auto_fill_inline`.

Management commands:
- `ess_approve_scheduler --hour 22 --catch-up` — embedded inline approver, default saa 22 (EAT).
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
| Auto-approve haikufanya kazi jana (16 Okt) — ilibidi mkuu abofye "Idhinisha" mwenyewe | Sababu 2: (1) **dry-run ilihesabiwa kama approve** — jaribio la [DRY-RUN] la 15 Okt 07:00 EAT lilifanya `approve_last_auto` irudie (run #55), ikazima ratiba mpaka 29 Okt; (2) kipindi kilikuwa **wiki mbili**. Marekebisho: `approve_last_auto` sasa `.exclude(log__startswith='[DRY-RUN]')`; chaguo jipya **`auto_approve_weeks=0` (kila siku)** kwenye model/form/UI/views; kiendesha/beat/README yote saa **22:00 EAT** (jibu la mtumiaji: "saa 10 jioni"). | — |
| Kasi kwa wakuu wengi | `run_approve_inline` inatumia `ThreadPoolExecutor` (concurrency configurable), `_approve_one` kwa kila mkuu, `connection.close()` kwa thread, env `ESS_APPROVE_CONCURRENCY` (default 3, max 8). Aggregation sahihi ya verified/processed/failed. | `976d83f1` |
| UI ilikuwa na vitu vingi inakera watumiaji | Mpangilio upya wa `ess_home.html` na `ess_approve.html`: vichwa wazi (Hali, Hatua kuu, Maendeleo, Zana za ziada, Uhidhinishaji), kitufe kikuu mbele, zana za hiari zimepangika vizuri. Kila kipengele kimebaki. | `d21adac4` |
| Django multi-line `{# #}` comment inaonekana kwenye header | Badilisha kwenda `{% comment %}...{% endcomment %}` kwenye `_ess_install.html` (Django 5.2 haitupi multi-line `{# #}`). | `1c2f7af1` |
| Kalenda ililazimisha asilimia ya kila sub-task (kila sub-task = kalenda %) — si sahihi | Kalenda ni "total score" ya mwaka. Ondoa matangazo ya kalenda kwenye `expected_pct` na `pct_auto_for`; sub-task sasa hufuata **ratiba yake** (`schedule`). Ongeza `profile_calendar_status` (jumla ya maendeleo ya mwalimu vs lengo la kalenda) na kuionyesha kwenye `ess_home`. | `5feebbfc` |
| Ratiba ya jaribio ilikuwa tarehe pekee; walimu wanatofautiana kuandika nukuu | Aina tatu za anchor (`date`/`month`/`term_week`) kwenye `SubTaskEvent` (migration 0021), `resolve_event_date`/`term_bounds`/`event_anchor_text`. Nukuu (nafasi 2) → mode `count` kwa default (autogen + sync); fomu ya nyumbani hujaza X **na** Y. Sub-task inayosubiri (cap=0) haipitishwi kwenye kujaza; onyesho la "inasubiri" chini ya maelezo nyumbani. | mpya (migration 0021) |
| Screenshot za hitilafu zilichukuliwa **nje** ya `with sync_playwright()` — browser ilikuwa imezimwa, hivyo artifacts hazikuhifadhiwa kamwe | `artifacts.py` (`ess_browser` contextmanager) hunasa screenshot+HTML **ndani** ya browser context; selectors zote zimehamia `selectors.py`; `EssFillRun.error_step`/`artifacts` (migration 0022); UI (log + status JSON) huonyesha hatua iliyovunjika + kiungo cha picha/HTML; arifa kwa admins (`ESS_ADMIN_PROFILE_IDS`); `ess_probe` command ya kugundua selectors zilizobadilika mapema. | mpya (migration 0022) |
| Mkuu alisema "nimeset **wiki mbili** lakini kila siku naona approved" | Ukweli: auto-approve **tayari** heshimu kipindi (uthibitisho: `approve_due_for` ni False siku 1–13, True siku 14) — lakini **kitufe cha "Idhinisha maendeleo" (mkono) hakiheshimu kipindi**, ndiyo kilichokuwa kikipindua (mkuu alikuwa abofye kila siku — rejelea ESS_DOCUMENTATION §3). Marekebisho: (1) `ess_approve_now` **huzui** approve ya mkono mpaka kipindi kikafike — lazima bonyeza "Ndio, idhinisha sasa" (`override=1`); dry-run haizuiwi; (2) `approve_last_auto` sasa inahesabi **run iliyofanikiwa tu** (`status='done'`) — run iliyoshindwa/ilitosha **haichukui** kipindi (jaribio tena siku inayo); (3) UI: onyesho kipindi kinachofanya + tarehe ya ijayo + tarehe ya auto-approve ya mwisho + onyo la auto-approve iliyoshindwa + **badge "Kiotomatiki/Mkono"** kwenye historia; (4) amri mpya `ess_approve_status` ya kuagulia hali halisi (kipindi, run ya mwisho, ijayo, historia). | mpya (commit pending) |

### Artifacts za hitilafu & Admin feedback (mpya)

- **Chanzo kimoja cha selectors:** `ess_tracker/selectors.py` — `PASSWORD_SEL`, `USERNAME_SELS`, `SELECTORS`, `PROBE_CHECKS`. Fill/approve/probe zote hutumia hapa (badilika mara moja).
- **`ess_tracker/artifacts.py`:** `ess_browser(state, run_id=, label=)` (contextmanager) huchukua screenshot (`.png`) + HTML (`.html`) ya ukurasa uliokuwa wazi pale hitilafu inatokea, huhifadhi `media/ess_artifacts/`, na huweka `state['step']`/`state['artifacts']`/`state['error']`. `describe_failure()` hutoa `step`/`error`/`url`/`hint`; `prune_artifacts()` huacha 200 za mwisho (dir inaweza kubadilishwa kwa `ESS_ARTIFACT_DIR`).
- **Kila run:** `EssFillRun.error_step` (hatua iliyovunjika: `open`/`login`/`subtasks_table`/`row_actions`/...) na `artifacts` (dict ya screenshot/html/url). Ukurasa wa `fill/log/` huonyesha badge ya hatua + vitufe vya Picha/HTML; `ess_fill_status` huonyesha hivyo moja kwa moja bila ku-refresh.
- **Arifa:** `notify_run_result()` (inaitwa na Celery **na** thread fallback): mwenye wasifu hupata matokeo (done/error); kama **error**, admins walioorodheshwa kwenye env `ESS_ADMIN_PROFILE_IDS` (CSV ya `TeacherProfile.id`) hupata arifa yenye hatua + kiungo cha artifact.
- **`ess_probe`:** `python manage.py ess_probe` hupima hatua 7 (`open`→`add_progress`) kwa session halisi; kitu kikivunjika huchapisha FAIL + huhifadhi artifacts na kurudi **exit 1** (kwa CI/alerting). `--headed`, `--keep-going`, `--json`, `--profile`. Amri hii hutumika kuangalia ESS portal imebadilisha DOM **kabla** ya walimu kugundua.

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
- `ESS_ADMIN_PROFILE_IDS` — CSV ya `TeacherProfile.id` wa maombi/admins wanaopokea arifa za push pale run ya ESS inaposhindwa (mf. `12,15`).
- `ESS_ARTIFACT_DIR` — diri mbadala ya artifacts (default `media/ess_artifacts/`).
- `ESS_LOGIN_URL`, `ESS_PROFILE_LOCK_SECONDS`, `ESS_RUN_STALE_SECONDS`, `ESS_FILL_RATE_LIMIT`.

### Beat (Celery)
`field_management/settings.py:CELERY_BEAT_SCHEDULE`:
- `ess-auto-fill-daily` — 06:30 EAT (crontab)
- `ess-approve-daily` — 22:00 EAT (crontab) — **imebadilishwa saa 22** (saa 10 jioni).

### Embedded schedulers
- `ess_scheduler` (mgmt cmd) — inline auto-fill kila siku 06:30.
- `ess_approve_scheduler` (mgmt cmd) — inline approve kila siku 22:00, `--hour`, `--catch-up`, `--once`. Hupitisha `only_due=True`.

### Docker
- Multi-stage (builder/runtime), Playwright Chromium pre-installed.
- Entrypoint huanzisha TTC portal (optional), migrations, collectstatic, seeds, background jobs, embedded schedulers (kulingana na `SERVICE_ROLE` na Railway env), kisha gunicorn/nginx.

### Management Commands (zilizo muhimu)
`ess_approve`, `ess_approve_scheduler`, `ess_auto_fill`, `ess_scheduler`, `ess_key_check`, `ess_set_password`, `ess_enc_key`, **`ess_probe`** (smoke-test ya selectors/mtiririko; exit 1 ikivunjika), `import_academic_calendar.py`, `data/`, n.k.

## 5. Njia ya Kufanya Kazi (Overview Flow)

1. **Usajili (ESS):** `/ess/register/` — mkuu/mwalimu anajisajili na username/password ya e-Tendaji. `ess_register` huunda User + TeacherProfile.
2. **Wasifu:** `/ess/profile/` — kuweka ess_username/ess_password, kalenda shule, entries_per_week, holidays.
3. **Kujaza:** `/ess/` (nyumbani) — bofya **"Jaza ESS sasa"**. Hutoa POST `/ess/fill/` → `ess_fill` view au `run_ess_fill` (queue). Huangalia sub-tasks zilizochaguliwa au zote, inasoma hali kutoka ESS na kuwasilisha.
4. **Kuidhinisha (mkono):** `/ess/approve/run/` (POST) → `ess_approve_now` → `run_ess_approve` (queue) au inline. Inapata approvers na kufungua ESS. **Haina kizuizi:** mkuu anaweza kuidhinisha mwenyewe wakati wowote (hata kama kipindi kimekwisha — mfumo wa kiotomatiki ndiyo husimama, si mwalimu).
5. **Auto-approve:** kila siku **22:00 EAT** — beat au embedded scheduler inaita `approve_due` → kwa approvers walio `due_for` hutoa `run_ess_approve` (queue). Concurrency inline (ThreadPool) kwa embedded. Ndani ya **kipindi (lease)** hufanyika **KILA SIKU**; run iliyofanikiwa leo huzuia run ya pili ya leo (dry-run haihesabiwi, run iliyoshindwa hairuhusu kurudiwa siku ile ile). Amri ya kuagulia hali: `python manage.py ess_approve_status [--profile ID]`.
5b. **Mzunguko wa kila siku (alarm + beat) + kipindi (lease):** mfumo hujiamsha kila siku kwa njia mbili — **alarm** (kiendesha kilichopachikwa kwenye container ya web: `ess_scheduler` 06:30 + `ess_approve_scheduler` 22:00) na **beat** (`ess-auto-fill-daily` 06:30 + `ess-approve-daily` 22:00). **06:30 = kujaza** maendeleo ya walimu (kwa ratiba ya kila mwalimu: `entries_per_week`); **22:00 = verify** (approve) maendeleo ya SUBMITTED. Hakuna matokeo mbadala kama alarm na beat zote zikiwa nafasi (`auto_fill_decision` huruka mwalimu aliyejaza leo; `approve_due_for` huruka mkuu aliyefanyikiwa leo).
   **Maana ya "kipindi" (`auto_approve_weeks` + `auto_lease_until`):** muda (wiki) ambao mfumo unaweza kuendelea kwa moja kwa moja. Ndani ya kipindi: **kujaza na verify KILA SIKU**. Kipindi kikichisha: **mfumo husimama** (hakuna kujaza, hakuna verify) hadi mtumiaji aweke muda upya (kupiga "Hifadhi" kwenye ukurasa wa kuidhinisha huanza kipindi mpya). Mwalimu wa shule husimamishwa na kipindi cha mkuu wa shule yake (`school`); mwalimu bila mkuu katika shule hafungwiwi. Kila siku 22:00 hakuna "kipindi cha wiki" — ni kila siku.
6. **Onboarding approver:** admin (custom `/admin/`) → ESS e-Tendaji Tracker → Teacher profiles → chagua → action **"Washa kuidhinisha kwa waliochaguliwa"**. Kitufe kinaonekana kwenye nyumbani/approve.

## 6. Hitimisho
Tumeunda mfumo imara wa ESS (fill + approve) na kuiratibu vizuri (mpangilio wa UI msafi kwa walimu), tumeongeza automation yenye kipindi (kila siku/wiki 1/wiki 2) na trigger wa kila siku 22:00 EAT, tukaboresha kasi kwa concurrency, tukarekesha matatizo ya Docker/trixie, key ya crypto, approve selectors/data detection, na admin registration. Hivi karibuni tume**tenganisha kalenda na sub-task**: kalenda sasa ni "total score" tu (inayokua kwa miezi/wiki, ikilinganishwa na jumla ya maendeleo kwenye nyumbani + arifa 07:15), huku kila sub-task ikifuata ratiba yake mwenyewe. Documentation hii inasambaza muundo, suluhisho na namna ya kuendeshwa kwa usahihi.
