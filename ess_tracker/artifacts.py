"""Artifacts za hitilafu za ESS: screenshot + HTML + maelezo ya hatua.

Kila run inayoshindwa huhifadhi picha na HTML ya ukurasa uliokuwa wazi
wakati wa hitilafu (chini ya `media/ess_artifacts/`) ili admin aweze
kurekebisha selectors bila kuingia ESS. Pia hutoa `describe_failure`
(maelezo mafupi ya hatua iliyovunjika) inayohifadhiwa kwenye
`EssFillRun.error_step`.

Muhimu: artifact lazima zichukuliwe WAKATI BROWSER BADO IKO WAZI. Njia
sahihi ni `ess_browser()` contextmanager — inachukua screenshot/HTML
kabla ya Playwright kuzimwa (kanda ya `except` ya juu ni baada ya
`with sync_playwright()` kufungwa → page tayari imekufa).

Matumizi:
    state = {}
    with ess_browser(state, run_id=run.id, label='fill') as (page, browser):
        state['step'] = 'login'
        ...
    # kama hitilafu imetokea ndani: state['artifacts'], state['error']
"""
from __future__ import annotations

import logging
import re
import time
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('ess_tracker')

# Idadi ya artifacts zinazobaki (zilizotengenezwa hivi karibuni).
KEEP_DEFAULT = 200

# Error class / ujumbe → maelezo ya kimtongozi kwa admin (selectors yapi
# yanahitaji kurekebishwa). Thamani ya kwanza inashinda.
_HINTS = [
    ('spa haijafunguka',
     'ESS SPA haijafunguka (Angular haijapakia/yamechelewa) — SI fomu '
     'imebadilika; angalia request zilizoshindwa kwenye kosa.'),
    ('fomu ya login', 'Login haikufunguka — ESS imebadilisha fomu ya login.'),
    ('wrong credentials', 'Jina/nywila ya ESS si sahihi (au imebadilika).'),
    ('login failed', 'Jina/nywila ya ESS si sahihi (au imebadilika).'),
    ('password ya ESS', 'Jina/nywila ya ESS si sahihi (au imebadilika).'),
    ('add sub task progress', 'Menyu ya Actions imebadilika — jina la "Add Sub Task Progress" halipo.'),
    ('department', 'Ukurasa wa department-report haupatikani (menyu/kielelezo kimebadilika).'),
    ('graphql', 'API ya ESS (GraphQL) imebadilika au haikubali ombi.'),
    ('waiting for locator', 'Selector imepotea — linganisha na HTML artifact.'),
    ('waiting for selector', 'Selector imepotea — linganisha na HTML artifact.'),
    ('no such element', 'Selector imepotea — linganisha na HTML artifact.'),
    ('timeout', 'Kitu hakikuonekana kwa muda — selector imepotea au ESS imechelewa (angalia HTML).'),
    ('net::', 'Mtandao/ESS haikufikiwa.'),
]


def artifact_root() -> Path:
    """Diri ya artifacts (inaweza kubadilishwa kwa `ESS_ARTIFACT_DIR`)."""
    root = getattr(settings, 'ESS_ARTIFACT_DIR', None) or \
        Path(settings.MEDIA_ROOT) / 'ess_artifacts'
    root = Path(root)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover - edge
        logger.warning('Siwezi kutengeneza artifact dir %s: %s', root, exc)
    return root


def _rel(path: Path) -> str:
    """Njia ya tendaji (relative) ya faili kutoka MEDIA_ROOT inapowezekana."""
    try:
        return str(path.relative_to(Path(settings.MEDIA_ROOT)))
    except (ValueError, TypeError):
        return str(path)


def dump_artifacts(page, run_id=None, label='error') -> dict | None:
    """Hifadhi screenshot + HTML ya `page`.

    Hurudisha `{'screenshot': rel, 'html': rel, 'url': str}` (njia za
    tendaji chini ya MEDIA_ROOT) au None kama hakuna kilichohifadhiwa.
    Kila hatua imezingatiwa — hitilafu kwenye screenshot haizuii HTML
    (na kinyake).
    """
    if page is None:
        return None
    root = artifact_root()
    safe = re.sub(r'[^a-z0-9_-]+', '-', str(label or 'error').lower()).strip('-') \
        or 'error'
    stamp = time.strftime('%Y%m%d-%H%M%S')
    base = f'run_{run_id or "x"}_{safe}_{stamp}'
    out = {}

    try:
        html = page.content() or ''
        p = root / f'{base}.html'
        p.write_text(html, encoding='utf-8', errors='replace')
        out['html'] = _rel(p)
    except Exception as exc:  # noqa: BLE001
        logger.warning('HTML dump imeshindwa (run %s): %s', run_id, exc)

    try:
        p = root / f'{base}.png'
        page.screenshot(path=str(p), full_page=True)
        out['screenshot'] = _rel(p)
    except Exception as exc:  # noqa: BLE001
        logger.warning('Screenshot imeshindwa (run %s): %s', run_id, exc)

    try:
        out['url'] = str(page.url or '')
    except Exception:  # noqa: BLE001
        pass

    if not out:
        return None
    prune_artifacts()
    return out


def prune_artifacts(keep: int = KEEP_DEFAULT) -> int:
    """Ondoa artifacts za zamani; ache `keep` za mpya zaidi. Rudi idadi iliyofutwa."""
    root = artifact_root()
    try:
        files = sorted((f for f in root.iterdir()
                        if f.suffix in ('.png', '.html') and f.is_file()),
                       key=lambda f: f.stat().st_mtime, reverse=True)
    except OSError:  # pragma: no cover - edge
        return 0
    removed = 0
    for f in files[max(keep, 0):]:
        try:
            f.unlink()
            removed += 1
        except OSError:  # pragma: no cover - edge
            pass
    return removed


def _hint_for(text: str) -> str:
    low = (text or '').lower()
    for needle, hint in _HINTS:
        if needle in low and hint:
            return hint
    return 'Angalia HTML/screenshot artifact kwa maelezo.'


def describe_failure(exc, step: str = '', url: str = '') -> dict:
    """Maelezo mafupi ya kimtindo ya hitilafu kwa admin/UI."""
    msg = re.sub(r'\s+', ' ', str(exc) or '').strip()
    err = f'{type(exc).__name__}: {msg}' if msg else type(exc).__name__
    return {
        'step': step or '',
        'error': err[:400],
        'url': (url or '')[:300],
        'hint': _hint_for(err),
        'ts': timezone.now().isoformat(),
    }


def artifacts_snippet(info: dict | None) -> str:
    """Sehemu ya log: ` [artifacts: a.png, b.html]` (au '')."""
    if not info:
        return ''
    paths = [info.get('screenshot'), info.get('html')]
    paths = [p for p in paths if p]
    if not paths:
        return ''
    return ' [artifacts: ' + ', '.join(paths) + ']'


@contextmanager
def ess_browser(state: dict, *, run_id=None, label='error', headless=True,
                args=None):
    """Fungua browser ya Playwright; nasa hitilafu WAKATI page bado wazi.

    `state` (dict ya nje) huandika:
      - `state['step']` — hatua ya sasa (iwekwe na mwitaji: `state['step'] = 'login'`)
      - `state['artifacts']` — screenshot/HTML zilizohifadhiwa (kama hitilafu)
      - `state['error']` — `describe_failure(...)` (kama hitilafu)

    Hurudisha `(page, browser)`.
    """
    from playwright.sync_api import sync_playwright

    if args is None:
        args = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, args=args)
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()
        page.set_default_timeout(45000)
        try:
            yield page, browser
        except BaseException as exc:  # noqa: BLE001 - hupisha yote
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            step = state.get('step') or ''
            url = ''
            try:
                url = str(page.url or '')
            except Exception:  # noqa: BLE001
                pass
            state['artifacts'] = dump_artifacts(page, run_id, label or step or 'error')
            state['error'] = describe_failure(exc, step, url)
            raise
        finally:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass
