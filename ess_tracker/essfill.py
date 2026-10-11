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

from .compute import built_wanted, pct_auto_for, pct_for
from .models import EssFillRun, SubTask

BASE_URL = 'https://ess.utumishi.go.tz/'
SIGNIN_URL = 'https://ess.utumishi.go.tz/sessions/signin'
DASHBOARD_URL = 'https://ess.utumishi.go.tz/dashboard'
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
    # Vitufe vya kuwasilisha (ESS inahitaji Submit, si Save pekee)
    'submit_labels': ['Submit', 'SUBMIT', 'Submit Progress', 'Wasilisha', 'Tuma',
                      'Thibitisha', 'Send', 'Sumit'],
    'confirm_labels': ['Yes', 'YES', 'Ok', 'OK', 'Confirm', 'Continue',
                       'Ndiyo', 'Thibitisha', 'Submit', 'SUBMIT'],
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


def _visible_text(page, limit=400) -> str:
    try:
        txt = page.inner_text('body') or ''
    except Exception:
        return ''
    return re.sub(r'\s+', ' ', txt).strip()[:limit]


def _pick_visible_input(page, sels, min_width=40):
    """Chagua input iliyo wazi kabisa (ESS ina nakala zilizofichwa/ndogo)."""
    best, best_area = None, 0.0
    for sel in sels:
        try:
            for el in page.query_selector_all(sel):
                box = el.bounding_box()
                if not box or box['width'] < min_width or box['height'] < 5:
                    continue
                area = box['width'] * box['height']
                if area > best_area:
                    best, best_area = el, area
        except Exception:
            continue
    return best


def _set_input_value(el, value) -> None:
    """Jaza input; ESS huweka `readonly` dhidi ya autofill hivyo inaondolewa."""
    el.evaluate(
        """(node, val) => {
            node.removeAttribute('readonly');
            node.removeAttribute('disabled');
            node.focus();
            node.value = val;
            node.dispatchEvent(new Event('input', {bubbles: true}));
            node.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        value,
    )


def _login_error_text(page) -> str:
    txt = _visible_text(page, 2500).lower()
    for needle in ('wrong credentials', 'login failed', 'internal server error',
                   'gateway timeout', 'service is unreachable', 'invalid user',
                   'invalid credentials', 'bad credentials'):
        if needle in txt:
            return needle.title()
    return ''


def _click_login(page, pw_el) -> None:
    for sel in ("button[type='submit']", "button:has-text('LOGIN')",
                "button:has-text('Login')", "button:has-text('INGIA')"):
        try:
            for el in page.query_selector_all(sel):
                if el.is_visible() and el.is_enabled():
                    el.click()
                    return
        except Exception:
            continue
    if pw_el is not None:
        pw_el.press('Enter')


def _auto_login(page, username, password) -> bool:
    """Rudi True — login imetengenezwa au tayari tumelogin."""
    try:
        if page.evaluate("() => !!localStorage.getItem('token')"):
            return True
    except Exception:
        pass

    # Subiri fomu ya login (Angular inaichelewa kuionesha).
    try:
        page.wait_for_function(
            """() => [...document.querySelectorAll("input[formcontrolname='email']")]
                     .some(e => e.getBoundingClientRect().width > 50)""",
            timeout=60000)
    except Exception:
        try:
            if page.evaluate("() => !!localStorage.getItem('token')"):
                return True
        except Exception:
            pass
        raise RuntimeError('Fomu ya login ya ESS haikuonekana (URL: %s).' % page.url)

    if not username or not password:
        raise RuntimeError('Mwalimu hajaweka ESS username na password.')

    user_el = _pick_visible_input(page, USERNAME_SELS)
    pw_el = _pick_visible_input(page, [
        "input[formcontrolname='password']",
        "input[name='password']",
        "input[type='password']",
    ])
    if user_el is None:
        raise RuntimeError('Sikuweza kupata fomu ya username kwenye ESS login.')
    if pw_el is None:
        raise RuntimeError('Sikuweza kupata fomu ya password (ESS).')

    _set_input_value(user_el, username)
    _set_input_value(pw_el, password)
    _click_login(page, pw_el)

    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            if page.evaluate("() => !!localStorage.getItem('token')"):
                return True
        except Exception:
            pass
        if '/user/must-change-password' in page.url:
            raise RuntimeError(
                'Akaunti yako ya ESS inahitaji kubadilisha password kwenye portal '
                '(must-change-password) kabla ya kujaza.')
        err = _login_error_text(page)
        if err:
            raise RuntimeError('Login ya ESS haikufaulu: ' + err)
        page.wait_for_timeout(1500)
    raise RuntimeError('Login ya ESS haikufaulu (URL: %s).' % page.url)


def _rows(page):
    """Safu za jedwali zenye data (mat-row; si safu ya 'hakuna data')."""
    for sel in ('table tbody tr[mat-row]',
                'table tbody tr.mat-mdc-row.mdc-data-table__row',
                'table tbody tr.mat-mdc-row'):
        try:
            els = page.query_selector_all(sel)
            if els:
                return els
        except Exception:
            continue
    return []


def _wait_for_table(page, timeout_s=30) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if page.query_selector(
                    '.mat-column-subTaskDescription, .mat-column-progressPercentage, '
                    '.pepmis-table-container table'):
                return True
        except Exception:
            pass
        if '/sessions/signin' in page.url:
            return False
        page.wait_for_timeout(500)
    return False


def _current_year(page):
    try:
        return page.evaluate(
            "() => { const y = localStorage.getItem('currentYear');"
            " return y ? JSON.parse(y) : null; }")
    except Exception:
        return None


def _wait_for_current_year(page, timeout_s=20):
    """Subiri ESS iweke mwaka wa PEPMIS (currentYear) kwenye localStorage."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _current_year(page):
            return True
        page.wait_for_timeout(1000)
    return False


def _set_current_year(page, year_obj) -> None:
    page.evaluate(
        "y => localStorage.setItem('currentYear', JSON.stringify(y))", year_obj)


def _candidate_years(page):
    """Miaka iliyohifadhiwa kwenye kikao (FY/CY) -- moja inaweza kuwa na sub-tasks."""
    out, seen = [], set()
    for key in ('currentYear', 'currentFinancialYear', 'currentCalendarYear',
                'planningYear'):
        try:
            y = page.evaluate(
                "k => { const v = localStorage.getItem(k);"
                " return v ? JSON.parse(v) : null; }", key)
        except Exception:
            y = None
        if isinstance(y, dict) and y.get('id') and y['id'] not in seen:
            seen.add(y['id'])
            out.append(y)
    return out


def _goto_subtasks(page) -> None:
    _goto_retry(page, SUBTASKS_URL)
    ok = _wait_for_table(page, 30)
    if '/user/must-change-password' in page.url:
        raise RuntimeError(
            'Akaunti yako ya ESS inahitaji kubadilisha password kwenye portal '
            '(must-change-password) kwanza. URL: %s' % page.url)
    if not ok and '/sessions/signin' in page.url:
        raise RuntimeError(
            'ESS inarudisha kwenye login baada ya kuingia (kikao hakihifadhiwa). '
            'Hakikisha username/password za ESS ni sahihi. URL: %s' % page.url)
    if not ok:
        _click_fuzzy_text(page, 'e-Utendaji')
        page.wait_for_timeout(2500)
        for sel in ("a[href='/pepmis/implementation/progress']",
                    "a[href*='implementation/progress' i]"):
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    break
            except Exception:
                continue
        ok = _wait_for_table(page, 30)
    if not ok:
        raise RuntimeError(
            'Ukurasa wa sub-tasks (ESS) hauleti jedwali. URL: %s | Kichwa: %s | '
            'Kimeonekana: %s' % (page.url, page.title(), _visible_text(page, 300)))


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


def _dialog_button_texts(page):
    out = []
    for b in page.query_selector_all('mat-dialog-container button'):
        try:
            if b.is_visible():
                out.append((b.inner_text() or '').strip())
        except Exception:
            continue
    return [t for t in out if t]


def _click_first_text(page, needles, scope='mat-dialog-container'):
    """Bofya kitufe cha kwanza kinacholingana na mojawapo ya majina."""
    for needle in needles:
        for sel in (f"{scope} button:has-text('{needle}')",
                    f"{scope} button:text-is('{needle}')"):
            try:
                for el in page.query_selector_all(sel):
                    if el.is_visible() and el.is_enabled():
                        el.click()
                        return needle
            except Exception:
                continue
    return None


def _confirm_if_any(page, labels):
    """Bofya 'Ndiyo/Yes/OK' kama dialog ya uthibitisho imetokea."""
    for needle in labels:
        try:
            el = page.query_selector(
                f".cdk-overlay-container button:has-text('{needle}')")
            if el and el.is_visible() and el.is_enabled():
                el.click()
                return needle
        except Exception:
            continue
    return None


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
        _set_progress(run_id, msg=msg, log=list(log), done=False)

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
    page = None
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
            # Pitia dashboard ili app ikamilishe kikao na iweke mwaka wa PEPMIS.
            try:
                _goto_retry(page, DASHBOARD_URL)
                _wait_for_current_year(page, 20)
            except Exception:
                pass
            _goto_subtasks(page)

            cy = _current_year(page)
            if cy:
                import json as _json
                emit('currentYear: ' + _json.dumps(cy, default=str)[:300])
            else:
                emit('currentYear: HAIPO')

            # ESS inaweza kuwa na sub-tasks chini ya mwaka mwingine (FY vs CY);
            # pima miaka iliyohifadhiwa na uchague unao na safu.
            cands = _candidate_years(page)
            if cy and cy.get('id'):
                cands.sort(key=lambda c: 0 if c['id'] == cy['id'] else 1)
            chosen = cy
            for cand in cands:
                try:
                    _set_current_year(page, cand)
                    _goto_subtasks(page)
                    n = len(_rows(page))
                except Exception as exc:
                    emit(f'mwaka {cand.get("id")}: kosa {exc}')
                    continue
                emit(f'mwaka {cand.get("id")} '
                     f'({cand.get("yearTypeCode") or cand.get("yearType") or "?"}): safu {n}')
                if n > 0:
                    chosen = cand
                    break

            threshold = SELECTORS['match_threshold']
            remaining = list(wanted)
            page_no = 0
            while remaining:
                page_no += 1
                page.wait_for_selector(SELECTORS['row_selector'], timeout=15000)
                row_els = _rows(page)
                visible = []
                for i, el in enumerate(row_els):
                    cell = el.query_selector(SELECTORS['subtask_cell_selector'])
                    if cell:
                        visible.append({'i': i, 'text': cell.inner_text(),
                                        'pct': _row_current_pct(el)})
                emit(f'Ukurasa {page_no}: safu {len(visible)}')
                if page_no == 1:
                    for v in visible:
                        one = re.sub(r'\s+', ' ', v['text']).strip()[:90]
                        emit(f'   • [{v["pct"]}] {one}')
                    if not visible:
                        emit(f'   (jedwali tupu) URL: {page.url}')
                        emit('   ukurasa: ' + _visible_text(page, 400))

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
                    _fill_one(page, match['i'], text, pct, emit=emit)
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
        snippet = ''
        if page is not None:
            try:
                shot = f'/tmp/ess_fill_{run_id}.png'
                page.screenshot(path=shot, full_page=True)
                snippet = f' [screenshot: {shot}; URL: {page.url}]'
            except Exception:
                try:
                    snippet = f' [URL: {page.url}]'
                except Exception:
                    pass
        run.status = 'error'
        run.finished = tz.now()
        run.saved = saved
        run.skipped = skipped
        run.not_found = not_found
        run.log = '\n'.join(log + [f'ERROR: {exc}{snippet}'])
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


def _fill_one(page, row_index, text, pct, emit=None) -> None:
    """Fungua dialog na ujaze sub task moja (selectors zimehakikiwa)."""
    row_els = _rows(page)
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
    page.wait_for_timeout(300)

    if emit:
        emit('  vitufe vya dialog: ' + ', '.join(_dialog_button_texts(page)) or '(hakuna)')

    # 1) Bofya "Submit" (ESS inahitaji kuwasilisha, si Save pekee).
    pressed = _click_first_text(page, SELECTORS['submit_labels'])
    # 2) Kama hakuna Submit, angalia dialog ya kuthibitisha yenyewe.
    if not pressed:
        page.wait_for_timeout(600)
        pressed = _confirm_if_any(page, SELECTORS['confirm_labels'])
    # 3) Mwisho: Save (kama njia ya akiba).
    if not pressed:
        try:
            page.click(SELECTORS['save_button'])
            pressed = 'Save'
        except Exception:
            raise RuntimeError(
                'Sikuweza kubofya Submit wala Save kwenye dialog: '
                + (', '.join(_dialog_button_texts(page)) or '(hakuna vitufe)'))
    if emit:
        emit(f'  -> imebofya: {pressed}')

    # Dialog ya uthibitisho inaweza kutokea baada ya Submit.
    page.wait_for_timeout(900)
    conf = _confirm_if_any(page, SELECTORS['confirm_labels'])
    if conf and emit:
        emit(f'  -> uthibitisho: {conf}')

    page.wait_for_selector(SELECTORS['dialog_selector'], state='detached', timeout=25000)
    try:
        page.wait_for_load_state('networkidle', timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(800)


def subtask_snapshot(task) -> list[dict]:
    """Maelezo ya UI (asilimia, target, actual) kwa template."""
    out = []
    for st in task.subtasks.all().prefetch_related('entries'):
        pct, src = pct_auto_for(st)
        recorded, _ = pct_for(st)
        out.append({
            'st': st,
            'target': target_display(st),
            'actual': actual_display(st),
            'expected': expected_display(st),
            'pct': pct,
            'pct_str': '' if pct is None else f'{pct:.0f}%',
            'recorded_pct': recorded,
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