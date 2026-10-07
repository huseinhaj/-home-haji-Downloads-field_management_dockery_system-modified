"""
Afisa Wilaya (Halmashauri) — joint exams za shule zote za wilaya.

Afisa (TeacherAccount.ROLE_DISTRICT):
  /shule/wilaya/                          dashibodi: joint exams za wilaya yake
  /shule/wilaya/joint/mpya/               kuunda joint exam (masomo + shule)
  /shule/wilaya/joint/<id>/               maendeleo + ranking ya shule zote
  /shule/wilaya/joint/<id>/excel/         Excel ya Halmashauri (shule zote pamoja)
  /shule/wilaya/joint/<id>/fungua/        kufungua/kufunga matokeo kwa shule
  /shule/wilaya/shule/                    kata + umiliki wa kila shule

Shule (Mtaaluma/Mwalimu wa shule inayoshiriki):
  /shule/exam/<exam_id>/wilaya/           performance ya shule zote za wilaya

Umma (bila login — kama NECTA, baada ya afisa kuyafungua):
  /shule/wilaya/<joint_id>/matokeo/       chagua herufi → shule zinazoanzia nayo
  /shule/wilaya/<joint_id>/matokeo/<id>/  matokeo kamili ya shule hiyo
"""
import datetime

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .district_models import (
    JointExam, district_key, district_program_name, is_empty_placeholder,
    joints_for_school, schools_in_district,
)
from .models import Exam, ExamResult, ProcessedResult, School, Subject
from .permissions import _role_required, academic_required, teacher_or_academic_required
from .services.joint_analysis import analyse_joint_exam
from .utils import get_grade_for_exam, get_grade_primary

district_officer_required = _role_required(
    lambda user: getattr(user, 'is_district_officer', False),
    "District Education Officer access required.",
)

# Masomo ya O-Level yanayochaguliwa moja kwa moja kwenye fomu ya joint mpya
DEFAULT_SUBJECTS = [
    'Civics', 'History', 'Geography', 'Kiswahili', 'English', 'English Language',
    'Physics', 'Chemistry', 'Biology', 'Basic Mathematics', 'Mathematics',
    'Historia ya Tanzania na Maadili', 'Business Studies', 'Agriculture',
]


def _officer_joint_or_404(request, joint_id):
    joint = get_object_or_404(JointExam, pk=joint_id)
    user = request.user
    if joint.district.strip().lower() != (user.district or '').strip().lower():
        raise Http404('Joint exam si ya wilaya yako.')
    return joint


@district_officer_required
def district_dashboard(request):
    user = request.user
    joints = JointExam.objects.filter(district__iexact=user.district)
    schools = schools_in_district(user.district, user.region)
    missing_info = schools.filter(ownership='').count() + schools.filter(ward='').count()
    return render(request, 'results/district/dashboard.html', {
        'joints': joints,
        'school_count': schools.count(),
        'joined_count': schools.filter(joint_member=True).count(),
        'missing_info': missing_info,
    })


@district_officer_required
def joint_exam_create(request):
    user = request.user
    schools = list(schools_in_district(user.district, user.region).order_by('name'))
    subjects = list(Subject.objects.order_by('name'))

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        try:
            form = int(request.POST.get('form') or 0)
            year = int(request.POST.get('year') or 0)
        except ValueError:
            form = year = 0
        date = None
        if request.POST.get('date'):
            try:
                date = datetime.date.fromisoformat(request.POST['date'])
            except ValueError:
                date = None
        subject_ids = {int(x) for x in request.POST.getlist('subjects') if x.isdigit()}
        # Shule zilizojiunga (Mtaaluma alibonyeza "Join") zinapata mtihani
        # moja kwa moja; afisa anaweza kuongeza nyingine hapa pia.
        school_ids = {int(x) for x in request.POST.getlist('schools') if x.isdigit()}
        chosen_schools = [s for s in schools if s.pk in school_ids or s.joint_member]

        errors = []
        if not name:
            errors.append('Weka jina la mtihani.')
        if form not in range(1, 7) or year < 2000:
            errors.append('Chagua kidato na mwaka sahihi.')
        if not subject_ids:
            errors.append('Chagua angalau somo moja.')
        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            joint = JointExam.objects.create(
                name=name, form=form, year=year, date=date,
                exam_type=request.POST.get('exam_type') or 'DISTRICT_JOINT',
                district=user.district, region=user.region, created_by=user,
            )
            joint.subjects.set(Subject.objects.filter(pk__in=subject_ids))
            for school in chosen_schools:
                joint.attach_school(school)
            messages.success(
                request,
                f'"{joint.name}" imeundwa na kupewa shule {len(chosen_schools)} zilizojiunga. '
                f'Shule zitakazojiunga baadaye zitaupata moja kwa moja.',
            )
            return redirect('joint_exam_detail', joint_id=joint.pk)

    default_subject_ids = {
        s.pk for s in subjects if s.name.strip().lower() in {d.lower() for d in DEFAULT_SUBJECTS}
    }
    return render(request, 'results/district/joint_form.html', {
        'schools': schools,
        'subjects': subjects,
        'default_subject_ids': default_subject_ids,
        'exam_type_choices': [c for c in Exam.EXAM_TYPE_CHOICES if 'JOINT' in c[0]],
        'this_year': datetime.date.today().year,
        'post': request.POST if request.method == 'POST' else None,
    })


@district_officer_required
def joint_exam_detail(request, joint_id):
    joint = _officer_joint_or_404(request, joint_id)

    if request.method == 'POST' and request.POST.get('action') == 'add_schools':
        ids = {int(x) for x in request.POST.getlist('schools') if x.isdigit()}
        added = 0
        for school in schools_in_district(joint.district, joint.region).filter(pk__in=ids):
            joint.attach_school(school)
            added += 1
        messages.success(request, f'Shule {added} zimeongezwa kwenye mtihani huu.')
        return redirect('joint_exam_detail', joint_id=joint.pk)

    data = analyse_joint_exam(joint)
    in_joint = {row['school'].pk for row in data['schools'] if row['school']}
    not_in_joint = [
        s for s in schools_in_district(joint.district, joint.region).order_by('name')
        if s.pk not in in_joint
    ]
    return render(request, 'results/district/joint_detail.html', {
        'joint': joint, 'data': data, 'is_officer': True,
        'not_in_joint': not_in_joint,
    })


@district_officer_required
def joint_exam_excel(request, joint_id):
    """?kind=division (DIVISION + GRADE) | subjects (LIST OF SUBJECTS + masomo)
       &own=GOV | PRIVATE | (tupu = shule zote)"""
    from .services.joint_excel import (
        build_division_workbook, build_subjects_workbook, workbook_filename,
    )

    joint = _officer_joint_or_404(request, joint_id)
    kind = 'subjects' if request.GET.get('kind') == 'subjects' else 'division'
    own = request.GET.get('own') if request.GET.get('own') in ('GOV', 'PRIVATE') else None
    build = build_subjects_workbook if kind == 'subjects' else build_division_workbook
    content = build(joint, ownership=own)
    filename = workbook_filename(joint, kind, own)
    resp = HttpResponse(
        content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@require_POST
@district_officer_required
def joint_exam_publish(request, joint_id):
    joint = _officer_joint_or_404(request, joint_id)
    joint.published = not joint.published
    joint.save(update_fields=['published'])
    if joint.published:
        messages.success(request, 'Shule zote zinazoshiriki sasa zinaona performance ya wilaya.')
    else:
        messages.info(request, 'Matokeo ya wilaya yamefungwa — shule haziyaoni tena.')
    return redirect('joint_exam_detail', joint_id=joint.pk)


@district_officer_required
def district_schools(request):
    user = request.user
    schools = list(schools_in_district(user.district, user.region).order_by('name'))
    if request.method == 'POST':
        valid = {c[0] for c in School.OWNERSHIP_CHOICES}
        changed = 0
        for s in schools:
            ward = request.POST.get(f'ward_{s.pk}', s.ward).strip().upper()[:100]
            ownership = request.POST.get(f'ownership_{s.pk}', s.ownership)
            if ownership not in valid:
                ownership = ''
            if ward != s.ward or ownership != s.ownership:
                s.ward, s.ownership = ward, ownership
                s.save(update_fields=['ward', 'ownership'])
                changed += 1
        messages.success(request, f'Shule {changed} zimesasishwa.')
        return redirect('district_schools')
    return render(request, 'results/district/schools.html', {
        'schools': schools,
        'ownership_choices': School.OWNERSHIP_CHOICES,
    })


@teacher_or_academic_required
def school_joint_results(request, exam_id):
    """Shule inayoshiriki inaona performance ya shule zote za wilaya."""
    exam = get_object_or_404(Exam.objects.select_related('joint_exam'), pk=exam_id)
    joint = exam.joint_exam
    school = getattr(request.user, 'school', None)
    if joint is None:
        raise Http404('Mtihani huu si wa pamoja wa wilaya.')
    if school is None or not joint.school_exams.filter(school=school).exists():
        raise PermissionDenied('Shule yako haishiriki mtihani huu.')
    if not joint.published:
        messages.info(request, 'Afisa Wilaya bado hajafungua matokeo ya wilaya kwa shule.')
        return redirect('exam_overview', exam.pk)
    data = analyse_joint_exam(joint)
    return render(request, 'results/district/joint_detail.html', {
        'joint': joint, 'data': data, 'is_officer': False,
        'my_school': school,
    })


# ================= Mtaaluma: "Join <Wilaya> DC Joint Exams" =================

@academic_required
def district_joint_home(request):
    """Mtaaluma: joint exams za wilaya yake. Kama shule bado haijajiunga →
    fomu ya kujiunga."""
    school = request.user.school
    program = district_program_name(school)
    if program is None:
        messages.info(request, 'Wilaya ya shule yako haina joint exams kwenye mfumo bado.')
        return redirect('home')
    if not school.joint_member:
        return redirect('district_joint_join')

    rows = []
    for joint in joints_for_school(school):
        exam = joint.attach_school(school)  # hakikisha Exam ipo (joint mpya)
        rows.append({'joint': joint, 'exam': exam})
    return render(request, 'results/district/joint_school_home.html', {
        'program': program, 'school': school, 'rows': rows,
    })


@academic_required
def district_joint_join(request):
    """Fomu ya kujiunga: Kata → Umiliki → Jina la shule (dropdown + search).

    Shule iliyochaguliwa ni rekodi ya orodha ya Halmashauri. Kama si shule
    ya akaunti hii lakini ni "tupu" (haina akaunti/data yoyote), shule ya
    Mtaaluma inachukua nafasi yake na rekodi tupu inaondolewa — ili shule
    moja isionekane mara mbili kwenye ripoti za wilaya.
    """
    my_school = request.user.school
    program = district_program_name(my_school)
    if program is None:
        messages.info(request, 'Wilaya ya shule yako haina joint exams kwenye mfumo bado.')
        return redirect('home')

    district_schools_qs = schools_in_district(my_school.district).exclude(level='primary')
    schools = list(district_schools_qs.order_by('name'))
    wards = sorted({s.ward for s in schools if s.ward})
    form = {
        'ward': my_school.ward, 'ownership': my_school.ownership, 'school_id': str(my_school.pk),
    }

    if request.method == 'POST':
        form = {
            'ward': request.POST.get('ward', '').strip().upper()[:100],
            'ownership': request.POST.get('ownership', ''),
            'school_id': request.POST.get('school_id', ''),
        }
        chosen = next((s for s in schools if str(s.pk) == form['school_id']), None)
        errors = []
        if not form['ward']:
            errors.append('Jaza kata ya shule.')
        if form['ownership'] not in dict(School.OWNERSHIP_CHOICES):
            errors.append('Chagua umiliki (Serikali au Binafsi).')
        if chosen is None:
            errors.append('Chagua jina la shule kwenye orodha.')
        elif chosen.pk != my_school.pk and not is_empty_placeholder(chosen):
            errors.append(
                f'"{chosen.name}" tayari inatumiwa na akaunti nyingine kwenye mfumo. '
                f'Chagua shule yako, au wasiliana na Afisa Wilaya.'
            )
        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            with transaction.atomic(using=School.objects.db):
                if chosen.pk != my_school.pk:
                    chosen.delete()
                my_school.ward = form['ward']
                my_school.ownership = form['ownership']
                my_school.joint_member = True
                my_school.joint_joined_at = timezone.now()
                my_school.save(update_fields=['ward', 'ownership', 'joint_member', 'joint_joined_at'])
                for joint in joints_for_school(my_school):
                    joint.attach_school(my_school)
            messages.success(
                request,
                f'{my_school.name} imejiunga na {program.title()} DC Joint Exams. '
                f'Walimu wanaingiza alama kwenye Marks Entry kama kawaida.',
            )
            return redirect('district_joint_home')

    return render(request, 'results/district/joint_join.html', {
        'program': program, 'schools': schools, 'wards': wards, 'form': form,
        'my_school': my_school,
        'ownership_choices': School.OWNERSHIP_CHOICES,
    })


# ==================== Matokeo ya umma — muundo wa NECTA ====================
#
# NECTA inachapisha matokeo kwa mtiririko huu: mtu anafungua ukurasa wa
# wilaya, anapata herufi A–Z, anabonyeza herufi ya kwanza ya jina la shule
# yake, kisha anapata shule zinazoanzia nayo — alichague moja na aone
# matokeo YOTE ya shule hiyo (nafasi, jina, alama za masomo, points,
# daraja) kama ilivyochapishwa.
#
# Hapa: /shule/wilaya/<joint_id>/matokeo/  na  .../matokeo/<exam_id>/


def _public_joint_or_404(request, joint_id):
    """Joint ya wilaya kwa ukurasa huu wa umma.

    Baada ya Afisa kuyafungua (`joint.published`) mtu yeyote anaona —
    hiyo ndiyo "kuchapisha" kama NECTA. Kabla ya hapo ni Afisa Wilaya ya
    hiyo joint na shule zinazoshiriki pekee ndizo zinaona; mwingine anaona
    404 (si 403 — tusionyeshe kuwa mtihani huu upo).
    """
    joint = get_object_or_404(JointExam, pk=joint_id)
    if joint.published:
        return joint
    user = request.user
    if not getattr(user, 'is_authenticated', False):
        raise Http404('Matokeo ya wilaya hayajafunguliwa bado.')
    if getattr(user, 'is_district_officer', False) and \
            district_key(user.district) == district_key(joint.district):
        return joint
    school = getattr(user, 'school', None)
    if school and joint.school_exams.filter(school=school).exists():
        return joint
    raise Http404('Matokeo ya wilaya hayajafunguliwa bado.')


def _school_letter(name):
    """Herufi ya kwanza ya jina la shule — NECTA hupanga kwa hiyo.

    Herufi si herufi (namba, alama za nukta) hupitwa: "Shule ya Sekondari
    ..." na "St. Mary's" zote zinawekea kwenye S.
    """
    for ch in (name or ''):
        if ch.isalpha():
            return ch.upper()
    return '#'


def district_necta_index(request, joint_id):
    """Ukurasa wa umma: chagua herufi → orodha ya shule zinazoanzia nayo."""
    joint = _public_joint_or_404(request, joint_id)

    exams = [
        ex for ex in joint.school_exams.select_related('school')
        .order_by('school__name')
        if ex.school_id and ex.school
    ]
    grouped = {}
    for ex in exams:
        grouped.setdefault(_school_letter(ex.school.name), []).append(ex)

    alphabet = [
        {'letter': chr(code), 'count': len(grouped.get(chr(code), []))}
        for code in range(ord('A'), ord('Z') + 1)
    ]

    selected = (request.GET.get('L') or '').strip().upper()[:1]
    if not selected.isalpha():
        selected = ''

    return render(request, 'results/district/necta_schools.html', {
        'joint': joint,
        'alphabet': alphabet,
        'selected': selected,
        'schools': grouped.get(selected, []) if selected else [],
        'school_total': len(exams),
        # Masthead ya base.html inatoka kwa mtumiaji aliyeingia — kwa ukurasa
        # wa umma tunalazimisha jina la wilaya ya hii joint (mf. KYERWA).
        'DISTRICT_NAME': joint.district,
        'IS_KYERWA': 'kyerwa' in (joint.district or '').lower(),
    })


def district_necta_school(request, joint_id, exam_id):
    """Matokeo kamili ya shule moja — kama NECTA inavyochapisha: kila
    mwanafunzi na nafasi yake, alama za masomo (A–F/X), points na daraja."""
    joint = _public_joint_or_404(request, joint_id)
    exam = get_object_or_404(
        Exam.objects.select_related('school'), pk=exam_id, joint_exam=joint,
    )
    school = exam.school
    if school is None:
        raise Http404('Mtihani huu hauna shule.')

    processed = list(
        ProcessedResult.objects.filter(exam=exam).select_related('student')
        .order_by(
            F('position').asc(nulls_last=True),
            'student__last_name', 'student__first_name',
        )
    )

    subjects = list(
        Subject.objects.filter(examresult__exam=exam)
        .distinct().order_by('name')
    )

    # Gredi ya kila (mwanafunzi, somo) — 'X' kwa aliyetosa/aliye absent.
    marks = {}
    for student_id, subject_id, score, is_absent in ExamResult.objects.filter(
        exam=exam,
    ).values_list('student_id', 'subject_id', 'score', 'is_absent'):
        if is_absent or score is None:
            marks[(student_id, subject_id)] = 'X'
        else:
            marks[(student_id, subject_id)] = get_grade_for_exam(score, exam)

    is_primary = bool(school.is_primary)
    rows = []
    divisions = {'I': 0, 'II': 0, 'III': 0, 'IV': 0, '0': 0, 'INC': 0, 'ABS': 0}
    for pr in processed:
        st = pr.student
        name = ' '.join(p for p in [st.first_name, st.middle_name or '', st.last_name] if p)
        if pr.division in divisions:
            divisions[pr.division] += 1
        rows.append({
            'position': pr.position,
            'name': name,
            'gender': st.gender,
            'division': pr.division,
            # Msingi hauna division — NECTA ya PSLE inaonyesha wastani +
            # daraja (A–E), kwa hiyo hiyo ndiyo "daraja" ya mwanafunzi hapa.
            'display_division': (
                pr.division if pr.division else
                (f'{pr.average_score:g} ({get_grade_primary(float(pr.average_score))})'
                 if is_primary and pr.average_score is not None else '—')
            ),
            'points': pr.points,
            'average': pr.average_score,
            'grades': [marks.get((st.pk, s.pk), '') for s in subjects],
        })

    sat = sum(v for k, v in divisions.items() if k != 'ABS')
    return render(request, 'results/district/necta_school_results.html', {
        'joint': joint,
        'exam': exam,
        'school': school,
        'subjects': subjects,
        'rows': rows,
        'divisions': divisions,
        'registered': len(rows),
        'sat': sat,
        'is_primary': is_primary,
        'DISTRICT_NAME': joint.district,
        'IS_KYERWA': 'kyerwa' in (joint.district or '').lower(),
    })
