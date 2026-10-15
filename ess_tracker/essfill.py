"""Jaza ESS e-Utendaji kwa Playwright (auto-login kwa akaunti ya mwalimu).

Selectors zote zimethibitishwa dhidi ya DOM halisi ya ESS
(/pepmis/implementation/progress, Angular Material MDC). Kitu pekee
kilichoongezwa tofauti na CLI ya ess_utendaji ni login ya kiotomatiki:
haina waendeshaji wa browser wa ndani — inaendesha kwenye server (Celery),
hivyo inajaza username/password iliyohifadhiwa na kuendelea.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from difflib import SequenceMatcher

from django.core.cache import cache
from django.utils import timezone as tz

from .compute import (built_wanted, entry_from_values,
                      on_track_status, parse_count, pct_auto_for, pct_for,
                      plan_for, subtask_increment_pct, target_for)
from .models import EssFillRun, SubTask

BASE_URL = 'https://ess.utumishi.go.tz/'
SIGNIN_URL = 'https://ess.utumishi.go.tz/sessions/signin'
DASHBOARD_URL = 'https://ess.utumishi.go.tz/dashboard'
SUBTASKS_URL = 'https://ess.utumishi.go.tz/pepmis/implementation/progress'


def _parse_id_list(raw) -> set:
    """'12, 15; 18' -> {12, 15, 18}. Ni salama kwa tupu/None."""
    if not raw:
        return set()
    out = set()
    for part in re.split(r'[,\s;]+', str(raw)):
        if part.isdigit():
            out.add(int(part))
    return out


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
    'add_entry_labels': ['Add Sub Task Progress', 'Add Progress Details',
                         'Add Progress', 'Add Implementation'],
    'view_impl_labels': ['View Implementation', 'View Progress', 'View Impl'],
    'submit_entry_labels': ['Submit', 'SUBMIT', 'Submit Progress', 'Wasilisha',
                            'Tuma', 'Send'],
    'delete_entry_labels': ['Delete', 'Remove', 'Futa', 'Ondoa'],
    'delete_confirm_labels': ['Yes', 'YES', 'Delete', 'Confirm', 'Ok', 'OK',
                              'Continue', 'Ndiyo', 'Thibitisha', 'Futa',
                              'Proceed', 'Submit', 'SUBMIT'],
    'progress_row_selector': 'mat-dialog-container table tbody tr',
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


class PendingProgressError(RuntimeError):
    """ESS ina pending progress iliyowasilishwa/isiyoidhinishwa bado.

    Haiwezekani kuongeza progress mpya mpaka ile iliyopo iidhinishwe. Hii
    si kosa la kudumu — tunairuka na kuendelea na sub-task nyingine.
    """


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


def _page_loading(page) -> bool:
    """True kama jedwali bado linaonyesha spinner/'Loading...' inayoonekana."""
    try:
        for el in page.query_selector_all(
                'mat-progress-spinner, .mat-mdc-progress-spinner, '
                '.mdc-circular-progress, .mat-mdc-progress-bar, '
                '[class*=spinner i]'):
            try:
                if el.is_visible():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    try:
        return 'loading...' in _visible_text(page, 400).lower()
    except Exception:
        return False


def _table_settled(page, timeout_s=25):
    """Subiri jedwali litulie kisha rudi safu halisi (au [] kama 'No data').

    ESS ni Angular: baada ya kubadilisha mwaka ukurasa hupakia tena, hivyo
    huonekana safu ya mpito/kiunzi wakati 'Loading...' bado ipo. Hii husubiri
    hadi idadi ya safu itulie na spinner iishe ili tusichague mwaka kwa safu
    ya kiunzi (jambo lililotokea kwenye Run #35).
    """
    deadline = time.time() + timeout_s
    last_n = None
    stable = 0
    while time.time() < deadline:
        loading = _page_loading(page)
        rows = _rows(page)
        n = len(rows)
        if not loading and n == last_n:
            stable += 1
            if stable >= 2:
                return rows
        else:
            stable = 0
        last_n = n
        page.wait_for_timeout(400)
    return _rows(page)


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
    clean = {k: v for k, v in year_obj.items() if not k.startswith('_')}
    src = year_obj.get('_src') or 'currentYear'
    page.evaluate(
        "([obj, src]) => {"
        " localStorage.setItem('currentYear', JSON.stringify(obj));"
        " localStorage.setItem(src, JSON.stringify(obj)); }",
        [clean, src])


def _iter_year_like(value):
    """Toa dict zote zinazofanana na mwaka (zina id + yearTitle/yearTypeCode)."""
    found = []
    if isinstance(value, dict):
        if value.get('id') and (value.get('yearTitle')
                                or value.get('yearTypeCode')
                                or value.get('yearType')):
            found.append(value)
        for v in value.values():
            found.extend(_iter_year_like(v))
    elif isinstance(value, list):
        for v in value:
            found.extend(_iter_year_like(v))
    return found


def _storage_dump(page):
    """Maadili yote ya localStorage/sessionStorage: {key: value}."""
    try:
        return page.evaluate(
            "() => { const res = {};"
            " for (const s of [localStorage, sessionStorage]) {"
            "  for (let i = 0; i < s.length; i++) {"
            "   const k = s.key(i); res[k] = s.getItem(k); } }"
            " return res; }") or {}
    except Exception:
        return {}


def _candidate_years(page):
    """Miaka yote inayopatikana kwenye kikao (FY/CY) -- moja huenda na sub-tasks."""
    out, seen = [], set()
    for key, raw in _storage_dump(page).items():
        try:
            val = json.loads(raw)
        except Exception:
            continue
        for obj in _iter_year_like(val):
            yid = obj.get('id')
            if yid and yid not in seen:
                seen.add(yid)
                obj = dict(obj)
                obj['_src'] = key
                out.append(obj)
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


def _find_row_index(page, text):
    """Tafuta index ya safu ya jedwali kwa maandishi (baada ya jedwali kubadilika)."""
    cands = []
    for i, el in enumerate(_rows(page)):
        cell = el.query_selector(SELECTORS['subtask_cell_selector'])
        if cell:
            cands.append({'i': i, 'text': cell.inner_text()})
    match, _ = _best_row_match(text, cands, SELECTORS['match_threshold'])
    return match['i'] if match else None


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


def _menu_item_click(page, labels):
    """Bofya kipengele cha menu (mat-mdc-menu-panel) kwa maandishi."""
    for label in labels:
        for sel in (f".mat-mdc-menu-panel button.mat-mdc-menu-item:has-text('{label}')",
                    f".cdk-overlay-container button.mat-mdc-menu-item:has-text('{label}')"):
            try:
                for el in page.query_selector_all(sel):
                    if el.is_visible():
                        el.click()
                        return label
            except Exception:
                continue
    return None


def _open_view_implementation(page, row_index, emit=None) -> bool:
    """Fungua 'View Implementation' ya safu ya sub-task (kuona entries)."""
    row_els = _rows(page)
    if row_index >= len(row_els):
        return False
    trigger = row_els[row_index].query_selector(
        SELECTORS['row_action_button_selector'])
    if not trigger:
        return False
    try:
        trigger.click()
        page.wait_for_timeout(700)
    except Exception:
        return False
    label = _menu_item_click(page, SELECTORS['view_impl_labels'])
    if not label:
        try:
            page.keyboard.press('Escape')
        except Exception:
            pass
        return False
    page.wait_for_timeout(1200)
    if emit:
        emit(f'  -> View Implementation: {label}')
    return True


def _close_panel(page) -> None:
    """Funga panel/dialog ya Sub Task Progress (isiyo ya kuongeza)."""
    try:
        el = page.query_selector('.swal2-confirm')
        if el and el.is_visible():
            el.click()
            page.wait_for_timeout(300)
    except Exception:
        pass
    for sel in ("mat-dialog-container button[mat-dialog-close]",
                "mat-dialog-container button:has-text('close')",
                "mat-dialog-container button:has-text('Close')",
                "mat-dialog-container button:has-text('Funga')",
                "mat-dialog-container button:has-text('Cancel')"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(500)
                if not page.query_selector('mat-dialog-container'):
                    return
        except Exception:
            continue
    try:
        page.keyboard.press('Escape')
        page.wait_for_timeout(400)
    except Exception:
        pass


def _entries_table(page):
    """Jedwali la entries lenye 'Implementation Description'/'Status'."""
    root = page.query_selector(SELECTORS['dialog_selector']) or page
    for tbl in root.query_selector_all('table'):
        try:
            head = tbl.query_selector('thead')
            htxt = head.inner_text() if head else tbl.inner_text()
        except Exception:
            htxt = ''
        if ('Implementation' in htxt or 'Status' in htxt
                or 'Percentage' in htxt):
            return tbl
    return None


def _entries_rows(page):
    """Safu za jedwali la entries (bila safu za Performance Indicators)."""
    tbl = _entries_table(page)
    return tbl.query_selector_all('tbody tr') if tbl else []


def _read_progress_entries(page):
    """Soma entries za Sub Task Progress: [{desc, date, pct, status}]."""
    out = []
    for r in _entries_rows(page):
        try:
            cells = r.query_selector_all('td')
            txt = [re.sub(r'\s+', ' ', c.inner_text()).strip() for c in cells]
        except Exception:
            continue
        if len(txt) >= 2:
            out.append({
                'desc': txt[1] if len(txt) > 1 else '',
                'date': txt[2] if len(txt) > 2 else '',
                'pct': txt[3] if len(txt) > 3 else '',
                'status': txt[4] if len(txt) > 4 else '',
            })
    return out


def _panel_diag(page, row=None) -> str:
    """Maelezo ya panel ya Sub Task Progress (kwa utambuzi wa Actions/Submit)."""
    parts = []
    try:
        parts.append('rows=%d' % len(_entries_rows(page)))
    except Exception:
        pass
    try:
        btns = [re.sub(r'\s+', ' ', b.inner_text()).strip()
                for b in page.query_selector_all('mat-dialog-container button')]
        btns = [b for b in btns if b][:12]
        if btns:
            parts.append('buttons: ' + ', '.join(btns))
    except Exception:
        pass
    if row is not None:
        try:
            cells = row.query_selector_all('td')
            if cells:
                parts.append('last-cell: ' + re.sub(
                    r'\s+', ' ', cells[-1].inner_html())[:400])
        except Exception:
            pass
    return ' | '.join(parts)


def _menu_items_diag(page) -> str:
    """Majina ya vipengele vya menu ya Actions iliyofunguliwa (kwa utambuzi)."""
    try:
        return ', '.join(page.evaluate(
            """() => [...document.querySelectorAll(
                 '.mat-mdc-menu-panel button, .cdk-overlay-container .mat-mdc-menu-item')]
                 .map(b => (b.innerText || '').trim()).filter(Boolean).slice(0, 12)"""))
    except Exception:
        return ''


def _open_row_actions(page, row) -> bool:
    """Fungua menu ya 'Actions' ya safu ya entries."""
    for sel in ("td:last-child .mat-mdc-menu-trigger",
                "td.mat-column-manage .mat-mdc-menu-trigger",
                "td:last-child button",
                "button.mat-mdc-menu-trigger"):
        try:
            btn = row.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(700)
                return True
        except Exception:
            continue
    return False


def _not_submitted_row(page, text):
    """Safu ya entry ya 'NOT SUBMITTED' (au inayolingana na maandishi yetu)."""
    rows = _entries_rows(page)
    for r in rows:
        try:
            if 'not submitted' in _normalize(r.inner_text()):
                return r
        except Exception:
            continue
    key = _normalize(text)[:40]
    if key:
        for r in rows:
            try:
                if key in _normalize(r.inner_text()):
                    return r
            except Exception:
                continue
    return None


def _submit_latest_progress(page, text, emit=None) -> bool:
    """Wasilisha (Submit) entry kwenye jedwali la Sub Task Progress.

    Hurudi True ikifanikiwa; False vinginevyo (haisimamishi run).
    """
    try:
        page.wait_for_selector(SELECTORS['dialog_selector'], timeout=8000)
    except Exception:
        if emit:
            emit('  !! panel ya Sub Task Progress haipo (Submit imeachwa).')
        return False
    rows = _entries_rows(page)
    if not rows:
        if emit:
            emit('  !! hakuna entry kwenye panel. ' + _panel_diag(page))
        return False
    target = _not_submitted_row(page, text) or rows[0]
    if not _open_row_actions(page, target):
        if emit:
            emit('  !! kitufe cha Actions hakipatikani. ' + _panel_diag(page, target))
        return False
    label = _menu_item_click(page, SELECTORS['submit_entry_labels'])
    if not label:
        items = _menu_items_diag(page)
        if emit:
            emit('  !! hakuna kipengele cha Submit kwenye menu.'
                 + (f' | menu: {items}' if items else '')
                 + ' ' + _panel_diag(page, target))
        try:
            page.keyboard.press('Escape')
        except Exception:
            pass
        return False
    page.wait_for_timeout(1000)
    try:
        _confirm_if_any(page, SELECTORS['confirm_labels'])
    except Exception:
        pass
    if emit:
        emit(f'  -> imewasilishwa kwa idhini: {label}')
    return True


def _panel_is_entries(page) -> bool:
    """True kama dialog iliyo wazi ni panel ya 'Sub Task Progress' (na jedwali),
    SI fomu ya Add/Edit Progress."""
    try:
        if not page.query_selector(SELECTORS['dialog_selector']):
            return False
    except Exception:
        return False
    if _progress_dialog_open(page):
        return False
    return _entries_table(page) is not None


def _status_for_pct(pct):
    if pct >= 100:
        return SELECTORS['status_option_completed']
    if pct > 0:
        return SELECTORS['status_option_in_progress']
    return SELECTORS['status_option_not_started']


def _select_status(page, pct) -> None:
    status_opt = _status_for_pct(pct)
    status = page.wait_for_selector(SELECTORS['status_select_selector'], timeout=10000)
    status.click()
    page.wait_for_timeout(800)
    if not _click_text_option(page, status_opt, exact=True):
        raise RuntimeError(f'Sikuweza kuchagua status {status_opt}.')
    page.wait_for_timeout(500)


def _press_save_or_submit(page, emit=None):
    """Bofya Submit/Save kwenye fomu ya progress; subiri swal.

    Hurudi (kitufe, onyo_la_pending) -- onyo ni tupu kama hakuna.
    """
    pressed = _click_first_text(page, SELECTORS['submit_labels'])
    if not pressed:
        page.wait_for_timeout(600)
        pressed = _confirm_if_any(page, SELECTORS['confirm_labels'])
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
    swal_seen, pending = [], ''
    for _ in range(6):
        page.wait_for_timeout(800)
        txt = _swal_text(page)
        if txt and txt not in swal_seen:
            swal_seen.append(txt)
            if emit:
                emit('  !! ESS: ' + txt[:200])
            if 'pending progress' in txt.lower():
                pending = txt
                break
        if not _progress_dialog_open(page):
            break
        conf = _confirm_if_any(page, SELECTORS['confirm_labels'])
        if conf and emit:
            emit(f'  -> uthibitisho: {conf}')
    return pressed, pending


def _delete_not_submitted_entry(page, text, emit=None) -> bool:
    """Futa entry ya 'NOT SUBMITTED' (draft inayozuia entry mpya).

    ESS haina 'Edit' kwenye Actions -- ni 'Submit' na 'Delete' pekee.
    """
    row = _not_submitted_row(page, text)
    if row is None:
        return False
    if not _open_row_actions(page, row):
        return False
    label = _menu_item_click(page, SELECTORS['delete_entry_labels'])
    if not label:
        items = _menu_items_diag(page)
        if emit:
            emit('  !! hakuna kipengele cha Delete kwenye Actions'
                 + (f' | menu: {items}' if items else ''))
        try:
            page.keyboard.press('Escape')
        except Exception:
            pass
        return False
    if emit:
        emit(f'  -> menu: {label}')
    page.wait_for_timeout(800)
    try:
        conf = _confirm_if_any(page, SELECTORS['delete_confirm_labels'])
        if conf and emit:
            emit(f'  -> kuthibitisha kufuta: {conf}')
    except Exception:
        pass
    page.wait_for_timeout(1200)
    return _not_submitted_row(page, text) is None


def _submit_panel_or_view(page, row_index, text, emit=None) -> bool:
    """Hakikisha panel ya 'Sub Task Progress' ipo, kisha wasilisha entry.

    Fomu ya 'Add Sub Task Progress' (yenye percentageRank) huwa wazi baada ya
    onyo la ESS 'There is pending progress created or rolled back'. Hiyo SI
    panel ya entries -- ifunge kwanza, kisha fungua 'View Implementation'.
    """
    if not _panel_is_entries(page):
        _close_progress_dialog(page)
        _close_panel(page)
        ridx = row_index
        if ridx is None or ridx >= len(_rows(page)):
            ridx = _find_row_index(page, text)
        if ridx is None or not _open_view_implementation(page, ridx, emit):
            if emit:
                emit('  !! hatukuweza kufungua View Implementation '
                     '(Submit imeachwa).')
            return False
    if emit:
        for e in _read_progress_entries(page)[:8]:
            emit('   entry [%s] %s%% %s: %s'
                 % (e['status'] or '?', e['pct'] or '?', e['date'] or '?',
                    e['desc'][:60]))
    try:
        return _submit_latest_progress(page, text, emit)
    except Exception as exc:  # noqa: BLE001
        if emit:
            emit(f'  !! Submit imeshindikana: {exc}')
        return False
    finally:
        _close_panel(page)


def _replace_pending_entry(page, row_index, text, pct, note, emit=None) -> bool:
    """Badilisha draft ya 'NOT SUBMITTED' kwa entry yetu, kisha wasilisha.

    ESS hairuhusu entry mpya ikiwepo draft; kwa kuwa Actions haina Edit,
    tunafuta draft kisha kuongeza entry mpya (description/asilimia yetu).
    """
    ridx = row_index
    if ridx is None or ridx >= len(_rows(page)):
        ridx = _find_row_index(page, text)
    if not _panel_is_entries(page):
        if ridx is None or not _open_view_implementation(page, ridx, emit):
            if emit:
                emit('  !! View Implementation haikufungukana (kufuta kumeshindikana).')
            return False
    deleted = _delete_not_submitted_entry(page, text, emit)
    _close_panel(page)
    if not deleted:
        # Tushindwa kufuta -- wasilisha draft iliyopo angalau.
        return _submit_panel_or_view(page, ridx, text, emit)
    if emit:
        emit('  -> draft imefutwa; naongeza entry mpya.')
    try:
        again = _open_fill_save(page, ridx, text, pct, emit=emit, note=note)
    except Exception as exc:  # noqa: BLE001
        if emit:
            emit(f'  !! kuongeza entry baada ya kufuta imeshindikana: {exc}')
        return False
    if again and emit:
        emit('  !! bado kuna pending baada ya kufuta; naendelea kusubmit.')
    return _submit_panel_or_view(page, ridx, text, emit)


def _prior_actual_for_ess(page, row_index, st, emit=None):
    """Soma entries za nyuma za sub-task; rudi (idadi kubwa iliyokubaliwa, entries).

    Hufungua 'View Implementation', husoma jedwali la entries, kisha hufunga.
    """
    entries = []
    try:
        if _open_view_implementation(page, row_index, emit):
            entries = _read_progress_entries(page)
    except Exception as exc:  # noqa: BLE001
        if emit:
            emit(f'  (sikuweza kusoma entries za nyuma: {exc})')
    finally:
        _close_panel(page)
    prev = None
    for e in entries:
        if 'accepted' not in (e.get('status') or '').lower():
            continue
        n = parse_count(e.get('desc') or '', st.position)
        if n is not None and (prev is None or n > prev):
            prev = n
    if emit:
        shown = '; '.join(
            f'{e.get("status")}/{e.get("pct")}: {e.get("desc", "")[:35]}'
            for e in entries[:4])
        emit(f'  entries za nyuma ({len(entries)}): {shown}')
        emit(f'  prev_actual(nafasi {st.position}) = {prev}')
    return prev, entries


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


def _save_official_pcts(mapping) -> int:
    """Hifadhi asilimia HALISI za ESS kwa sub-task zilizolingana.

    `mapping`: {subtask_id: asilimia}. Hurudi idadi iliyohifadhiwa.
    """
    if not mapping:
        return 0
    now = tz.now()
    saved = 0
    for sid, val in mapping.items():
        try:
            f = float(val)
        except (TypeError, ValueError):
            continue
        updated = SubTask.objects.filter(pk=sid).update(
            official_pct=f, official_at=now)
        saved += updated
    return saved


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
    only_ids = _parse_id_list(getattr(run, 'only_subtasks', ''))
    if only_ids:
        available = {w[0].id for w in wanted}
        matched = only_ids & available
        missing = only_ids - available
        if matched:
            wanted = [w for w in wanted if w[0].id in matched]
            emit('Chaguo la mwalimu: sub-task %s pekee.'
                 % ','.join(str(i) for i in sorted(matched)))
        if missing:
            emit('Tahadhari: sub-task za chaguo hazipo tena (%s) — zimepuuzwa.'
                 % ','.join(str(i) for i in sorted(missing)))
        if not matched:
            emit('Tahadhari: hakuna sub-task ya chaguo iliyopo sasa — '
                 'tunajaza sub-task zote zinazohitaji.')
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
    official = {}
    page = None
    finalized = False
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
                emit('currentYear: ' + json.dumps(cy, default=str)[:300])
            else:
                emit('currentYear: HAIPO')
            try:
                ysel = page.evaluate(
                    "() => Array.from(document.querySelectorAll("
                    "'mat-select, button, [role=button]'))"
                    ".map(e => (e.innerText || '').trim())"
                    ".filter(t => /20\\d\\d/.test(t)).slice(0, 20)")
                if ysel:
                    emit('year-selectors: ' + ' | '.join(ysel)[:300])
            except Exception:
                pass

            # ESS inaweza kuwa na sub-tasks chini ya mwaka mwingine (FY vs CY);
            # pima miaka iliyohifadhiwa. Hujaribu mwaka unaotarajiwa (CY)
            # kwanza, kisha mingine hadi sub-task zipatikane (fallback).
            cands = _candidate_years(page)
            for c in cands:
                emit('mwaka-pendekezwa: id=%s type=%s title=%s src=%s'
                     % (c.get('id'),
                        c.get('yearTypeCode') or c.get('yearType'),
                        c.get('yearTitle'), c.get('_src')))
            if cy and cy.get('id'):
                cands.sort(key=lambda c: 0 if c['id'] == cy['id'] else 1)
                if not any(c.get('id') == cy['id'] for c in cands):
                    cands.insert(0, cy)

            threshold = SELECTORS['match_threshold']
            remaining = list(wanted)
            tried = set()

            def _process_year(cand):
                """Weka mwaka, subiri jedwali litulie, jaza sub-task zilizosalia."""
                nonlocal saved, skipped, failed
                yid = cand.get('id')
                if not yid or yid in tried:
                    return
                tried.add(yid)
                try:
                    _set_current_year(page, cand)
                    _goto_subtasks(page)
                    row_els = _table_settled(page)
                except Exception as exc:
                    emit(f'mwaka {yid}: kosa {exc}')
                    return
                emit(f'mwaka {yid} '
                     f'({cand.get("yearTypeCode") or cand.get("yearType") or "?"}): '
                     f'safu {len(row_els)}')
                page_no = 0
                while remaining:
                    page_no += 1
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
                    if not visible:
                        break

                    for entry in list(remaining):
                        st, text, note, pct, target = entry
                        match, score = _best_row_match(text, visible, threshold)
                        if not match:
                            continue
                        remaining.remove(entry)
                        cur = match['pct']
                        if cur is not None:
                            official[st.id] = float(cur)
                        # Jumla inayotakiwa (target) isomwe kutoka jina la ESS.
                        ess_target = parse_count(match.get('text') or '', st.position)
                        if ess_target and ess_target > 0:
                            target = float(ess_target)
                        emit(f'  target = {target:g} (kutoka ESS)')
                        # Soma entries za nyuma za ESS ili actual/asilimia ziwe sawa.
                        prev, _prior = _prior_actual_for_ess(
                            page, match['i'], st, emit)
                        note, pct = entry_from_values(st, target, pct, prev)
                        emit(f'  hesabu: prev={prev} => {pct:.2f}% (actual/target)')
                        if cur is not None and float(pct) <= float(cur) + 0.5:
                            skipped += 1
                            emit(f'= ESS tayari {float(cur):.0f}% (>= {pct:.2f}%): {text[:50]}')
                            continue
                        emit(f'-> {text[:50]}  (match {score:.2f}) => {pct:.2f}%')
                        emit(f'   desc: {note[:70]}')
                        try:
                            _fill_one(page, match['i'], text, pct, emit=emit, note=note)
                            saved += 1
                            _set_progress(run_id, saved=saved)
                        except Exception as exc:
                            if (isinstance(exc, PendingProgressError)
                                    or 'pending progress' in str(exc).lower()):
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
                    before = [v['text'] for v in visible]
                    nxt.click()
                    page.wait_for_timeout(700)
                    row_els = _rows(page)
                    after = []
                    for el in row_els:
                        c = el.query_selector(SELECTORS['subtask_cell_selector'])
                        if c:
                            after.append(c.inner_text())
                    # Kinga: usizunguke milele kama paginator haibadili ukurasa.
                    if page_no >= 50 or after == before:
                        break

            # Jaribu mwaka unaotarajiwa kwanza, kisha mingine hadi zipatikane.
            for cand in cands:
                if not remaining:
                    break
                _process_year(cand)

            not_found = len(remaining) + failed

            # Kamilisha run KABLA ya kufunga browser. `browser.close()` (na
            # Playwright stop kwenye `with`) zinaweza kuning'inia, na hapo
            # run ilibaki 'running' milele (Run #37). Kwa kuandika matokeo
            # kwanza, UI inaonyesha 'done' hata kama close inakwama.
            run.status = 'done'
            run.finished = tz.now()
            run.saved = saved
            run.skipped = skipped
            run.not_found = not_found
            run.log = '\n'.join(log)
            run.save()
            for _st, text, _note, _p, _t in remaining:
                emit(f'# haijapatikana: {text[:60]}')
            _set_progress(run_id, done=True, status='done', saved=saved,
                          skipped=skipped, not_found=not_found)
            finalized = True
            try:
                browser.close()
            except Exception:
                pass
        _save_official_pcts(official)
    except Exception as exc:  # noqa: BLE001
        if finalized:
            return {'status': 'done', 'saved': saved, 'skipped': skipped,
                    'not_found': not_found}
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

    return {'status': 'done', 'saved': saved, 'skipped': skipped,
            'not_found': not_found}


def _open_fill_save(page, row_index, text, pct, emit=None, note=None) -> str:
    """Fungua 'Add Sub Task Progress', jaza, na bofya Save/Submit.

    Hurudi onyo la ESS ('pending progress'...) au '' kama hakuna.
    """
    row_els = _rows(page)
    if row_index is None or row_index >= len(row_els):
        fresh = _find_row_index(page, text)
        if fresh is None:
            raise RuntimeError(
                'Mstari wa jedwali haupo tena (ulibadilika baada ya Save).')
        row_index = fresh
        row_els = _rows(page)
    row_el = row_els[row_index]
    row_el.query_selector(SELECTORS['row_action_button_selector']).click()
    page.wait_for_timeout(700)
    if not _menu_item_click(page, SELECTORS['add_entry_labels']):
        try:
            page.keyboard.press('Escape')
        except Exception:
            pass
        raise RuntimeError('Sikuweza kufungua "Add Sub Task Progress" kwenye Actions.')
    page.wait_for_selector(SELECTORS['dialog_selector'], timeout=15000)

    subtype = page.wait_for_selector(SELECTORS['subtype_select_selector'], timeout=10000)
    if not (subtype.inner_text() or '').strip():
        subtype.click()
        page.wait_for_timeout(800)
        if not _click_text_option(page, text, exact=False):
            raise RuntimeError('Sikuweza kuchagua Sub Task kwenye dialog.')
        page.wait_for_timeout(500)

    desc = page.wait_for_selector(SELECTORS['description_selector'], timeout=10000)
    desc.fill((note or text)[:500])

    _select_status(page, pct)

    inp = page.wait_for_selector(SELECTORS['percentage_input_selector'], timeout=10000)
    inp.fill(str(int(round(pct))))
    page.wait_for_timeout(300)

    if emit:
        emit('  vitufe vya dialog: ' + ', '.join(_dialog_button_texts(page)) or '(hakuna)')

    _pressed, pending = _press_save_or_submit(page, emit)
    return pending


def _fill_one(page, row_index, text, pct, emit=None, note=None) -> None:
    """Fungua dialog na ujaze sub task moja (selectors zimehakikiwa)."""
    pending = _open_fill_save(page, row_index, text, pct, emit, note)

    if pending:
        # ESS hairuhusu entry mpya ikiwepo draft 'NOT SUBMITTED'. Kwa kuwa
        # Actions haina Edit, futa draft kisha ongeza entry yetu na uwasilishe.
        _close_progress_dialog(page)
        if _replace_pending_entry(page, row_index, text, pct, note, emit):
            return
        raise PendingProgressError(pending)

    detached = False
    try:
        page.wait_for_selector(SELECTORS['dialog_selector'], state='detached',
                               timeout=8000)
        detached = True
    except Exception:
        # Kawaida dialog hugeuka kuwa panel 'Sub Task Progress' yenye orodha.
        if emit:
            emit('  (dialog bado wazi -- inaonyesha Sub Task Progress)')
    if detached:
        try:
            page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(800)

    # Entry mpya huanza 'NOT SUBMITTED'. Iwasilishe (Submit) ili iende kwa idhini.
    if not _submit_panel_or_view(page, row_index, text, emit) and emit:
        emit('  !! Submit ya entry haikupatikana (angalia Actions).')


# ── Sawazisha majina na ESS (official) ───────────────────────────────
PEPMIS_GQL = 'https://gateway.ess.utumishi.go.tz/ess-pepmis/graphql'

_GQL_EMPLOYEE_TASKS = (
    'query getEmployeeTasks($financialYear: Long, $checkNumber: Long, '
    '$calendarYear: Long) {'
    ' getEmployeeTasks(financialYear: $financialYear, '
    'checkNumber: $checkNumber, calendarYear: $calendarYear) {'
    ' id taskDescription subTask { id subTaskDescription } } }')

_GQL_EMPLOYEE_TASKS_DATES = (
    'query getEmployeeTasks($financialYear: Long, $checkNumber: Long, '
    '$calendarYear: Long) {'
    ' getEmployeeTasks(financialYear: $financialYear, '
    'checkNumber: $checkNumber, calendarYear: $calendarYear) {'
    ' id taskDescription startDate endDate'
    ' subTask { id subTaskDescription startDate endDate } } }')

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


def _ess_sdate(value):
    """Tarehe ya ESS (startDate/endDate) au None kama haipo/batili."""
    if isinstance(value, str) and value.strip():
        m = re.match(r'(\d{4})-(\d{2})-(\d{2})', value.strip())
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    return None


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
                                       mode='manual', target=0,
                                       start=_ess_sdate(es.get('start')),
                                       end=_ess_sdate(es.get('end')))
                saved += 1
                total += 1
                emit(f'  + Sub-task: {es["sub_name"][:55]}')
            continue

        task = best[1]
        somo_now = (_norm_somo(tname)
                    or (_norm_somo(et['subs'][0]['sub_name']) if et['subs'] else ''))
        kidato_now = (_norm_kidato(tname)
                      or (_norm_kidato(et['subs'][0]['sub_name']) if et['subs'] else ''))
        meta = False
        if somo_now and task.somo != somo_now:
            task.somo = somo_now
            meta = True
        if kidato_now and task.kidato != kidato_now:
            task.kidato = kidato_now
            meta = True
        if tname and _normalize(task.name) != _normalize(tname):
            sim = SequenceMatcher(
                None, _normalize(task.name), _normalize(tname)).ratio()
            if sim < 0.9:
                task.name = tname
                task.save(update_fields=['name'])
                saved += 1
                emit(f'Task: -> "{tname[:50]}"')
            elif task.name != tname:
                meta = True
                task.name = tname
        if meta:
            task.save(update_fields=['name', 'somo', 'kidato'])
            saved += 1
            emit(f'Task meta (herufi): somo="{task.somo}" kidato="{task.kidato}"')

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
                s_e = _ess_sdate(es.get('start'))
                e_e = _ess_sdate(es.get('end'))
                d_upd = []
                if s_e and st.start != s_e:
                    st.start = s_e
                    d_upd.append('start')
                if e_e and st.end != e_e:
                    st.end = e_e
                    d_upd.append('end')
                if d_upd:
                    st.save(update_fields=d_upd)
                if _normalize(st.description) == _normalize(name):
                    if st.description == name:
                        skipped += 1
                        emit(f'= sawa: {st.description[:55]}')
                    else:
                        emit(f'-> (herufi) "{st.description[:38]}" => "{name[:38]}"')
                        st.description = name
                        st.save(update_fields=['description'])
                        saved += 1
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
                mode='manual', target=0,
                start=_ess_sdate(es.get('start')),
                end=_ess_sdate(es.get('end')))
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


def _collect_official_rows(page, emit) -> dict:
    """Soma {maandishi_ya_safu: asilimia} za sub-task kutoka ESS (miaka yote)."""
    rows = {}

    def _scan():
        page_no = 0
        while True:
            page_no += 1
            els = _rows(page)
            if not els:
                break
            for el in els:
                cell = el.query_selector(SELECTORS['subtask_cell_selector'])
                if not cell:
                    continue
                t = re.sub(r'\s+', ' ', cell.inner_text()).strip()
                if t and t not in rows:
                    rows[t] = _row_current_pct(el)
            nxt = page.query_selector(SELECTORS['paginator_next_selector'])
            if not nxt or nxt.get_attribute('disabled') is not None or nxt.is_disabled():
                break
            before = []
            for el in els:
                c = el.query_selector(SELECTORS['subtask_cell_selector'])
                before.append(c.inner_text() if c else '')
            nxt.click()
            page.wait_for_timeout(700)
            after = []
            for el in _rows(page):
                c = el.query_selector(SELECTORS['subtask_cell_selector'])
                after.append(c.inner_text() if c else '')
            if page_no >= 50 or after == before:
                break

    cands = _candidate_years(page)
    cy = _current_year(page)
    if cy and cy.get('id'):
        cands.sort(key=lambda c: 0 if c['id'] == cy['id'] else 1)
        if not any(c.get('id') == cy['id'] for c in cands):
            cands.insert(0, cy)

    if not cands:
        _scan()
    else:
        for cand in cands:
            try:
                _set_current_year(page, cand)
                _goto_subtasks(page)
                _table_settled(page)
            except Exception as exc:
                emit(f'pct mwaka {cand.get("id")}: {exc}')
                continue
            _scan()
    emit(f'Asilimia kutoka jedwali: safu {len(rows)}.')
    return rows


def _supervise_official_rows(profile, rows, emit) -> int:
    """Linganisha safu za ESS na sub-task za local, hifadhi official_pct."""
    if not rows:
        return 0
    local = [(st.id, st.description)
             for task in profile.tasks.all()
             for st in task.subtasks.all()]
    cands = [{'text': k, 'pct': v} for k, v in rows.items()]
    mapping = {}
    for sid, text in local:
        m, _sc = _best_row_match(text, cands, SELECTORS['match_threshold'])
        if m and m['pct'] is not None:
            mapping[sid] = m['pct']
    saved = _save_official_pcts(mapping)
    emit(f'Asilimia za ESS zimehifadhiwa kwa sub-task {saved}.')
    return saved


def _read_official_map(page, local, emit, threshold=None) -> dict:
    """Soma asilimia za safu za ESS na zilinganishe na sub-task za local.

    `local`: [(subtask_id, maandishi)]. Rudi {subtask_id: asilimia}.
    """
    threshold = SELECTORS['match_threshold'] if threshold is None else threshold
    found = {}
    page_no = 0
    while True:
        page_no += 1
        cands = []
        for i, el in enumerate(_rows(page)):
            cell = el.query_selector(SELECTORS['subtask_cell_selector'])
            if cell:
                cands.append({'i': i, 'text': cell.inner_text(),
                              'pct': _row_current_pct(el)})
        if not cands:
            break
        for sid, text in local:
            if sid in found:
                continue
            m, _sc = _best_row_match(text, cands, threshold)
            if m and m['pct'] is not None:
                found[sid] = float(m['pct'])
        emit(f'Ukurasa {page_no}: safu {len(cands)}, zimepatikana {len(found)}')
        nxt = page.query_selector(SELECTORS['paginator_next_selector'])
        if not nxt or nxt.get_attribute('disabled') is not None or nxt.is_disabled():
            break
        before = [c['text'] for c in cands]
        nxt.click()
        page.wait_for_timeout(700)
        after = []
        for el in _rows(page):
            c = el.query_selector(SELECTORS['subtask_cell_selector'])
            if c:
                after.append(c.inner_text())
        if page_no >= 50 or after == before:
            break
    return found


def run_read(profile_id: int, run_id: int) -> dict:
    """Soma asilimia HALISI za kila sub-task kutoka ESS (hakuna kubadilisha)."""
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

    local = [(st.id, st.description)
             for task in profile.tasks.all()
             for st in task.subtasks.all()]
    if not local:
        emit('Hakuna sub-task ya kusoma.')
        run.status = 'error'
        run.finished = tz.now()
        run.log = '\n'.join(log)
        run.save()
        return {'status': 'error', 'msg': 'Hakuna sub-task.'}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        run.status = 'error'
        run.finished = tz.now()
        run.log = 'Playwright haiko kwenye server.'
        run.save()
        return {'status': 'error', 'msg': str(exc)}

    emit('Kusoma asilimia ESS kumeanza — naingia ESS...')
    official = {}
    saved = 0
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
            try:
                _goto_retry(page, DASHBOARD_URL)
                _wait_for_current_year(page, 20)
            except Exception:
                pass
            _goto_subtasks(page)

            cands = _candidate_years(page)
            cy = _current_year(page)
            if cy and cy.get('id'):
                cands.sort(key=lambda c: 0 if c['id'] == cy['id'] else 1)
                if not any(c.get('id') == cy['id'] for c in cands):
                    cands.insert(0, cy)

            if not cands:
                official.update(_read_official_map(page, local, emit))
            else:
                for cand in cands:
                    if len(official) >= len(local):
                        break
                    try:
                        _set_current_year(page, cand)
                        _goto_subtasks(page)
                        _table_settled(page)
                    except Exception as exc:
                        emit(f'mwaka {cand.get("id")}: kosa {exc}')
                        continue
                    official.update(_read_official_map(page, local, emit))
            try:
                browser.close()
            except Exception:
                pass
        saved = _save_official_pcts(official)
    except Exception as exc:  # noqa: BLE001
        snippet = ''
        if page is not None:
            try:
                snippet = f' [URL: {page.url}]'
            except Exception:
                pass
        run.status = 'error'
        run.finished = tz.now()
        run.saved = saved
        run.required = len(local)
        run.log = '\n'.join(log + [f'ERROR: {exc}{snippet}'])
        run.save()
        _set_progress(run_id, done=True, status='error', saved=saved)
        return {'status': 'error', 'msg': str(exc)}

    not_found = len(local) - len(official)
    run.status = 'done'
    run.finished = tz.now()
    run.saved = saved
    run.not_found = not_found
    run.required = len(local)
    run.log = '\n'.join(log)
    run.save()
    _set_progress(run_id, done=True, status='done', saved=saved,
                  not_found=not_found)
    return {'status': 'done', 'saved': saved, 'not_found': not_found}


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
    official_rows = {}
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
                gql_vars = {'financialYear': fin, 'checkNumber': check,
                            'calendarYear': cal}
                # Jaribu kwanza query yenye startDate/endDate; ikikataliwa,
                # rudi kwenye ile ya awali ili sync isivunjike.
                payload = _ess_fetch_json(
                    page, auth, _GQL_EMPLOYEE_TASKS_DATES, gql_vars, emit)
                tree = _ess_tree_from_payload(payload)
                if not tree:
                    payload = _ess_fetch_json(
                        page, auth, _GQL_EMPLOYEE_TASKS, gql_vars, emit)
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
            try:
                official_rows = _collect_official_rows(page, emit)
            except Exception as exc:
                emit(f'Kusoma asilimia za ESS: {exc}')
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
        try:
            _supervise_official_rows(profile, official_rows, emit)
        except Exception as exc:
            emit(f'Kuhifadhi asilimia za ESS: {exc}')
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
        inc = subtask_increment_pct(st)
        ess_val = float(st.official_pct) if st.official_pct is not None else None
        # Badge: linganisha thamani HALISI (ESS, kisha actual, kisha iliyopangwa)
        # na tarajio — sio thamani iliyopangwa (ambayo kwa kujenga = tarajio,
        # ingefanya kila kitu kionekane "sawa").
        cur_real = ess_val if ess_val is not None else (
            recorded if recorded is not None else pct)
        status, expected_pct, gap = on_track_status(st, cur_real)
        plan = plan_for(st, ess_val if ess_val is not None else pct)
        # Asilimia ITAKAYOTUMWA: hii ndiyo thamani ambayo kujaza kutatumia
        # (floor ya target x base), SIO base yenyewe. Na itaskip kama ESS
        # tayari ipo juu/sawa.
        target = target_for(st)
        if target and target > 0 and pct is not None:
            tf = float(target)
            planned = int(tf * pct / 100.0)
            send_pct = round(100.0 * planned / tf, 2)
        else:
            send_pct = pct
        will_skip = (ess_val is not None and send_pct is not None
                     and send_pct <= ess_val + 0.5)
        out.append({
            'st': st,
            'target': target_display(st),
            'actual': actual_display(st),
            'expected': expected_display(st),
            'pct': pct,
            'pct_str': '' if pct is None else f'{pct:.0f}%',
            'send_pct': send_pct,
            'send_pct_str': '' if send_pct is None else f'{send_pct:.0f}%',
            'will_skip': will_skip,
            'recorded_pct': recorded,
            'source': src,
            'by_calendar': src == 'calendar',
            'increment': inc,
            'increment_str': '' if inc is None else f'{inc:.2f}%',
            'status': status,
            'expected_pct': expected_pct,
            'expected_pct_str': '' if expected_pct is None else f'{expected_pct:.0f}%',
            'gap': gap,
            'ess_pct': st.official_pct,
            'ess_pct_str': '' if st.official_pct is None
                           else f'{float(st.official_pct):.0f}%',
            'ess_at': st.official_at,
            'plan': plan,
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