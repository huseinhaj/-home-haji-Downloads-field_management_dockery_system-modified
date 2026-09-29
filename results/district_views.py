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
"""
import datetime

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .district_models import JointExam, schools_in_district
from .models import Exam, School, Subject
from .permissions import _role_required, teacher_or_academic_required
from .services.joint_analysis import analyse_joint_exam

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
        school_ids = {int(x) for x in request.POST.getlist('schools') if x.isdigit()}
        chosen_schools = [s for s in schools if s.pk in school_ids]

        errors = []
        if not name:
            errors.append('Weka jina la mtihani.')
        if form not in range(1, 7) or year < 2000:
            errors.append('Chagua kidato na mwaka sahihi.')
        if not subject_ids:
            errors.append('Chagua angalau somo moja.')
        if not chosen_schools:
            errors.append('Chagua angalau shule moja.')
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
                f'"{joint.name}" imeundwa kwa shule {len(chosen_schools)}. '
                f'Walimu wa kila shule sasa wanaweza kuingiza alama.',
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
    from .services.joint_excel import build_joint_workbook

    joint = _officer_joint_or_404(request, joint_id)
    content = build_joint_workbook(joint)
    filename = f'{joint.district} {joint.name} Form {joint.form} {joint.year}.xlsx'.replace('/', '-')
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
