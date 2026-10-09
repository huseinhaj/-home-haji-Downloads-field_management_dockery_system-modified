"""Jaza ESS e-Utendaji kwa Playwright (auto-login kwa akaunti ya mwalimu).

Selectors zote zimethibitishwa dhidi ya DOM halisi ya ESS
(/pepmis/implementation/progress, Angular Material MDC). Kitu pekee
kilichoongezwa tofauti na CLI ya ess_utendaji ni login ya kiotomatiki:
haina waendeshaji wa browser wa ndani — inaendesha kwenye server (Celery),
hivyo inajaza username/password iliyohifadhiwa na kuendelea.
"""
from __future__ import annotations

import re
import time
from difflib import SequenceMatcher

from django.core.cache import cache
from django.utils import timezone as tz

from .compute import built_wanted, pct_for
from .models import EssFillRun, SubTask

BASE_URL = 'https://ess.utumishi.go.tz/'
SUBTASKS_URL = 'https://ess.utumishi.go.tz/pepmis/implementation/progress'

PASSWORD_SEL = "input[formcontrolname='password'], input[name='password'], input[type='password']"

USERNAME_SELS = [
    "input[formcontrolname='username']",
    "input[formcontrolname='email']",
    "input[type='email']",
    "input[name='username']",
    "input[name='email']",
    "input[id='username']",
    "input[id='email']",
    "input.form-control:not([type='password'])",
]

SELECTORS = {
    'row_selector': 'table tbody tr.mat-mdc-row.mdc-data-table__row',
    'subtask_cell_selector': 'td.mat-column-subTaskDescription',
    'percentage_cell_selector': 'td.mat-column-progressPercentage',
    'percentage_value_selector': 'mat-progress-bar',
    'percentage_value_attr': 'aria-valuenow',
    'row_action_button_selector': 'td.mat-column-manage .mat-mdc-menu-trigger',
    'edit_menu_item': ".mat-mdc-menu-panel button.mat-mdc-menu-item:has-text('Add Progress Details')",
    'dialog_selector': 'mat-dialog-container',
    'subtype_select_selector': "mat-dialog-container mat-select[formcontrolname='subActivityType']",
    'description_selector': "mat-dialog-container textarea[formcontrolname='description']",
    'status_select_selector': "mat-dialog-container mat-select[formcontrolname='implementationStatus']",
    'status_option_completed': 'COMPLETED',
    'status_option_in_progress': 'IN_PROGRESS',
    'status_option_not_started': 'NOT_STARTED',
    'percentage_input_selector': "mat-dialog-container input[formcontrolname='percentageRank']",
    'save_button': "mat-dialog-container button[type='submit']",
    'paginator_next_selector': '.mat-mdc-paginator-navigation-next',
    'match_threshold': 0.9,
}

CACHE_PREFIX = 'ess_fill:'


# ── Msaada wa Playwright ─────────────────────────────────────────────
def _normalize(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '').strip().lower())


def _goto_retry(page, url, tries=3):
    for attempt in range(tries):
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            return
        except Exception:
            if attempt == tries - 1:
                raise
            page.wait_for_timeout(2000)


def _click_fuzzy_text(page, needle) -> bool:
    for sel in (f'text={needle}', f":has-text('{needle}')",
                f"span:text-is('{needle}')", f"div:text-is('{needle}')"):
        try:
            for el in page.query_selector_all(sel):
                if el.is_visible():
                    el.click()
                    return True
        except Exception:
            continue
    return False


def _has_password_form(page) -> bool:
    return len(page.query_selector_all(PASSWORD_SEL)) > 0


def _fill_first_visible(page, sels, value):
    for sel in sels:
        try:
            for el in page.query_selector_all(sel):
                if el.is_visible() and not el.get_attribute('type') in ('password', 'submit'):
                    el.fill(value)
                    return True
        except Exception:
            continue
    return False


def _auto_login(page, username, password) -> bool:
    """Rudi True — login imetengenezwa au tayari tumelogin."""
    try:
        page.wait_for_selector(PASSWORD_SEL, timeout=30000)
    except Exception:
        return True
    if not username or not password:
        raise RuntimeError('Mwalimu hajaweka ESS username na password.')
    if not _fill_first_visible(page, USERNAME_SELS, username):
        raise RuntimeError('Sikuweza kupata fomu ya username kwenye ESS login.')
    pw = page.query_selector(PASSWORD_SEL)
    if not pw:
        raise RuntimeError('Sikuweza kupata fomu ya password (ESS).')
    pw.fill(password)
    try:
        page.click("button[type='submit']")
    except Exception:
        pw.press('Enter')
    deadline = time.time() + 90
    while time.time() < deadline:
        if not _has_password_form(page):
            return True
        page.wait_for_timeout(2000)
    raise RuntimeError('Login ya ESS haikufaulu (fomu yake ilibaki wazi).')


def _goto_subtasks(page) -> None:
    try:
        page.goto(SUBTASKS_URL, wait_until='domcontentloaded')
        page.wait_for_selector(SELECTORS['row_selector'], timeout=25000)
        return
    except Exception:
        pass
    if 'pepmis' not in page.url:
        _click_fuzzy_text(page, 'e-Utendaji')
        page.wait_for_timeout(4000)
    try:
        el = page.query_selector("button:has-text('Implementation and Monitoring')")
        if el and el.is_visible():
            el.click()
    except Exception:
        pass
    page.wait_for_timeout(1500)
    for sel in ("a[href='/pepmis/implementation/progress']",
                "a[href*='implementation/progress' i]"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                break
        except Exception:
            continue
    page.wait_for_timeout(3500)
    page.wait_for_selector(SELECTORS['row_selector'], timeout=30000)


def _best_row_match(target_text, candidates, threshold):
    tnorm = _normalize(target_text)
    best, best_score = None, 0.0
    second = 0.0
    for item in candidates:
        score = SequenceMatcher(None, tnorm, _normalize(item['text'])).ratio()
        if score > best_score:
            second = best_score
            best, best_score = item, score
        elif score > second:
            second = score
    if best_score < threshold:
        return None, best_score
    if best_score < 1.0 and best_score - second < 0.03:
        return None, best_score
    return best, best_score


def _to_number(val):
    if val is None:
        return None
    s = str(val).replace('%', '').replace(',', '').strip()
    if not s:
        return None
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


def _row_current_pct(row_el):
    cell = row_el.query_selector(SELECTORS['percentage_cell_selector'])
    if not cell:
        return None
    bar = cell.query_selector(SELECTORS['percentage_value_selector'])
    if bar:
        raw = bar.get_attribute(SELECTORS['percentage_value_attr'])
        n = _to_number(raw)
        if n is not None:
            return float(n)
    return _to_number(cell.inner_text())


def _click_text_option(page, needle, exact=True):
    opts = page.query_selector_all('.cdk-overlay-container .mat-mdc-option')
    if not opts:
        opts = page.query_selector_all('mat-option, .mat-mdc-option')
    if exact:
        target = (needle or '').strip().upper()
        for o in opts:
            if ((o.inner_text() or '').strip().upper() == target
                    or (o.get_attribute('value') or '').upper() == target):
                o.click()
                return True
        return False
    best, score = None, 0.0
    nn = _normalize(needle)
    for o in opts:
        s = SequenceMatcher(None, nn, _normalize(o.inner_text())).ratio()
        if s > score:
            best, score = o, s
    if best and score >= 0.5:
        best.click()
        return True
    return False


# ── Mtiririko mkuu ───────────────────────────────────────────────────
def _set_progress(run_id, **kw):
    data = cache.get(CACHE_PREFIX + str(run_id)) or {}
    data.update(kw)
    cache.set(CACHE_PREFIX + str(run_id), data, timeout=3600)


def run_fill(profile_id: int, run_id: int) -> dict:
    """Jaza ESS kwa profile ya mwalimu (inaitwa ndani ya Celery)."""
    from .models import TeacherProfile

    profile = TeacherProfile.objects.select_related('user').get(pk=profile_id)
    run = EssFillRun.objects.get(pk=run_id)
    log = []

    def emit(msg):
        log.append(msg)
        _set_progress(run_id, msg=msg, done=False)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        run.status = 'error'
        run.finished = tz.now()
        run.log = 'Playwright haiko kwenye server.'
        run.save()
        return {'status': 'error', 'msg': str(exc)}

    wanted = built_wanted(profile)
    run.required = len(wanted)
    run.save()

    if not wanted:
        emit('Hakuna sub-task yenye asilimia. Ongeza actual/target kwanza.')
        run.status = 'error'
        run.finished = tz.now()
        run.log = '\n'.join(log)
        run.save()
        return {'status': 'error', 'msg': 'Hakuna sub-task zenye asilimia.'}

    emit(f'Sub-task {len(wanted)} zitaingizwa ESS.')
    run.log = '\n'.join(log)
    run.save()

    saved = skipped = not_found = 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
            ctx = browser.new_context(ignore_https_errors=True)
            page = ctx.new_page()
            page.set_default_timeout(45000)

            _goto_retry(page, BASE_URL)
            _auto_login(page, profile.ess_username, profile.ess_password_plain)
            emit('Login kamili.')
            _goto_subtasks(page)

            threshold = SELECTORS['match_threshold']
            remaining = list(wanted)
            page_no = 0
            while remaining:
                page_no += 1
                page.wait_for_selector(SELECTORS['row_selector'], timeout=15000)
                row_els = page.query_selector_all(SELECTORS['row_selector'])
                visible = []
                for i, el in enumerate(row_els):
                    cell = el.query_selector(SELECTORS['subtask_cell_selector'])
                    if cell:
                        visible.append({'i': i, 'text': cell.inner_text(),
                                        'pct': _row_current_pct(el)})
                emit(f'Ukurasa {page_no}: safu {len(visible)}')

                for entry in list(remaining):
                    text, pct = entry
                    match, score = _best_row_match(text, visible, threshold)
                    if not match:
                        continue
                    remaining.remove(entry)
                    cur = match['pct']
                    if cur is not None and abs(float(cur) - pct) < 0.5:
                        skipped += 1
                        emit(f'= sawa tayari ({pct:.2f}%): {text[:50]}')
                        continue
                    emit(f'-> {text[:50]}  (match {score:.2f}) => {pct:.2f}%')
                    _fill_one(page, match['i'], text, pct)
                    saved += 1
                    _set_progress(run_id, saved=saved)

                nxt = page.query_selector(SELECTORS['paginator_next_selector'])
                if not nxt or nxt.get_attribute('disabled') is not None or nxt.is_disabled():
                    break
                nxt.click()
                page.wait_for_timeout(700)

            not_found = len(remaining)
            browser.close()
    except Exception as exc:  # noqa: BLE001
        run.status = 'error'
        run.finished = tz.now()
        run.saved = saved
        run.skipped = skipped
        run.not_found = not_found
        run.log = '\n'.join(log + [f'ERROR: {exc}'])
        run.save()
        _set_progress(run_id, done=True, error=str(exc), status='error')
        return {'status': 'error', 'msg': str(exc)}

    run.status = 'done'
    run.finished = tz.now()
    run.saved = saved
    run.skipped = skipped
    run.not_found = not_found
    run.log = '\n'.join(log)
    run.save()
    for text, _p in remaining:
        emit(f'# haijapatikana: {text[:60]}')
    _set_progress(run_id, done=True, status='done', saved=saved,
                  skipped=skipped, not_found=not_found)
    return {'status': 'done', 'saved': saved, 'skipped': skipped, 'not_found': not_found}


def _fill_one(page, row_index, text, pct) -> None:
    """Fungua dialog na ujaze sub task moja (selectors zimehakikiwa)."""
    row_els = page.query_selector_all(SELECTORS['row_selector'])
    if row_index >= len(row_els):
        raise RuntimeError('Mstari wa jedwali haupo tena (ulibadilika baada ya Save).')
    row_el = row_els[row_index]
    row_el.query_selector(SELECTORS['row_action_button_selector']).click()
    page.wait_for_selector(SELECTORS['edit_menu_item'], timeout=8000)
    page.click(SELECTORS['edit_menu_item'])
    page.wait_for_selector(SELECTORS['dialog_selector'], timeout=15000)

    subtype = page.wait_for_selector(SELECTORS['subtype_select_selector'], timeout=10000)
    if not (subtype.inner_text() or '').strip():
        subtype.click()
        page.wait_for_timeout(800)
        if not _click_text_option(page, text, exact=False):
            raise RuntimeError('Sikuweza kuchagua Sub Task kwenye dialog.')
        page.wait_for_timeout(500)

    desc = page.wait_for_selector(SELECTORS['description_selector'], timeout=10000)
    desc.fill(text[:500])

    status_opt = (SELECTORS['status_option_completed'] if pct >= 100
                  else SELECTORS['status_option_in_progress'] if pct > 0
                  else SELECTORS['status_option_not_started'])
    status = page.wait_for_selector(SELECTORS['status_select_selector'], timeout=10000)
    status.click()
    page.wait_for_timeout(800)
    if not _click_text_option(page, status_opt, exact=True):
        raise RuntimeError(f'Sikuweza kuchagua status {status_opt}.')
    page.wait_for_timeout(500)

    inp = page.wait_for_selector(SELECTORS['percentage_input_selector'], timeout=10000)
    inp.fill(str(int(round(pct))))
    page.click(SELECTORS['save_button'])
    page.wait_for_selector(SELECTORS['dialog_selector'], state='detached', timeout=20000)
    try:
        page.wait_for_load_state('networkidle', timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(600)


def subtask_snapshot(task) -> list[dict]:
    """Maelezo ya UI (asilimia, target, actual) kwa template."""
    out = []
    for st in task.subtasks.all().prefetch_related('entries'):
        pct, src = pct_for(st)
        out.append({
            'st': st,
            'target': target_display(st),
            'actual': actual_display(st),
            'expected': expected_display(st),
            'pct': pct,
            'pct_str': '' if pct is None else f'{pct:.2f}%',
            'source': src,
        })
    return out


def target_display(st: SubTask) -> str:
    from .compute import target_for
    t = target_for(st)
    if st.mode == 'periods':
        return f'{t:g} (vila {st.vila_per_week:g} x wiki {st.week_count})'
    return f'{t:g}'


def actual_display(st: SubTask) -> str:
    from .compute import actual_for
    return f'{actual_for(st):g}'


def expected_display(st: SubTask) -> str:
    from .compute import expected_for
    e = expected_for(st)
    return '' if e is None else f'{e:g}'