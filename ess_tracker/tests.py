"""Majaribio ya Schedule Guard (ratiba ya matukio na idadi ya nukuu).

Huhakikisha mfumo haujazi 100% mapema: jaribio la Novemba halionyeshwi
kama limekamilika Oktoba; nukuu hutumia idadi mwalimu aliyojaza.
"""

import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from ess_tracker import compute as C
from ess_tracker.essfill import subtask_snapshot
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
