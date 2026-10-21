"""Majaribio ya Schedule Guard (ratiba ya matukio na idadi ya nukuu).

Huhakikisha mfumo haujazi 100% mapema: jaribio la Novemba halionyeshwi
kama limekamilika Oktoba; nukuu hutumia idadi mwalimu aliyojaza.
"""

import datetime as dt
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import (SimpleTestCase, TestCase, TransactionTestCase,
                         override_settings)
from django.utils import timezone

from ess_tracker import compute as C
from ess_tracker import essfill as F
from ess_tracker.essfill import CACHE_PREFIX, subtask_snapshot
from ess_tracker.models import (EssFillRun, SubTask, SubTaskEvent, Task,
                                 TeacherProfile)


class ScheduleGuardTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.user = U.objects.create_user('mwalimu', password='x')
        self.profile = TeacherProfile.objects.create(
            user=self.user, full_name='Mwalimu Mfano',
            school_open=dt.date(2026, 1, 7),
            school_close=dt.date(2026, 11, 13))
        self.task = Task.objects.create(
            profile=self.profile, name='Task 1', somo='Hisabati', kidato='1',
            topics_total=10, start=dt.date(2026, 7, 1),
            end=dt.date(2026, 12, 12))

    def _events_subtask(self, dates):
        st = SubTask.objects.create(
            task=self.task, position=7, description='Majaribio',
            mode='events', target=Decimal('5'))
        for i, (d, label) in enumerate(dates, start=1):
            SubTaskEvent.objects.create(subtask=st, index=i, due_date=d,
                                        label=label)
        return st

    def test_events_cap_stops_early_full_claim(self):
        """Jaribio la 5 (Novemba) halifanyi 100% Oktoba."""
        st = self._events_subtask([
            (dt.date(2026, 3, 15), 'Jaribio 1'),
            (dt.date(2026, 6, 15), 'Jaribio 2'),
            (dt.date(2026, 8, 15), 'Jaribio 3'),
            (dt.date(2026, 11, 15), 'Jaribio 4'),
            (dt.date(2026, 12, 15), 'Jaribio 5'),
        ])
        leo = dt.date(2026, 10, 15)
        self.assertEqual(C.events_total(st), 5)
        self.assertEqual(C.events_completed(st, leo), 3)
        self.assertEqual(C.schedule_cap_pct(st, leo), 60.0)
        self.assertTrue(C.is_waiting(st, leo))
        nxt = C.events_next(st, leo)
        self.assertEqual(nxt['index'], 4)
        # entry_from_values hairuhusiwi kupita cap.
        _note, pct = C.entry_from_values(
            st, 5, 100.0, 0, max_pct=C.schedule_cap_pct(st, leo))
        self.assertLessEqual(pct, 60.0)

    def test_events_fill_up_to_cap_even_when_waiting(self):
        """Ingawa inasubiri tukio la 4, hujaza hadi cap (3/5 = 60%)."""
        st = self._events_subtask([
            (dt.date(2026, 3, 15), 'Jaribio 1'),
            (dt.date(2026, 6, 15), 'Jaribio 2'),
            (dt.date(2026, 8, 15), 'Jaribio 3'),
            (dt.date(2026, 11, 15), 'Jaribio 4'),
            (dt.date(2026, 12, 15), 'Jaribio 5'),
        ])
        leo = dt.date(2026, 10, 15)
        note, pct = C.entry_from_values(
            st, 5, 100.0, 0, max_pct=C.schedule_cap_pct(st, leo))
        self.assertEqual(pct, 60.0)
        self.assertIn('3 kati ya 5', note)

    def test_events_no_dates_falls_back_to_linear(self):
        """Sub-task ya events bila tarehe haivunji tabia ya zamani (linear)."""
        st = SubTask.objects.create(
            task=self.task, position=8, description='Empty', mode='events',
            target=Decimal('4'), vila_per_week=Decimal('1'), week_count=10)
        leo = dt.date(2026, 10, 15)
        self.assertIsNone(C.schedule_cap_pct(st, leo))
        self.assertFalse(C.is_waiting(st, leo))
        pct, src = C.pct_auto_for(st, leo)
        self.assertIsNotNone(pct)
        self.assertEqual(src, 'schedule')

    def test_count_mode_uses_teacher_count(self):
        """Nukuu 3 kati ya 7 => 42.86% (bila kudhani linear)."""
        st = SubTask.objects.create(
            task=self.task, position=2, description='Nukuu', mode='count',
            target=Decimal('7'))
        st.actual_base = Decimal('3')
        st.save()
        self.assertEqual(C.count_pct(st), 42.86)
        self.assertEqual(C.schedule_cap_pct(st), 42.86)
        self.assertEqual(C.pct_auto_for(st), (42.86, 'count'))

    def test_count_caps_at_target(self):
        st = SubTask.objects.create(
            task=self.task, position=2, description='Nukuu', mode='count',
            target=Decimal('7'))
        st.actual_base = Decimal('99')
        st.save()
        self.assertEqual(C.count_pct(st), 100.0)

    def test_snapshot_exposes_waiting_and_events(self):
        st = self._events_subtask([
            (dt.date(2026, 3, 15), 'Jaribio 1'),
            (dt.date(2026, 11, 15), 'Jaribio 2'),
        ])
        snap = subtask_snapshot(self.task)
        row = next(s for s in snap if s['st'].id == st.id)
        self.assertTrue(row['is_events'])
        self.assertTrue(row['waiting'])
        self.assertEqual(row['events_total'], 2)
        self.assertEqual(len(row['events_list']), 2)
        self.assertEqual(row['next_event']['label'], 'Jaribio 2')


class SaveEventsFromFormsTests(TestCase):
    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('m2', password='x')
        p = TeacherProfile.objects.create(user=u, full_name='T')
        t = Task.objects.create(profile=p, name='Task', somo='Hisabati',
                                kidato='1', start=dt.date(2026, 1, 1),
                                end=dt.date(2026, 12, 1))
        self.st = SubTask.objects.create(task=t, position=7,
                                         description='Majaribio',
                                         mode='events', target=Decimal('5'))

    def test_save_sorts_indexes_and_ignores_bad(self):
        from types import SimpleNamespace
        from django.http import QueryDict
        from ess_tracker.views import _save_events_from_forms
        q = QueryDict('', mutable=True)
        q.setlist(f'event_date_{self.st.id}',
                  ['2026-07-10', '2026-04-10', '2026-09-01', '', 'bad'])
        q.setlist(f'event_label_{self.st.id}', ['B', 'A', 'C', '', 'x'])
        _save_events_from_forms(SimpleNamespace(POST=q), self.st)
        rows = list(self.st.events.values_list('index', 'due_date', 'label'))
        self.assertEqual(rows, [
            (1, dt.date(2026, 4, 10), 'A'),
            (2, dt.date(2026, 7, 10), 'B'),
            (3, dt.date(2026, 9, 1), 'C'),
        ])

    def test_resave_replaces_all(self):
        from types import SimpleNamespace
        from django.http import QueryDict
        from ess_tracker.views import _save_events_from_forms
        q = QueryDict('', mutable=True)
        q.setlist(f'event_date_{self.st.id}',
                  ['2026-04-10', '2026-07-10'])
        _save_events_from_forms(SimpleNamespace(POST=q), self.st)
        self.assertEqual(self.st.events.count(), 2)
        q2 = QueryDict('', mutable=True)
        q2.setlist(f'event_date_{self.st.id}', ['2026-05-05'])
        _save_events_from_forms(SimpleNamespace(POST=q2), self.st)
        self.assertEqual(self.st.events.count(), 1)
        self.assertEqual(self.st.events.first().due_date, dt.date(2026, 5, 5))


class AnchorResolutionTests(TestCase):
    """Ratiba ya mwezi na muhula+wiki (chaguo la 6)."""

    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('mw', password='x')
        self.profile = TeacherProfile.objects.create(
            user=u, full_name='Mwalimu',
            school_open=dt.date(2026, 1, 7),
            school_close=dt.date(2026, 11, 13))
        self.task = Task.objects.create(
            profile=self.profile, name='Task', somo='Hisabati', kidato='1',
            start=dt.date(2026, 1, 7), end=dt.date(2026, 11, 13))
        self.st = SubTask.objects.create(
            task=self.task, position=7, description='Majaribio',
            mode='events', target=Decimal('6'))

    def _ev(self, **kw):
        kw.setdefault('due_date', dt.date(2026, 1, 1))
        return SubTaskEvent(subtask=self.st, index=1, **kw)

    def test_month_without_day_uses_end_of_month(self):
        ev = self._ev(anchor='month', month=3, due_date=dt.date(2026, 3, 1))
        self.assertEqual(C.resolve_event_date(ev, self.task), dt.date(2026, 3, 31))

    def test_month_with_day_uses_that_day(self):
        ev = self._ev(anchor='month', month=3, day=15,
                      due_date=dt.date(2026, 3, 1))
        self.assertEqual(C.resolve_event_date(ev, self.task), dt.date(2026, 3, 15))

    def test_month_february_leap_end(self):
        ev = self._ev(anchor='month', month=2, due_date=dt.date(2026, 2, 1))
        self.assertEqual(C.resolve_event_date(ev, self.task), dt.date(2026, 2, 28))

    def test_term_week_uses_school_window(self):
        t1, t2 = C.term_bounds(self.task)
        self.assertEqual(t1, dt.date(2026, 1, 7))
        ev1 = self._ev(anchor='term_week', term=1, term_week=6)
        self.assertEqual(C.resolve_event_date(ev1, self.task),
                         t1 + dt.timedelta(days=35))
        ev2 = self._ev(anchor='term_week', term=2, term_week=1)
        self.assertEqual(C.resolve_event_date(ev2, self.task), t2)

    def test_anchor_text_month_and_term(self):
        ev = self._ev(anchor='month', month=7, due_date=dt.date(2026, 7, 31))
        self.assertIn('Julai', C.event_anchor_text(ev))
        ev2 = self._ev(anchor='term_week', term=1, term_week=6,
                       due_date=dt.date(2026, 2, 11))
        txt = C.event_anchor_text(ev2)
        self.assertIn('Muhula 1, wiki ya 6', txt)

    def test_save_events_with_anchors(self):
        from types import SimpleNamespace
        from django.http import QueryDict
        from ess_tracker.views import _save_events_from_forms
        q = QueryDict('', mutable=True)
        q.setlist(f'event_anchor_{self.st.id}', ['month', 'term_week'])
        q.setlist(f'event_date_{self.st.id}', ['', ''])
        q.setlist(f'event_month_{self.st.id}', ['3', ''])
        q.setlist(f'event_day_{self.st.id}', ['', ''])
        q.setlist(f'event_term_{self.st.id}', ['', '1'])
        q.setlist(f'event_week_{self.st.id}', ['', '6'])
        q.setlist(f'event_label_{self.st.id}', ['Jaribio 1', 'Jaribio 2'])
        _save_events_from_forms(SimpleNamespace(POST=q), self.st)
        rows = list(self.st.events.values_list('anchor', 'due_date', 'label'))
        t1, _t2 = C.term_bounds(self.task)
        self.assertIn(('month', dt.date(2026, 3, 31), 'Jaribio 1'), rows)
        self.assertIn(('term_week', t1 + dt.timedelta(days=35), 'Jaribio 2'),
                      rows)

    def test_next_event_has_anchor_text(self):
        SubTaskEvent.objects.create(subtask=self.st, index=1,
                                    anchor='month', month=11,
                                    due_date=dt.date(2026, 11, 30),
                                    label='Jaribio 3')
        nxt = C.events_next(self.st, dt.date(2026, 10, 15))
        self.assertEqual(nxt['index'], 1)
        self.assertIn('Novemba', nxt['anchor_text'])


class NukuuCountDefaultTests(TestCase):
    """Nukuu (nafasi 2) ni mode='count' kwa sub-task mpya."""

    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('mw2', password='x')
        self.profile = TeacherProfile.objects.create(user=u, full_name='M')
        self.task = Task.objects.create(
            profile=self.profile, name='Task', somo='Hisabati', kidato='1',
            start=dt.date(2026, 1, 7), end=dt.date(2026, 11, 13))

    def test_autogen_nukuu_is_count(self):
        specs = C.autogen_subtasks('Hisabati', '1', nukuu=7)
        by_pos = {s['position']: s for s in specs}
        self.assertEqual(by_pos[1]['mode'], 'annual')
        self.assertEqual(by_pos[2]['mode'], 'count')

    def test_count_target_update_via_view(self):
        from ess_tracker.views import ess_subtask_count
        st = SubTask.objects.create(task=self.task, position=2,
                                    description='Nukuu', mode='count',
                                    target=Decimal('0'))
        self.client.force_login(self.profile.user)
        resp = self.client.post(
            f'/ess/subtask/{st.id}/count/',
            {'count_done': '3', 'count_target': '7'})
        self.assertEqual(resp.status_code, 302)
        st.refresh_from_db()
        self.assertEqual(float(st.target), 7.0)
        self.assertEqual(float(st.actual_base), 3.0)
        self.assertEqual(C.count_pct(st), 42.86)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class TemplateSmokeTests(TestCase):
    """Kurasa za nyumbani na hariri zinajenga bila hitilafu (HTML/JS)."""
    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('mw4', password='x')
        self.profile = TeacherProfile.objects.create(
            user=u, full_name='M', ess_username='mw4', ess_password='x',
            school_open=dt.date(2026, 1, 7),
            school_close=dt.date(2026, 11, 13))
        self.task = Task.objects.create(
            profile=self.profile, name='Task', somo='Hisabati', kidato='1',
            start=dt.date(2026, 1, 7), end=dt.date(2026, 11, 13))
        st = SubTask.objects.create(task=self.task, position=7,
                                    description='Majaribio', mode='events',
                                    target=Decimal('6'))
        SubTaskEvent.objects.create(subtask=st, index=1, anchor='month',
                                    month=11, due_date=dt.date(2026, 11, 30),
                                    label='Jaribio 3')
        SubTask.objects.create(task=self.task, position=2, description='Nukuu',
                               mode='count', target=Decimal('7'))
        self.client.force_login(self.profile.user)

    def test_home_renders(self):
        resp = self.client.get('/ess/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('inasubiri', body.lower())
        self.assertIn('kati ya', body)
        self.assertIn('name="count_target"', body)

    def test_task_edit_renders(self):
        resp = self.client.get(f'/ess/task/{self.task.id}/edit/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('event_anchor_', body)
        self.assertIn('event_month_', body)
        self.assertIn('term_week', body)


class WaitingSkipTests(TestCase):
    """Sub-task inayosubiri (cap=0) haijazwi kwenye run_fill."""

    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('mw3', password='x')
        self.profile = TeacherProfile.objects.create(
            user=u, full_name='M', ess_username='mw3', ess_password='x',
            school_open=dt.date(2026, 1, 7),
            school_close=dt.date(2026, 11, 13))
        self.task = Task.objects.create(
            profile=self.profile, name='Task', somo='Hisabati', kidato='1',
            start=dt.date(2026, 1, 7), end=dt.date(2026, 11, 13))

    def test_waiting_decided_and_marked(self):
        st = SubTask.objects.create(task=self.task, position=7,
                                    description='Majaribio', mode='events',
                                    target=Decimal('5'))
        SubTaskEvent.objects.create(subtask=st, index=1,
                                    due_date=dt.date(2026, 12, 15),
                                    label='Jaribio 4')
        self.assertTrue(C.is_waiting(st, dt.date(2026, 10, 15)))
        self.assertEqual(C.schedule_cap_pct(st, dt.date(2026, 10, 15)), 0.0)
        # Hakuna asilimia ya kuongeza — pct_auto_for = cap (0.0), chanzo 'events'
        pct, src = C.pct_auto_for(st, dt.date(2026, 10, 15))
        self.assertEqual(pct, 0.0)
        self.assertEqual(src, 'events')


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class FillLogWeekTests(TestCase):
    """Historia ya kujaza huonyesha run za wiki husika (si historia yote)."""

    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('mw5', password='x')
        self.profile = TeacherProfile.objects.create(
            user=u, full_name='M', ess_username='mw5', ess_password='x')
        self.client.force_login(self.profile.user)

        today = dt.date.today()
        old = today - dt.timedelta(days=30)
        self.this_week = EssFillRun.objects.create(
            profile=self.profile, status='done', saved=3)
        self.old_week = EssFillRun.objects.create(
            profile=self.profile, status='done', saved=9)
        EssFillRun.objects.filter(pk=self.this_week.pk).update(
            started=dt.datetime.combine(today, dt.time(9, 0)))
        EssFillRun.objects.filter(pk=self.old_week.pk).update(
            started=dt.datetime.combine(old, dt.time(9, 0)))

    def test_default_shows_current_week_only(self):
        body = self.client.get('/ess/fill/log/').content.decode()
        self.assertIn(f'#log{self.this_week.id}"', body)
        self.assertNotIn(f'#log{self.old_week.id}"', body)

    def test_all_shows_everything(self):
        body = self.client.get('/ess/fill/log/?week=all').content.decode()
        self.assertIn(f'#log{self.old_week.id}"', body)
        self.assertIn(f'#log{self.this_week.id}"', body)

    def test_old_week_param_shows_old_run(self):
        old = dt.date.today() - dt.timedelta(days=30)
        body = self.client.get(f'/ess/fill/log/?week={old.isoformat()}').content.decode()
        self.assertIn(f'#log{self.old_week.id}"', body)
        self.assertNotIn(f'#log{self.this_week.id}"', body)


# ── Artifacts, diagnostics na ess_probe ─────────────────────────────────────

from contextlib import contextmanager  # noqa: E402
from io import StringIO  # noqa: E402

from ess_tracker import tasks as T  # noqa: E402
from ess_tracker.artifacts import (artifacts_snippet,  # noqa: E402
                                   describe_failure, dump_artifacts,
                                   ess_browser, prune_artifacts)
from ess_tracker.essfill import run_read  # noqa: E402
from ess_tracker.management.commands.ess_probe import (Command as ProbeCommand,  # noqa: E402
                                                       ProbeFailure)
from ess_tracker.runs import launch_run  # noqa: E402
from ess_tracker.selectors import PROBE_CHECKS  # noqa: E402


class _FakePage:
    def __init__(self, html='<html><body>ESS</body></html>'):
        self.url = 'https://ess.utumishi.go.tz/pepmis/implementation/progress'
        self._html = html

    def set_default_timeout(self, ms):
        pass

    def content(self):
        return self._html

    def screenshot(self, path=None, full_page=False):
        Path(path).write_bytes(b'PNG')


class _FakeBrowser:
    def new_context(self, ignore_https_errors=False):
        return self

    def new_page(self):
        return _FakePage()

    def close(self):
        pass


class _FakeChromium:
    def launch(self, headless=True, args=None):
        return _FakeBrowser()


class _FakePW:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def chromium(self):
        return _FakeChromium()


class ArtifactsHelperTests(SimpleTestCase):
    """describe_failure / artifacts_snippet / dump / prune."""

    def test_describe_failure_includes_step_and_hint(self):
        info = describe_failure(RuntimeError('Timeout 30000ms exceeded waiting for locator'),
                                'subtasks_table', 'https://ess/x')
        self.assertEqual(info['step'], 'subtasks_table')
        self.assertIn('RuntimeError', info['error'])
        self.assertIn('Selector imepotea', info['hint'])
        self.assertEqual(info['url'], 'https://ess/x')

    def test_describe_failure_generic_hint(self):
        info = describe_failure(ValueError('nonsense'), 'login', '')
        self.assertIn('HTML/screenshot', info['hint'])

    def test_artifacts_snippet_formats_paths(self):
        self.assertEqual(artifacts_snippet(None), '')
        self.assertEqual(artifacts_snippet({}), '')
        s = artifacts_snippet({'screenshot': 'ess_artifacts/a.png',
                               'html': 'ess_artifacts/a.html'})
        self.assertIn('ess_artifacts/a.png', s)
        self.assertIn('ess_artifacts/a.html', s)

    def test_dump_artifacts_writes_html_and_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(ESS_ARTIFACT_DIR=tmp):
                info = dump_artifacts(_FakePage(), run_id=9, label='login')
                self.assertTrue(Path(tmp, Path(info['html']).name).exists()
                                or Path(info['html']).exists())
                self.assertTrue(Path(info['screenshot']).exists())
                self.assertIn('progress', info['url'])

    def test_prune_artifacts_keeps_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(ESS_ARTIFACT_DIR=tmp):
                root = Path(tmp)
                for i in range(5):
                    p = root / f'old_{i}.png'
                    p.write_bytes(b'x')
                keep = root / 'new.png'
                keep.write_bytes(b'y')
                removed = prune_artifacts(keep=2)
                self.assertEqual(removed, 4)
                self.assertTrue(keep.exists())


class _LoginPage:
    """Ukurasa wa ESS wa kuigwa kwa majaribio ya `_auto_login`."""

    def __init__(self, url='https://ess.utumishi.go.tz/sessions/signin',
                 token=False, form=False, booted=False,
                 text='Please wait ... loading'):
        self.url = url
        self._token = token
        self._form = form
        self._booted = booted
        self._text = text
        self.reloads = 0

    def evaluate(self, js):
        if 'localStorage' in js:
            return self._token
        if 'app-root' in js:
            return self._booted
        return self._form

    def inner_text(self, selector):
        return self._text

    def wait_for_timeout(self, ms):
        pass

    def reload(self, **kw):
        self.reloads += 1

    def on(self, event, fn):
        pass

    def remove_listener(self, event, fn):
        pass

    def query_selector_all(self, sel):
        return []


class LoginWaitDiagnosticsTests(SimpleTestCase):
    """_auto_login: utambuzi wa 'SPA haijafunguka' VS 'fomu imebadilika'.

    Kipindi cha zamani cha 25s + reload kilikatiza bootstrap kila mara ESS
    inapochelewa (Run #79); sasa subiri ni 75s bila reload kisha reload moja.
    """

    def test_message_when_spa_never_booted(self):
        msg = F._login_missing_msg(_LoginPage(booted=False), [])
        self.assertIn('ESS SPA haijafunguka', msg)
        self.assertIn('SI fomu imebadilika', msg)

    def test_message_when_angular_booted_without_form(self):
        msg = F._login_missing_msg(_LoginPage(booted=True), [])
        self.assertIn('ESS imebadilisha fomu ya login', msg)

    def test_message_includes_failed_requests(self):
        msg = F._login_missing_msg(
            _LoginPage(), ['net::ERR_CONNECTION_RESET https://ess/x/main.js'])
        self.assertIn('net::ERR_CONNECTION_RESET', msg)

    def test_hint_tells_apart_spa_vs_form_change(self):
        spa = describe_failure(
            RuntimeError('ESS SPA haijafunguka ndani ya 135s'), 'login', 'u')
        self.assertIn('SPA haijafunguka', spa['hint'])
        form = describe_failure(
            RuntimeError('Fomu ya login ya ESS haikuonekana (URL: x) — '
                         'ESS imebadilisha fomu ya login.'),
            'login', 'u')
        self.assertIn('imebadilisha fomu ya login', form['hint'])

    def test_auto_login_short_circuits_when_token_present(self):
        self.assertTrue(F._auto_login(_LoginPage(token=True), 'u', 'p'))

    def test_auto_login_no_reload_while_form_arrives(self):
        page = _LoginPage(form=True)
        with self.assertRaises(RuntimeError) as ctx:
            F._auto_login(page, 'u', 'p')
        self.assertEqual(page.reloads, 0)
        self.assertIn('fomu ya username', str(ctx.exception))

    def test_auto_login_single_reload_then_spa_error(self):
        page = _LoginPage(form=False, booted=False)
        with mock.patch.object(F, 'LOGIN_FORM_S', 0.01), \
                mock.patch.object(F, 'LOGIN_RELOAD_S', 0.01):
            with self.assertRaises(RuntimeError) as ctx:
                F._auto_login(page, 'u', 'p')
        self.assertEqual(page.reloads, 1)
        self.assertIn('ESS SPA haijafunguka', str(ctx.exception))

    def test_wait_budgets_cover_slow_ess_render(self):
        # ESS ilipimwa ikichukua 15-60s kulionyesha fomu (Okt 2026).
        self.assertGreaterEqual(F.LOGIN_FORM_S, 60)
        self.assertGreaterEqual(F.LOGIN_RELOAD_S, 45)


class EssBrowserCaptureTests(SimpleTestCase):
    """ess_browser nasa screenshot/HTML WAKATI page bado wazi."""

    def _run(self, state, exc=None):
        with mock.patch('playwright.sync_api.sync_playwright',
                        return_value=_FakePW()):
            with ess_browser(state, run_id=1, label='fill') as (page, browser):
                state['step'] = 'login'
                if exc:
                    raise exc

    def test_no_error_leaves_state_clean(self):
        state = {}
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(ESS_ARTIFACT_DIR=tmp):
                self._run(state)
        self.assertNotIn('error', state)
        self.assertNotIn('artifacts', state)

    def test_error_captures_artifacts_and_step(self):
        state = {}
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(ESS_ARTIFACT_DIR=tmp):
                with self.assertRaises(RuntimeError):
                    self._run(state, RuntimeError('Login ya ESS haikufaulu'))
                art = state['artifacts']
                self.assertTrue(Path(art['screenshot']).exists())
                self.assertTrue(Path(art['html']).exists())
        self.assertEqual(state['error']['step'], 'login')
        self.assertIn('Login ya ESS haikufaulu', state['error']['error'])


class RunReadErrorArtifactTests(TestCase):
    """run_read hurekodi error_step + artifacts pale login inaposhindwa."""

    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('mw6', password='x')
        self.profile = TeacherProfile.objects.create(
            user=u, full_name='M', ess_username='mw6', ess_password='x')
        task = Task.objects.create(
            profile=self.profile, name='Task', somo='Hisabati', kidato='1',
            start=dt.date(2026, 1, 7), end=dt.date(2026, 11, 13))
        SubTask.objects.create(task=task, position=1, description='Kufundisha',
                              mode='annual', target=Decimal('10'))

    @mock.patch('ess_tracker.essfill.ess_browser')
    def test_error_sets_step_and_artifacts(self, m_browser):
        def _fake(state, **kw):
            @contextmanager
            def cm():
                state['step'] = 'login'
                state['artifacts'] = {'screenshot': 'ess_artifacts/a.png',
                                      'html': 'ess_artifacts/a.html',
                                      'url': 'https://ess/x'}
                state['error'] = describe_failure(
                    RuntimeError('Login ya ESS haikufaulu'), 'login', '')
                raise RuntimeError('Login ya ESS haikufaulu')
                yield
            return cm()
        m_browser.side_effect = _fake

        run = EssFillRun.objects.create(profile=self.profile, kind='read',
                                        status='running')
        res = run_read(self.profile.id, run.id)
        self.assertEqual(res['status'], 'error')
        run.refresh_from_db()
        self.assertEqual(run.status, 'error')
        self.assertEqual(run.error_step, 'login')
        self.assertEqual(run.artifacts['screenshot'], 'ess_artifacts/a.png')
        self.assertIn('ERROR [login]', run.log)
        self.assertIn('HINT', run.log)


class LaunchRunTests(TestCase):
    """launch_run: kuunda run, fallback ya thread, na notify ya matokeo."""

    class ImmediateThread:
        def __init__(self, target=None, args=(), daemon=None):
            self._t, self._a = target, args

        def start(self):
            self._t(*self._a)

    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('mw7', password='x')
        self.profile = TeacherProfile.objects.create(user=u, full_name='M')

    def test_creates_running_run_and_seeds_cache(self):
        with mock.patch('ess_tracker.runs.threading.Thread') as m_thread:
            run = launch_run(profile=self.profile, kind='fill',
                             thread_target=lambda *a: None)
            m_thread.return_value.start.assert_called_once()
        self.assertEqual(run.status, 'running')
        self.assertEqual(run.kind, 'fill')
        data = cache.get(CACHE_PREFIX + str(run.id))
        self.assertEqual(data['msg'], 'Inaanzisha...')

    def test_run_fields_are_applied(self):
        with mock.patch('ess_tracker.runs.threading.Thread'):
            run = launch_run(profile=self.profile, kind='fill',
                             thread_target=lambda *a: None,
                             run_fields={'only_subtasks': '3,4'})
        self.assertEqual(run.only_subtasks, '3,4')

    def test_async_success_sets_task_id_and_skips_thread(self):
        task = mock.Mock()
        task.apply_async.return_value = mock.Mock(id='abc123')
        with mock.patch('ess_tracker.runs.threading.Thread') as m_thread:
            run = launch_run(profile=self.profile, kind='sync', task=task,
                             thread_target=lambda *a: None)
        self.assertEqual(run.task_id, 'abc123')
        m_thread.assert_not_called()

    def test_async_failure_falls_back_to_thread(self):
        task = mock.Mock()
        task.apply_async.side_effect = RuntimeError('broker down')
        calls = []

        def target(pid, rid):
            calls.append((pid, rid))

        with mock.patch('ess_tracker.runs.threading.Thread',
                        self.ImmediateThread):
            run = launch_run(profile=self.profile, kind='read', task=task,
                             thread_target=target)
        self.assertEqual(calls, [(self.profile.id, run.id)])
        self.assertEqual(run.task_id, '')

    def test_thread_wrapper_notifies_result(self):
        calls = []

        def target(pid, rid):
            calls.append((pid, rid))

        with mock.patch('ess_tracker.runs.threading.Thread',
                        self.ImmediateThread), \
                mock.patch('ess_tracker.tasks.notify_run_result') as m_notify:
            run = launch_run(profile=self.profile, kind='fill',
                             thread_target=target)
        self.assertEqual(calls, [(self.profile.id, run.id)])
        m_notify.assert_called_once_with(run.id)

    def test_approve_thread_args_are_passed(self):
        seen = []

        def target(pid, rid, dry_run=False):
            seen.append((pid, rid, dry_run))

        with mock.patch('ess_tracker.runs.threading.Thread',
                        self.ImmediateThread):
            launch_run(profile=self.profile, kind='approve',
                       thread_target=target, thread_args=(True,),
                       use_async=False)
        self.assertEqual(seen[0][2], True)


class NotifyResultTests(TestCase):
    """Arifa za matokeo: mwenye wasifu + admins kama run ilivunjika."""

    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('mw8', password='x')
        self.profile = TeacherProfile.objects.create(user=u, full_name='M')
        u2 = get_user_model().objects.create_user('admin', password='x')
        self.admin = TeacherProfile.objects.create(user=u2, full_name='A')

    def test_admin_ids_parse(self):
        with override_settings(ESS_ADMIN_PROFILE_IDS='11, 12;13'):
            self.assertEqual(T._admin_ids(), [11, 12, 13])
        with override_settings(ESS_ADMIN_PROFILE_IDS=''):
            self.assertEqual(T._admin_ids(), [])

    def test_result_body_done_and_error(self):
        run = EssFillRun(profile=self.profile, status='done', saved=3,
                         skipped=1, not_found=2)
        self.assertIn('imeongezwa 3', T._result_body(run, 'Kujaza'))
        run2 = EssFillRun(profile=self.profile, status='error',
                          error_step='subtasks_table',
                          artifacts={'screenshot': 'ess_artifacts/x.png'})
        body = T._result_body(run2, 'Kujaza')
        self.assertIn('subtasks_table', body)
        self.assertIn('ess_artifacts/x.png', body)

    def test_done_run_notifies_owner_only(self):
        run = EssFillRun.objects.create(profile=self.profile, status='done',
                                        saved=2)
        with override_settings(ESS_ADMIN_PROFILE_IDS=str(self.admin.id)), \
                mock.patch('ess_tracker.push.push_configured',
                           return_value=True), \
                mock.patch('ess_tracker.push.send_to_profile',
                           return_value={'sent': 1}) as m_send:
            T.notify_run_result(run.id)
        self.assertEqual(m_send.call_count, 1)
        self.assertEqual(m_send.call_args.args[0], self.profile.id)

    def test_error_run_notifies_owner_and_admins(self):
        run = EssFillRun.objects.create(
            profile=self.profile, status='error', error_step='login',
            artifacts={'screenshot': 'ess_artifacts/x.png'},
            log='ERROR [login]: boom\nHINT: weka')
        with override_settings(ESS_ADMIN_PROFILE_IDS=str(self.admin.id)), \
                mock.patch('ess_tracker.push.push_configured',
                           return_value=True), \
                mock.patch('ess_tracker.push.send_to_profile',
                           return_value={'sent': 1}) as m_send:
            T.notify_run_result(run.id)
        self.assertEqual(m_send.call_count, 2)
        targets = {c.args[0] for c in m_send.call_args_list}
        self.assertEqual(targets, {self.profile.id, self.admin.id})
        admin_call = [c for c in m_send.call_args_list
                      if c.args[0] == self.admin.id][0]
        self.assertIn('login', admin_call.kwargs['body'])
        self.assertIn('ess_artifacts/x.png', admin_call.kwargs['body'])
        self.assertEqual(admin_call.kwargs['tag'], 'ess-admin-error')

    def test_error_run_skips_owner_in_admin_list(self):
        run = EssFillRun.objects.create(profile=self.profile, status='error',
                                        error_step='open')
        with override_settings(ESS_ADMIN_PROFILE_IDS=str(self.profile.id)), \
                mock.patch('ess_tracker.push.push_configured',
                           return_value=True), \
                mock.patch('ess_tracker.push.send_to_profile',
                           return_value={'sent': 1}) as m_send:
            T.notify_run_result(run.id)
        self.assertEqual(m_send.call_count, 1)
        self.assertEqual(m_send.call_args.args[0], self.profile.id)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ErrorFeedbackUITests(TestCase):
    """JSON ya status na ukurasa wa historical huonyesha error_step/artifacts."""

    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('mw9', password='x')
        self.profile = TeacherProfile.objects.create(user=u, full_name='M')
        self.run = EssFillRun.objects.create(
            profile=self.profile, status='error', kind='fill',
            error_step='subtasks_table',
            artifacts={'screenshot': 'ess_artifacts/run_1_x.png',
                       'html': 'ess_artifacts/run_1_x.html',
                       'url': 'https://ess/x'},
            log='ERROR [subtasks_table]: timeout\nHINT: angalia HTML')
        self.client.force_login(self.profile.user)

    def test_status_json_exposes_error_step_and_artifacts(self):
        data = self.client.get(f'/ess/fill/{self.run.id}/json/').json()
        self.assertEqual(data['error_step'], 'subtasks_table')
        self.assertEqual(data['artifacts']['screenshot'],
                         'ess_artifacts/run_1_x.png')
        self.assertTrue(data['done'])

    def test_fill_log_shows_badge_and_artifact_links(self):
        body = self.client.get('/ess/fill/log/').content.decode()
        self.assertIn('subtasks_table', body)
        self.assertIn('/media/ess_artifacts/run_1_x.png', body)
        self.assertIn('/media/ess_artifacts/run_1_x.html', body)

    def test_home_shows_error_banner_with_step(self):
        body = self.client.get('/ess/').content.decode()
        self.assertIn('kumeshindwa', body)
        self.assertIn('subtasks_table', body)
        self.assertIn(f'/ess/fill/{self.run.id}/', body)


class EssProbeCommandTests(TestCase):
    """ess_probe: exit 1 + artifacts pale selector inapobadilika."""

    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('mw10', password='x')
        self.profile = TeacherProfile.objects.create(
            user=u, full_name='M', ess_username='mw10', ess_password='x',
            ess_ready=True)

    def test_requires_profile_or_credentials(self):
        TeacherProfile.objects.all().delete()
        with self.assertRaises(CommandError):
            call_command('ess_probe', stdout=StringIO())

    def test_record_raises_probe_failure_on_fail(self):
        cmd = ProbeCommand()
        results = []
        with self.assertRaises(ProbeFailure):
            cmd._record(results, 'login', False, 'boom', keep_going=False)
        self.assertEqual(results[0]['status'], 'fail')
        self.assertEqual(results[0]['step'], 'login')

    def test_record_keep_going_does_not_raise(self):
        cmd = ProbeCommand()
        results = []
        cmd._record(results, 'login', False, 'boom', keep_going=True)
        self.assertEqual(results[0]['status'], 'fail')

    def test_all_pass_returns_ok(self):
        def fake_run(results, state, username, password, *, headed, keep):
            for c in PROBE_CHECKS:
                results.append({'name': c['name'], 'step': c['step'],
                                'desc': c['desc'], 'status': 'pass',
                                'detail': ''})
        with mock.patch.object(ProbeCommand, '_run_checks',
                               side_effect=fake_run):
            call_command('ess_probe', username='u', password='p',
                         stdout=StringIO())

    def test_failed_check_raises_command_error(self):
        def fake_run(results, state, username, password, *, headed, keep):
            results.append({'name': 'login', 'step': 'login', 'desc': 'x',
                            'status': 'fail', 'detail': 'boom'})
            raise ProbeFailure('login', 'boom')
        out = StringIO()
        with mock.patch.object(ProbeCommand, '_run_checks',
                               side_effect=fake_run):
            with self.assertRaises(CommandError):
                call_command('ess_probe', username='u', password='p',
                             stdout=out)
        self.assertIn('login', out.getvalue())

    def test_json_output_lists_checks(self):
        def fake_run(results, state, username, password, *, headed, keep):
            results.append({'name': 'open', 'step': 'open', 'desc': 'x',
                            'status': 'pass', 'detail': ''})
        out = StringIO()
        with mock.patch.object(ProbeCommand, '_run_checks',
                               side_effect=fake_run):
            call_command('ess_probe', username='u', password='p',
                         json=True, stdout=out)
        data = json.loads(out.getvalue())
        self.assertEqual(data['summary']['passed'], 1)
        self.assertEqual(data['checks'][0]['name'], 'open')


class OrmOffloadTests(TransactionTestCase):
    """Kuhifadhi ndani ya `sync_playwright` lazima kupitia `_orm_offload`.

    Playwright sync API huendesha asyncio loop kwenye thread ile ile ya
    kazi, hivyo Django inakataa ORM ya moja kwa moja (Run #74 ilishindwa
    hapa baada ya sub-task zote kujazwa).
    """

    def setUp(self):
        U = get_user_model()
        u = U.objects.create_user('mw_offload', password='x')
        self.profile = TeacherProfile.objects.create(
            user=u, full_name='M Offload', ess_username='mw_offload',
            ess_password='x')

    @contextmanager
    def _running_loop(self):
        import asyncio
        try:
            import greenlet
        except ImportError:
            self.skipTest('greenlet haipo')
            return
        loop = asyncio.new_event_loop()
        parent = greenlet.getcurrent()
        holder = {}

        async def boot():
            fut = loop.create_future()
            holder['fut'] = fut
            parent.switch()
            await fut

        worker = greenlet.greenlet(lambda: loop.run_until_complete(boot()))
        worker.switch()
        try:
            yield loop
        finally:
            holder['fut'].set_result(None)
            worker.switch()
            loop.close()

    def test_direct_save_is_rejected_inside_running_loop(self):
        import asyncio

        from django.core.exceptions import SynchronousOnlyOperation

        run = EssFillRun.objects.create(profile=self.profile, status='running')
        with self._running_loop() as loop:
            self.assertIs(asyncio.get_running_loop(), loop)
            with self.assertRaises(SynchronousOnlyOperation):
                run.save()

    def test_orm_offload_saves_and_returns_inside_running_loop(self):
        from ess_tracker.essfill import _orm_offload

        run = EssFillRun.objects.create(profile=self.profile, status='running')
        with self._running_loop():
            run.status = 'done'
            run.log = 'zote zimejazwa'
            _orm_offload(run.save, update_fields=['log', 'status'])
            status = _orm_offload(
                lambda: EssFillRun.objects.filter(pk=run.pk)
                .values_list('status', flat=True).get())
        self.assertEqual(status, 'done')
        run.refresh_from_db()
        self.assertEqual(run.log, 'zote zimejazwa')


class AutoApproveLeaseTests(TestCase):
    """Kipindi (lease) cha mchakato wa moja kwa moja.

    Maana: mkuu anaweka muda (mf. wiki mbili) → ndani ya muda huo mfumo
    hujamsha KILA SIKU (kujaza + kuidhinisha). Muda ukiisha, mfumo husimama
    hadi mkuu aweke upya.
    """

    def setUp(self):
        U = get_user_model()
        self.user = U.objects.create_user('mkuu_lease', password='x')
        self.profile = TeacherProfile.objects.create(
            user=self.user, full_name='Mkuu Lease', ess_username='mkuu1',
            ess_password='x', approver_enabled=True, ess_ready=True,
            auto_approve_weeks=2)
        self.now = timezone.now()
        # Anza kipindi (mwaka mzito = wiki mbili)
        from ess_tracker import tasks as T
        T.start_auto_lease(self.profile, weeks=2)
        self.profile.save(update_fields=['auto_lease_until', 'auto_lease_set_at'])

    def _run(self, when=None, source='auto', status='done',
             log='Kuanza kuidhinisha (verify) ESS...'):
        run = EssFillRun.objects.create(
            profile=self.profile, kind='approve', source=source,
            status=status, log=log)
        # `started` ni auto_now_add — tunaset manually baada ya kuunda.
        EssFillRun.objects.filter(pk=run.pk).update(started=when or self.now)
        run.refresh_from_db()
        return run

    def test_interval_days_per_weeks(self):
        from ess_tracker import tasks as T
        for weeks, days in ((0, 0), (1, 7), (2, 14), (4, 28), (12, 84)):
            self.profile.auto_approve_weeks = weeks
            self.assertEqual(T.approve_interval_days(self.profile), days)
        self.profile.auto_approve_weeks = 2
        self.assertEqual(T.approve_interval_label(self.profile),
                         'kwa wiki mbili')
        self.profile.auto_approve_weeks = 0
        self.assertEqual(T.approve_interval_label(self.profile),
                         'kila siku (hakuna mwisho)')

    def test_lease_starts_on_save_and_ends_after_14_days(self):
        from ess_tracker import tasks as T
        self.client.force_login(self.user)
        resp = self.client.post('/ess/approve/schedule/',
                                {'auto_approve_weeks': '2'})
        self.assertEqual(resp.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.auto_approve_weeks, 2)
        self.assertIsNotNone(self.profile.auto_lease_until)
        days = (self.profile.auto_lease_until - self.profile.auto_lease_set_at).days
        self.assertEqual(days, 14)
        self.assertTrue(T.approve_lease_active(self.profile))

    def test_verify_runs_every_day_inside_the_lease(self):
        """Ndani ya kipindi: kuidhinisha kila siku (siku 0, 1, 2 ... 13)."""
        from ess_tracker import tasks as T
        for d in range(0, 14):
            self.assertTrue(
                T.approve_due_for(self.profile, now=self.now + dt.timedelta(days=d)),
                msg='haipaswi kuwa due siku %d' % d)

    def test_only_one_auto_run_per_day(self):
        from ess_tracker import tasks as T
        self._run(when=self.now)
        self.assertFalse(T.approve_due_for(self.profile, now=self.now))
        self.assertTrue(
            T.approve_due_for(self.profile, now=self.now + dt.timedelta(days=1)))

    def test_lease_expired_stops_the_system(self):
        """Baada ya kipindi: mfumo husimama (hakuna verify, hakuna kujaza)."""
        from ess_tracker import tasks as T
        after = self.now + dt.timedelta(days=15)
        self.assertFalse(T.approve_lease_active(self.profile, now=after))
        self.assertFalse(T.approve_due_for(self.profile, now=after))
        st = T.approve_status(self.profile, now=after)
        self.assertTrue(st['lease_expired'])
        self.assertEqual(st['lease_days_left'], 0)
        self.assertIsNone(st['next_due'])

    def test_every_day_option_has_no_expiry(self):
        from ess_tracker import tasks as T
        self.profile.auto_approve_weeks = 0
        T.start_auto_lease(self.profile, weeks=0)
        self.assertIsNone(self.profile.auto_lease_until)
        far = self.now + dt.timedelta(days=400)
        self.assertTrue(T.approve_lease_active(self.profile, now=far))
        self.assertTrue(T.approve_due_for(self.profile, now=far))

    def test_failed_auto_run_does_not_consume_the_day(self):
        """Auto-approve iliyoshindwa hairuhusu kurudiwa siku ile ile."""
        from ess_tracker import tasks as T
        self._run(when=self.now, status='error', log='Hitilafu: timeout')
        self.assertTrue(T.approve_due_for(self.profile, now=self.now))
        st = T.approve_status(self.profile, now=self.now)
        self.assertIsNotNone(st['last_failed'])

    def test_running_run_today_blocks_a_second_run(self):
        """Run iliyosimama LEO hairuzii run ya pili ya leo."""
        from ess_tracker import tasks as T
        self._run(when=self.now, status='running', log='Umeanza...')
        self.assertFalse(T.approve_due_for(self.profile, now=self.now))

    def test_stale_running_run_does_not_block(self):
        """Run ya zamani (zamani) inaweza kureapwa; si kizuizi."""
        from ess_tracker import tasks as T
        self._run(when=self.now - dt.timedelta(days=3), status='running',
                  log='Umeanza...')
        self.assertTrue(T.approve_due_for(self.profile, now=self.now))

    def test_dry_run_does_not_consume_the_day(self):
        from ess_tracker import tasks as T
        self._run(when=self.now, log='[DRY-RUN] Uhidhinishaji umeanza...')
        self.assertTrue(T.approve_due_for(self.profile, now=self.now))

    def test_approve_page_shows_lease_and_source(self):
        self._run(when=self.now)
        self.client.force_login(self.user)
        resp = self.client.get('/ess/approve/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('kwa wiki mbili', body)
        self.assertIn('Automatic', body)  # chanzo cha run kwenye historia

    def test_approve_page_swahili_shows_period_and_daily_cycle(self):
        self._run(when=self.now)
        session = self.client.session
        session['ui_lang'] = 'sw'
        session.save()
        self.client.force_login(self.user)
        resp = self.client.get('/ess/approve/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('Mchakato wa moja kwa moja', body)
        self.assertIn('Kipindi kinaendelea hadi', body)
        self.assertIn('Kiotomatiki', body)  # noqa

    def test_expired_lease_shows_stopped_banner(self):
        from ess_tracker import tasks as T
        T.start_auto_lease(self.profile, weeks=2)
        self.profile.auto_lease_until = self.now - dt.timedelta(days=1)
        self.profile.save(update_fields=['auto_lease_until'])
        session = self.client.session
        session['ui_lang'] = 'sw'
        session.save()
        self.client.force_login(self.user)
        resp = self.client.get('/ess/approve/')
        body = resp.content.decode()
        self.assertIn('Kipindi chako kimekwisha', body)
        self.assertIn('umesimama', body)

    def test_manual_approve_always_allowed(self):
        """Mkuu anaweza kuidhinisha mwenyewe hata kama kipindi kimekwisha."""
        self.client.force_login(self.user)
        with mock.patch('ess_tracker.runs.launch_run') as launch:
            launch.return_value.id = 1
            resp = self.client.post('/ess/approve/run/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(launch.called)

    def test_manual_approve_allowed_when_lease_expired(self):
        from ess_tracker import tasks as T
        T.start_auto_lease(self.profile, weeks=2)
        self.profile.auto_lease_until = self.now - dt.timedelta(days=1)
        self.profile.save(update_fields=['auto_lease_until'])
        self.client.force_login(self.user)
        with mock.patch('ess_tracker.runs.launch_run') as launch:
            launch.return_value.id = 1
            resp = self.client.post('/ess/approve/run/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(launch.called)

    def test_dry_run_preview_is_never_blocked(self):
        self._run(when=self.now)
        self.client.force_login(self.user)
        with mock.patch('ess_tracker.runs.launch_run') as launch:
            launch.return_value.id = 1
            resp = self.client.post('/ess/approve/run/', {'dry_run': '1'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(launch.called)


class AutoApproveLeaseBlocksFillTests(TestCase):
    """Kipindi kikichisha husimamisha MFUMO KWAUTOA (kujaza na kuidhinisha).

    Ndani ya kipindi: kila siku. Baada ya kipindi: mfumo husimama hadi
    mtumiaji aweke muda upya.
    """

    def setUp(self):
        from field_app.models import District, Region, School
        U = get_user_model()
        region = Region.objects.create(name='Mkoa wa Test')
        district = District.objects.create(name='Wilaya ya Test', region=region)
        self.school = School.objects.create(name='Shule ya Test', district=district,
                                            level='Primary', ownership='government')
        self.mkuu_user = U.objects.create_user('mkuu_fill', password='x')
        self.mkuu = TeacherProfile.objects.create(
            user=self.mkuu_user, full_name='Mkuu Fill', ess_username='mk1',
            ess_password='x', approver_enabled=True, ess_ready=True,
            school=self.school, auto_approve_weeks=2)
        self.user = U.objects.create_user('mwalimu_fill', password='x')
        self.profile = TeacherProfile.objects.create(
            user=self.user, full_name='Mwalimu Fill', ess_username='mf1',
            ess_password='x', school=self.school, school_open=dt.date(2026, 1, 7),
            school_close=dt.date(2026, 12, 20), entries_per_week=3,
            auto_fill_enabled=True)
        # Jumatano (weekday=2) = siku ya kujaza kwa entries_per_week=3
        self.today = dt.date(2026, 10, 21)

    def _decision(self):
        from ess_tracker import tasks as T
        start, end = T._eat_day_bounds(self.today)
        return T.auto_fill_decision(self.profile, self.today, None, start, end)

    def _lease(self, until):
        from ess_tracker import tasks as T
        T.start_auto_lease(self.mkuu, weeks=2)
        self.mkuu.auto_lease_until = until
        self.mkuu.save(update_fields=['auto_lease_until'])

    def test_fill_runs_daily_inside_the_lease(self):
        from ess_tracker import tasks as T
        self._lease(timezone.now() + dt.timedelta(days=14))
        ready, why = self._decision()
        self.assertTrue(ready, msg='kujaza kimesitishwa: %s' % why)

    def test_expired_lease_stops_the_fill(self):
        self._lease(timezone.now() - dt.timedelta(days=1))
        ready, why = self._decision()
        self.assertFalse(ready)
        self.assertEqual(why, 'lease-expired')

    def test_teacher_without_head_teacher_is_not_blocked(self):
        """Mwalimu bila mkuu katika shule yake: hakuna kizuizi."""
        from ess_tracker import tasks as T
        self.mkuu.delete()
        ready, why = self._decision()
        self.assertTrue(ready, msg='kujaza kimesitishwa: %s' % why)
        self.assertTrue(T.fill_lease_active(self.profile))

    def test_fill_still_runs_when_approve_already_ran_today(self):
        from ess_tracker import tasks as T
        self._lease(timezone.now() + dt.timedelta(days=14))
        run = EssFillRun.objects.create(profile=self.profile, kind='fill',
                                        source='auto', status='done')
        EssFillRun.objects.filter(pk=run.pk).update(started=timezone.now())
        ready, why = self._decision()
        self.assertFalse(ready)
        self.assertEqual(why, 'already')
