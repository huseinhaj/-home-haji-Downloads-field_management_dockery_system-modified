import json
import threading
from datetime import date

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Prefetch, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.http import require_POST

from .compute import (actual_for, autogen_subtasks, create_task_from_row,
                      elapsed_weeks, parse_csv_text, pct_for, periods_per_week,
                      school_days, target_for)
from .essfill import CACHE_PREFIX, expected_display, subtask_snapshot
from .forms import (AutogenForm, ProfileForm, SubTaskEditForm, TaskForm,
                    TeacherRegistrationForm)
from .models import EssFillRun, SubTask, Task, TeacherProfile, WeekEntry

ESS_LOGIN_URL = '/ess/login/'


def _safe_next(request, fallback='/ess/'):
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if not next_url or next_url.startswith('http') or not next_url.startswith('/'):
        return fallback
    return next_url


def ess_login(request):
    """Login ya walimu kwa username+password zake Mwenyewe ZA ESS (e-Tendaji)."""
    if request.user.is_authenticated:
        if _me(request) is None:
            return redirect('ess_tracker:ess_profile')
        return redirect('ess_tracker:ess_home')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        profile = None
        if username:
            profile = TeacherProfile.objects.filter(
                ess_username__iexact=username).select_related('user').first()
        if profile is None:
            messages.error(request, 'Username hii ya ESS haijasajiliwa. Jisajili kwanza.')
        elif not _ess_password_ok(profile, password):
            messages.error(request, 'Password si sahihi. Jaribu tena.')
        else:
            login(request, profile.user, backend='field_app.backends.EmailBackend')
            request.session.set_expiry(60 * 60 * 24 * 30)  # wiki 4 — ingia mara moja
            messages.success(request, 'Umeingia e-Tendaji (ESS).')
            return redirect(_safe_next(request))
    return render(request, 'ess_tracker/ess_login.html', {'hide_navbar': True})


def _ess_password_ok(profile, raw: str) -> bool:
    try:
        stored = profile.ess_password_plain
    except Exception:
        return False
    from secrets import compare_digest
    return bool(stored) and compare_digest(stored, raw)


def ess_register(request):
    """Kujisajili kwa ESS username+password (akaunti ya app haitumiwi kwa email)."""
    if request.user.is_authenticated:
        return redirect('ess_tracker:ess_home')
    if request.method == 'POST':
        form = TeacherRegistrationForm(request.POST)
        if form.is_valid():
            user, profile = form.build_user_and_profile()
            login(request, user, backend='field_app.backends.EmailBackend')
            request.session.set_expiry(60 * 60 * 24 * 30)  # wiki 4 — ingia mara moja
            messages.success(request,
                             'Akaunti yako ya ESS imesajiliwa. Jaza maelezo yako zaidi kwenye wasifu.')
            return redirect('ess_tracker:ess_profile')
        messages.error(request, 'Tafadhali sahihisha makosa ya fomu.')
    else:
        form = TeacherRegistrationForm()
    return render(request, 'ess_tracker/ess_register.html', {
        'form': form,
        'hide_navbar': True,
    })


def ess_logout(request):
    logout(request)
    return redirect('ess_tracker:ess_login')


def _me(request) -> TeacherProfile | None:
    if not request.user.is_authenticated:
        return None
    try:
        return request.user.ess_profile
    except TeacherProfile.DoesNotExist:
        return None


def _week_of(task: Task, d: date) -> int:
    return int((d - task.start).days // 7) + 1


@login_required(login_url=ESS_LOGIN_URL)
def ess_home(request):
    profile = _me(request)
    if profile is None:
        return redirect('ess_tracker:ess_profile')
    tasks = []
    behind_count = 0
    for task in profile.tasks.all():
        week_now = 0
        if date.today() >= task.start:
            week_now = _week_of(task, date.today())
        last_entry = WeekEntry.objects.filter(profile=profile, subtask__task=task) \
            .order_by('-week_no').first()
        subtasks = subtask_snapshot(task)
        behind_count += sum(1 for s in subtasks if s['status'] == 'behind')
        tasks.append({
            'task': task,
            'subtasks': subtasks,
            'week_now': week_now,
            'last_week': last_entry.week_no if last_entry else 0,
            'total_actual': WeekEntry.objects.filter(profile=profile,
                                                      subtask__task=task)
            .aggregate(t=Sum('amount'))['t'] or 0,
        })
    latest_run = profile.fill_runs.first()
    return render(request, 'ess_tracker/ess_home.html', {
        'profile': profile,
        'tasks': tasks,
        'latest_run': latest_run,
        'behind_count': behind_count,
    })


@login_required(login_url=ESS_LOGIN_URL)
def ess_profile(request):
    profile = _me(request)
    creating = profile is None
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save()
            messages.success(request, 'Wasifu umehifadhiwa.')
            return redirect('ess_tracker:ess_home')
        messages.error(request, 'Tafadhali sahihisha makosa kwenye fomu.')
    else:
        form = ProfileForm(instance=profile)
    recommend = None
    if profile and not creating:
        from .compute import recommend_entries_per_week
        tasks_qs = profile.tasks.prefetch_related(
            Prefetch('subtasks',
                     queryset=SubTask.objects
                     .select_related('task__profile')
                     .prefetch_related('entries')))
        recommend = recommend_entries_per_week(profile, tasks=tasks_qs)
    return render(request, 'ess_tracker/ess_profile.html', {
        'form': form,
        'creating': creating,
        'school_days': school_days(profile) if profile else None,
        'recommend': recommend,
    })


@login_required(login_url=ESS_LOGIN_URL)
def ess_task_new(request):
    profile = _me(request)
    if profile is None:
        return redirect('ess_tracker:ess_profile')
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.profile = profile
            task.save()
            messages.success(request, 'Task imeundwa. Sasa ongeza sub-tasks.')
            return redirect('ess_tracker:ess_task_edit', task_id=task.id)
        messages.error(request, 'Makosa kwenye fomu ya Task.')
    else:
        initial = {}
        if profile.school_open and profile.school_close:
            initial = {'start': profile.school_open, 'end': profile.school_close}
        form = TaskForm(initial=initial)
    return render(request, 'ess_tracker/ess_task_new.html', {'form': form})


@login_required(login_url=ESS_LOGIN_URL)
def ess_task_edit(request, task_id):
    profile = _me(request)
    task = get_object_or_404(Task, pk=task_id, profile=profile)
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            task = form.save()
        else:
            messages.error(request, 'Makosa kwenye fomu ya Task.')
        _save_subtasks_from_forms(request, task)
        messages.success(request, 'Sub-tasks zimehifadhiwa.')
        return redirect('ess_tracker:ess_task_edit', task_id=task.id)
    form = TaskForm(instance=task)
    snapshot = subtask_snapshot(task)
    existing = task.subtasks.filter(mode='periods').first()
    autogen = AutogenForm(initial={
        'vila_per_week': existing.vila_per_week if existing
        else periods_per_week(task.somo, task.kidato),
        'week_count': existing.week_count if existing else None,
        'nukuu': task.subtasks.filter(position=2).first().target if task.subtasks.filter(position=2).exists() else None,
        'zana': task.subtasks.filter(position=4).first().target if task.subtasks.filter(position=4).exists() else None,
    })
    return render(request, 'ess_tracker/ess_task_edit.html', {
        'form': form,
        'task': task,
        'snapshot': snapshot,
        'autogen': autogen,
    })


def _save_subtasks_from_forms(request, task):
    posted = {
        k.removeprefix('desc_').removeprefix('mode_').removeprefix('target_')
        .removeprefix('vila_').removeprefix('wk_').removeprefix('base_')
        .removeprefix('del_')
        for k in request.POST
    }
    seen = set()
    for p in (p for p in posted if p.isdigit()):
        seen.add(p)
    for p in seen:
        if request.POST.get(f'del_{p}'):
            SubTask.objects.filter(task=task, pk=p).delete()
            continue
        st = SubTask.objects.filter(pk=p, task=task).first()
        if st is None:
            continue
        st.description = (request.POST.get(f'desc_{p}') or st.description).strip()
        st.mode = request.POST.get(f'mode_{p}') or st.mode
        st.target = _dec_or_zero(request.POST.get(f'target_{p}'))
        st.vila_per_week = _dec_or_zero(request.POST.get(f'vila_{p}'))
        st.week_count = int(request.POST.get(f'wk_{p}') or 0)
        st.actual_base = _dec_or_zero(request.POST.get(f'base_{p}'))
        st.save()


def _dec_or_zero(v):
    try:
        from decimal import Decimal as D
        return D(str(v)) if v not in (None, '') else D('0')
    except Exception:
        return D('0')


@login_required
@require_POST
def ess_autogen(request, task_id):
    """Tengeneza sub-tasks 7 za kawaida (kwa fomu autogen)."""
    profile = _me(request)
    task = get_object_or_404(Task, pk=task_id, profile=profile)
    form = AutogenForm(request.POST)
    if form.is_valid():
        vila = form.cleaned_data.get('vila_per_week') or periods_per_week(task.somo, task.kidato) or 0
        wc = form.cleaned_data.get('week_count') or 0
        period_target = int(round((vila or 0) * (wc or 0)))
        nukuu_count = form.cleaned_data.get('nukuu')
        specs = autogen_subtasks(
            task.somo, task.kidato,
            maazimio=form.cleaned_data.get('maazimio') or 1,
            majaribio=form.cleaned_data.get('majaribio') or 6,
            mitihani=form.cleaned_data.get('mitihani') or 4,
            nukuu=nukuu_count,
            maandalio=period_target,
            vipindi=period_target,
            zana=form.cleaned_data.get('zana'))
        target_by_key = {
            'maazimio': form.cleaned_data.get('maazimio') or 1,
            'nukuu': nukuu_count or 0,
            'maandalio': period_target,
            'zana': form.cleaned_data.get('zana') or 0,
            'kufundisha': period_target,
            'mitihani': form.cleaned_data.get('mitihani') or 4,
            'majaribio': form.cleaned_data.get('majaribio') or 6,
        }
        for item in specs:
            periods = item['mode'] == 'periods'
            SubTask.objects.update_or_create(
                task=task, position=item['position'],
                defaults={'description': item['text'], 'mode': item['mode'],
                          'target': target_by_key.get(item['key'], 0),
                          'vila_per_week': vila if periods else 0,
                          'week_count': wc if periods else 0})
        messages.success(request, 'Sub-tasks 7 za kawaida zimetengenezwa.')
    else:
        messages.error(request, 'Makosa kwenye vigezo vya kuzalisha sub-tasks.')
    return redirect('ess_tracker:ess_task_edit', task_id=task.id)


@login_required
@require_POST
def ess_task_delete(request, task_id):
    profile = _me(request)
    task = get_object_or_404(Task, pk=task_id, profile=profile)
    task.delete()
    messages.success(request, 'Task imefutwa.')
    return redirect('ess_tracker:ess_home')


@login_required(login_url=ESS_LOGIN_URL)
def ess_week(request):
    profile = _me(request)
    if profile is None:
        return redirect('ess_tracker:ess_profile')
    tasks = list(profile.tasks.all())
    if not tasks:
        messages.info(request, 'Unda Task kwanza kisha uweze kuingiza wiki.')
        return redirect('ess_tracker:ess_task_new')

    week = int(request.GET.get('week') or 0)
    if week <= 0:
        first = tasks[0]
        week = _week_of(first, date.today()) if date.today() >= first.start else 1

    all_sts = SubTask.objects.filter(task__profile=profile) \
        .exclude(mode='annual').order_by('task__start', 'position')

    if request.method == 'POST':
        week_no = int(request.POST.get('week_no') or week)
        acc = {}
        for i in range(len(request.POST)):
            st_id = request.POST.get(f's_{i}', '').strip()
            amt = request.POST.get(f'a_{i}', '').strip()
            if not st_id or not amt:
                continue
            st = SubTask.objects.filter(pk=st_id, task__profile=profile).first()
            if st is None:
                continue
            d = _parse_date(request.POST.get(f'd_{i}', ''), default=date.today())
            note = request.POST.get(f'n_{i}', '').strip()
            wk = _week_of(st.task, d) if d else week_no
            key = (st.id, d)
            if key in acc:
                acc[key]['amount'] += _dec_or_zero(amt)
                if note:
                    acc[key]['note'] = (acc[key]['note'] + '; ' + note) if acc[key]['note'] else note
            else:
                acc[key] = {'amount': _dec_or_zero(amt), 'note': note,
                            'week_no': wk, 'profile': profile, 'st': st}
        for (st_id, d), v in acc.items():
            WeekEntry.objects.update_or_create(
                subtask_id=st_id, date=d,
                defaults={'week_no': v['week_no'], 'amount': v['amount'],
                          'note': v['note'], 'profile': profile})
        deleted = 0
        for key, val in request.POST.items():
            if not key.startswith('del_'):
                continue
            if val == 'on':
                WeekEntry.objects.filter(
                    pk=key.split('_', 1)[1], profile=profile).delete()
                deleted += 1
        msgs = []
        amount_rows = len(acc)
        if amount_rows:
            msgs.append(f'Viingilio {amount_rows} vimehifadhiwa.')
        if deleted:
            msgs.append(f'Vimefutwa: {deleted}.')
        (messages.success(request, ' '.join(msgs) or 'Hakuna kilichohifadhiwa.')
         if msgs else messages.info(request, 'Hakuna kilichohifadhiwa.'))
        return redirect(f'{request.path}?week={week}')

    entries = list(WeekEntry.objects.filter(profile=profile, week_no=week)
                   .select_related('subtask__task').order_by('-date', '-created_at'))
    return render(request, 'ess_tracker/ess_week.html', {
        'profile': profile,
        'tasks': tasks,
        'week': week,
        'subtasks': all_sts,
        'entries': entries,
    })


def _parse_date(val, default=None):
    from .compute import parse_date as _pd
    d = _pd(val)
    return d or default


@login_required(login_url=ESS_LOGIN_URL)
def ess_csv(request):
    profile = _me(request)
    if profile is None:
        return redirect('ess_tracker:ess_profile')
    if request.method == 'POST':
        text = request.POST.get('csv_text', '')
        if 'csv_file' in request.FILES:
            text += '\n' + request.FILES['csv_file'].read().decode('utf-8-sig', errors='replace')
        rows = parse_csv_text(text)
        if not rows:
            messages.error(request, 'Hakuna safu yenye "somo" — hakiki faili.')
        else:
            made = 0
            for row in rows:
                if create_task_from_row(profile, row):
                    made += 1
            messages.success(request, f'Tasks {made} zimeingizwa (safu {len(rows)}).')
        return redirect('ess_tracker:ess_home')
    return render(request, 'ess_tracker/ess_csv.html', {'profile': profile})


@login_required
@require_POST
def ess_fill(request):
    profile = _me(request)
    if profile is None:
        return redirect('ess_tracker:ess_profile')
    if not profile.ess_ready:
        messages.error(request, 'Weka kwanza ESS username na password kwenye wasifu.')
        return redirect('ess_tracker:ess_profile')
    from .runstate import reap_stale_runs
    reap_stale_runs(profile)
    existing = profile.fill_runs.filter(kind='fill', status='running').first()
    if existing:
        messages.info(request, 'Kujaza kunaendelea tayari kwa mwalimu huyu — subiri kukamilika.')
        return redirect('ess_tracker:ess_fill_status', run_id=existing.id)
    selected = []
    for raw in request.POST.getlist('subtasks'):
        if str(raw).isdigit():
            selected.append(int(raw))
    run = EssFillRun.objects.create(profile=profile)
    run.only_subtasks = ','.join(str(i) for i in sorted(set(selected)))
    run.status = 'running'
    run.save()
    try:
        from .tasks import run_ess_fill
        res = run_ess_fill.apply_async(args=[profile.id, run.id], queue='essfill')
        run.task_id = res.id
        run.save()
        started = True
    except Exception:
        started = False
    if not started:
        threading.Thread(target=_run_in_thread, args=(profile.id, run.id), daemon=True).start()
    cache.set(CACHE_PREFIX + str(run.id), {'msg': 'Inaanzisha...', 'step': 0,
                                           'done': False, 'error': ''}, timeout=3600)
    return redirect('ess_tracker:ess_fill_status', run_id=run.id)


def _run_in_thread(profile_id, run_id):
    from .essfill import run_fill
    run_fill(profile_id, run_id)


@login_required
@require_POST
def ess_sync_names(request):
    """Chukua majina ya task/sub-task kutoka official ESS na usawazishe local."""
    profile = _me(request)
    if profile is None:
        return redirect('ess_tracker:ess_profile')
    if not profile.ess_ready:
        messages.error(request, 'Weka kwanza ESS username na password kwenye wasifu.')
        return redirect('ess_tracker:ess_profile')
    run = EssFillRun.objects.create(profile=profile, kind='sync')
    run.status = 'running'
    run.save()
    try:
        from .tasks import run_ess_sync
        res = run_ess_sync.apply_async(args=[profile.id, run.id], queue='essfill')
        run.task_id = res.id
        run.save()
        started = True
    except Exception:
        started = False
    if not started:
        threading.Thread(target=_run_sync_in_thread,
                         args=(profile.id, run.id), daemon=True).start()
    cache.set(CACHE_PREFIX + str(run.id), {'msg': 'Inaanzisha...', 'step': 0,
                                           'done': False, 'error': ''}, timeout=3600)
    return redirect('ess_tracker:ess_fill_status', run_id=run.id)


def _run_sync_in_thread(profile_id, run_id):
    from .essfill import run_sync
    run_sync(profile_id, run_id)


@login_required
@require_POST
def ess_read_pcts(request):
    """Soma asilimia HALISI za sub-task kutoka ESS official (bila kujaza)."""
    profile = _me(request)
    if profile is None:
        return redirect('ess_tracker:ess_profile')
    if not profile.ess_ready:
        messages.error(request, 'Weka kwanza ESS username na password kwenye wasifu.')
        return redirect('ess_tracker:ess_profile')
    run = EssFillRun.objects.create(profile=profile, kind='read')
    run.status = 'running'
    run.save()
    try:
        from .tasks import run_ess_read
        res = run_ess_read.apply_async(args=[profile.id, run.id], queue='essfill')
        run.task_id = res.id
        run.save()
        started = True
    except Exception:
        started = False
    if not started:
        threading.Thread(target=_run_read_in_thread,
                         args=(profile.id, run.id), daemon=True).start()
    cache.set(CACHE_PREFIX + str(run.id), {'msg': 'Inaanzisha...', 'step': 0,
                                           'done': False, 'error': ''}, timeout=3600)
    return redirect('ess_tracker:ess_fill_status', run_id=run.id)


def _run_read_in_thread(profile_id, run_id):
    from .essfill import run_read
    run_read(profile_id, run_id)


@login_required
@require_POST
def ess_push_names(request):
    """Tuma majina ya local kwenda ESS official (badilisha yanayotofautiana)."""
    profile = _me(request)
    if profile is None:
        return redirect('ess_tracker:ess_profile')
    if not profile.ess_ready:
        messages.error(request, 'Weka kwanza ESS username na password kwenye wasifu.')
        return redirect('ess_tracker:ess_profile')
    run = EssFillRun.objects.create(profile=profile, kind='push')
    run.status = 'running'
    run.save()
    try:
        from .tasks import run_ess_push
        res = run_ess_push.apply_async(args=[profile.id, run.id], queue='essfill')
        run.task_id = res.id
        run.save()
        started = True
    except Exception:
        started = False
    if not started:
        threading.Thread(target=_run_push_in_thread,
                         args=(profile.id, run.id), daemon=True).start()
    cache.set(CACHE_PREFIX + str(run.id), {'msg': 'Inaanzisha...', 'step': 0,
                                           'done': False, 'error': ''}, timeout=3600)
    return redirect('ess_tracker:ess_fill_status', run_id=run.id)


def _run_push_in_thread(profile_id, run_id):
    from .essfill import run_push
    run_push(profile_id, run_id)


@login_required(login_url=ESS_LOGIN_URL)
def ess_fill_status(request, run_id):
    run = get_object_or_404(EssFillRun, pk=run_id)
    if request.user != run.profile.user and not request.user.is_staff:
        return redirect('ess_tracker:ess_home')
    return render(request, 'ess_tracker/ess_fill_status.html', {'run': run})


@login_required(login_url=ESS_LOGIN_URL)
def ess_fill_status_json(request, run_id):
    run = get_object_or_404(EssFillRun, pk=run_id)
    if request.user != run.profile.user and not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    data = cache.get(CACHE_PREFIX + str(run.id)) or {}
    run_log = data.get('log')
    if not run_log:
        run_log = run.log.splitlines() if run.log else []
    return JsonResponse({
        'status': run.status,
        'msg': data.get('msg', ''),
        'saved': run.saved,
        'skipped': run.skipped,
        'not_found': run.not_found,
        'required': run.required,
        'done': run.status in ('done', 'error'),
        'error': '' if run.status == 'done' else run.log.splitlines()[-1] if run.log else '',
        'log': run_log,
    })


@login_required(login_url=ESS_LOGIN_URL)
def ess_fill_log(request):
    profile = _me(request)
    if profile is None:
        return redirect('ess_tracker:ess_profile')
    from .runstate import reap_stale_runs
    reap_stale_runs(profile)
    runs = profile.fill_runs.all()[:30]
    return render(request, 'ess_tracker/ess_fill_log.html', {'profile': profile, 'runs': runs})


def ess_manifest(request):
    """Manifest ya PWA (icona zinatumia {% static %} hivyo hash inafuata)."""
    data = {
        'id': '/ess/',
        'name': 'e-Tendaji — Kujaza ESS',
        'short_name': 'e-Tendaji',
        'description': 'Kujaza maendeleo ya e-Utendaji (ESS) kiotomatiki.',
        'start_url': '/ess/',
        'scope': '/ess/',
        'display': 'standalone',
        'display_override': ['window-controls-overlay', 'standalone', 'minimal-ui'],
        # 'any' ili isilazimishe mwelekeo — Android na Desktop vinautumia sawa.
        'orientation': 'any',
        'background_color': '#F0F5F9',
        'theme_color': '#1F41BB',
        'lang': 'sw',
        'dir': 'ltr',
        'categories': ['education', 'productivity', 'government'],
        'prefer_related_applications': False,
        'icons': [
            {'src': static('ess/icon-192.png'), 'sizes': '192x192',
             'type': 'image/png', 'purpose': 'any'},
            {'src': static('ess/icon-512.png'), 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'any'},
            {'src': static('ess/icon-512.png'), 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'maskable'},
        ],
        'shortcuts': [
            {'name': 'Jaza ESS sasa', 'short_name': 'Jaza',
             'url': '/ess/', 'icons': [
                 {'src': static('ess/icon-192.png'), 'sizes': '192x192'}]},
            {'name': 'Rekodi wiki', 'short_name': 'Rekodi',
             'url': '/ess/week/'},
        ],
    }
    return HttpResponse(json.dumps(data), content_type='application/manifest+json')


def ess_sw(request):
    """Service worker ya PWA (offline cache + arifa za push)."""
    js = """
const CACHE = 'ess-v2';
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/ess/fill/')) return;
  e.respondWith(
    fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match(req))
  );
});
self.addEventListener('push', (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (err) {}
  const title = data.title || 'e-Tendaji';
  e.waitUntil(self.registration.showNotification(title, {
    body: data.body || '',
    icon: data.icon || undefined,
    badge: data.badge || undefined,
    tag: data.tag || 'ess',
    renotify: !!data.renotify,
    data: { url: data.url || '/ess/' },
  }));
});
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/ess/';
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const c of all) {
      if (c.url.indexOf('/ess/') !== -1 && 'focus' in c) {
        if (c.navigate) await c.navigate(url);
        return c.focus();
      }
    }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  })());
});
""".strip()
    resp = HttpResponse(js, content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/ess/'
    resp['Cache-Control'] = 'no-cache'
    return resp


def ess_push_key(request):
    """VAPID public key kwa JS ili kujiandikisha kupokea arifa."""
    from django.conf import settings
    key = getattr(settings, 'VAPID_PUBLIC_KEY', '')
    return JsonResponse({'enabled': bool(key), 'key': key})


@login_required(login_url=ESS_LOGIN_URL)
@require_POST
def ess_push_subscribe(request):
    """Hifadhi subscription ya kifaa cha mwalimu (Web Push)."""
    from .models import PushSubscription
    profile = _me(request)
    if profile is None:
        return JsonResponse({'ok': False, 'error': 'no-profile'}, status=400)
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'bad-json'}, status=400)
    endpoint = (data.get('endpoint') or '').strip()
    keys = data.get('keys') or {}
    p256dh = (keys.get('p256dh') or '').strip()
    auth = (keys.get('auth') or '').strip()
    if not (endpoint and p256dh and auth):
        return JsonResponse({'ok': False, 'error': 'missing-fields'}, status=400)
    sub, _ = PushSubscription.objects.update_or_create(
        endpoint=endpoint[:500],
        defaults={
            'profile': profile,
            'p256dh': p256dh[:200],
            'auth': auth[:100],
            'user_agent': (request.META.get('HTTP_USER_AGENT') or '')[:300],
            'active': True,
            'last_seen': timezone.now(),
        })
    return JsonResponse({'ok': True, 'id': sub.id})


@login_required(login_url=ESS_LOGIN_URL)
@require_POST
def ess_push_unsubscribe(request):
    """Zima arifa za kifaa hiki."""
    from .models import PushSubscription
    profile = _me(request)
    if profile is None:
        return JsonResponse({'ok': False, 'error': 'no-profile'}, status=400)
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        data = {}
    endpoint = (data.get('endpoint') or '').strip()
    qs = profile.push_subscriptions.all()
    if endpoint:
        qs = qs.filter(endpoint=endpoint)
    deleted = qs.delete()[0]
    return JsonResponse({'ok': True, 'deleted': deleted})


@login_required(login_url=ESS_LOGIN_URL)
@require_POST
def ess_push_test(request):
    """Tuma arifa ya jaribio kwa vifaa vya mwalimu mwenyewe."""
    from .push import push_configured, send_to_profile
    profile = _me(request)
    if profile is None:
        return JsonResponse({'ok': False, 'error': 'no-profile'}, status=400)
    if not push_configured():
        return JsonResponse({'ok': False, 'error': 'not-configured'}, status=400)
    res = send_to_profile(profile, title='e-Tendaji: jaribio la arifa',
                          body='Arifa zinafanya kazi. Utapata kumbukumbu siku za kujaza.',
                          url='/ess/', tag='ess-test', renotify=True)
    return JsonResponse({'ok': True, 'result': res})