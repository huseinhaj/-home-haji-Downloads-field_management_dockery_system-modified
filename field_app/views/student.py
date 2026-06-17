import io
import json
import re
import threading
from io import BytesIO
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import Count, F, Q
from django.db.models.functions import Greatest
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, inch
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable

from geopy.distance import geodesic

from .decorators import assessor_login_required, board_login_required
from .forms import (
    CustomLoginForm, StudentRegistrationForm, StudentTeacherForm, LogbookForm,
)
from .models import (
    Assessor, School, SchoolAssignment, StudentTeacher,
    StudentAssessment, SchoolAssessment, SchoolRequirement,
    StudentApplication, Region, RegionPin, SchoolPin,
    District, Subject, SchoolSubjectCapacity,
    LogbookEntry, ApprovalLetter, AcademicYear,
    BoardMember, BoardComment, LessonPlan, MonthlyReport,
    DistrictAllocation, SchoolAllocation, FinalAssessment,
)

from .utils import (
    _cached_active_year, _cached_subjects, _cached_today_logbook,
    _invalidate_today_logbook, _cached_schools_by_district,
    get_or_create_student_profile, invalidate_student_cache,
    get_current_academic_year, _build_individual_letter_pdf,
    _get_deo_for_district,
)

User = get_user_model()


@login_required
def dashboard(request):
    """Student dashboard"""

    if request.user.is_staff:
        return redirect('admin_dashboard')

    try:
        Assessor.objects.get(user=request.user)
        return redirect('assessor_dashboard')
    except Assessor.DoesNotExist:
        pass

    try:
        BoardMember.objects.get(user=request.user)
        return redirect('board_home')
    except BoardMember.DoesNotExist:
        pass

    student = get_or_create_student_profile(request.user)
    current_year = _cached_active_year()

    pinned_regions = Region.objects.none()
    if current_year:
        pinned_region_ids = RegionPin.objects.filter(
            academic_year=current_year,
            is_pinned=True
        ).values_list('region_id', flat=True)
        pinned_regions = Region.objects.filter(id__in=pinned_region_ids)

    assessors = []
    if student.selected_school:
        qs = SchoolAssessment.objects.filter(school=student.selected_school)
        if current_year:
            qs = qs.filter(academic_year=current_year)
        for assessment in qs.select_related('assessor'):
            assessors.append({
                'assessor': assessment.assessor,
                'assignment_date': assessment.assessment_date,
                'is_completed': assessment.is_completed,
            })

    applications = []
    approved_applications_count = 0
    pending_applications_count = 0
    has_approved_applications = False
    can_change_school_now = False
    change_days_remaining = 0
    change_deadline = None

    if student:
        applications = StudentApplication.objects.filter(student=student).select_related('subject', 'school')
        approved_applications_count = applications.filter(status='approved').count()
        pending_applications_count = applications.filter(status='pending').count()
        has_approved_applications = approved_applications_count > 0

        # Change school window: 7 days from approval_date of approved application
        approved_app = applications.filter(status='approved').select_related('subject').first()
        if approved_app and approved_app.approval_date:
            days_since = (timezone.now() - approved_app.approval_date).days
            can_change_school_now = days_since <= 7
            change_days_remaining = max(0, 7 - days_since)
            change_deadline = approved_app.approval_date + timezone.timedelta(days=7)

        # Auto-sync selected_school to match the actual application's school
        canonical_app = (
            applications.filter(status='approved').first() or
            applications.filter(status='pending').first()
        )
        if canonical_app and student.selected_school_id != canonical_app.school_id:
            old_school = student.selected_school
            student.selected_school = canonical_app.school
            student.save(update_fields=['selected_school'])
            if old_school:
                School.objects.filter(id=old_school.id).update(current_students=Greatest(F('current_students') - 1, 0))
            School.objects.filter(id=canonical_app.school_id).update(current_students=F('current_students') + 1)
            invalidate_student_cache(student)

    logbook_entries = []
    if student:
        logbook_entries = LogbookEntry.objects.filter(
            student=student
        ).select_related('subject_taught').order_by('-date')[:5]

    board_comments = []
    if student:
        board_comments = BoardComment.objects.filter(
            student=student
        ).select_related('board_member').order_by('-created_at')[:5]
        BoardComment.objects.filter(student=student, is_read=False).update(is_read=True)

    # Monthly reports visible to the student — find their entry in each report
    my_monthly_reports = []
    if student and student.selected_school:
        district = student.selected_school.district
        reports = MonthlyReport.objects.filter(district=district).order_by('-year', '-month')[:6]
        for report in reports:
            content = report.ai_content or {}
            student_entry = None
            # Search primary and secondary lists for this student by name
            for level_key in ('primary', 'secondary'):
                for entry in content.get(level_key, []):
                    if entry.get('jina', '').strip().lower() == student.full_name.strip().lower():
                        student_entry = entry
                        break
                if student_entry:
                    break
            my_monthly_reports.append({
                'report': report,
                'entry': student_entry,   # None if student had no logbook that month
            })

    final_assessment = None
    try:
        final_assessment = student.final_assessment
    except Exception:
        pass

    approved_app_ctx = applications.filter(status='approved').select_related('subject', 'school__district__region').first() if student else None

    return render(request, 'field_app/dashboard.html', {
        'regions': pinned_regions,
        'current_year': current_year,
        'student': student,
        'applications': applications,
        'approved_applications_count': approved_applications_count,
        'pending_applications_count': pending_applications_count,
        'has_approved_applications': has_approved_applications,
        'approved_app': approved_app_ctx,
        'can_change_school_now': can_change_school_now,
        'change_days_remaining': change_days_remaining,
        'change_deadline': change_deadline,
        'logbook_entries': logbook_entries,
        'assessors': assessors,
        'board_comments': board_comments,
        'my_monthly_reports': my_monthly_reports,
        'final_assessment': final_assessment,
    })

@login_required
def student_monthly_report(request, report_id):
    """Show a monthly report to the student who is in that district."""
    student = get_or_create_student_profile(request.user)
    report = get_object_or_404(MonthlyReport, id=report_id)

    # Ensure the student belongs to this district
    if not student.selected_school or student.selected_school.district_id != report.district_id:
        messages.error(request, 'Huna ruhusa ya kuona ripoti hii.')
        return redirect('dashboard')

    content = report.ai_content or {}
    student_entry = None
    for level_key in ('primary', 'secondary'):
        for entry in content.get(level_key, []):
            if entry.get('jina', '').strip().lower() == student.full_name.strip().lower():
                student_entry = entry
                break
        if student_entry:
            break

    return render(request, 'field_app/student_monthly_report.html', {
        'report': report,
        'student': student,
        'student_entry': student_entry,
        'muhtasari': content.get('muhtasari', ''),
        'hitimisho': content.get('hitimisho', ''),
    })


@login_required
def select_region(request):
    """Show ONLY regions that are NOT pinned for current academic year"""
    current_year = get_current_academic_year()

    if not current_year:
        messages.error(request, "No active academic year found!")
        return redirect('dashboard')

    # Get PINNED region IDs (regions to HIDE from students)
    pinned_region_ids = RegionPin.objects.filter(
        academic_year=current_year,
        is_pinned=True  # Pinned = HIDDEN
    ).values_list('region_id', flat=True)

    # Show ONLY regions that are NOT pinned
    available_regions = Region.objects.exclude(
        id__in=pinned_region_ids
    ).order_by('name')

    print(f"📅 Academic Year: {current_year.year}")
    print(f"🔒 Pinned (Hidden) Regions: {pinned_region_ids.count()}")
    print(f"✅ Available Regions: {available_regions.count()}")

    # Debug: Print region names
    for region in available_regions:
        print(f"   - {region.name}")

    return render(request, 'field_app/select_region.html', {
        'regions': available_regions,
        'current_year': current_year,
        'pinned_count': pinned_region_ids.count(),
        'available_count': available_regions.count(),
    })

@login_required
def select_district(request, region_id):
    region = get_object_or_404(Region, id=region_id)
    districts = District.objects.filter(region=region)
    current_year = _cached_active_year()

    # Fetch allocations for all districts in this region at once
    alloc_qs = DistrictAllocation.objects.filter(district__region=region)
    if current_year:
        alloc_qs = alloc_qs.filter(academic_year=current_year)
    alloc_map = {a.district_id: a for a in alloc_qs}

    for district in districts:
        district.school_count = School.objects.filter(district=district).count()
        alloc = alloc_map.get(district.id)
        district.allocation = alloc  # may be None if DEO hasn't set it yet

    request.session['selected_region_id'] = region.id

    return render(request, 'field_app/select_district.html', {
        'districts': districts,
        'region': region,
    })

@login_required
def select_school(request, district_id):
    district = get_object_or_404(District, id=district_id)
    current_year = _cached_active_year()

    # Get pinned schools
    pinned_school_ids = []
    if current_year:
        pinned_school_ids = list(SchoolPin.objects.filter(
            academic_year=current_year, is_pinned=True
        ).values_list('school_id', flat=True))

    # Get parameters
    search_query = request.GET.get('q', '')
    selected_level = request.GET.get('level', 'Secondary')
    selected_ownership = request.GET.get('ownership', '')

    # Get schools
    schools_qs = School.objects.filter(district=district, level=selected_level)
    if search_query:
        schools_qs = schools_qs.filter(name__icontains=search_query)
    if selected_ownership:
        schools_qs = schools_qs.filter(ownership=selected_ownership)

    # Fetch district allocation and per-school quotas for display
    da_qs = DistrictAllocation.objects.filter(district=district)
    if current_year:
        da_qs = da_qs.filter(academic_year=current_year)
    district_alloc = da_qs.first()
    school_alloc_map = {}
    if district_alloc:
        school_alloc_map = {
            sa.school_id: sa
            for sa in SchoolAllocation.objects.filter(district_allocation=district_alloc)
        }

    # Pre-calculate district-level fullness for the selected level
    district_primary_full = False
    district_secondary_full = False
    if district_alloc:
        if district_alloc.primary_needed > 0 and district_alloc.primary_remaining == 0:
            district_primary_full = True
        if district_alloc.secondary_needed > 0 and district_alloc.secondary_remaining == 0:
            district_secondary_full = True

    schools = []
    for school in schools_qs:
        school.is_pinned = school.id in pinned_school_ids
        sa = school_alloc_map.get(school.id)
        school.deo_quota = sa.quota if sa else None
        school.deo_filled = sa.filled if sa else None
        school.deo_remaining = sa.remaining if sa else None

        # School general capacity full?
        school_cap_full = school.current_students >= school.capacity
        # DEO quota full? (only enforced when quota > 0)
        deo_quota_full = bool(sa and sa.quota > 0 and sa.filled >= sa.quota)
        # District level full?
        dist_full = district_primary_full if school.level == 'Primary' else district_secondary_full

        school.is_deo_full = deo_quota_full
        school.is_district_full = dist_full
        school.is_selectable = (not school.is_pinned) and (not school_cap_full) and (not deo_quota_full) and (not dist_full)
        school.occupancy_percentage = round((school.current_students / school.capacity) * 100) if school.capacity > 0 else 0
        schools.append(school)

    total_schools = len(schools)
    pinned_schools_count = sum(1 for s in schools if s.is_pinned)
    available_schools_count = sum(1 for s in schools if s.is_selectable)
    full_schools_count = total_schools - pinned_schools_count - available_schools_count

    # ========== SIMPLE SESSION LOGIC ==========
    selected_school = None
    temp_selected_id = request.session.get('temp_selected_school_id')
    if temp_selected_id:
        try:
            selected_school = School.objects.get(id=temp_selected_id)
        except School.DoesNotExist:
            request.session.pop('temp_selected_school_id', None)

    # ========== HANDLE POST ==========
    if request.method == 'POST':
        action = request.POST.get('action')
        school_id = request.POST.get('school_id')

        if action == 'select' and school_id:
            school = get_object_or_404(School, id=school_id)
            request.session['temp_selected_school_id'] = school.id
            messages.info(request, f'Umchagua {school.name}. Bonyeza Thibitisha au Ghairi.')
            return redirect(f"{request.path}?level={selected_level}&q={search_query}")

        elif action == 'confirm':
            if temp_selected_id:
                try:
                    school = School.objects.get(id=temp_selected_id)
                    student = get_or_create_student_profile(request.user)
                    sw = request.session.get('lang') == 'sw'

                    # ── Server-side quota enforcement ──────────────────────────
                    # 1. DEO school quota
                    confirm_da = DistrictAllocation.objects.filter(district=district)
                    if current_year:
                        confirm_da = confirm_da.filter(academic_year=current_year)
                    confirm_da = confirm_da.first()
                    confirm_sa = None
                    if confirm_da:
                        confirm_sa = SchoolAllocation.objects.filter(
                            district_allocation=confirm_da, school=school
                        ).first()

                    if confirm_sa and confirm_sa.quota > 0 and confirm_sa.filled >= confirm_sa.quota:
                        messages.error(request,
                            'Shule hii imejaa kwa mujibu wa quota ya DEO. Tafadhali chagua shule nyingine.'
                            if sw else
                            'This school has reached its DEO quota. Please choose another school.'
                        )
                        request.session.pop('temp_selected_school_id', None)
                        return redirect(f"{request.path}?level={selected_level}&q={search_query}")

                    # 2. District-level quota
                    if confirm_da:
                        if school.level == 'Primary' and confirm_da.primary_needed > 0 and confirm_da.primary_remaining == 0:
                            messages.error(request,
                                'Wilaya hii imejaa kwa walimu wa shule za msingi. Hakuna nafasi zaidi.'
                                if sw else
                                'This district has reached its primary school quota. No more spots available.'
                            )
                            request.session.pop('temp_selected_school_id', None)
                            return redirect(f"{request.path}?level={selected_level}&q={search_query}")
                        if school.level == 'Secondary' and confirm_da.secondary_needed > 0 and confirm_da.secondary_remaining == 0:
                            messages.error(request,
                                'Wilaya hii imejaa kwa walimu wa shule za sekondari. Hakuna nafasi zaidi.'
                                if sw else
                                'This district has reached its secondary school quota. No more spots available.'
                            )
                            request.session.pop('temp_selected_school_id', None)
                            return redirect(f"{request.path}?level={selected_level}&q={search_query}")

                    # 3. General school capacity
                    if school.current_students >= school.capacity:
                        messages.error(request,
                            f'Shule {school.name} imejaa kabisa ({school.capacity} wanafunzi).'
                            if sw else
                            f'School {school.name} is at full capacity ({school.capacity} students).'
                        )
                        request.session.pop('temp_selected_school_id', None)
                        return redirect(f"{request.path}?level={selected_level}&q={search_query}")
                    # ──────────────────────────────────────────────────────────

                    is_changing_school = student.selected_school and student.selected_school.id != school.id

                    if is_changing_school:
                        # Block if student has any approved application — cannot change school after approval
                        approved_apps = StudentApplication.objects.filter(student=student, status='approved')
                        if approved_apps.exists():
                            messages.error(request,
                                'Huwezi kubadili shule. Ombi lako limeshaidhinishwa tayari.'
                                if sw else
                                'You cannot change school. You already have an approved application.'
                            )
                            request.session.pop('temp_selected_school_id', None)
                            return redirect('dashboard')

                        # Delete pending applications at old school before switching
                        StudentApplication.objects.filter(student=student, status='pending').delete()
                        School.objects.filter(id=student.selected_school.id).update(current_students=Greatest(F('current_students') - 1, 0))

                    elif student.selected_school:
                        School.objects.filter(id=student.selected_school.id).update(current_students=Greatest(F('current_students') - 1, 0))

                    student.selected_school = school
                    student.save()
                    invalidate_student_cache(student)
                    School.objects.filter(id=school.id).update(current_students=F('current_students') + 1)

                    request.session.pop('temp_selected_school_id', None)
                    messages.success(request, f'Shule imethibitishwa: {school.name}')
                    return redirect('select_subjects', school_id=school.id)
                except School.DoesNotExist:
                    messages.error(request, 'Shule haipo')
                messages.error(request, 'Hakuna shule iliyochaguliwa')
            return redirect(f"{request.path}?level={selected_level}&q={search_query}")

        elif action == 'cancel':
            request.session.pop('temp_selected_school_id', None)
            messages.success(request, 'Umeghairi uchaguzi wa shule')
            return redirect(f"{request.path}?level={selected_level}&q={search_query}")

    # Subject capacity preview for the selected school confirm panel
    selected_school_subjects = []
    if selected_school:
        for cap in SchoolSubjectCapacity.objects.filter(
            school=selected_school
        ).select_related('subject').order_by('subject__name'):
            selected_school_subjects.append({
                'name': cap.subject.name,
                'filled': cap.current_students,
                'max': cap.max_students,
                'remaining': max(0, cap.max_students - cap.current_students),
                'is_full': cap.current_students >= cap.max_students,
                'pct': min(100, round(cap.current_students / cap.max_students * 100)) if cap.max_students > 0 else 0,
            })

    return render(request, 'field_app/select_school.html', {
        'district': district,
        'schools': schools,
        'selected_school': selected_school,
        'selected_school_subjects': selected_school_subjects,
        'query': search_query,
        'selected_level': selected_level,
        'selected_ownership': selected_ownership,
        'total_schools': total_schools,
        'pinned_schools_count': pinned_schools_count,
        'available_schools_count': available_schools_count,
        'full_schools_count': full_schools_count,
        'current_year': current_year,
        'district_alloc': district_alloc,
        'district_primary_full': district_primary_full,
        'district_secondary_full': district_secondary_full,
    })

@login_required
def search_schools_ajax(request, district_id):
    """Live search endpoint — returns school cards as JSON for instant search."""
    district = get_object_or_404(District, id=district_id)
    current_year = _cached_active_year()

    q         = request.GET.get('q', '').strip()
    level     = request.GET.get('level', 'Secondary')
    ownership = request.GET.get('ownership', '')

    pinned_ids = []
    if current_year:
        pinned_ids = list(SchoolPin.objects.filter(
            academic_year=current_year, is_pinned=True
        ).values_list('school_id', flat=True))

    qs = School.objects.filter(district=district, level=level)
    if q:
        qs = qs.filter(name__icontains=q)
    if ownership:
        qs = qs.filter(ownership=ownership)

    da_qs = DistrictAllocation.objects.filter(district=district)
    if current_year:
        da_qs = da_qs.filter(academic_year=current_year)
    district_alloc = da_qs.first()
    alloc_map = {}
    if district_alloc:
        alloc_map = {sa.school_id: sa for sa in
                     SchoolAllocation.objects.filter(district_allocation=district_alloc)}

    dist_primary_full = (district_alloc and district_alloc.primary_needed > 0
                         and district_alloc.primary_remaining == 0)
    dist_secondary_full = (district_alloc and district_alloc.secondary_needed > 0
                           and district_alloc.secondary_remaining == 0)

    results = []
    for school in qs[:60]:
        sa = alloc_map.get(school.id)
        is_pinned     = school.id in pinned_ids
        cap_full      = school.current_students >= school.capacity
        deo_full      = bool(sa and sa.quota > 0 and sa.filled >= sa.quota)
        dist_full     = dist_primary_full if level == 'Primary' else dist_secondary_full
        selectable    = not is_pinned and not cap_full and not deo_full and not dist_full

        status = ('pinned' if is_pinned
                  else 'district_full' if dist_full
                  else 'deo_full'      if deo_full
                  else 'cap_full'      if cap_full
                  else 'available')

        results.append({
            'id':        school.id,
            'name':      school.name,
            'level':     school.get_level_display(),
            'ownership': school.ownership,
            'selectable': selectable,
            'status':    status,
            'deo_quota':    sa.quota    if sa else None,
            'deo_filled':   sa.filled   if sa else None,
            'deo_remaining':sa.remaining if sa else None,
        })

    return JsonResponse({'schools': results, 'total': len(results)})


@login_required
def select_subjects(request, school_id):
    school = get_object_or_404(School, id=school_id)
    student = get_or_create_student_profile(request.user)
    sw = request.session.get('lang') == 'sw'

    # Only subjects with capacity set by DEO
    caps = list(SchoolSubjectCapacity.objects.filter(school=school).select_related('subject'))

    # Student's approved application at this school (only one allowed)
    approved_app = StudentApplication.objects.filter(
        student=student, school=school, status='approved'
    ).select_related('subject').first()

    if request.method == 'POST':
        subject_id = request.POST.get('subject_id')
        action = request.POST.get('action')

        if action == 'apply' and subject_id:
            try:
                subject = Subject.objects.get(id=subject_id)
                cap = SchoolSubjectCapacity.objects.get(school=school, subject=subject)
            except (Subject.DoesNotExist, SchoolSubjectCapacity.DoesNotExist):
                messages.error(request, 'Somo hili halipatikani katika shule hii.')
                return redirect('select_subjects', school_id=school.id)

            # Block if already has any approved application anywhere
            any_approved = StudentApplication.objects.filter(student=student, status='approved').exists()
            if any_approved:
                messages.error(request, 'Umeshaidhinishwa tayari. Huwezi kuomba tena.')
                return redirect('dashboard')

            # Block if capacity full (re-check with select_for_update)
            from django.db import transaction
            with transaction.atomic():
                cap = SchoolSubjectCapacity.objects.select_for_update().get(id=cap.id)
                if cap.current_students >= cap.max_students:
                    messages.error(request, f'Somo la {subject.name} limejaa. Chagua somo lingine.')
                    return redirect('select_subjects', school_id=school.id)

                # Auto-approve immediately
                app, created = StudentApplication.objects.get_or_create(
                    student=student, subject=subject, school=school,
                    defaults={'status': 'approved', 'approval_date': timezone.now()}
                )
                if not created:
                    if app.status == 'approved':
                        messages.info(request, f'Umeshaidhinishwa kwa {subject.name}.')
                        return redirect('dashboard')
                    app.status = 'approved'
                    app.approval_date = timezone.now()
                    app.save()

                student.subjects.add(subject)
                cap.current_students = F('current_students') + 1
                cap.save()

            messages.success(request,
                f'✅ Umeidhinishwa kwa {subject.name} katika {school.name}! Pakua barua yako hapa chini.'
                if sw else
                f'✅ Approved for {subject.name} at {school.name}! Download your letter below.'
            )
            return redirect('dashboard')

    # Build subject list with live fill counts
    subject_list = []
    for cap in caps:
        subject_list.append({
            'cap': cap,
            'subject': cap.subject,
            'max': cap.max_students,
            'filled': cap.current_students,
            'remaining': max(0, cap.max_students - cap.current_students),
            'is_full': cap.current_students >= cap.max_students,
            'is_mine': approved_app and approved_app.subject_id == cap.subject_id,
            'pct': min(100, round(cap.current_students / cap.max_students * 100)) if cap.max_students > 0 else 0,
        })

    return render(request, 'field_app/select_subjects.html', {
        'school': school,
        'subject_list': subject_list,
        'approved_app': approved_app,
        'available_count': sum(1 for s in subject_list if not s['is_full']),
        'full_count': sum(1 for s in subject_list if s['is_full']),
    })

@login_required
def apply_for_subject(request, subject_id, school_id):
    subject = get_object_or_404(Subject, id=subject_id)
    school = get_object_or_404(School, id=school_id)

    student = get_or_create_student_profile(request.user)

    existing_application = StudentApplication.objects.filter(
        student=student,
        subject=subject,
        school=school
    ).first()

    if existing_application:
        messages.info(request, f"You have already applied for {subject.name}")
        return redirect('select_subjects', school_id=school.id)

    # Enforce one school, one subject rule
    any_other_application = StudentApplication.objects.filter(
        student=student
    ).exclude(subject=subject, school=school).exists()
    if any_other_application:
        messages.error(request,
            "Una ombi tayari katika shule/somo lingine. Unaweza kuomba shule moja na somo moja tu."
            if request.session.get('lang') == 'sw' else
            "You already have an application elsewhere. Only one school and one subject is allowed."
        )
        return redirect('select_subjects', school_id=school.id)

    try:
        capacity = SchoolSubjectCapacity.objects.get(school=school, subject=subject)
        if capacity.current_students >= capacity.max_students:
            messages.error(request, f"{subject.name} is already full at {school.name}")
            return redirect('select_subjects', school_id=school.id)
    except SchoolSubjectCapacity.DoesNotExist:
        messages.error(request, f"{subject.name} is not available at {school.name}")
        return redirect('select_subjects', school_id=school.id)

    StudentApplication.objects.create(
        student=student,
        subject=subject,
        school=school,
        status='pending'
    )

    messages.success(request, f"Application for {subject.name} submitted successfully! Waiting for approval.")
    return redirect('dashboard')

# =========================
# LOGBOOK VIEWS
# =========================

@login_required
def submit_logbook(request):
    student = get_or_create_student_profile(request.user)
    today = timezone.now().date()

    # Check if weekend
    if today.weekday() >= 5:  # Saturday (5) or Sunday (6)
        messages.info(request, "Hakuna kazi ya uwanjani wikendi. Rudi tena Jumatatu.")
        return redirect('dashboard')

    if not student.selected_school:
        messages.error(request, "Lazima uchague shule kabla ya kujaza logbook.")
        return redirect('select_region')

    school = student.selected_school

    logbook_entry = _cached_today_logbook(student, school, today)

    if request.method == 'POST':
        form = LogbookForm(request.POST, instance=logbook_entry)

        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        is_location_verified = request.POST.get('is_location_verified', 'false') == 'true'

        days_swahili = {0: 'Jumatatu', 1: 'Jumanne', 2: 'Jumatano', 3: 'Alhamisi', 4: 'Ijumaa'}

        def _render_logbook(extra=None):
            subjects = _cached_subjects(student)
            ctx = {
                'form': form, 'student': student, 'logbook_entry': logbook_entry,
                'today': today, 'today_name': days_swahili.get(today.weekday(), 'Leo'),
                'school': school, 'subjects': subjects,
            }
            if extra:
                ctx.update(extra)
            return render(request, 'field_app/logbook.html', ctx)

        if not is_location_verified:
            messages.error(request, "Thibiti eneo lako kwanza kabla ya kuwasilisha logbook.")
            return _render_logbook({'location_error': True})

        if not latitude or not longitude:
            messages.error(request, "Eneo halipatikani. Washa GPS na ujaribu tena.")
            return _render_logbook({'location_error': True})

        try:
            lat = float(latitude)
            lng = float(longitude)
            logbook_entry.latitude = lat
            logbook_entry.longitude = lng
            logbook_entry.location_address = request.POST.get('location_address', '')

            if school and school.latitude and school.longitude:
                from geopy.distance import geodesic
                distance_m = geodesic((lat, lng), (school.latitude, school.longitude)).meters
                school_verified = distance_m <= 1000
            else:
                school_verified = (-11.8 <= lat <= -1.0) and (29.3 <= lng <= 40.5)

            logbook_entry.is_location_verified = school_verified
            logbook_entry.is_at_school = school_verified

        except (ValueError, TypeError) as e:
            messages.error(request, f"Hitilafu ya eneo: {e}")
            return _render_logbook()

        if form.is_valid():
            entry = form.save(commit=False)

            import json as _json
            try:
                entry.lessons_data = _json.loads(request.POST.get('lessons_data', '[]'))
            except (ValueError, TypeError):
                entry.lessons_data = []

            entry.latitude = logbook_entry.latitude
            entry.longitude = logbook_entry.longitude
            entry.is_location_verified = logbook_entry.is_location_verified
            entry.is_at_school = logbook_entry.is_at_school
            entry.location_address = logbook_entry.location_address
            entry.save()
            _invalidate_today_logbook(student, today)

            # Send email in background thread — never block the response
            import threading
            def _notify(school_id, student_name, entry_id, verified):
                try:
                    from .models import SchoolAssessment, AcademicYear
                    from django.core.mail import send_mail as _send
                    from django.conf import settings as _s
                    yr = AcademicYear.objects.filter(is_active=True).first()
                    asgn = SchoolAssessment.objects.filter(
                        school_id=school_id, academic_year=yr
                    ).select_related('assessor').first()
                    if asgn and asgn.assessor.email:
                        loc = "GPS Verified" if verified else "Not Verified"
                        _send(
                            subject=f"[IMS] Logbook Submitted — {student_name}",
                            message=(
                                f"Student {student_name} amewasilisha logbook.\n"
                                f"Eneo: {loc}\n\nIngia IMS kuona maelezo."
                            ),
                            from_email=_s.DEFAULT_FROM_EMAIL,
                            recipient_list=[asgn.assessor.email],
                            fail_silently=True,
                        )
                except Exception:
                    pass
            threading.Thread(
                target=_notify,
                args=(school.id, student.full_name, entry.id, entry.is_location_verified),
                daemon=True,
            ).start()

            if entry.is_location_verified:
                messages.success(request, "✅ Logbook imesajiliwa kikamilifu!")
            else:
                messages.warning(request, "⚠️ Logbook imesajiliwa. Eneo halikuthibitishwa.")

            return redirect('logbook_history')
        else:
            messages.error(request, "Tafadhali kagua makosa yaliyomo kwenye fomu.")
    else:
        form = LogbookForm(instance=logbook_entry)

    subjects = _cached_subjects(student)
    days_swahili = {0: 'Jumatatu', 1: 'Jumanne', 2: 'Jumatano', 3: 'Alhamisi', 4: 'Ijumaa'}

    return render(request, 'field_app/logbook.html', {
        'form': form,
        'student': student,
        'logbook_entry': logbook_entry,
        'today': today,
        'today_name': days_swahili.get(today.weekday(), 'Leo'),
        'school': school,
        'subjects': subjects,
    })

@login_required
def logbook_history(request):
    student = get_or_create_student_profile(request.user)

    week_filter = request.GET.get('week')
    month_filter = request.GET.get('month')

    entries = LogbookEntry.objects.filter(student=student).select_related('subject_taught', 'school')

    if week_filter:
        try:
            year, week = map(int, week_filter.split('-W'))
            start_date = datetime.strptime(f'{year}-W{week}-1', "%Y-W%W-%w").date()
            entries = entries.filter(date__range=[start_date, start_date + timedelta(days=6)])
        except ValueError:
            messages.error(request, "Tarehe ya wiki si sahihi.")

    elif month_filter:
        try:
            year, month = map(int, month_filter.split('-'))
            entries = entries.filter(date__year=year, date__month=month)
        except ValueError:
            messages.error(request, "Tarehe ya mwezi si sahihi.")

    else:
        today = timezone.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        entries = entries.filter(date__range=[start_of_week, start_of_week + timedelta(days=4)])

    return render(request, 'field_app/logbook_history.html', {
        'entries': entries.order_by('-date'),
        'student': student,
    })

@login_required
def download_logbook_pdf(request, period=None, period_type=None):
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import cm

    student = get_or_create_student_profile(request.user)
    period_value = period or period_type or 'week'
    today = timezone.now().date()

    if period_value == 'today':
        entries = LogbookEntry.objects.filter(student=student, date=today)
        filename = f"logbook_{today}.pdf"
        title = f"Logbook — {today}"
    elif period_value == 'week':
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=4)
        entries = LogbookEntry.objects.filter(student=student, date__range=[start_of_week, end_of_week])
        filename = f"logbook_wiki_{start_of_week}.pdf"
        title = f"Logbook — Wiki {start_of_week} hadi {end_of_week}"
    elif period_value == 'month':
        start_of_month = today.replace(day=1)
        next_month = today.replace(day=28) + timedelta(days=4)
        end_of_month = next_month - timedelta(days=next_month.day)
        entries = LogbookEntry.objects.filter(student=student, date__range=[start_of_month, end_of_month])
        filename = f"logbook_mwezi_{today.year}_{today.month:02d}.pdf"
        title = f"Logbook — Mwezi {today.month}/{today.year}"
    else:
        entries = LogbookEntry.objects.filter(student=student)
        filename = f"logbook_zote_{today}.pdf"
        title = "Logbook Zote"

    entries = entries.order_by('date')

    NAVY = rl_colors.HexColor('#0A2B5E')
    GOLD = rl_colors.HexColor('#C8900A')
    LIGHT = rl_colors.HexColor('#EEF1F6')
    WHITE = rl_colors.white

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
    )

    styles = getSampleStyleSheet()
    s_title = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=14, textColor=NAVY, spaceAfter=4)
    s_sub = ParagraphStyle('sub', fontName='Helvetica', fontSize=9, textColor=rl_colors.HexColor('#4A5568'), spaceAfter=2)
    s_head = ParagraphStyle('head', fontName='Helvetica-Bold', fontSize=10, textColor=WHITE)
    s_label = ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=8, textColor=NAVY)
    s_body = ParagraphStyle('body', fontName='Helvetica', fontSize=8, textColor=rl_colors.HexColor('#1A1A2E'), leading=11)
    s_small = ParagraphStyle('small', fontName='Helvetica', fontSize=7.5, textColor=rl_colors.HexColor('#4A5568'), leading=10)

    school_name = student.selected_school.name if student.selected_school else '—'
    district_name = (student.selected_school.district.name if student.selected_school and student.selected_school.district else '—')
    current_year = _cached_active_year()
    year_label = str(current_year) if current_year else '—'

    story = []

    # ── Cover header ──────────────────────────────────────────────────────────
    story.append(Paragraph("WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA", ParagraphStyle('gov', fontName='Helvetica-Bold', fontSize=11, textColor=NAVY, alignment=1)))
    story.append(Paragraph("Mfumo wa Ufuatiliaji wa Walimu Wanafunzi (IMS)", ParagraphStyle('gov2', fontName='Helvetica', fontSize=9, textColor=rl_colors.HexColor('#4A5568'), alignment=1, spaceAfter=6)))
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=6))
    story.append(Paragraph(title, s_title))

    info_data = [
        [Paragraph('<b>Jina la Mwanafunzi:</b>', s_label), Paragraph(student.full_name, s_body),
         Paragraph('<b>Shule:</b>', s_label), Paragraph(school_name, s_body)],
        [Paragraph('<b>Wilaya:</b>', s_label), Paragraph(district_name, s_body),
         Paragraph('<b>Mwaka wa Masomo:</b>', s_label), Paragraph(year_label, s_body)],
        [Paragraph('<b>Tarehe ya Chapisha:</b>', s_label), Paragraph(str(today), s_body),
         Paragraph('<b>Idadi ya Siku:</b>', s_label), Paragraph(str(entries.count()), s_body)],
    ]
    info_tbl = Table(info_data, colWidths=[3.5*cm, 5.5*cm, 3.5*cm, 5.5*cm])
    info_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT),
        ('BOX', (0,0), (-1,-1), 0.5, NAVY),
        ('INNERGRID', (0,0), (-1,-1), 0.3, rl_colors.HexColor('#CBD5E0')),
        ('PADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 10))

    # ── Per-entry ─────────────────────────────────────────────────────────────
    day_names = {'Monday':'Jumatatu','Tuesday':'Jumanne','Wednesday':'Jumatano',
                 'Thursday':'Alhamisi','Friday':'Ijumaa','Saturday':'Jumamosi','Sunday':'Jumapili'}

    for entry in entries:
        day_sw = day_names.get(entry.date.strftime('%A'), entry.date.strftime('%A'))
        gps_status = "✓ Imehakikiwa" if entry.is_location_verified else "✗ Haijahakikiwa"
        gps_color = rl_colors.HexColor('#10B981') if entry.is_location_verified else rl_colors.HexColor('#F59E0B')

        # Day header row
        day_hdr = Table(
            [[Paragraph(f"{day_sw} — {entry.date}", s_head),
              Paragraph(f"GPS: {gps_status}", ParagraphStyle('gps', fontName='Helvetica-Bold', fontSize=8, textColor=gps_color))]],
            colWidths=[13*cm, 5*cm]
        )
        day_hdr.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), NAVY),
            ('PADDING', (0,0), (-1,-1), 6),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ]))
        story.append(day_hdr)

        # Lesson periods
        lessons = entry.lessons_data if entry.lessons_data else []
        if not lessons:
            # Fallback to legacy fields
            if entry.morning_activity or entry.afternoon_activity:
                legacy_data = [
                    [Paragraph('<b>Shughuli za Asubuhi</b>', s_label),
                     Paragraph(entry.morning_activity or '—', s_body)],
                    [Paragraph('<b>Shughuli za Mchana</b>', s_label),
                     Paragraph(entry.afternoon_activity or '—', s_body)],
                ]
                leg_tbl = Table(legacy_data, colWidths=[4*cm, 14*cm])
                leg_tbl.setStyle(TableStyle([
                    ('BOX', (0,0), (-1,-1), 0.5, rl_colors.HexColor('#CBD5E0')),
                    ('INNERGRID', (0,0), (-1,-1), 0.3, rl_colors.HexColor('#CBD5E0')),
                    ('BACKGROUND', (0,0), (0,-1), LIGHT),
                    ('PADDING', (0,0), (-1,-1), 4),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ]))
                story.append(leg_tbl)
            else:
                story.append(Paragraph("Hakuna data ya masomo.", s_small))
        else:
            for lesson in lessons:
                period_num = lesson.get('period', '?')
                subj = lesson.get('subject', '—')
                cls = lesson.get('class', '—')
                main_topic = lesson.get('main_topic', '—')
                subtopic = lesson.get('subtopic', '') or '—'
                enrolled = lesson.get('enrolled', '—')
                present = lesson.get('present', '—')
                activity = lesson.get('activity_type', '—')
                methods = lesson.get('methods', '') or '—'
                aids = lesson.get('teaching_aids', '') or '—'
                intro = lesson.get('introduction', '') or '—'
                development = lesson.get('development', '') or '—'
                conclusion = lesson.get('conclusion', '') or '—'
                assessment = lesson.get('assessment', '') or '—'
                homework = lesson.get('homework', '') or '—'

                # Period header
                period_hdr = Table(
                    [[Paragraph(f"Kipindi {period_num}  |  {subj}  |  Darasa: {cls}  |  Waliojumuishwa: {enrolled}  |  Waliopo: {present}  |  Aina: {activity}",
                               ParagraphStyle('ph', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE))]],
                    colWidths=[18*cm]
                )
                period_hdr.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), GOLD),
                    ('PADDING', (0,0), (-1,-1), 5),
                ]))
                story.append(period_hdr)

                lesson_rows = [
                    [Paragraph('<b>Mada Kuu</b>', s_label), Paragraph(main_topic, s_body),
                     Paragraph('<b>Mada Ndogo</b>', s_label), Paragraph(subtopic, s_body)],
                    [Paragraph('<b>Mbinu</b>', s_label), Paragraph(methods, s_body),
                     Paragraph('<b>Vifaa vya Kufundishia</b>', s_label), Paragraph(aids, s_body)],
                    [Paragraph('<b>Utangulizi</b>', s_label), Paragraph(intro, s_small),
                     Paragraph('<b>Hitimisho</b>', s_label), Paragraph(conclusion, s_small)],
                    [Paragraph('<b>Uendelezaji</b>', s_label), Paragraph(development, s_small),
                     Paragraph('<b>Tathmini</b>', s_label), Paragraph(assessment, s_small)],
                    [Paragraph('<b>Kazi ya Nyumbani</b>', s_label), Paragraph(homework, s_small),
                     Paragraph('', s_label), Paragraph('', s_body)],
                ]
                lesson_tbl = Table(lesson_rows, colWidths=[3.5*cm, 5.5*cm, 3.5*cm, 5.5*cm])
                lesson_tbl.setStyle(TableStyle([
                    ('BOX', (0,0), (-1,-1), 0.5, rl_colors.HexColor('#CBD5E0')),
                    ('INNERGRID', (0,0), (-1,-1), 0.3, rl_colors.HexColor('#CBD5E0')),
                    ('BACKGROUND', (0,0), (0,-1), LIGHT),
                    ('BACKGROUND', (2,0), (2,-1), LIGHT),
                    ('PADDING', (0,0), (-1,-1), 4),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ]))
                story.append(lesson_tbl)

        # Other activities / challenges / reflection
        extra_rows = []
        if entry.other_activities:
            extra_rows.append([Paragraph('<b>Shughuli Nyingine</b>', s_label), Paragraph(entry.other_activities, s_body)])
        if entry.challenges_faced:
            extra_rows.append([Paragraph('<b>Changamoto</b>', s_label), Paragraph(entry.challenges_faced, s_body)])
        if entry.lessons_learned:
            extra_rows.append([Paragraph('<b>Tafakuri</b>', s_label), Paragraph(entry.lessons_learned, s_body)])
        if entry.supervisor_remarks:
            extra_rows.append([Paragraph('<b>Maoni ya Msimamizi</b>', ParagraphStyle('sr', fontName='Helvetica-Bold', fontSize=8, textColor=NAVY)),
                               Paragraph(entry.supervisor_remarks, s_body)])
        if extra_rows:
            extra_tbl = Table(extra_rows, colWidths=[4*cm, 14*cm])
            extra_tbl.setStyle(TableStyle([
                ('BOX', (0,0), (-1,-1), 0.5, rl_colors.HexColor('#CBD5E0')),
                ('INNERGRID', (0,0), (-1,-1), 0.3, rl_colors.HexColor('#CBD5E0')),
                ('BACKGROUND', (0,0), (0,-1), LIGHT),
                ('PADDING', (0,0), (-1,-1), 4),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ]))
            story.append(extra_tbl)

        story.append(Spacer(1, 10))

    if not entries.exists():
        story.append(Spacer(1, 20))
        story.append(Paragraph("Hakuna rekodi za logbook kwa kipindi kilichochaguliwa.", s_sub))

    # Footer
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceBefore=10, spaceAfter=4))
    story.append(Paragraph("© Wizara ya Elimu, Sayansi na Teknolojia — IMS v2.1.0",
                           ParagraphStyle('footer', fontName='Helvetica', fontSize=7, textColor=rl_colors.HexColor('#4A5568'), alignment=1)))

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
def logbook_download_options(request):
    """Page for choosing download options"""
    student = get_or_create_student_profile(request.user)

    total_entries = LogbookEntry.objects.filter(student=student).count()
    this_week_entries = LogbookEntry.objects.filter(
        student=student,
        date__gte=timezone.now().date() - timedelta(days=7)
    ).count()

    return render(request, 'field_app/logbook_download.html', {
        'student': student,
        'total_entries': total_entries,
        'this_week_entries': this_week_entries,
    })


@login_required
def profile_create(request):
    student = get_or_create_student_profile(request.user)

    if request.method == 'POST':
        form = StudentTeacherForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StudentTeacherForm(instance=student)

    return render(request, 'field_app/profile_create.html', {'form': form})

@login_required
def get_subjects(request, school_id):
    subject_caps = SchoolSubjectCapacity.objects.filter(school_id=school_id).select_related('subject')
    data = [
        {
            'id': sc.subject.id,
            'name': sc.subject.name,
            'current': sc.current_students,
            'max': sc.max_students
        }
        for sc in subject_caps
    ]
    return JsonResponse(data, safe=False)

@login_required
def confirm_school_selection(request, district_id):
    if request.method != 'POST':
        return redirect('select_school', district_id=district_id)

    school_id = request.POST.get('school_id')
    if not school_id:
        messages.error(request, "No school selected.")
        return redirect('select_school', district_id=district_id)

    district = get_object_or_404(District, id=district_id)
    school = get_object_or_404(School, id=school_id)

    school.refresh_from_db()
    if school.current_students >= school.capacity:
        messages.error(request, f"{school.name} is at full capacity!")
        return redirect('select_school', district_id=district_id)

    old_school_id = request.session.get('selected_school_id')
    if old_school_id and old_school_id != school.id:
        old_school = School.objects.filter(id=old_school_id).first()
        if old_school:
            old_school.current_students = Greatest(F('current_students') - 1, 0)
            old_school.save()

    request.session['selected_school_id'] = school.id
    school.current_students = F('current_students') + 1
    school.save()
    school.refresh_from_db()

    student = get_or_create_student_profile(request.user)
    student.selected_school = school
    student.save()
    invalidate_student_cache(student)

    messages.success(request, f"You have successfully selected {school.name}.")
    return redirect('dashboard')

@login_required
def my_assessors(request):
    """Wanafunzi waone assessors wao kwa mwaka huu wa masomo"""
    student = get_or_create_student_profile(request.user)

    if not student.selected_school:
        messages.error(request, "You need to select a school first to see your assessors.")
        return redirect('select_region')

    school = student.selected_school

    # 🔴 FIX: Get current academic year
    current_year = get_current_academic_year()

    print(f"\n🔍 MY ASSESSORS DEBUG:")
    print(f"   Student: {student.full_name}")
    print(f"   School: {school.name} (ID: {school.id})")
    print(f"   Current Academic Year: {current_year.year if current_year else 'None'}")

    if current_year:
        school_assessments = SchoolAssessment.objects.filter(
            school=school,
            academic_year=current_year
        ).select_related('assessor')
    else:
        school_assessments = SchoolAssessment.objects.none()

    assessors_data = []
    for assessment in school_assessments:
        assessors_data.append({
            'assessor': assessment.assessor,
            'assessment_date': assessment.assessment_date,
            'is_completed': assessment.is_completed,
        })
        print(f"   - Assessor: {assessment.assessor.full_name}, Completed: {assessment.is_completed}")

    return render(request, 'field_app/my_assessors.html', {
        'student': student,
        'school': school,
        'assessors_data': assessors_data,
        'current_year': current_year,
    })


@login_required
def change_school(request):
    """Mwanafunzi anaweza kubadili shule na somo ndani ya wiki 1 baada ya kuidhinishwa."""
    student = get_or_create_student_profile(request.user)

    if not student.selected_school:
        messages.error(request, "Hujachagua shule yoyote bado.")
        return redirect('select_region')

    CAN_CHANGE_DAYS = 7

    # Window is based on approval_date of the approved application
    approved_app = StudentApplication.objects.filter(
        student=student, status='approved'
    ).select_related('subject', 'school').first()

    approval_date = approved_app.approval_date if approved_app and approved_app.approval_date else None
    if approval_date:
        days_since_approval = (timezone.now() - approval_date).days
        remaining_days = max(0, CAN_CHANGE_DAYS - days_since_approval)
        can_change = days_since_approval <= CAN_CHANGE_DAYS
        cant_change_reason = None if can_change else 'expired'
        deadline = approval_date + timezone.timedelta(days=CAN_CHANGE_DAYS)
    else:
        # No approval yet — use selection date window
        if not student.initial_school_selection_date:
            student.initial_school_selection_date = timezone.now()
            student.save()
            invalidate_student_cache(student)
        days_since_approval = (timezone.now() - student.initial_school_selection_date).days
        remaining_days = max(0, CAN_CHANGE_DAYS - days_since_approval)
        can_change = days_since_approval <= CAN_CHANGE_DAYS
        cant_change_reason = None if can_change else 'expired'
        deadline = student.initial_school_selection_date + timezone.timedelta(days=CAN_CHANGE_DAYS)

    current_district = student.selected_school.district
    current_region = current_district.region
    districts_in_region = District.objects.filter(region=current_region).select_related('region')

    if request.method == 'POST' and not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        new_school_id = request.POST.get('new_school_id')

        if not new_school_id:
            messages.error(request, "Tafadhali chagua shule mpya.")
            return redirect('change_school')

        if not can_change:
            messages.error(request, "Muda wa kubadili shule umekwisha. Wiki moja baada ya kuidhinishwa tu.")
            return redirect('dashboard')

        try:
            from django.db import transaction
            new_school = School.objects.select_related('district', 'district__region').get(id=new_school_id)
            old_school = student.selected_school

            current_year = get_current_academic_year()
            is_pinned = SchoolPin.objects.filter(
                school=new_school, academic_year=current_year, is_pinned=True
            ).exists()
            if is_pinned:
                messages.error(request, f"Shule {new_school.name} haipatikani kwa sasa.")
                return redirect('change_school')

            with transaction.atomic():
                # Remove approved application and release subject capacity
                if approved_app:
                    if approved_app.subject:
                        SchoolSubjectCapacity.objects.filter(
                            school=old_school, subject=approved_app.subject
                        ).update(current_students=Greatest(F('current_students') - 1, 0))
                    approved_app.delete()

                # Clear student subjects
                student.subjects.clear()

                # Decrement old school, update student
                School.objects.filter(id=old_school.id).update(
                    current_students=Greatest(F('current_students') - 1, 0)
                )
                student.selected_school = new_school
                student.school_change_count = F('school_change_count') + 1
                student.last_school_change_date = timezone.now()
                student.save()
                invalidate_student_cache(student)

            if 'selected_school_id' in request.session:
                del request.session['selected_school_id']
            cache.delete(f'schools_district_{old_school.district_id}')
            cache.delete(f'schools_district_{new_school.district_id}')

            messages.success(request, f"Umebadili shule hadi {new_school.name}. Chagua somo lako jipya.")
            return redirect('select_subjects', school_id=new_school.id)

        except School.DoesNotExist:
            messages.error(request, "Shule haipatikani.")
            return redirect('change_school')
        except Exception as e:
            messages.error(request, f"Hitilafu: {str(e)}")
            return redirect('change_school')

    return render(request, 'field_app/change_school.html', {
        'student': student,
        'current_school': student.selected_school,
        'current_region': current_region,
        'districts': districts_in_region,
        'remaining_days': remaining_days,
        'deadline': deadline,
        'can_change': can_change,
        'cant_change_reason': cant_change_reason,
        'approved_app': approved_app,
    })


# ─────────────────────────────────────────────────────────────────────────────
# CHETI CHA MWANAFUNZI — Internship Completion Certificate
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def student_certificate(request):
    """Onesha cheti — preview daima, download baada ya is_final=True."""
    from field_app.models import BoardMember
    student = get_or_create_student_profile(request.user)
    fa = getattr(student, 'final_assessment', None)
    completed = fa is not None and fa.certificate_ready

    # Auto-lookup DEO wa wilaya ya shule
    deo = None
    if student.selected_school and student.selected_school.district:
        deo = BoardMember.objects.filter(
            role='deo',
            district=student.selected_school.district,
            is_active=True
        ).first()

    return render(request, 'field_app/student_certificate.html', {
        'student': student,
        'fa': fa,
        'completed': completed,
        'deo': deo,
    })


@login_required
def student_certificate_pdf(request):
    """Teaching Practice Certificate — top-down canvas, fills full A4 page."""
    import io, os, math
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.utils import simpleSplit

    student = get_or_create_student_profile(request.user)
    fa = getattr(student, 'final_assessment', None)
    # TEMPORARY PREVIEW — any logged-in user can download with sample data
    # TODO: restore gate after review: if not fa or not fa.certificate_ready: return Forbidden
    if fa is None:
        from types import SimpleNamespace
        from datetime import datetime as _dt
        fa = SimpleNamespace(
            kuhudhuria=18, daftari_la_kazi=17, mpango_wa_kazi=16,
            mpango_wa_somo=17, utendaji_darasani=18, jumla=86,
            daraja='A', daraja_maandishi='Excellent', maoni='',
            academic_year=SimpleNamespace(year='2024/2025'),
            assessed_by=SimpleNamespace(full_name='John Mwalimu'),
            finalized_at=_dt.now(), updated_at=_dt.now(),
            certificate_ready=True,
        )

    # ── Colors ────────────────────────────────────────────────────────────────
    NAVY  = colors.HexColor('#0A2B5E')
    GOLD  = colors.HexColor('#C8900A')
    LIGHT = colors.HexColor('#EEF1F6')
    WHITE = colors.white
    BLACK = colors.black
    GRADE_COL = {
        'A': colors.HexColor('#14532d'), 'B': colors.HexColor('#1e40af'),
        'C': colors.HexColor('#92400e'), 'F': colors.HexColor('#7f1d1d'),
    }
    GRADE_LABEL = {'A': 'EXCELLENT', 'B': 'GOOD', 'C': 'AVERAGE', 'F': 'FAIL'}

    # ── Coat of arms path ─────────────────────────────────────────────────────
    from django.conf import settings
    from django.contrib.staticfiles import finders as sf_finders
    _base = getattr(settings, 'BASE_DIR', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _sroot = getattr(settings, 'STATIC_ROOT', '') or ''
    coat_img_path = next((p for p in [
        sf_finders.find('images/tz_coat_of_arms.png'),
        os.path.join(_sroot, 'images', 'tz_coat_of_arms.png'),
        os.path.join(_base, 'field_app', 'static', 'images', 'tz_coat_of_arms.png'),
        os.path.join(_base, 'staticfiles', 'images', 'tz_coat_of_arms.png'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images', 'tz_coat_of_arms.png'),
    ] if p and os.path.exists(p)), None)

    # ── Data ──────────────────────────────────────────────────────────────────
    district = student.selected_school.district if student.selected_school else None
    deo = _get_deo_for_district(district) if district else None

    acad_year       = fa.academic_year.year if fa.academic_year else ''
    school_name     = student.selected_school.name if student.selected_school else '—'
    school_dist     = district.name if district else '—'
    from datetime import date as dt_date
    cert_date       = fa.finalized_at or fa.updated_at
    date_str        = cert_date.strftime('%d %B %Y') if cert_date else dt_date.today().strftime('%d %B %Y')
    supervisor_name = fa.assessed_by.full_name if fa.assessed_by else '—'
    deo_name        = deo.full_name if deo else '—'
    grade           = fa.daraja or 'B'

    # ── Serial number (security ID unique per student) ───────────────────────
    cert_date2 = fa.finalized_at or fa.updated_at
    _year      = cert_date2.year if cert_date2 else dt_date.today().year
    _dcode     = ''.join(ch for ch in school_dist.upper()[:5] if ch.isalpha())
    serial_no  = f"IMS/{_year}/{_dcode}/{student.pk:05d}"

    # ── Canvas setup ──────────────────────────────────────────────────────────
    buf = io.BytesIO()
    W, H = A4
    CX   = W / 2
    LM   = 1.8*cm
    RM   = W - 1.8*cm

    c = rl_canvas.Canvas(buf, pagesize=A4)

    # ── BORDERS ───────────────────────────────────────────────────────────────
    c.setStrokeColor(NAVY); c.setLineWidth(5)
    c.rect(0.65*cm, 0.65*cm, W - 1.3*cm, H - 1.3*cm)
    c.setStrokeColor(GOLD); c.setLineWidth(1.5)
    c.rect(1.05*cm, 1.05*cm, W - 2.1*cm, H - 2.1*cm)

    # ══════════════════════════════════════════════════════════════════════════
    # SECURITY WATERMARKS — drawn first (behind all content)
    # ══════════════════════════════════════════════════════════════════════════

    # 1. Micro-text security pattern — anti-forgery background texture
    micro = f"IMS CHETI CHA MAFUNZO YA UALIMU • {serial_no} • HALISI •  "
    micro_w = c.stringWidth(micro, 'Helvetica', 5.5)
    c.saveState()
    c.setFont('Helvetica', 5.5); c.setFillColor(NAVY); c.setFillAlpha(0.055)
    row_i, yp = 0, 4.0
    while yp < H + 9:
        xp = (-micro_w / 2) if row_i % 2 == 1 else 0.0
        while xp < W + micro_w:
            c.drawString(xp, yp, micro); xp += micro_w
        yp += 9.0; row_i += 1
    c.restoreState()

    # 2. Diagonal ghost watermark
    c.saveState()
    c.setFont('Helvetica-Bold', 72); c.setFillColor(NAVY); c.setFillAlpha(0.045)
    c.translate(CX, H / 2); c.rotate(45)
    c.drawCentredString(0,  52, "IMS")
    c.drawCentredString(0, -28, "HALISI")
    c.restoreState()

    # 3. Guilloche wave lines
    c.saveState()
    c.setStrokeColor(NAVY); c.setLineWidth(0.3); c.setStrokeAlpha(0.07)
    for offset in range(0, int(W), 12):
        c.bezier(offset, 0, offset+6, H*0.33, offset-6, H*0.66, offset, H)
    c.restoreState()

    # 4. CoA watermark (centred, faint background)
    if coat_img_path:
        try:
            c.saveState(); c.setFillAlpha(0.07)
            c.drawImage(coat_img_path, (W-230)/2, (H-276)/2, width=230, height=276, mask='auto')
            c.restoreState()
        except Exception:
            pass

    # 5. TAMISEMI circular seal (bottom-right)
    sx, sy = W - 3.5*cm, 3.5*cm
    ro, ri = 82, 55
    c.saveState()
    c.setFillColor(NAVY); c.setFillAlpha(0.06)
    c.circle(sx, sy, ro, fill=1, stroke=0)
    c.setFillAlpha(0); c.setStrokeColor(NAVY); c.setLineWidth(1.2)
    c.circle(sx, sy, ro, fill=0, stroke=1)
    c.setStrokeColor(GOLD); c.setLineWidth(0.7)
    c.circle(sx, sy, ri, fill=0, stroke=1)
    c.setFillAlpha(1)
    seal_txt = "OFISI YA RAIS  •  TAWALA ZA MIKOA NA SERIKALI ZA MITAA  •  "
    c.setFont('Helvetica-Bold', 6); c.setFillColor(NAVY); c.setFillAlpha(0.50)
    for i, ch in enumerate(seal_txt):
        ang = math.radians(90 - 360*i/len(seal_txt))
        tx, ty = sx + (ro-8)*math.cos(ang), sy + (ro-8)*math.sin(ang)
        c.saveState(); c.translate(tx, ty); c.rotate(math.degrees(ang)-90)
        c.drawCentredString(0, 0, ch); c.restoreState()
    c.setFont('Helvetica-Bold', 10); c.setFillColor(NAVY); c.setFillAlpha(0.60)
    c.drawCentredString(sx, sy + 6, "PO-RALG")
    c.setFont('Helvetica-Bold', 7); c.drawCentredString(sx, sy - 5, "TAMISEMI")
    c.setFont('Helvetica', 6); c.setFillAlpha(0.40)
    c.drawCentredString(sx, sy - 14, "TANZANIA")
    c.restoreState()

    # ══════════════════════════════════════════════════════════════════════════
    # VISIBLE CONTENT — top-down, precisely sized to fill full A4
    # Available height = 841.89 - 2*1.5cm = 756pt; total below = ~754pt ✓
    # ══════════════════════════════════════════════════════════════════════════
    y = H - 1.5*cm    # 799pt — start just inside top border

    # ── COAT OF ARMS (visible, top-centre) ────────────────────────────────────
    coa_w, coa_h = 68, 64     # 64pt tall = 2.26cm  (saves vs 86pt)
    if coat_img_path:
        try:
            c.drawImage(coat_img_path, CX - coa_w/2, y - coa_h, width=coa_w, height=coa_h, mask='auto')
        except Exception:
            pass
    y -= coa_h + 8             # 64 + 8 gap = 72pt

    # ── HEADER ────────────────────────────────────────────────────────────────
    c.setFont('Helvetica-Bold', 12); c.setFillColor(NAVY)
    c.drawCentredString(CX, y, "THE UNITED REPUBLIC OF TANZANIA");  y -= 17
    c.setFont('Helvetica-Bold', 10.5)
    c.drawCentredString(CX, y, "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY");  y -= 15
    c.setFont('Helvetica', 8.5)
    c.drawCentredString(CX, y, "PRESIDENT'S OFFICE — REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT (PO-RALG / TAMISEMI)")
    y -= 16

    # Double rule under header
    c.setStrokeColor(NAVY); c.setLineWidth(3)
    c.line(LM, y, RM, y);  y -= 4
    c.setStrokeColor(GOLD); c.setLineWidth(1.2)
    c.line(LM, y, RM, y);  y -= 14

    # ── TITLE ─────────────────────────────────────────────────────────────────
    c.setFont('Helvetica-Bold', 17); c.setFillColor(NAVY)
    c.drawCentredString(CX, y, "CERTIFICATE OF TEACHING PRACTICE COMPLETION");  y -= 20

    # Gold centre rule
    gl = W * 0.55 / 2
    c.setStrokeColor(GOLD); c.setLineWidth(1.2)
    c.line(CX - gl, y, CX + gl, y);  y -= 22

    # ── BODY ──────────────────────────────────────────────────────────────────
    c.setFont('Helvetica', 11); c.setFillColor(BLACK)
    c.drawCentredString(CX, y, "This is to certify that");  y -= 34

    c.setFont('Helvetica-Bold', 26); c.setFillColor(NAVY)
    c.drawCentredString(CX, y, student.full_name.upper());  y -= 38

    c.setFont('Helvetica', 11); c.setFillColor(BLACK)
    c.drawCentredString(CX, y, "has successfully completed a period of Teaching Practice at");  y -= 30

    c.setFont('Helvetica-Bold', 15); c.setFillColor(NAVY)
    c.drawCentredString(CX, y, school_name.upper());  y -= 22

    detail = f"{school_dist} District"
    if acad_year: detail += f"   |   Academic Year: {acad_year}"
    c.setFont('Helvetica', 10.5); c.setFillColor(colors.HexColor('#444'))
    c.drawCentredString(CX, y, detail);  y -= 24

    stmt = ("The student demonstrated satisfactory performance in all required areas of the "
            "teaching practicum as stipulated by the Ministry of Education, Science and Technology "
            "guidelines for Initial Teacher Education (ITE) programmes in Tanzania.")
    c.setFont('Helvetica', 10.5); c.setFillColor(colors.HexColor('#333'))
    for line in simpleSplit(stmt, 'Helvetica', 10.5, W - 4*cm):
        c.drawCentredString(CX, y, line);  y -= 16
    y -= 14

    # ── SCORE TABLE ───────────────────────────────────────────────────────────
    tbl_data = [
        ('ASSESSMENT CRITERION',  'MARKS', 'MAX'),
        ('Attendance',            str(fa.kuhudhuria),        '20'),
        ('Work Diary (Logbook)',  str(fa.daftari_la_kazi),   '20'),
        ('Scheme of Work',        str(fa.mpango_wa_kazi),    '20'),
        ('Lesson Planning',       str(fa.mpango_wa_somo),    '20'),
        ('Classroom Performance', str(fa.utendaji_darasani), '20'),
        ('TOTAL',                 str(fa.jumla),             '100'),
    ]
    COL_W   = [W - 2*LM - 6*cm, 3*cm, 3*cm]
    ROW_H   = 25
    tbl_top = y

    for idx, row in enumerate(tbl_data):
        rt = tbl_top - idx * ROW_H
        rb = rt - ROW_H
        if idx == 0:              bg = NAVY
        elif idx == len(tbl_data)-1: bg = LIGHT
        elif idx % 2 == 0:        bg = colors.HexColor('#f4f6fb')
        else:                     bg = WHITE
        c.setFillColor(bg)
        c.rect(LM, rb, sum(COL_W), ROW_H, fill=1, stroke=0)
        ty = rb + 8; xc = LM
        for j, (cell, cw) in enumerate(zip(row, COL_W)):
            if idx == 0:   c.setFont('Helvetica-Bold', 9.5); c.setFillColor(WHITE)
            elif j == 0:   c.setFont('Helvetica', 10);       c.setFillColor(BLACK)
            else:          c.setFont('Helvetica-Bold', 10);   c.setFillColor(NAVY if idx < len(tbl_data)-1 else BLACK)
            if j == 0: c.drawString(xc+12, ty, cell)
            else:      c.drawCentredString(xc+cw/2, ty, cell)
            xc += cw
        c.setStrokeColor(colors.HexColor('#b0c0d8')); c.setLineWidth(0.4)
        c.rect(LM, rb, sum(COL_W), ROW_H, fill=0, stroke=1)
        xg = LM
        for cw in COL_W[:-1]:
            xg += cw; c.line(xg, rb, xg, rt)

    y = tbl_top - len(tbl_data)*ROW_H - 18

    # ── GRADE ─────────────────────────────────────────────────────────────────
    c.setStrokeColor(colors.HexColor('#aabbcc')); c.setLineWidth(0.5)
    c.line(LM, y+6, RM, y+6);  y -= 10

    c.setFont('Helvetica-Bold', 12); c.setFillColor(GOLD)
    c.drawCentredString(CX, y, f"OVERALL GRADE: {GRADE_LABEL.get(grade,'')}  ({fa.jumla}/100)");  y -= 14

    c.setFont('Helvetica-Bold', 48); c.setFillColor(GRADE_COL.get(grade, NAVY))
    c.drawCentredString(CX, y, grade);  y -= 46

    if fa.maoni:
        c.setFont('Helvetica-Oblique', 9.5); c.setFillColor(colors.HexColor('#555'))
        c.drawCentredString(CX, y, f"Remarks: {fa.maoni}");  y -= 14
    y -= 8

    # ── BOTTOM RULES ──────────────────────────────────────────────────────────
    c.setStrokeColor(GOLD); c.setLineWidth(1.2)
    c.line(LM, y, RM, y);  y -= 5
    c.setStrokeColor(NAVY); c.setLineWidth(3)
    c.line(LM, y, RM, y);  y -= 20

    # ── SIGNATURES ────────────────────────────────────────────────────────────
    # White background strip clears watermark rows so signatures are readable
    c.saveState()
    c.setFillColor(colors.white); c.setFillAlpha(1)
    c.rect(LM - 4, y - 30, (RM - LM) + 8, 52, fill=1, stroke=0)
    c.restoreState()

    SIG_COLS = [
        (LM,           LM+5.8*cm,   'School Supervisor',          supervisor_name, date_str),
        (LM+6.1*cm,   LM+11.8*cm,  'District Education Officer',  deo_name,        f'{school_dist} District'),
        (LM+12.1*cm,  RM,           'Date of Issue',              date_str,        ''),
    ]
    for x1, x2, ttl, nm, sub in SIG_COLS:
        xc = (x1+x2)/2
        c.setFont('Helvetica-Oblique', 11); c.setFillColor(NAVY)
        c.drawCentredString(xc, y+15, nm)
        c.setStrokeColor(colors.HexColor('#666')); c.setLineWidth(0.7)
        c.line(x1, y, x2, y)
        c.setFont('Helvetica-Bold', 8.5); c.setFillColor(NAVY)
        c.drawCentredString(xc, y-13, ttl)
        if sub:
            c.setFont('Helvetica', 7.5); c.setFillColor(colors.HexColor('#444'))
            c.drawCentredString(xc, y-24, sub)

    # ── SECURITY FOOTER (serial number + verification code visible) ────────────
    fy = 0.85*cm
    c.setStrokeColor(colors.HexColor('#888')); c.setLineWidth(0.4)
    c.line(LM, fy+0.35*cm, RM, fy+0.35*cm)
    c.setFont('Helvetica', 6.5); c.setFillColor(colors.HexColor('#555'))
    c.drawString(LM, fy+0.05*cm, f"Namba ya Uthibitisho: {serial_no}")
    c.drawRightString(RM, fy+0.05*cm, f"Tarehe: {date_str}  |  IMS • TAMISEMI")

    c.save()
    buf.seek(0)
    safe_name = student.full_name.replace(' ', '_').replace('/', '_')
    response  = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Teaching_Practice_Certificate_{safe_name}.pdf"'
    return response


# ─────────────────────────────────────────────────────────────────────────────
# BARUA RASMI YA UTHIBITISHO — Official GoT-format confirmation letter
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def student_confirmation_letter_pdf(request):
    """Official GoT-style confirmation letter matching placement letter format, with anti-forgery watermarks."""
    import io, os, math
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.utils import simpleSplit

    student = get_or_create_student_profile(request.user)
    fa = getattr(student, 'final_assessment', None)
    if not fa or not fa.certificate_ready:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Barua haipatikani. Mafunzo lazima yakamilishwe kwanza.")

    # ── Colors ────────────────────────────────────────────────────────────────
    NAVY  = colors.HexColor('#0A2B5E')
    BLACK = colors.black

    # ── Coat of arms path ─────────────────────────────────────────────────────
    from django.conf import settings
    from django.contrib.staticfiles import finders as sf_finders
    _base = getattr(settings, 'BASE_DIR', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _sroot = getattr(settings, 'STATIC_ROOT', '') or ''
    coat_img_path = next((p for p in [
        sf_finders.find('images/tz_coat_of_arms.png'),
        os.path.join(_sroot, 'images', 'tz_coat_of_arms.png'),
        os.path.join(_base, 'field_app', 'static', 'images', 'tz_coat_of_arms.png'),
        os.path.join(_base, 'staticfiles', 'images', 'tz_coat_of_arms.png'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images', 'tz_coat_of_arms.png'),
    ] if p and os.path.exists(p)), None)

    # ── Data ──────────────────────────────────────────────────────────────────
    district = student.selected_school.district if student.selected_school else None
    region   = getattr(district, 'region', None) if district else None
    deo      = _get_deo_for_district(district) if district else None

    from datetime import date as dt_date
    cert_date       = fa.finalized_at or fa.updated_at
    date_str        = cert_date.strftime('%d %B %Y') if cert_date else dt_date.today().strftime('%d %B %Y')
    acad_year       = fa.academic_year.year if fa.academic_year else ''
    school_name     = student.selected_school.name if student.selected_school else '—'
    school_dist     = district.name if district else '—'
    region_name     = region.name if region else '—'
    supervisor_name = fa.assessed_by.full_name if fa.assessed_by else '—'
    deo_name        = deo.full_name if deo else '—'
    deo_phone       = deo.phone_number if deo and deo.phone_number else '—'
    grade           = fa.daraja
    GRADE_SW        = {'A': 'BORA SANA', 'B': 'VIZURI', 'C': 'WASTANI', 'F': 'KUSHINDWA'}

    # ── Unique serial & reference ──────────────────────────────────────────────
    year       = cert_date.year if cert_date else dt_date.today().year
    dist_code  = ''.join(ch for ch in school_dist.upper()[:5] if ch.isalpha())
    serial_no  = f"IMS/{year}/{dist_code}/{student.pk:05d}"
    kumb_no    = f"IMS.ELIMU/{year}/{dist_code}/{student.pk:05d}"

    # ── Canvas setup ──────────────────────────────────────────────────────────
    buf = io.BytesIO()
    W, H = A4
    CX = W / 2
    LM = 2.0*cm
    RM = W - 2.0*cm

    c = rl_canvas.Canvas(buf, pagesize=A4)

    # ══════════════════════════════════════════════════════════════════════════
    # SECURITY WATERMARKS — drawn first so they appear behind text
    # ══════════════════════════════════════════════════════════════════════════

    # 1. Micro-text pattern — fills entire page with tiny repeating text
    #    This shows as degraded/visible pattern when photocopied, proving forgery
    micro = f"IMS MAFUNZO YA UALIMU • {serial_no} • HALISI •  "
    micro_w = c.stringWidth(micro, 'Helvetica', 5.5)
    c.saveState()
    c.setFont('Helvetica', 5.5)
    c.setFillColor(NAVY)
    c.setFillAlpha(0.055)
    row_idx = 0
    y_pos = 4.0
    while y_pos < H + 9:
        x_pos = (-micro_w / 2) if row_idx % 2 == 1 else 0.0
        while x_pos < W + micro_w:
            c.drawString(x_pos, y_pos, micro)
            x_pos += micro_w
        y_pos += 9.0
        row_idx += 1
    c.restoreState()

    # 2. Diagonal large watermark — "IMS HALISI" at 45° centred on page
    c.saveState()
    c.setFont('Helvetica-Bold', 60)
    c.setFillColor(NAVY)
    c.setFillAlpha(0.032)
    c.translate(CX, H / 2)
    c.rotate(45)
    c.drawCentredString(0,  48, "IMS")
    c.drawCentredString(0, -20, "HALISI")
    c.restoreState()

    # 3. Fine guilloche border lines — repeating waves, very faint
    c.saveState()
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.3)
    c.setStrokeAlpha(0.07)
    for offset in range(0, int(W), 12):
        c.bezier(offset, 0, offset + 6, H * 0.33, offset - 6, H * 0.66, offset, H)
    c.restoreState()

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE CONTENT
    # ══════════════════════════════════════════════════════════════════════════

    y = H - 1.5*cm   # starting y (top)

    # ── Main title ────────────────────────────────────────────────────────────
    c.setFont('Helvetica-Bold', 13); c.setFillColor(BLACK)
    c.drawCentredString(CX, y, "JAMHURI YA MUUNGANO WA TANZANIA"); y -= 0.58*cm

    c.setFont('Helvetica-Bold', 11)
    c.drawCentredString(CX, y, "OFISI YA RAIS - TAWALA ZA MIKOA NA SERIKALI ZA MITAA"); y -= 0.45*cm

    c.setFont('Helvetica', 9)
    c.drawCentredString(CX, y, "(PO-RALG / TAMISEMI)"); y -= 0.32*cm

    # Double rule under title
    c.setStrokeColor(BLACK); c.setLineWidth(1.5)
    c.line(LM, y, RM, y); y -= 4
    c.setLineWidth(0.5)
    c.line(LM, y, RM, y); y -= 0.45*cm

    # ── 3-column header (contact | coat of arms | address) ────────────────────
    section_top = y
    col_r_x = CX + 1.3*cm   # right block start x
    coa_w_pt, coa_h_pt = 68, 82

    if coat_img_path:
        try:
            c.drawImage(coat_img_path,
                        CX - coa_w_pt / 2 - 0.6*cm, section_top - coa_h_pt,
                        width=coa_w_pt, height=coa_h_pt, mask='auto')
        except Exception:
            pass

    # Left block — DEO / office contact
    lf = [
        ('Simu ya Upepo: ', f'"{school_dist.upper()}"'),
        ('Simu: ', deo_phone),
        ('Tovuti: ', 'www.tamisemi.go.tz'),
        ('Baruapepe: ', 'elimu@tamisemi.go.tz'),
        ('Unapojibu Taja:', ''),
    ]
    ly = section_top - 0.1*cm
    for lbl, val in lf:
        c.setFont('Helvetica-Bold', 8); c.setFillColor(BLACK)
        lw = c.stringWidth(lbl, 'Helvetica-Bold', 8)
        c.drawString(LM, ly, lbl)
        c.setFont('Helvetica', 8)
        c.drawString(LM + lw, ly, val)
        ly -= 0.40*cm

    # Right block — Office address
    rf = [
        (True,  f"Ofisi ya Afisa Elimu wa Wilaya,"),
        (False, f"Wilaya ya {school_dist},"),
        (False, f"Mkoa wa {region_name},"),
        (False, "TANZANIA."),
    ]
    ry = section_top - 0.1*cm
    for bold, line in rf:
        c.setFont('Helvetica-Bold' if bold else 'Helvetica', 8.5)
        c.setFillColor(BLACK)
        c.drawString(col_r_x, ry, line)
        ry -= 0.42*cm

    y = section_top - coa_h_pt - 0.35*cm   # below coat of arms

    # Double rule under header
    c.setStrokeColor(BLACK); c.setLineWidth(1.5)
    c.line(LM, y, RM, y); y -= 4
    c.setLineWidth(0.5)
    c.line(LM, y, RM, y); y -= 0.55*cm

    # ── Reference number & date (same line) ───────────────────────────────────
    c.setFont('Helvetica-Bold', 9.5); c.setFillColor(BLACK)
    c.drawString(LM, y, f"Kumb. Na. {kumb_no}")
    c.drawRightString(RM, y, date_str)
    y -= 0.85*cm

    # ── Recipient ─────────────────────────────────────────────────────────────
    c.setFont('Helvetica-Bold', 10)
    c.drawString(LM, y, f"{student.full_name},"); y -= 0.48*cm
    c.setFont('Helvetica', 10)
    c.drawString(LM, y, f"{school_name},"); y -= 0.48*cm
    c.setFont('Helvetica-Bold', 10)
    c.drawString(LM, y, f"{school_dist.upper()}."); y -= 0.95*cm

    # ── Subject line (centred, bold, underlined) ──────────────────────────────
    subj = "YAH: UTHIBITISHO WA KUKAMILISHA MAFUNZO YA UALIMU WA VITENDO"
    c.setFont('Helvetica-Bold', 10.5); c.setFillColor(BLACK)
    sw = c.stringWidth(subj, 'Helvetica-Bold', 10.5)
    c.drawCentredString(CX, y, subj)
    c.setLineWidth(0.9)
    c.line(CX - sw/2, y - 2, CX + sw/2, y - 2)
    y -= 0.95*cm

    # ── Body paragraphs (numbered, with first-line indent) ────────────────────
    body_w = RM - LM - 1.3*cm
    indent = LM + 1.3*cm

    def draw_para(num, text, cur_y):
        c.setFont('Helvetica-Bold', 10); c.setFillColor(BLACK)
        c.drawString(LM, cur_y, f"{num}.")
        c.setFont('Helvetica', 10)
        for line in simpleSplit(text, 'Helvetica', 10, body_w):
            c.drawString(indent, cur_y, line)
            cur_y -= 0.50*cm
        return cur_y - 0.22*cm

    p1 = (f"Tafadhali rejea mafunzo ya ualimu wa vitendo (Teaching Practice) yaliyofanyika "
          f"katika {school_name} wilayani {school_dist}, Mkoa wa {region_name}, "
          f"katika Mwaka wa Masomo {acad_year}. Ninayo furaha kukuthibitishia kwamba "
          f"umefanya vizuri na kukamilisha mafunzo yako ya ualimu wa vitendo.")
    y = draw_para("1", p1, y)

    p2 = (f"Katika tathmini iliyofanywa na msimamizi wa shule Ndg. {supervisor_name}, "
          f"ulipata alama {fa.jumla}/100 na kufaulu kwa Daraja {grade} "
          f"({GRADE_SW.get(grade, grade)}).")
    y = draw_para("2", p2, y)

    p3 = ("Uthibitisho huu umetolewa kwa mujibu wa mwongozo wa Wizara ya Elimu, Sayansi "
          "na Teknolojia unaosimamia Mafunzo ya Awali ya Ualimu (Initial Teacher Education "
          "— ITE) nchini Tanzania.")
    y = draw_para("3", p3, y)

    p4 = (f"Nambari ya uthibitisho wa hati hii ni {serial_no}. Hati hii ina alama za "
          f"usalama za kuzuia uigaji, zikiwemo maandishi madogo ya siri yanayojaza ukurasa "
          f"wote. Hati bandia inaweza kutambuliwa kwa urahisi na wataalamu.")
    y = draw_para("4", p4, y)

    p5 = "Nakutakia kila la kheri katika taaluma yako ya ualimu."
    y = draw_para("5", p5, y)

    y -= 0.7*cm

    # ── Signature ─────────────────────────────────────────────────────────────
    # Italic auto-generated name (looks like a signature)
    c.setFont('Helvetica-Oblique', 13); c.setFillColor(NAVY)
    c.drawString(LM, y, deo_name); y -= 0.38*cm

    c.setStrokeColor(BLACK); c.setLineWidth(0.7)
    c.line(LM, y, LM + 6.5*cm, y); y -= 0.42*cm

    c.setFont('Helvetica-Bold', 10); c.setFillColor(BLACK)
    c.drawString(LM, y, deo_name); y -= 0.42*cm
    c.drawString(LM, y, "AFISA ELIMU WA WILAYA"); y -= 0.40*cm
    c.setFont('Helvetica', 9.5)
    c.drawString(LM, y, f"Wilaya ya {school_dist}")

    # ── Security footer ───────────────────────────────────────────────────────
    footer_y = 1.9*cm
    c.setStrokeColor(BLACK); c.setLineWidth(0.5)
    c.line(LM, footer_y + 0.55*cm, RM, footer_y + 0.55*cm)
    c.setFont('Helvetica', 7); c.setFillColor(colors.HexColor('#333'))
    c.drawString(LM, footer_y + 0.22*cm,
                 f"Namba ya Uthibitisho: {serial_no}   |   Tarehe: {date_str}")
    c.drawRightString(RM, footer_y + 0.22*cm, "Hati Rasmi — IMS • TAMISEMI")

    # ── Nakala (CC) ───────────────────────────────────────────────────────────
    nak_y = footer_y - 0.3*cm
    c.setFont('Helvetica-Bold', 8.5); c.setFillColor(BLACK)
    c.drawString(LM, nak_y, "Nakala:")
    c.setFont('Helvetica', 8.5)
    for item in [
        f"Mkuu wa Shule — {school_name}, Wilaya ya {school_dist}.",
        "Afisa Elimu wa Mkoa (REO).",
        "Kumbukumbu — Ofisi ya DEO.",
    ]:
        nak_y -= 0.38*cm
        c.drawString(LM + 2.0*cm, nak_y, item)

    c.save()
    buf.seek(0)
    safe_name = student.full_name.replace(' ', '_').replace('/', '_')
    response  = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Barua_Uthibitisho_{safe_name}.pdf"'
    return response
