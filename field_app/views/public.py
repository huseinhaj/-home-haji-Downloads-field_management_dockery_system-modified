"""
Public-facing views: school head request form and district submission.
"""
import re

from django.contrib import messages
from django.contrib.auth import login
from django.core.cache import cache
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from .models import (
    Region, Subject, School, District, BoardMember,
    SchoolHeadRequest,
)
from .utils import _cached_active_year


def _subject_lists():
    """Primary / Secondary / Technical subject name lists for the head form."""
    return (
        list(Subject.objects.filter(level='primary').order_by('name').values_list('name', flat=True)),
        list(Subject.objects.filter(level='secondary').order_by('name').values_list('name', flat=True)),
        list(Subject.objects.filter(level='technical').order_by('name').values_list('name', flat=True)),
    )


def public_school_head_form(request):
    """General public form for any school head in Tanzania."""
    current_year = _cached_active_year()
    regions = Region.objects.all().order_by('name')
    primary_subjects, secondary_subjects, technical_subjects = _subject_lists()

    def _ctx(**extra):
        ctx = {
            'regions': regions,
            'primary_subjects': primary_subjects,
            'secondary_subjects': secondary_subjects,
            'technical_subjects': technical_subjects,
            'current_year': current_year,
        }
        ctx.update(extra)
        return ctx

    if request.method == 'POST':
        school_id  = request.POST.get('school_id', '').strip()
        head_name  = request.POST.get('head_name', '').strip()
        head_phone = request.POST.get('head_phone', '').strip()
        notes      = request.POST.get('notes', '').strip()

        school = (School.objects.filter(id=school_id).select_related('district__region').first()
                  if school_id else None)

        subjects_needed_json = {}
        i = 1
        while True:
            sname = request.POST.get(f'subject_name_{i}', '').strip()
            if not sname:
                break
            try:
                scount = max(1, int(request.POST.get(f'subject_count_{i}', 1) or 1))
            except ValueError:
                scount = 1
            subjects_needed_json[sname] = scount
            i += 1

        students_needed = sum(subjects_needed_json.values()) if subjects_needed_json else 0

        error = None
        if not school:
            error = 'Tafadhali chagua shule.'
        elif not head_name:
            error = 'Tafadhali weka jina la mkuu wa shule.'
        elif not subjects_needed_json:
            error = 'Tafadhali ongeza angalau somo moja na idadi inayohitajika.'

        if error:
            return render(request, 'field_app/public_school_head_form.html', _ctx(
                error=error, post=request.POST))

        SchoolHeadRequest.objects.create(
            district=school.district,
            academic_year=current_year,
            school_name_submitted=school.name,
            school=school,
            head_name=head_name,
            head_phone=head_phone,
            level=school.level,
            students_needed=students_needed,
            subjects_needed=subjects_needed_json,
            notes=notes,
        )
        from django.utils.http import urlencode
        params = urlencode({'submitted': '1', 'school_id': school.id, 'first_time': '1'})
        messages.success(request, f'Asante {head_name}! Ombi la {school.name} limetumwa. Sasa weka nywila ya akaunti yako.')
        return redirect(f"{reverse('head_login')}?{params}")

    # Stage 0: initial code entry — handle POST stages
    if request.method == 'POST':
        stage = request.POST.get('stage', '')

        if stage == 'select':
            school_id = request.POST.get('school_id', '').strip()
            school = School.objects.filter(id=school_id).first()
            if not school:
                return render(request, 'field_app/public_school_head_form.html', _ctx(
                    stage='verify', error='Shule haikutambuliwa. Jaribu tena.'))
            already = SchoolHeadRequest.objects.filter(
                school=school, academic_year=current_year,
            ).exclude(status='rejected').exists()
            if already:
                return render(request, 'field_app/public_school_head_form.html', _ctx(
                    stage='verify',
                    error=f'Shule ya {school.name} tayari imetuma ombi kwa mwaka huu.'))
            return render(request, 'field_app/public_school_head_form.html', _ctx(
                stage='form', school=school))

        if stage == 'verify':
            query = request.POST.get('school_code', '').strip()
            raw = query.upper().replace(' ', '').replace('-', '').replace('.', '')
            if re.match(r'^PS\d+$', raw):
                code = raw
            else:
                code = re.sub(r'^([SP])(\d+)$', r'\1.\2', raw)

            school = School.objects.filter(school_code__iexact=code).first()

            if not school:
                q_lower = query.lower()
                name_query = re.sub(r'\b(primary|secondary|msingi|sekondari)\b', '', q_lower, flags=re.IGNORECASE).strip()
                qs = School.objects.select_related('district')
                if any(w in q_lower for w in ['primary', 'msingi']):
                    qs = qs.filter(level='Primary')
                elif any(w in q_lower for w in ['secondary', 'sekondari']):
                    qs = qs.filter(level='Secondary')
                matches = qs.filter(name__icontains=name_query or query).order_by('level', 'name')[:10]

                if not matches:
                    return render(request, 'field_app/public_school_head_form.html', _ctx(
                        stage='verify',
                        error=f'"{query}" haikupatikana. Jaribu namba ya usajili (S.2895) au sehemu ya jina la shule.'))
                if len(matches) == 1:
                    school = matches[0]
                else:
                    return render(request, 'field_app/public_school_head_form.html', _ctx(
                        stage='select', matches=matches, query=query))

            already = SchoolHeadRequest.objects.filter(
                school=school, academic_year=current_year,
            ).exclude(status='rejected').exists()
            if already:
                bm = BoardMember.objects.filter(school=school, role='head_teacher', is_active=True).first()
                request.session['ombi_school_id'] = school.id
                return render(request, 'field_app/public_school_head_form.html', _ctx(
                    stage='goto_login', school=school,
                    has_account=bm is not None,
                    needs_password=bm is not None and not bm.user.has_usable_password()))
            return render(request, 'field_app/public_school_head_form.html', _ctx(
                stage='form', school=school))

    return render(request, 'field_app/public_school_head_form.html', _ctx(stage='verify'))


def school_head_submit(request, district_id):
    """Public form — school head submits subjects + capacity needed."""
    district = get_object_or_404(District, id=district_id)
    current_year = _cached_active_year()
    schools = School.objects.filter(district=district).order_by('level', 'name')

    primary_subjects, secondary_subjects, technical_subjects = _subject_lists()

    if request.method == 'POST':
        school_name = request.POST.get('school_name', '').strip()
        head_name   = request.POST.get('head_name', '').strip()
        head_email  = request.POST.get('head_email', '').strip().lower()
        head_phone  = request.POST.get('head_phone', '').strip()
        level       = request.POST.get('level', '').strip()
        notes       = request.POST.get('notes', '').strip()

        subjects_needed_json = {}
        i = 1
        while True:
            sname = request.POST.get(f'subject_name_{i}', '').strip()
            if not sname:
                break
            try:
                scount = max(1, int(request.POST.get(f'subject_count_{i}', 1) or 1))
            except ValueError:
                scount = 1
            subjects_needed_json[sname] = scount
            i += 1

        students_needed = sum(subjects_needed_json.values()) if subjects_needed_json else 0

        error = None
        if not school_name or not head_name or not level or not head_email:
            error = 'Tafadhali jaza sehemu zote zinazohitajika (Shule, Kiwango, Jina la Mkuu, Barua Pepe).'
        elif not subjects_needed_json:
            error = 'Tafadhali ongeza angalau somo moja na idadi inayohitajika.'

        if error:
            messages.error(request, error)
        else:
            matched_school = None
            name_lower = school_name.lower()
            for s in schools:
                if name_lower in s.name.lower() or s.name.lower() in name_lower:
                    matched_school = s
                    break

            SchoolHeadRequest.objects.create(
                district=district,
                academic_year=current_year,
                school_name_submitted=school_name,
                school=matched_school,
                head_name=head_name,
                head_phone=head_phone,
                submitter_email=head_email,
                level=level,
                students_needed=students_needed,
                subjects_needed=subjects_needed_json,
                notes=notes,
            )
            from django.utils.http import urlencode
            params = urlencode({'email': head_email, 'submitted': '1'})
            messages.success(request, f'Asante {head_name}! Ombi lako limetumwa kwa DEO wa {district.name}. Ingia sasa kuona hali ya ombi lako.')
            return redirect(f"{reverse('head_login')}?{params}")

    return render(request, 'field_app/school_head_submit.html', {
        'district': district,
        'schools': schools,
        'current_year': current_year,
        'primary_subjects': primary_subjects,
        'secondary_subjects': secondary_subjects,
        'technical_subjects': technical_subjects,
    })
