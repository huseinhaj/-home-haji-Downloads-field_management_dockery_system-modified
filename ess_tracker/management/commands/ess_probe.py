"""Smoke-test ya ESS: thibitisha selectors/mtiririko kwa session halisi.

Kila mtiririko wa ESS (fill/read/sync/push/approve) hutegemea selectors
zilizo kwenye `ess_tracker.selectors`. ESS portal inaweza kubadilisha DOM
bila taarifa — amri hii hupima hatua zote muhimu kwa mpangilio na kukuambia
kwanza kitu kimevunjika wapi, pamoja na screenshot/HTML ya ukurasa uliokuwa
wazi (media/ess_artifacts/).

Matumizi:
    python manage.py ess_probe                      # profile ya kwanza yenye ess_ready
    python manage.py ess_probe --profile 5
    python manage.py ess_probe --headed --keep-going
    python manage.py ess_probe --json

Exit code 1 kama hata moja kati ya checks imevunjika (F1 - CI/alerting).
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from ess_tracker.selectors import (PASSWORD_SEL, PROBE_CHECKS, SELECTORS,
                                   USERNAME_SELS)


class ProbeFailure(Exception):
    """Check moja imeshindwa — ess_browser huchukua screenshot/HTML kabla."""

    def __init__(self, step: str, detail: str = ''):
        super().__init__(f'{step}: {detail}' if detail else step)
        self.step = step
        self.detail = detail


class Command(BaseCommand):
    help = ('Smoke-test ya ESS: thibitisha login, jedwali la sub-tasks na '
            'menyu ya Actions kwa session halisi; hifadhi artifacts kama '
            'kitu kimevunjika.')

    def add_arguments(self, parser):
        parser.add_argument('--profile', type=int, metavar='ID',
                            help='TeacherProfile id ya kutumia (chagua moja '
                                 'yenye ess_ready)')
        parser.add_argument('--username', help='Badilisha ESS username (bila profile)')
        parser.add_argument('--password', help='Badilisha ESS password (bila profile)')
        parser.add_argument('--headed', action='store_true',
                            help='Onyesha browser (si headless) — kwa kuchunguza')
        parser.add_argument('--keep-going', action='store_true',
                            help='Endelea na checks zinazofuata baada ya FAIL')
        parser.add_argument('--json', action='store_true', dest='as_json',
                            help='Chapisha matokeo kama JSON')

    # -- checks ----------------------------------------------------------
    def _record(self, results, name, passed, detail='', keep_going=False):
        info = next((c for c in PROBE_CHECKS if c['name'] == name), None)
        step = info['step'] if info else name
        results.append({
            'name': name,
            'step': step,
            'desc': info['desc'] if info else name,
            'status': 'pass' if passed else 'fail',
            'detail': (detail or '')[:300],
        })
        if not passed and not keep_going:
            raise ProbeFailure(step, detail or '')

    def handle(self, *args, **opts):
        username = (opts.get('username') or '').strip()
        password = opts.get('password') or ''
        if not username:
            from ess_tracker.models import TeacherProfile
            qs = TeacherProfile.objects.filter(ess_ready=True)
            if opts.get('profile'):
                profile = qs.filter(pk=opts['profile']).first()
            else:
                profile = qs.order_by('id').first()
            if profile is None:
                raise CommandError(
                    'Hakuna profile yenye ess_ready. Weka --profile au weka '
                    'ESS username/password kwenye wasifu.')
            username = profile.ess_username
            password = profile.ess_password_plain or ''

        results = []
        state = {}
        keep = bool(opts['keep_going'])
        failed_exc = None
        try:
            self._run_checks(results, state, username, password,
                             headed=bool(opts['headed']), keep=keep)
        except ProbeFailure as exc:
            failed_exc = exc
        except Exception as exc:  # noqa: BLE001 - mengine (browser/mtandao)
            results.append({'name': 'browser', 'step': state.get('step') or '?',
                            'desc': 'Browser/session ya ESS', 'status': 'fail',
                            'detail': str(exc)[:300]})
            failed_exc = ProbeFailure(state.get('step') or '?', str(exc))

        art = state.get('artifacts') or {}
        bad = [r for r in results if r['status'] == 'fail']
        summary = {
            'total': len(results),
            'passed': len(results) - len(bad),
            'failed': len(bad),
            'failed_step': (bad[0]['step'] if bad else ''),
            'artifacts': art,
        }
        if opts['as_json']:
            self.stdout.write(json.dumps({'checks': results, 'summary': summary},
                                         ensure_ascii=False, indent=2))
        else:
            for r in results:
                mark = self.style.SUCCESS('PASS') if r['status'] == 'pass' \
                    else self.style.ERROR('FAIL')
                line = f"  [{mark}] {r['name']:<16} {r['desc']}"
                if r['detail'] and r['status'] == 'fail':
                    line += f"\n           -> {r['detail']}"
                self.stdout.write(line)
            if art:
                self.stdout.write(self.style.WARNING(
                    'Artifacts: ' + ', '.join(
                        f'{k}={v}' for k, v in art.items() if v)))
            self.stdout.write(
                f"Jumla: {summary['passed']}/{summary['total']} PASS"
                + (f" | imeshindwa kwenye hatua: {summary['failed_step']}"
                   if bad else ' | sawa'))

        if failed_exc is not None or bad:
            step = summary['failed_step'] or '?'
            raise CommandError(
                f'ESS probe IMESHINDWA kwenye hatua "{step}". '
                f'Angalia artifacts na kurekebisha selectors '
                f'(ess_tracker/selectors.py).')

    def _run_checks(self, results, state, username, password, *, headed, keep):
        from ess_tracker.artifacts import ess_browser
        from ess_tracker.essfill import (_auto_login, _open_ess,
                                         _pick_visible_input, _rows,
                                         _goto_subtasks)

        with ess_browser(state, label='probe', headless=not headed) as (page, browser):
            # 1. open
            state['step'] = 'open'
            try:
                _open_ess(page)
                self._record(results, 'open', True, keep_going=keep)
            except ProbeFailure:
                raise
            except Exception as exc:  # noqa: BLE001
                self._record(results, 'open', False, str(exc), keep)

            # 2. login_form
            state['step'] = 'login_form'
            try:
                page.wait_for_selector(PASSWORD_SEL, timeout=25000)
                pw_ok = True
                pw_detail = ''
            except Exception as exc:  # noqa: BLE001
                pw_ok, pw_detail = False, str(exc)
            user_el = _pick_visible_input(page, USERNAME_SELS)
            if pw_ok and user_el is None:
                pw_ok, pw_detail = False, 'Hakuna input ya username iliyowazi'
            self._record(results, 'login_form', pw_ok,
                         pw_detail or f'URL: {page.url}', keep)

            # 3. login
            state['step'] = 'login'
            try:
                _auto_login(page, username, password)
                self._record(results, 'login', True, keep_going=keep)
            except ProbeFailure:
                raise
            except Exception as exc:  # noqa: BLE001
                self._record(results, 'login', False, str(exc), keep)

            # 4. session
            state['step'] = 'session'
            try:
                has_token = bool(page.evaluate(
                    "() => !!localStorage.getItem('token')"))
            except Exception as exc:  # noqa: BLE001
                has_token, detail = False, str(exc)
            else:
                detail = 'Hakuna localStorage.token'
            self._record(results, 'session', has_token,
                         '' if has_token else detail, keep)

            # 5. subtasks_table
            state['step'] = 'subtasks_table'
            try:
                _goto_subtasks(page)
                rows = _rows(page)
                self._record(results, 'subtasks_table', bool(rows),
                             f'safu {len(rows)}; URL: {page.url}' if rows
                             else f'Jedwali halina safu; URL: {page.url}', keep)
            except ProbeFailure:
                raise
            except Exception as exc:  # noqa: BLE001
                self._record(results, 'subtasks_table', False, str(exc), keep)
                rows = []

            # 6. row_actions
            state['step'] = 'row_actions'
            trigger = None
            if rows:
                try:
                    trigger = rows[0].query_selector(
                        SELECTORS['row_action_button_selector'])
                except Exception:  # noqa: BLE001
                    trigger = None
            self._record(results, 'row_actions', trigger is not None,
                         '' if trigger else
                         'Safu ya kwanza haina kitufe cha Actions '
                         f'({SELECTORS["row_action_button_selector"]})', keep)

            # 7. add_progress — fungua menyu, THIBITISHA kipengele tu (bila
            #    kubonyeza = hakuna mabadiliko kwenye ESS).
            state['step'] = 'add_progress'
            labels = SELECTORS['add_entry_labels']
            detail, found = '', False
            if trigger is None:
                detail = 'Hakuna kitufe cha Actions'
            else:
                try:
                    trigger.click()
                    page.wait_for_timeout(900)
                    texts = []
                    for sel in ('.cdk-overlay-container button.mat-mdc-menu-item',
                                '.mat-mdc-menu-panel button.mat-mdc-menu-item',
                                'button.mat-mdc-menu-item'):
                        for el in page.query_selector_all(sel):
                            try:
                                if el.is_visible():
                                    t = (el.inner_text() or '').strip()
                                    if t:
                                        texts.append(t)
                            except Exception:  # noqa: BLE001
                                continue
                        if texts:
                            break
                    low = [t.lower() for t in texts]
                    hit = [lab for lab in labels
                           if any(lab.lower() in t for t in low)]
                    found = bool(hit)
                    detail = '' if found else \
                        'Menyu hauna: ' + ' / '.join(labels) + \
                        f' | iliyopatikana: {texts[:6]}'
                except Exception as exc:  # noqa: BLE001
                    found, detail = False, str(exc)
                finally:
                    try:
                        page.keyboard.press('Escape')
                    except Exception:  # noqa: BLE001
                        pass
            self._record(results, 'add_progress', found, detail, keep)
