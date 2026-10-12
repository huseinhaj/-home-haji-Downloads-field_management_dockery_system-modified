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
from datetime import date
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


def _open_ess(page) -> None:
    """Fungua ESS kwa imara: jaribu signin/root/dashboard kwa 'commit' kwanza.

    'commit' hurudi mara tu server inapojibu (haisubiri DOM), hivyo
    kuepuka timeouts kwenye kurasa nzito.
    """
    last = None
    for url in (SIGNIN_URL, BASE_URL, DASHBOARD_URL):
        for wait in ('commit', 'domcontentloaded'):
            try:
                page.goto(url, wait_until=wait, timeout=30000)
                return
            except Exception as exc:  # noqa: BLE001
                last = exc
                page.wait_for_timeout(2000)
    if last is not None:
        raise last


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

    # Subiri fomu ya login (Angular inaichelewa kuionesha); reload kama lazima.
    login_js = ("() => [\"input[formcontrolname='email']\","
                "\"input[name='email']\", \"input[type='email']\","
                "\"input[formcontrolname='username']\", \"input[name='username']\","
                "\"input[id='username']\", \"input[id='email']\","
                "\"input[type='password']\"].some(sel =>"
                " [...document.querySelectorAll(sel)].some(e => {"
                " const r = e.getBoundingClientRect();"
                " return r.width > 50 && r.height > 5; }))")
    found = False
    for attempt in range(3):
        try:
            page.wait_for_function(login_js, timeout=25000)
            found = True
            break
        except Exception:
            page.wait_for_timeout(2000)
            try:
                if page.evaluate("() => !!localStorage.getItem('token')"):
                    return True
            except Exception:
                pass
            try:
                page.reload(wait_until='commit')
            except Exception:
                try:
                    _goto_retry(page, page.url)
                except Exception:
                    pass
    if not found:
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
    """Bofya uthibitisho: SweetAlert2 au dialog ya Material (si ile ya progress)."""
    try:
        el = page.query_selector('.swal2-confirm')
        if el and el.is_visible():
            el.click()
            return 'swal2'
    except Exception:
        pass
    try:
        hit = page.evaluate(
            """(labels) => {
              const prog = [...document.querySelectorAll("mat-dialog-container")]
                 .find(d => d.querySelector("input[formcontrolname='percentageRank']"));
              const btns = [...document.querySelectorAll("button")].filter(b => {
                 if (!b.offsetParent || b.disabled) return false;
                 if (prog && prog.contains(b)) return false;
                 const t = (b.innerText || '').trim().toUpperCase();
                 return labels.includes(t);
              });
              if (btns.length) { btns[0].click(); return btns[0].innerText.trim(); }
              return null;
            }""",
            [l.upper() for l in labels])
        return hit
    except Exception:
        return None


def _progress_dialog_open(page) -> bool:
    try:
        return page.query_selector(
            "mat-dialog-container input[formcontrolname='percentageRank']") is not None
    except Exception:
        return False


def _close_progress_dialog(page) -> None:
    """Funga dialog ya progress (baada ya kosa) ili kuendelea na sub-task nyingine."""
    try:
        el = page.query_selector('.swal2-confirm')
        if el and el.is_visible():
            el.click()
            page.wait_for_timeout(400)
    except Exception:
        pass
    if not _progress_dialog_open(page):
        return
    for sel in ("mat-dialog-container button[mat-dialog-close]",
                "mat-dialog-container button:has-text('close')",
                "mat-dialog-container button:has-text('Cancel')",
                "mat-dialog-container button:has-text('Funga')"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(500)
                if not _progress_dialog_open(page):
                    return
        except Exception:
            continue
    try:
        page.keyboard.press('Escape')
        page.wait_for_timeout(500)
    except Exception:
        pass


def _swal_text(page):
    try:
        el = page.query_selector('.swal2-html-container, .swal2-title')
        if el:
            return re.sub(r'\s+', ' ', el.inner_text()).strip()
    except Exception:
        pass
    return ''


def _dialog_diagnostics(page):
    """Maelezo ya dialog iliyokwama: vitufe, validation errors, swal, maandishi."""
    parts = []
    try:
        btns = _dialog_button_texts(page)
        if btns:
            parts.append('vitufe: ' + ', '.join(btns))
    except Exception:
        pass
    try:
        errs = page.evaluate(
            """() => [...document.querySelectorAll(
                 'mat-error, .mat-mdc-form-field-error')]
                 .map(e => (e.innerText || '').trim()).filter(Boolean)""")
        if errs:
            parts.append('makosa: ' + ' | '.join(dict.fromkeys(errs)))
    except Exception:
        pass
    try:
        swal = page.query_selector('.swal2-html-container, .swal2-title')
        if swal:
            parts.append('swal: ' + re.sub(r'\s+', ' ', swal.inner_text()).strip()[:200])
    except Exception:
        pass
    try:
        dtxt = page.evaluate(
            """() => { const d = document.querySelector('mat-dialog-container');
                 return d ? (d.innerText||'').replace(/\\s+/g,' ').trim().slice(0,300) : ''; }""")
        if dtxt:
            parts.append('dialog: ' + dtxt)
    except Exception:
        pass
    return ' ; '.join(parts) or '(hakuna maelezo)'


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

    saved = skipped = not_found = failed = 0
    page = None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
            ctx = browser.new_context(ignore_https_errors=True)
            page = ctx.new_page()
            page.set_default_timeout(45000)

            _open_ess(page)
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
                    if cur is not None and float(pct) <= float(cur) + 0.5:
                        skipped += 1
                        emit(f'= ESS tayari {float(cur):.0f}% (>= {pct:.2f}%): {text[:50]}')
                        continue
                    emit(f'-> {text[:50]}  (match {score:.2f}) => {pct:.2f}%')
                    try:
                        _fill_one(page, match['i'], text, pct, emit=emit)
                        saved += 1
                        _set_progress(run_id, saved=saved)
                    except Exception as exc:
                        if 'pending progress' in str(exc).lower():
                            skipped += 1
                            emit(f'  = ESS ina pending progress (imeachwa): {text[:40]}')
                        else:
                            failed += 1
                            emit(f'  !! imeshindikana ({pct:.2f}%): {exc}')
                        _close_progress_dialog(page)
                        _set_progress(run_id, saved=saved, skipped=skipped,
                                      not_found=failed)
                        continue

                nxt = page.query_selector(SELECTORS['paginator_next_selector'])
                if not nxt or nxt.get_attribute('disabled') is not None or nxt.is_disabled():
                    break
                nxt.click()
                page.wait_for_timeout(700)

            not_found = len(remaining) + failed
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
        run.not_found = not_found + failed
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

    # Dialog ya uthibitisho / onyo (SweetAlert au Material) inaweza kutokea.
    swal_seen = []
    for _ in range(6):
        page.wait_for_timeout(800)
        txt = _swal_text(page)
        if txt and txt not in swal_seen:
            swal_seen.append(txt)
            if emit:
                emit('  !! ESS: ' + txt[:200])
        if not _progress_dialog_open(page):
            break
        conf = _confirm_if_any(page, SELECTORS['confirm_labels'])
        if conf and emit:
            emit(f'  -> uthibitisho: {conf}')

    try:
        page.wait_for_selector(SELECTORS['dialog_selector'], state='detached',
                               timeout=8000)
    except Exception:
        diag = _dialog_diagnostics(page)
        if emit:
            emit('  !! dialog haikufungwa: ' + diag)
        raise RuntimeError('Dialog ya progress haikufungwa baada ya '
                           + pressed + '. ' + diag)
    try:
        page.wait_for_load_state('networkidle', timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(800)


# ── Sawazisha majina na ESS (official) ───────────────────────────────
PEPMIS_GQL = 'https://gateway.ess.utumishi.go.tz/ess-pepmis/graphql'

_GQL_EMPLOYEE_TASKS = (
    'query getEmployeeTasks($financialYear: Long, $checkNumber: Long, '
    '$calendarYear: Long) {'
    ' getEmployeeTasks(financialYear: $financialYear, '
    'checkNumber: $checkNumber, calendarYear: $calendarYear) {'
    ' id taskDescription subTask { id subTaskDescription } } }')

_GQL_SUBACTIVITY = (
    'query getEmployeeSubActivityYearId($checkNumber: Long, $yearId: Long) {'
    ' getEmployeeSubActivityYearId(checkNumber: $checkNumber, yearId: $yearId) {'
    ' activityDescription subActivityDescription } }')


def _name_key(s: str) -> str:
    """Ufunguo wa kulinganisha: bila namba, ili 384 == 432."""
    return re.sub(r'[0-9]+', ' ', _normalize(s)).strip()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _name_key(a), _name_key(b)).ratio()


def _match_name(target, candidates, threshold=0.75):
    best, best_sc, second = None, 0.0, 0.0
    for c in candidates:
        sc = _similar(target, c)
        if sc > best_sc:
            second = best_sc
            best, best_sc = c, sc
        elif sc > second:
            second = sc
    if best_sc < threshold:
        return None, best_sc
    if best_sc < 1.0 and best_sc - second < 0.03:
        return None, best_sc
    return best, best_sc


def _ess_fetch_json(page, auth, query, variables, emit):
    import json
    if not auth:
        emit('Hakuna auth header ya ESS — naruka GraphQL.')
        return None
    try:
        resp = page.request.post(
            PEPMIS_GQL,
            headers={
                'Authorization': auth,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'apollographql-client-name': 'ess-web',
                'apollographql-client-version': '1.0.0',
            },
            data=json.dumps({'query': query, 'variables': variables}),
            timeout=60000)
    except Exception as exc:
        emit(f'GraphQL haikufikiwa: {exc}')
        return None
    try:
        body = resp.text()
    except Exception:
        body = ''
    emit(f'GraphQL {resp.status} {body[:220]}')
    if resp.status >= 400:
        return None
    try:
        return json.loads(body)
    except Exception:
        return None


def _ess_names_from_payload(payload):
    """-> [(taskDescription, [subTaskDescription, ...])] au None."""
    if not isinstance(payload, dict):
        return None
    data = payload.get('data') or {}

    def _as_list(node):
        if isinstance(node, list):
            return node
        if isinstance(node, dict):
            if isinstance(node.get('dataList'), list):
                return node['dataList']
            return [node]
        return []

    node = data.get('getEmployeeTasks')
    items = _as_list(node)
    if items:
        out = []
        for it in items:
            subs = [s.get('subTaskDescription')
                    for s in (it.get('subTask') or [])
                    if s.get('subTaskDescription')]
            out.append((it.get('taskDescription') or '', subs))
        return out

    node = data.get('getEmployeeSubActivityYearId')
    items = _as_list(node)
    if items:
        groups, order = {}, []
        for it in items:
            t = it.get('activityDescription') or ''
            s = it.get('subActivityDescription')
            if t not in groups:
                groups[t] = []
                order.append(t)
            if s:
                groups[t].append(s)
        return [(t, groups[t]) for t in order]
    return None


def _ess_tree_from_payload(payload):
    """-> [{'task_id','task_name','start','end','subs':[{'sub_id','sub_name'}]}].

    Hutumika kuvuta (import) task/sub-task kutoka ESS kwenda local."""
    if not isinstance(payload, dict):
        return None
    data = payload.get('data') or {}

    def _as_list(node):
        if isinstance(node, list):
            return node
        if isinstance(node, dict):
            if isinstance(node.get('dataList'), list):
                return node['dataList']
            return [node]
        return []

    node = data.get('getEmployeeTasks')
    items = _as_list(node)
    if items:
        tree = []
        for it in items:
            subs = [{'sub_id': s.get('id'),
                     'sub_name': s.get('subTaskDescription'),
                     'start': s.get('startDate'),
                     'end': s.get('endDate')}
                    for s in (it.get('subTask') or [])
                    if s.get('subTaskDescription')]
            tree.append({'task_id': it.get('id'),
                         'task_name': it.get('taskDescription') or '',
                         'start': it.get('startDate'), 'end': it.get('endDate'),
                         'subs': subs})
        if tree:
            return tree

    node = data.get('getEmployeeSubActivityYearId')
    items = _as_list(node)
    if items:
        groups, order = {}, []
        for it in items:
            t = it.get('activityDescription') or ''
            s = it.get('subActivityDescription')
            if t not in groups:
                groups[t] = []
                order.append(t)
            if s:
                groups[t].append({'sub_id': None, 'sub_name': s,
                                  'start': None, 'end': None})
        return [{'task_id': None, 'task_name': t, 'start': None, 'end': None,
                 'subs': groups[t]} for t in order]
    return None


def _parse_named(text, prefixes):
    for p in prefixes:
        m = re.search(p + r'\s+([\w\u00c0-\u024f-]+)', text or '', re.I)
        if m:
            return m.group(1)
    return ''


def _ess_date(value, year, month, day):
    if isinstance(value, str) and value.strip():
        m = re.match(r'(\d{4})-(\d{2})-(\d{2})', value.strip())
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    return date(year, month, day)


def _norm_somo(text):
    return _parse_named(text, [r'somo\s+la', r'somo\s+ya']) or ''


def _norm_kidato(text):
    return _parse_named(text, [r'kidato\s+cha', r'kidato\s+ya']) or ''


def _ess_names_from_ui(page, emit):
    """Fallback: soma majina ya sub-task moja kwa moja kutoka jedwali."""
    try:
        _goto_subtasks(page)
    except Exception as exc:
        emit(f'Ukurasa wa sub-tasks haupatikani: {exc}')
        return []

    def _wait_rows(timeout_s=20):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if _rows(page):
                return True
            page.wait_for_timeout(700)
        return False

    if not _wait_rows():
        # Labda mwaka wa PEPMIS haujasetiwa kwenye ukurasa huu — pima miaka.
        cy = _current_year(page)
        cands = _candidate_years(page)
        if cy and cy.get('id'):
            cands.sort(key=lambda c: 0 if c['id'] == cy['id'] else 1)
        for cand in cands:
            try:
                _set_current_year(page, cand)
                _goto_subtasks(page)
                if _wait_rows():
                    break
            except Exception:
                continue

    names, seen = [], set()
    while True:
        try:
            page.wait_for_selector(SELECTORS['row_selector'], timeout=15000)
        except Exception:
            break
        for el in _rows(page):
            cell = el.query_selector(SELECTORS['subtask_cell_selector'])
            if not cell:
                continue
            t = re.sub(r'\s+', ' ', cell.inner_text()).strip()
            if t and t not in seen:
                seen.add(t)
                names.append(t)
        nxt = page.query_selector(SELECTORS['paginator_next_selector'])
        if not nxt or nxt.get_attribute('disabled') is not None or nxt.is_disabled():
            break
        nxt.click()
        page.wait_for_timeout(700)
    if not names:
        emit(f'Jedwali tupu. URL: {page.url}')
    emit(f'Kutoka jedwali: majina {len(names)} ya sub-task (bila task).')
    return [{'task_id': None, 'task_name': '', 'start': None, 'end': None,
             'subs': [{'sub_id': None, 'sub_name': n, 'start': None, 'end': None}]}
            for n in names]


def _pull_from_ess(profile, tree, year_num, emit):
    """Vuta task/sub-task kutoka ESS: badilisha majina na uunde zisizopo local."""
    from .models import Task

    saved = skipped = not_found = total = 0
    local_tasks = list(profile.tasks.all())
    ess_pool = [s['sub_name'] for t in tree for s in t['subs'] if s['sub_name']]

    for et in tree:
        tname = et['task_name']
        best = None
        for task in local_tasks:
            if not tname:
                continue
            sc = _similar(task.name, tname)
            if sc >= 0.7 and (best is None or sc > best[0]):
                best = (sc, task)

        if best is None:
            sub_first = et['subs'][0]['sub_name'] if et['subs'] else ''
            task = Task.objects.create(
                profile=profile, name=tname or 'Task',
                somo=_norm_somo(tname) or _norm_somo(sub_first),
                kidato=_norm_kidato(tname) or _norm_kidato(sub_first),
                start=_ess_date(et.get('start'), year_num, 1, 1),
                end=_ess_date(et.get('end'), year_num, 12, 31))
            local_tasks.append(task)
            saved += 1
            emit(f'+ Task mpya local: {task.name[:55]}')
            pos = 0
            for es in et['subs']:
                if not es['sub_name']:
                    continue
                pos += 1
                SubTask.objects.create(task=task, position=pos,
                                       description=es['sub_name'],
                                       mode='manual', target=0)
                saved += 1
                total += 1
                emit(f'  + Sub-task: {es["sub_name"][:55]}')
            continue

        task = best[1]
        if tname and _normalize(task.name) != _normalize(tname):
            sim = SequenceMatcher(
                None, _normalize(task.name), _normalize(tname)).ratio()
            if sim < 0.9:
                task.name = tname
                task.save(update_fields=['name'])
                saved += 1
                emit(f'Task: -> "{tname[:50]}"')

        local_subs = list(task.subtasks.all())
        next_pos = max([s.position for s in local_subs], default=0)
        for es in et['subs']:
            name = es['sub_name']
            if not name:
                continue
            total += 1
            m, _sc = _match_name(name, [s.description for s in local_subs])
            if m:
                st = next((s for s in local_subs if s.description == m), None)
            else:
                st = None
            if st is not None:
                if _normalize(st.description) == _normalize(name):
                    skipped += 1
                    emit(f'= sawa: {st.description[:55]}')
                    continue
                sim = SequenceMatcher(
                    None, _normalize(st.description), _normalize(name)).ratio()
                if sim >= 0.9:
                    skipped += 1
                    emit(f'= imeachwa (idadi/similar) — tunza la local: '
                         f'{st.description[:45]}')
                    continue
                emit(f'-> "{st.description[:38]}" => "{name[:38]}"')
                st.description = name
                st.save(update_fields=['description'])
                saved += 1
                continue
            next_pos += 1
            new_st = SubTask.objects.create(
                task=task, position=next_pos, description=name,
                mode='manual', target=0)
            local_subs.append(new_st)
            saved += 1
            total += 1
            emit(f'  + Sub-task mpya: {name[:55]}')

    for task in local_tasks:
        for st in task.subtasks.all():
            if not _match_name(st.description, ess_pool)[0]:
                not_found += 1
                emit(f'# haipo ESS (local pekee): {st.description[:50]}')

    return saved, skipped, not_found, total


def run_sync(profile_id: int, run_id: int) -> dict:
    """Chukua majina ya task/sub-task kutoka ESS na usawazishe local."""
    from .models import TeacherProfile

    profile = TeacherProfile.objects.select_related('user').get(pk=profile_id)
    run = EssFillRun.objects.get(pk=run_id)
    log = []

    def emit(msg):
        log.append(msg)
        _set_progress(run_id, msg=msg, log=list(log), done=False)
        try:
            run.log = '\n'.join(log)
            run.save(update_fields=['log'])
        except Exception:
            pass

    emit('Sync imeanza — naingia ESS...')

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        run.status = 'error'
        run.finished = tz.now()
        run.log = 'Playwright haiko kwenye server.'
        run.save()
        return {'status': 'error', 'msg': str(exc)}

    page = None
    saved = skipped = not_found = total = 0
    tree = None
    year_num = tz.localdate().year
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
            ctx = browser.new_context(ignore_https_errors=True)
            page = ctx.new_page()
            page.set_default_timeout(45000)

            cap = {'auth': None}

            def _on_req(req):
                try:
                    if ('graphql' in req.url and req.method == 'POST'
                            and not cap['auth']):
                        auth_h = (req.headers or {}).get('authorization')
                        if auth_h:
                            cap['auth'] = auth_h
                except Exception:
                    pass

            page.on('request', _on_req)

            _open_ess(page)
            _auto_login(page, profile.ess_username, profile.ess_password_plain)
            emit('Login kamili.')
            try:
                _goto_retry(page, DASHBOARD_URL)
                _wait_for_current_year(page, 20)
            except Exception:
                pass

            token = page.evaluate("() => localStorage.getItem('token')")
            emp = page.evaluate(
                "() => { const v = localStorage.getItem('currentEmployee');"
                " return v ? JSON.parse(v) : null; }")
            year = _current_year(page)
            ytitle = year.get('yearTitle') if isinstance(year, dict) else year
            emit(f'currentYear: {ytitle}')
            if str(ytitle).isdigit():
                year_num = int(ytitle)

            # Fungua ukurasa wa sub-tasks ili app yenyewe iite gateway —
            # kamata header halisi ya Authorization inayotumika.
            try:
                _goto_subtasks(page)
                page.wait_for_timeout(2500)
            except Exception as exc:
                emit(f'Ukurasa wa sub-tasks: {exc}')
            auth = cap['auth'] or (f'Bearer {token}' if token else None)
            if cap['auth']:
                emit('Auth header (app): ' + cap['auth'][:22] + '...')

            if auth and isinstance(emp, dict) and isinstance(year, dict):
                check = emp.get('checkNumber') or emp.get('check_number')
                ytype = year.get('yearTypeCode')
                fin = year.get('id') if ytype == 'FY' else None
                cal = year.get('id') if ytype != 'FY' else None
                emit(f'checkNumber={check} financialYear={fin} calendarYear={cal}')
                payload = _ess_fetch_json(
                    page, auth, _GQL_EMPLOYEE_TASKS,
                    {'financialYear': fin, 'checkNumber': check,
                     'calendarYear': cal}, emit)
                tree = _ess_tree_from_payload(payload)
                if not tree:
                    payload = _ess_fetch_json(
                        page, auth, _GQL_SUBACTIVITY,
                        {'checkNumber': check, 'yearId': year.get('id')}, emit)
                    tree = _ess_tree_from_payload(payload)
            else:
                emit('auth/currentEmployee/currentYear havipo — naruka GraphQL.')

            if not tree:
                emit('GraphQL haitoi data — najaribu kusoma jedwali.')
                tree = _ess_names_from_ui(page, emit)
            browser.close()

        if not tree:
            emit('Sikusoma task/sub-task yoyote kutoka ESS.')
            run.status = 'error'
            run.finished = tz.now()
            run.log = '\n'.join(log)
            run.save()
            return {'status': 'error', 'msg': 'Hakuna majina ya ESS.'}

        n_subs = sum(len(t['subs']) for t in tree)
        emit(f'ESS: tasks {len(tree)}, sub-tasks {n_subs}.')
        saved, skipped, not_found, total = _pull_from_ess(
            profile, tree, year_num, emit)
    except Exception as exc:  # noqa: BLE001
        snippet = ''
        if page is not None:
            try:
                shot = f'/tmp/ess_sync_{run_id}.png'
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
        _set_progress(run_id, done=True, status='error',
                      saved=saved, skipped=skipped, not_found=not_found)
        return {'status': 'error', 'msg': str(exc)}

    run.status = 'done'
    run.finished = tz.now()
    run.saved = saved
    run.skipped = skipped
    run.not_found = not_found
    run.required = total
    run.log = '\n'.join(log)
    run.save()
    _set_progress(run_id, done=True, status='done', saved=saved,
                  skipped=skipped, not_found=not_found)
    return {'status': 'done', 'saved': saved, 'skipped': skipped,
            'not_found': not_found}


_GQL_UPDATE_SUBTASK = (
    'mutation createSubTask($input: [EmployeeSubTaskDtoInput]) {'
    ' createSubTask(subTaskList: $input) {'
    ' code message swahiliMessage dataList { id subTaskDescription } } }')


def _ess_subtasks_from_payload(payload):
    """-> [{'task_id','task_name','sub_id','sub_name'}] au None.

    ESS hairudishi `id` kwenye response ya mutation, hivyo tunahitaji
    kitambulisho cha task na sub-task ili kuweza kubadilisha jina."""
    if not isinstance(payload, dict):
        return None
    data = payload.get('data') or {}
    node = data.get('getEmployeeTasks')
    if isinstance(node, dict) and isinstance(node.get('dataList'), list):
        items = node['dataList']
    elif isinstance(node, dict):
        items = [node]
    elif isinstance(node, list):
        items = node
    else:
        return None
    out = []
    for it in items:
        tid = it.get('id')
        tname = it.get('taskDescription') or ''
        for s in (it.get('subTask') or []):
            name = s.get('subTaskDescription')
            if name:
                out.append({'task_id': tid, 'task_name': tname,
                            'sub_id': s.get('id'), 'sub_name': name})
    return out or None


def _push_local_names(local_tasks, ess_subs, update, emit):
    """Tuma majina ya local kwenda ESS (badilisha yale yanayotofautiana).

    `local_tasks` ni orodha tayari ya dict (bila ORM) ili kuepuka ORM
    ndani ya sync_playwright (Django hukataa ORM kwenye async context).
    """
    task_names = list(dict.fromkeys(e['task_name'] for e in ess_subs if e['task_name']))
    pushed = skipped = not_found = total = 0
    used = set()

    for task in local_tasks:
        best_name, best_sc = None, 0.0
        for tname in task_names:
            sc = _similar(task['name'], tname)
            if sc > best_sc:
                best_name, best_sc = tname, sc
        pool = [e for e in ess_subs if e['task_name'] == best_name] if best_sc >= 0.7 else []

        for st in task['subs']:
            total += 1
            desc = st['desc']
            match = None
            if pool:
                m, _ = _match_name(desc, [e['sub_name'] for e in pool])
                if m:
                    match = next(e for e in pool if e['sub_name'] == m)
            if match is None:
                m, _ = _match_name(desc, [e['sub_name'] for e in ess_subs])
                if m:
                    match = next(e for e in ess_subs if e['sub_name'] == m)
            if match is None or match['sub_id'] is None:
                not_found += 1
                emit(f'# haipo ESS: {desc[:55]}')
                continue
            key = (match['task_id'], match['sub_id'])
            if key in used:
                not_found += 1
                emit(f'# imetumika kwa lingine: {desc[:50]}')
                continue
            if _normalize(desc) == _normalize(match['sub_name']):
                skipped += 1
                emit(f'= ESS tayari sawa: {desc[:55]}')
                continue
            ok, info = update(desc, match)
            if ok:
                used.add(key)
                pushed += 1
                emit(f'-> ESS imesahihishwa: "{match["sub_name"][:40]}" '
                     f'=> "{desc[:40]}"')
            else:
                not_found += 1
                emit(f'  !! imeshindikana: {desc[:40]} — {info}')
    return pushed, skipped, not_found, total


def run_push(profile_id: int, run_id: int) -> dict:
    """Badilisha majina ya sub-task kwenye ESS official kutoka yaliyo local."""
    from .models import TeacherProfile

    profile = TeacherProfile.objects.select_related('user').get(pk=profile_id)
    run = EssFillRun.objects.get(pk=run_id)
    log = []

    def emit(msg):
        log.append(msg)
        _set_progress(run_id, msg=msg, log=list(log), done=False)
        try:
            run.log = '\n'.join(log)
            run.save(update_fields=['log'])
        except Exception:
            pass

    emit('Tuma majina kwenye ESS imeanza — naingia ESS...')

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        run.status = 'error'
        run.finished = tz.now()
        run.log = 'Playwright haiko kwenye server.'
        run.save()
        return {'status': 'error', 'msg': str(exc)}

    page = None
    saved = skipped = not_found = total = 0
    local_tasks = [
        {'name': t.name,
         'subs': [{'id': st.id, 'desc': st.description}
                  for st in t.subtasks.all()]}
        for t in profile.tasks.all()
    ]
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
            ctx = browser.new_context(ignore_https_errors=True)
            page = ctx.new_page()
            page.set_default_timeout(45000)

            cap = {'auth': None}

            def _on_req(req):
                try:
                    if ('graphql' in req.url and req.method == 'POST'
                            and not cap['auth']):
                        auth_h = (req.headers or {}).get('authorization')
                        if auth_h:
                            cap['auth'] = auth_h
                except Exception:
                    pass

            page.on('request', _on_req)

            _open_ess(page)
            _auto_login(page, profile.ess_username, profile.ess_password_plain)
            emit('Login kamili.')
            try:
                _goto_retry(page, DASHBOARD_URL)
                _wait_for_current_year(page, 20)
            except Exception:
                pass

            token = page.evaluate("() => localStorage.getItem('token')")
            emp = page.evaluate(
                "() => { const v = localStorage.getItem('currentEmployee');"
                " return v ? JSON.parse(v) : null; }")
            year = _current_year(page)
            ytitle = year.get('yearTitle') if isinstance(year, dict) else year
            emit(f'currentYear: {ytitle}')

            try:
                _goto_subtasks(page)
                page.wait_for_timeout(2500)
            except Exception as exc:
                emit(f'Ukurasa wa sub-tasks: {exc}')
            auth = cap['auth'] or (f'Bearer {token}' if token else None)
            if cap['auth']:
                emit('Auth header (app): ' + cap['auth'][:22] + '...')

            ess_subs = None
            if auth and isinstance(emp, dict) and isinstance(year, dict):
                check = emp.get('checkNumber') or emp.get('check_number')
                ytype = year.get('yearTypeCode')
                fin = year.get('id') if ytype == 'FY' else None
                cal = year.get('id') if ytype != 'FY' else None
                payload = _ess_fetch_json(
                    page, auth, _GQL_EMPLOYEE_TASKS,
                    {'financialYear': fin, 'checkNumber': check,
                     'calendarYear': cal}, emit)
                ess_subs = _ess_subtasks_from_payload(payload)
            else:
                emit('auth/currentEmployee/currentYear havipo — siwezi kutuma.')

            if not ess_subs:
                browser.close()
                raise RuntimeError('Sijapata id za sub-task za ESS (GraphQL).')

            emit(f'ESS: sub-tasks {len(ess_subs)}.')

            def update(desc, match):
                variables = {'input': [{
                    'id': match['sub_id'],
                    'subTaskDescription': desc,
                    'emerging': False,
                    'task': {'id': match['task_id']},
                }]}
                res = _ess_fetch_json(
                    page, auth, _GQL_UPDATE_SUBTASK, variables, emit)
                try:
                    node = res['data']['createSubTask']
                except Exception:
                    return False, 'jibu lisilojulikana'
                code = node.get('code')
                if str(code) == '9000':
                    return True, 'ok'
                return False, (node.get('swahiliMessage') or node.get('message')
                               or f'code {code}')

            saved, skipped, not_found, total = _push_local_names(
                local_tasks, ess_subs, update, emit)
            browser.close()
    except Exception as exc:  # noqa: BLE001
        snippet = ''
        if page is not None:
            try:
                shot = f'/tmp/ess_push_{run_id}.png'
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
        _set_progress(run_id, done=True, status='error',
                      saved=saved, skipped=skipped, not_found=not_found)
        return {'status': 'error', 'msg': str(exc)}

    run.status = 'done'
    run.finished = tz.now()
    run.saved = saved
    run.skipped = skipped
    run.not_found = not_found
    run.required = total
    run.log = '\n'.join(log)
    run.save()
    _set_progress(run_id, done=True, status='done', saved=saved,
                  skipped=skipped, not_found=not_found)
    return {'status': 'done', 'saved': saved, 'skipped': skipped,
            'not_found': not_found}


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