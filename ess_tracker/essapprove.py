"""Idhinisha (verify) maendeleo ya walimu kwenye ESS kwa Playwright.

Mkuu wa shule hutumia check number + password kama mwalimu wa kawaida, lakini
ana kitu cha ziada: kuapprove (= "verify") description zilizowasilishwa
(SUBMITTED) na walimu.

Mtiririko (umethibitishwa dhidi ya DOM halisi ya ESS):

    1. Login (kama mwalimu).
    2. Department/Unit/Workstation -> /pepmis/implementation/department-report
       ("<Shule> Dashboard").
    3. Jedwali "Employee Sub Task Daily Performance Progress":
       kila safu ina vitone vitatu (more_vert).
    4. more_vert -> "Approve Progress" -> panel "Activity Progress Details".
    5. Kwenye safu zenye Status SUBMITTED: more_vert -> "Verify" -> thibitisha
       (SweetAlert2 "Action Completed Successfully" / OK).

Mwito halisi wa GraphQL unaofanyika ni:

    mutation attendSubTaskProgress($input: AttendProgressDtoInput) {
      attendSubTaskProgress(attendSubTaskDto: $input) { ... }
    }
    variables: {"input": {"progressId": <id>, "comment": "", "decision": "ACCEPTED"}}
"""
from __future__ import annotations

import re
import time

from django.utils import timezone as tz

from . import essfill
from .essfill import (_goto_retry, _normalize, _open_ess, _set_progress,
                      _visible_text, CACHE_PREFIX)

BASE_URL = essfill.BASE_URL
DASHBOARD_URL = essfill.DASHBOARD_URL
DEPT_URL = 'https://ess.utumishi.go.tz/pepmis/implementation/department-report'


class ApproveError(RuntimeError):
    """Hitilafu wakati wa kuidhinisha."""


# ── Utambuzi wa majedwali ────────────────────────────────────────────
def _header_text(table) -> str:
    for sel in ('thead', 'tr:first-child'):
        try:
            el = table.query_selector(sel)
            if el:
                return _normalize(el.inner_text())
        except Exception:
            continue
    return _normalize(table.inner_text()[:200])


def _find_main_table(page):
    """Jedwali la "Employee Sub Task Daily Performance Progress"."""
    for t in page.query_selector_all('table'):
        h = _header_text(t)
        if 'sub task' in h and ('employee' in h or 'percentage' in h) \
                and 'implementation description' not in h:
            return t
    return None


def _find_details_table(page):
    """Jedwali la "Activity Progress Details"."""
    for t in page.query_selector_all('table'):
        if 'implementation description' in _header_text(t):
            return t
    return None


def _main_rows(page):
    t = _find_main_table(page)
    if t is None:
        return []
    return [r for r in t.query_selector_all('tbody tr') if _row_cells(r)]


def _details_rows(page):
    t = _find_details_table(page)
    if t is None:
        return []
    return [r for r in t.query_selector_all('tbody tr') if _row_cells(r)]


def _row_cells(row):
    try:
        cells = row.query_selector_all('td')
    except Exception:
        return []
    return [c for c in cells if (c.inner_text() or '').strip()]


def _row_signature(row) -> str:
    """Employee + Sub Task (main) au Description (details) — kwa kufuatilia."""
    try:
        cells = row.query_selector_all('td')
    except Exception:
        return ''
    parts = [_normalize(c.inner_text()) for c in cells]
    return ' | '.join(p for p in parts if p)[:200]


def _main_row_signature(row) -> str:
    """Employee + Sub Task pekee (bila No./Actions) — thabiti baada ya DOM
    kupangwa upya."""
    try:
        cells = row.query_selector_all('td')
    except Exception:
        return ''
    vals = [_normalize(c.inner_text()) for c in cells]
    vals = [v for v in vals if v]
    if len(vals) >= 4:
        return f'{vals[1]} | {vals[2]}'[:200]
    return ' | '.join(vals)[:200]


def _details_status(row) -> str:
    txt = _normalize(row.inner_text()).upper()
    for s in ('SUBMITTED', 'APPROVED', 'REJECTED', 'ROLLEDBACK', 'COMPLETED',
              'PENDING', 'VERIFIED'):
        if s in txt:
            return s
    return ''


# ── Vitendo vya menyu ────────────────────────────────────────────────
def _open_more_menu(page, container) -> bool:
    """Bofya alama ya vitone vitatu (more_vert) ndani ya `container`."""
    for sel in ('td.mat-column-manage .mat-mdc-menu-trigger',
                '.mat-mdc-menu-trigger', 'button:has(mat-icon)',
                'button[aria-haspopup]', 'button'):
        try:
            for b in container.query_selector_all(sel):
                blob = (b.inner_html() or '') + (b.inner_text() or '')
                if 'more_vert' in blob or b.get_attribute('aria-haspopup'):
                    if b.is_visible():
                        b.click()
                        return True
        except Exception:
            continue
    return False


def _menu_item_texts(page):
    out = []
    for panel in page.query_selector_all(
            '.mat-mdc-menu-panel, .mat-menu-panel, div[role="menu"]'):
        try:
            if not panel.is_visible():
                continue
            for b in panel.query_selector_all(
                    'button, [role=menuitem], .mat-mdc-menu-item'):
                t = _normalize(b.inner_text())
                if t:
                    out.append(t)
        except Exception:
            continue
    return out


def _click_menu_item(page, label) -> bool:
    """Bofya kipengee cha menyu kwa jina (fuzzy/contains)."""
    needle = _normalize(label)
    for panel in page.query_selector_all(
            '.mat-mdc-menu-panel, .mat-menu-panel, div[role="menu"]'):
        try:
            if not panel.is_visible():
                continue
            for b in panel.query_selector_all(
                    'button, [role=menuitem], .mat-mdc-menu-item'):
                txt = _normalize(b.inner_text())
                if needle in txt or txt in needle:
                    b.click()
                    return True
        except Exception:
            continue
    return False


def _confirm_swal(page, timeout_s=20) -> bool:
    """Thibitisha SweetAlert2 ('Action Completed Successfully' -> OK)."""
    deadline = time.time() + timeout_s
    clicked = False
    while time.time() < deadline:
        for sel in ('.swal2-confirm', "button:has-text('OK')",
                    "button:has-text('Ok')", "button:has-text('Sawa')",
                    "button:has-text('Yes')", "button:has-text('Ndiyo')"):
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    clicked = True
                    break
            except Exception:
                continue
        if clicked:
            break
        page.wait_for_timeout(400)
    # Subiri swal ipotepe.
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        sw = page.query_selector('.swal2-container')
        try:
            if not sw or not sw.is_visible():
                break
        except Exception:
            break
        page.wait_for_timeout(400)
    return clicked


def _close_details(page) -> None:
    """Funga panel 'Activity Progress Details'."""
    for sel in ("button:has-text('close')", "button:has-text('Close')",
                "mat-icon:text-is('close')", "button[aria-label='Close']",
                "button[aria-label='close']"):
        try:
            for el in page.query_selector_all(sel):
                if el.is_visible():
                    el.click()
                    page.wait_for_timeout(800)
                    return
        except Exception:
            continue
    try:
        page.keyboard.press('Escape')
    except Exception:
        pass
    page.wait_for_timeout(600)


# ── Hatua kuu ────────────────────────────────────────────────────────
def _ensure_dept(page, emit) -> bool:
    """Fikia skrini ya department-report (deep-link moja kwa moja hurudisha
    login; hivyo hupitia tile ya e-Utendaji kisha kiungo cha menyu)."""
    if _on_dept(page):
        return True
    for attempt in range(5):
        for label in ('e-Utendaji (WATUMISHI)', 'e-Utendaji'):
            el = page.query_selector(f'text={label}')
            if el and el.is_visible():
                try:
                    el.click()
                    page.wait_for_timeout(4000)
                except Exception:
                    pass
                break
        for _ in range(15):
            if '/pepmis' in page.url:
                break
            page.wait_for_timeout(700)
        try:
            page.evaluate(
                """() => { const a = [...document.querySelectorAll('a')]
                     .find(x => /department-report/.test(x.getAttribute('href') || ''));
                   if (a) a.click(); }""")
        except Exception:
            pass
        page.wait_for_timeout(4500)
        if _on_dept(page):
            return True
        emit(f'jaribio {attempt + 1} kufikia dashboard: {page.url}')
    return False


def _on_dept(page) -> bool:
    if 'department-report' not in page.url:
        return False
    return _find_main_table(page) is not None or bool(_main_rows(page))


def _verify_submitted_in_details(page, emit, dry_run=False) -> int:
    """Kwenye panel iliyo wazi, verify kila safu yenye SUBMITTED. Hurudi idadi."""
    verified = 0
    for _ in range(200):
        rows = _details_rows(page)
        target = None
        for r in rows:
            if _details_status(r) == 'SUBMITTED':
                target = r
                break
        if target is None:
            break
        sig = _row_signature(target)
        if not _open_more_menu(page, target):
            emit(f'  !! sikuweza kufungua menyu ya safu: {sig[:70]}')
            break
        page.wait_for_timeout(1000)
        items = _menu_item_texts(page)
        if not any('verify' in it for it in items):
            emit(f'  = hakuna Verify kwenye menyu {items} — naruka')
            _close_menus(page)
            break
        if dry_run:
            emit(f'  [DRY-RUN] ningefanya Verify: {sig[:80]}')
            _close_menus(page)
            verified += 1
            # Zuia loop isiyoisha kwenye dry-run (safu haipotei).
            break
        if not _click_menu_item(page, 'Verify'):
            emit('  !! sikuweza kubofya Verify')
            _close_menus(page)
            break
        page.wait_for_timeout(1200)
        _confirm_swal(page)
        page.wait_for_timeout(1500)
        verified += 1
        emit(f'  -> Verify OK: {sig[:80]}')
    return verified


def _close_menus(page):
    try:
        page.keyboard.press('Escape')
        page.wait_for_timeout(400)
    except Exception:
        pass


def _process_main_row(page, row, emit, dry_run=False) -> int:
    """Fungua 'Approve Progress' ya safu moja na verify SUBMITTED zake."""
    if not _open_more_menu(page, row):
        return 0
    page.wait_for_timeout(1000)
    items = _menu_item_texts(page)
    if not any('approve progress' in it for it in items):
        _close_menus(page)
        return 0
    if not _click_menu_item(page, 'Approve Progress'):
        _close_menus(page)
        return 0
    page.wait_for_timeout(4000)
    if _find_details_table(page) is None:
        emit('  = hakuna jedwali la Activity Progress Details')
        _close_details(page)
        return 0
    n = _verify_submitted_in_details(page, emit, dry_run=dry_run)
    _close_details(page)
    page.wait_for_timeout(1200)
    return n


def _next_page(page) -> bool:
    for sel in ('.mat-mdc-paginator-navigation-next',
                'button[aria-label="Next page"]',
                'button[aria-label="Next Page"]'):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                disabled = el.get_attribute('disabled') is not None
                try:
                    disabled = disabled or el.is_disabled()
                except Exception:
                    pass
                if not disabled:
                    el.click()
                    page.wait_for_timeout(3500)
                    return True
        except Exception:
            continue
    return False


def run_approve(profile_id: int, run_id: int, dry_run: bool = False) -> dict:
    """Idhinisha maendeleo yote SUBMITTED kwa akaunti ya mkuu (Playwright)."""
    from .models import EssFillRun, TeacherProfile

    profile = TeacherProfile.objects.select_related('user').get(pk=profile_id)
    run = EssFillRun.objects.get(pk=run_id)
    log = []

    def emit(msg):
        # Hakuna DB humu ndani ya browser context (Django async-guard); cache pekee.
        log.append(str(msg))
        _set_progress(run_id, msg=str(msg), log=list(log), done=False)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        run.status = 'error'
        run.finished = tz.now()
        run.log = 'Playwright haiko kwenye server.'
        run.save()
        return {'status': 'error', 'msg': str(exc)}

    emit(('[DRY-RUN] ' if dry_run else '') + 'Kuanza kuidhinisha (verify) ESS...')
    verified = processed = failed = 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
                      '--ignore-certificate-errors',
                      '--disable-features=CertificateTransparencyEnforcement'])
            ctx = browser.new_context(ignore_https_errors=True)
            page = ctx.new_page()
            page.set_default_timeout(45000)

            _open_ess(page)
            essfill._auto_login(page, profile.ess_username,
                                profile.ess_password_plain)
            emit('Login kamili.')
            try:
                _goto_retry(page, DASHBOARD_URL)
                essfill._wait_for_current_year(page, 20)
            except Exception:
                pass

            if not _ensure_dept(page, emit):
                raise ApproveError(
                    'Sirikufikia skrini ya Department/Unit/Workstation. '
                    'URL: %s' % page.url)
            emit('Tumefikia dashboard: ' + page.url)

            page_no = 0
            attempted = set()
            while page_no < 500:
                page_no += 1
                rows = _main_rows(page)
                if not rows:
                    if _next_page(page):
                        attempted.clear()
                        continue
                    break
                target = None
                for row in rows:
                    sig = _main_row_signature(row)
                    if sig and sig not in attempted:
                        target = (row, sig)
                        break
                if target is None:
                    if _next_page(page):
                        attempted.clear()
                        continue
                    break
                row, sig = target
                attempted.add(sig)
                if page_no <= 1 or page_no % 5 == 0:
                    emit(f'Safu {len(attempted)}: {sig[:70]}')
                try:
                    n = _process_main_row(page, row, emit, dry_run=dry_run)
                    verified += n
                    if n:
                        _set_progress(run_id, saved=verified)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    emit(f'  !! hitilafu kwenye safu ({sig[:50]}): {exc}')
                    try:
                        _close_details(page)
                    except Exception:
                        pass
                processed += 1
                # DOM hupangwa upya baada ya verify — tunarudi kwenye orodha.
                page.wait_for_timeout(600)

            # Angalia kama bado kuna SUBMITTED (labda kurasa zilizosalia).
            emit(f'Zilizoidhinishwa: {verified}, safu zilizochunguzwa: {processed}, '
                 f'hitilafu: {failed}')
            result = {'status': 'done', 'verified': verified,
                      'processed': processed, 'failed': failed}
    except Exception as exc:  # noqa: BLE001
        result = {'status': 'error', 'msg': str(exc)}

    # DB saves nje ya browser context (Django async-guard).
    run.saved = verified
    run.skipped = max(processed - verified, 0)
    # `not_found` hutumika kama kihesabu cha "Hitilafu" kwenye UI.
    run.not_found = failed
    run.required = processed
    run.status = 'done' if result.get('status') == 'done' else 'error'
    run.finished = tz.now()
    if result.get('status') == 'error':
        log.append(f'HITILAFU: {result.get("msg")}')
    run.log = '\n'.join(log)
    run.save()
    _set_progress(run_id, done=True, status=run.status, saved=verified,
                  skipped=run.skipped, not_found=failed, log=list(log))
    return result
