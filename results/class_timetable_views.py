"""class_timetable_views.py — weekly class/teaching timetable: period
setup, teacher/subject assignment, AI-free generation (see
services/class_timetable_service.py for why this is a deterministic
algorithm, not an LLM prompt), display, and single-cell manual edit.

The timetable is a standing weekly template (ClassTimetableEntry) — not
tied to a calendar date — that applies every week until an academic
officer regenerates the classes affected by a change (new teacher,
dropped subject, etc.) or hand-edits a single lesson.
"""
from datetime import datetime

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import ClassTimetableEntry, Subject, TeacherAccount, TeachingAssignment, TimeSlot
from .permissions import academic_required, teacher_or_academic_required
from .services.class_timetable_service import (
    TimetableConflict,
    auto_populate_teaching_assignments,
    generate_class_timetable,
    save_class_timetable,
    seed_default_time_slots,
    set_single_cell,
)
from .services.ai_timetable_service import (
    generate_ai_suggestion,
    parse_natural_language_instructions,
)

FORM_CHOICES = [1, 2, 3, 4, 5, 6]


def _school_or_none(request):
    school = request.user.school
    if not school:
        messages.error(request, "Hakuna shule iliyowekwa kwenye akaunti yako.")
    return school


@academic_required
def time_slot_setup(request):
    """One-time (or occasional) setup of the daily period grid — shared
    by every class at this school."""
    school = _school_or_none(request)
    if school is None:
        return redirect('school_setup')

    if request.method == 'POST':
        if request.POST.get('action') == 'delete':
            TimeSlot.objects.filter(id=request.POST.get('slot_id'), school=school).delete()
            messages.success(request, "Kipindi kimeondolewa.")
            return redirect('time_slot_setup')

        if request.POST.get('action') == 'default_template':
            if TimeSlot.objects.filter(school=school).exists():
                messages.error(
                    request,
                    "Tayari una vipindi vilivyowekwa. Futa vipindi vyote kwanza kama unataka kuanza upya na muundo wa kawaida.",
                )
                return redirect('time_slot_setup')
            created = seed_default_time_slots(school)
            messages.success(request, f"Muundo wa kawaida umewekwa — vipindi {created} vya Jumatatu–Ijumaa.")
            return redirect('time_slot_setup')

        try:
            day = int(request.POST.get('day_of_week'))
            order = int(request.POST.get('order'))
            start_time = datetime.strptime(request.POST.get('start_time', ''), '%H:%M').time()
            end_time = datetime.strptime(request.POST.get('end_time', ''), '%H:%M').time()
        except (TypeError, ValueError):
            messages.error(request, "Muda au mpangilio wa kipindi si sahihi.")
            return redirect('time_slot_setup')

        is_teaching = request.POST.get('is_teaching_slot') == 'on'
        label = request.POST.get('label', '').strip()
        TimeSlot.objects.update_or_create(
            school=school, day_of_week=day, order=order,
            defaults={
                'start_time': start_time,
                'end_time': end_time,
                'is_teaching_slot': is_teaching,
                'label': '' if is_teaching else label,
            },
        )
        messages.success(request, "Kipindi kimehifadhiwa.")
        return redirect('time_slot_setup')

    slots_by_day = {}
    for slot in TimeSlot.objects.filter(school=school).order_by('day_of_week', 'order'):
        slots_by_day.setdefault(slot.day_of_week, []).append(slot)

    return render(request, 'results/time_slot_setup.html', {
        'slots_by_day': slots_by_day,
        'day_choices': TimeSlot.DAY_CHOICES,
    })


@academic_required
def teaching_assignment_manage(request):
    """Which teacher teaches which subject to which class (form+stream),
    and how many periods/week — the raw material the generator schedules."""
    school = _school_or_none(request)
    if school is None:
        return redirect('school_setup')

    if request.method == 'POST':
        if request.POST.get('action') == 'delete':
            TeachingAssignment.objects.filter(id=request.POST.get('assignment_id'), school=school).delete()
            messages.success(request, "Ugawaji umeondolewa.")
            return redirect('teaching_assignment_manage')

        if request.POST.get('action') == 'auto_populate':
            created, skipped = auto_populate_teaching_assignments(school)
            if created:
                messages.success(
                    request,
                    f"Ugawaji {created} umejazwa kiotomatiki kutoka 'Assign Mwalimu kwa Form'. "
                    "Kagua/rekebisha stream na vipindi/wiki kwa kila mmoja kabla ya kutengeneza ratiba.",
                )
            if skipped:
                messages.info(request, f"Ugawaji {skipped} tayari ulikuwepo — haukubadilishwa.")
            if not created and not skipped:
                messages.warning(request, "Hakuna 'Assign Mwalimu kwa Form' ya kujazia — weka angalau moja kwanza.")
            return redirect('teaching_assignment_manage')

        teacher = TeacherAccount.objects.filter(id=request.POST.get('teacher_id'), school=school).first()
        subject = Subject.objects.filter(id=request.POST.get('subject_id')).first()
        form_num = request.POST.get('form')
        stream = (request.POST.get('stream') or '').strip().upper()[:2]
        try:
            periods = max(1, int(request.POST.get('periods_per_week') or 4))
        except ValueError:
            periods = 4
        double_period = request.POST.get('double_period') == 'on'

        if not (teacher and subject and form_num):
            messages.error(request, "Taarifa hazijakamilika — chagua mwalimu, somo na form.")
            return redirect('teaching_assignment_manage')

        TeachingAssignment.objects.update_or_create(
            school=school, form=int(form_num), stream=stream, subject=subject,
            defaults={'teacher': teacher, 'periods_per_week': periods, 'double_period': double_period},
        )
        label = f"Form {form_num}{stream}" if stream else f"Form {form_num}"
        messages.success(request, f"{teacher.full_name or teacher.email} amewekwa {label} — {subject.name} ({periods}x/wiki).")
        return redirect('teaching_assignment_manage')

    teachers = TeacherAccount.objects.filter(school=school, role=TeacherAccount.ROLE_TEACHER).order_by('full_name')
    subjects = Subject.objects.all().order_by('name')
    assignments = TeachingAssignment.objects.filter(school=school).select_related('teacher', 'subject').order_by('form', 'stream', 'subject__name')

    return render(request, 'results/teaching_assignment_manage.html', {
        'teachers': teachers,
        'subjects': subjects,
        'assignments': assignments,
        'form_choices': FORM_CHOICES,
    })


@academic_required
def generate_class_timetable_view(request):
    """GET: shows the generate button + which classes have assignments.
    POST action=generate: runs the algorithm and shows a preview — nothing
    is saved until the officer reviews it and hits Save.

    POST action=generate_single: generates one class at a time (AI-style).
    POST action=ai_parse: parses natural language instructions via AI."""
    school = _school_or_none(request)
    if school is None:
        return redirect('school_setup')

    preview_rows = None
    unplaced = None
    error = None
    ai_constraints = None
    ai_instruction_text = ''
    ai_suggestions = []
    selected_class = None

    if request.method == 'POST':
        action = request.POST.get('action', '')
        ai_instruction_text = request.POST.get('ai_instruction', '').strip()

        if action == 'generate' or action == 'generate_single':
            # Parse AI instructions if provided
            if ai_instruction_text:
                subject_names = list(
                    TeachingAssignment.objects.filter(school=school)
                    .values_list('subject__name', flat=True).distinct()
                )
                parsed = parse_natural_language_instructions(
                    ai_instruction_text, available_subjects=subject_names
                )
                ai_constraints = parsed.get('constraints', [])

            # Determine form_streams to generate
            form_streams = None
            if action == 'generate_single':
                gen_form = request.POST.get('gen_form')
                gen_stream = (request.POST.get('gen_stream') or '').strip().upper()
                if gen_form:
                    form_streams = [(int(gen_form), gen_stream)]
                    selected_class = (int(gen_form), gen_stream)

            try:
                preview, unplaced = generate_class_timetable(
                    school, form_streams=form_streams, constraints=ai_constraints
                )
            except TimetableConflict as exc:
                error = str(exc)
            else:
                subjects_by_id = {s.id: s for s in Subject.objects.all()}
                teachers_by_id = {t.id: t for t in TeacherAccount.objects.filter(school=school)}
                slots_by_id = {slot.id: slot for slot in TimeSlot.objects.filter(school=school)}
                preview_rows = []
                for e in preview:
                    slot = slots_by_id.get(e['time_slot_id'])
                    preview_rows.append({
                        'form': e['form'],
                        'stream': e['stream'],
                        'day': slot.get_day_of_week_display() if slot else '?',
                        'time': f"{slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}" if slot else '?',
                        'subject': subjects_by_id.get(e['subject_id']),
                        'teacher': teachers_by_id.get(e['teacher_id']),
                        'time_slot_id': e['time_slot_id'],
                        'subject_id': e['subject_id'],
                        'teacher_id': e['teacher_id'],
                    })
                preview_rows.sort(key=lambda r: (r['form'], r['stream']))

                # Get AI suggestions for improvement
                if preview:
                    try:
                        suggestion_result = generate_ai_suggestion(school, preview)
                        ai_suggestions = suggestion_result.get('suggestions', [])
                    except Exception:
                        pass  # suggestions are best-effort

    class_keys = sorted({
        (a.form, a.stream)
        for a in TeachingAssignment.objects.filter(school=school).only('form', 'stream')
    })

    return render(request, 'results/generate_class_timetable.html', {
        'class_keys': class_keys,
        'preview_rows': preview_rows,
        'unplaced': unplaced,
        'error': error,
        'has_existing': ClassTimetableEntry.objects.filter(school=school).exists(),
        'ai_instruction_text': ai_instruction_text,
        'ai_constraints': ai_constraints or [],
        'ai_suggestions': ai_suggestions,
        'selected_class': selected_class,
    })


@academic_required
@require_POST
def save_class_timetable_view(request):
    school = _school_or_none(request)
    if school is None:
        return redirect('school_setup')

    forms = request.POST.getlist('form[]')
    streams = request.POST.getlist('stream[]')
    slot_ids = request.POST.getlist('time_slot_id[]')
    subject_ids = request.POST.getlist('subject_id[]')
    teacher_ids = request.POST.getlist('teacher_id[]')

    if not forms or not (len(forms) == len(streams) == len(slot_ids) == len(subject_ids) == len(teacher_ids)):
        messages.error(request, "Ratiba haikutumwa vizuri. Jaribu kutengeneza tena.")
        return redirect('generate_class_timetable')

    entries = [
        {'form': int(f), 'stream': s, 'time_slot_id': int(slot), 'subject_id': int(subj), 'teacher_id': int(t)}
        for f, s, slot, subj, t in zip(forms, streams, slot_ids, subject_ids, teacher_ids)
    ]
    saved = save_class_timetable(school, entries)
    messages.success(request, f"Ratiba imehifadhiwa — vipindi {saved} vimewekwa.")
    return redirect('class_timetable_view')


@teacher_or_academic_required
def class_timetable_view(request):
    """The standing, printable weekly timetable for every (form, stream)
    this school has teaching assignments (or already-saved entries) for."""
    school = _school_or_none(request)
    if school is None:
        return redirect('school_setup')

    slots = list(TimeSlot.objects.filter(school=school).order_by('day_of_week', 'order'))
    entries = ClassTimetableEntry.objects.filter(school=school).select_related('subject', 'teacher')
    entry_map = {(e.form, e.stream, e.time_slot_id): e for e in entries}

    class_keys = sorted({
        (a.form, a.stream)
        for a in TeachingAssignment.objects.filter(school=school).only('form', 'stream')
    })
    if not class_keys:
        class_keys = sorted({(e.form, e.stream) for e in entries})

    grid = []
    for day, day_label in TimeSlot.DAY_CHOICES:
        day_slots = [s for s in slots if s.day_of_week == day]
        if not day_slots:
            continue
        rows = []
        for form, stream in class_keys:
            cells = [
                {'slot': slot, 'entry': entry_map.get((form, stream, slot.id)) if slot.is_teaching_slot else None}
                for slot in day_slots
            ]
            rows.append({'form': form, 'stream': stream, 'cells': cells})
        grid.append({'day_label': day_label, 'slots': day_slots, 'rows': rows})

    subjects = Subject.objects.all().order_by('name')
    teachers = TeacherAccount.objects.filter(school=school).order_by('full_name')

    return render(request, 'results/class_timetable_view.html', {
        'grid': grid,
        'has_timetable': entries.exists(),
        'is_academic': getattr(request.user, 'is_academic', False),
        'subjects': subjects,
        'teachers': teachers,
    })


@academic_required
@require_POST
def delete_class_timetable(request):
    """Delete ALL ClassTimetableEntry rows for this school — a full reset
    so the academic officer can regenerate from scratch."""
    school = _school_or_none(request)
    if school is None:
        return redirect('school_setup')

    count = ClassTimetableEntry.objects.filter(school=school).delete()[0]
    messages.success(request, f"Ratiba yote ya darasa imefutwa (vipindi {count} vimeondolewa).")
    return redirect('class_timetable_view')


@academic_required
@require_POST
def class_timetable_cell_edit(request):
    """Hand-edit one lesson — the common case for a single teacher/subject
    swap — without regenerating the rest of the timetable."""
    school = _school_or_none(request)
    if school is None:
        return JsonResponse({'error': 'Hakuna shule.'}, status=400)

    try:
        form = int(request.POST.get('form'))
        stream = request.POST.get('stream') or ''
        time_slot_id = int(request.POST.get('time_slot_id'))
        subject_id = int(request.POST.get('subject_id'))
        teacher_id = int(request.POST.get('teacher_id'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Taarifa si sahihi.'}, status=400)

    try:
        set_single_cell(
            school, form=form, stream=stream, time_slot_id=time_slot_id,
            subject_id=subject_id, teacher_id=teacher_id,
        )
    except TimetableConflict as exc:
        return JsonResponse({'error': str(exc)}, status=409)

    return JsonResponse({'success': True})
