import threading
from datetime import date

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .compute import (actual_for, autogen_subtasks, create_task_from_row,
                      elapsed_weeks, parse_csv_text, pct_for, target_for)
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
    """Login ya walimu kwa username+password zake Mwenyewe ZA ESS (e-Utendaji)."""
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
            messages.success(request, 'Umeingia e-Utendaji (ESS).')
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
    for task in profile.tasks.all():
        week_now = 0
        if date.today() >= task.start:
            week_now = _week_of(task, date.today())
        last_entry = WeekEntry.objects.filter(profile=profile, subtask__task=task) \
            .order_by('-week_no').first()
        tasks.append({
            'task': task,
            'subtasks': subtask_snapshot(task),
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
    return render(request, 'ess_tracker/ess_profile.html', {
        'form': form,
        'creating': creating,
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
        form = TaskForm()
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
    autogen = AutogenForm(initial={
        'vila_per_week': task.subtasks.filter(mode='periods').first().vila_per_week
        if task.subtasks.filter(mode='periods').exists() else None,
        'week_count': task.subtasks.filter(mode='periods').first().week_count
        if task.subtasks.filter(mode='periods').exists() else None,
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
        vila = form.cleaned_data.get('vila_per_week') or 0
        wc = form.cleaned_data.get('week_count') or 0
        period_target = int(round((vila or 0) * (wc or 0)))
        specs = autogen_subtasks(
            task.somo, task.kidato,
            maazimio=form.cleaned_data.get('maazimio') or 2,
            majaribio=form.cleaned_data.get('majaribio') or 5,
            mitihani=form.cleaned_data.get('mitihani') or 4,
            nukuu=form.cleaned_data.get('nukuu') or period_target,
            maandalio=period_target,
            vipindi=period_target,
            zana=form.cleaned_data.get('zana'))
        target_by_key = {
            'maazimio': form.cleaned_data.get('maazimio') or 2,
            'nukuu': form.cleaned_data.get('nukuu') or period_target,
            'maandalio': period_target,
            'zana': form.cleaned_data.get('zana') or 0,
            'kufundisha': period_target,
            'tathmini': form.cleaned_data.get('mitihani') or 4,
            'majaribio': form.cleaned_data.get('majaribio') or 5,
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

    if request.method == 'POST':
        wk_no = int(request.POST.get('week_no') or week)
        entry_date = request.POST.get('entry_date') or date.today().isoformat()
        for field, val in request.POST.items():
            if not field.startswith('amount_'):
                continue
            st_id = field.split('_', 1)[1]
            val = val.strip()
            note = request.POST.get(f'note_{st_id}', '').strip()
            if not val:
                continue
            st = SubTask.objects.filter(pk=st_id, task__profile=profile).first()
            if st is None:
                continue
            WeekEntry.objects.update_or_create(
                subtask=st, week_no=wk_no,
                defaults={'amount': _dec_or_zero(val), 'note': note,
                          'profile': profile, 'date': entry_date})
        messages.success(request, f'Wiki {wk_no} imehifadhiwa.')
        return redirect(f'{request.path}?week={wk_no}')

    rows = []
    for task in tasks:
        for snap in subtask_snapshot(task):
            st = snap['st']
            entry = WeekEntry.objects.filter(subtask=st, week_no=week).first()
            rows.append({**snap, 'entry': entry})
    return render(request, 'ess_tracker/ess_week.html', {
        'profile': profile,
        'tasks': tasks,
        'week': week,
        'rows': rows,
    })


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
    run = EssFillRun.objects.create(profile=profile)
    run.status = 'running'
    run.save()
    try:
        from .tasks import run_ess_fill
        res = run_ess_fill.apply_async(args=[profile.id, run.id], queue='default')
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
    return JsonResponse({
        'status': run.status,
        'msg': data.get('msg', ''),
        'saved': run.saved,
        'skipped': run.skipped,
        'not_found': run.not_found,
        'required': run.required,
        'done': run.status in ('done', 'error'),
        'error': '' if run.status == 'done' else run.log.splitlines()[-1] if run.log else '',
    })


@login_required(login_url=ESS_LOGIN_URL)
def ess_fill_log(request):
    profile = _me(request)
    if profile is None:
        return redirect('ess_tracker:ess_profile')
    runs = profile.fill_runs.all()[:30]
    return render(request, 'ess_tracker/ess_fill_log.html', {'profile': profile, 'runs': runs})