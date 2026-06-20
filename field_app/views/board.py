import csv, io, json, re, secrets, string
from io import BytesIO
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count, Case, When, Value, BooleanField, F, Q, Prefetch, Max
from django.db import models
from django.db.models.functions import Greatest
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from geopy.distance import geodesic
from .ai_utils import client, model_name
from field_app.decorators import board_login_required, assessor_login_required
from .forms import (
    CustomLoginForm, StudentRegistrationForm, StudentTeacherForm,
    LogbookForm, AssessorLoginForm, BulkAssignForm, RegionFieldInputForm
)
from .forms import SchemeOfWorkForm
from .models import (
    Assessor, School, SchoolAssignment, StudentTeacher,
    StudentAssessment, SchoolAssessment, SchoolRequirement,
    StudentApplication, Region, RegionPin, SchoolPin,
    District, Subject, SchoolSubjectCapacity,
    LogbookEntry, ApprovalLetter, AcademicYear, SchemeOfWork,
    BoardMember, BoardComment, LessonPlan, MonthlyReport,
    DistrictAllocation, SchoolAllocation, SchoolHeadRequest,
    FinalAssessment,
)
User = get_user_model()
from .utils import (
    _cached_active_year, get_current_academic_year, get_or_create_student_profile,
    invalidate_student_cache, generate_random_password, _build_individual_letter_pdf,
    _cached_subjects, _cached_today_logbook, _invalidate_today_logbook,
    _active_year_students, _get_board_member, _can_access_region, _can_access_district,
    _get_deo_for_district, _cached_schools_by_district,
    process_bulk_assignment_with_academic_year, _generate_requests_pdf,
    _ai_parse_allocation_document, _ai_summarise_requests, _send_sms_africastalking,
)


def _head_only_bm(email):
    """Return BoardMember iff email belongs to an active head_teacher and NO other active role."""
    bms = BoardMember.objects.filter(
        user__email__iexact=email, is_active=True
    ).select_related('school', 'user')
    head = None
    for bm in bms:
        if bm.role == 'head_teacher':
            head = bm
        else:
            # Email belongs to another role — refuse entirely
            return None
    return head


def head_teacher_login(request):
    """Dedicated login page for school heads ONLY.
    Forces logout of any non-head session. Never grants access to other roles."""

    if request.user.is_authenticated:
        bm = _get_board_member(request)
        if bm and bm.role == 'head_teacher' and bm.school:
            return redirect('board_head_teacher', school_id=bm.school.id)
        # Logged in as wrong role (REO/DEO/etc.) — force logout, show login form
        logout(request)

    prefill_email = request.GET.get('email', '')
    prefill_school_id = request.GET.get('school_id', '')
    first_time = request.GET.get('first_time', '0') == '1'
    submitted_request = request.GET.get('submitted', '0') == '1'

    if request.method == 'POST':
        mode = request.POST.get('mode', 'head_login')

        if mode == 'head_set_password':
            email = request.POST.get('email', '').strip().lower()
            school_id = request.POST.get('school_id', '').strip()
            password1 = request.POST.get('password1', '')
            password2 = request.POST.get('password2', '')
            school = School.objects.filter(id=school_id).first()
            ctx = {'first_time': True, 'prefill_email': email,
                   'prefill_school_id': school_id, 'school': school}

            bm = _head_only_bm(email)
            if not bm:
                ctx['error'] = 'Barua pepe hii haipo kwenye orodha ya wakuu wa shule, au ina ruhusa nyingine. Wasiliana na DEO wako.'
                return render(request, 'field_app/head_teacher_login.html', ctx)
            if len(password1) < 6:
                ctx['error'] = 'Nywila iwe na herufi 6 au zaidi.'
                return render(request, 'field_app/head_teacher_login.html', ctx)
            if password1 != password2:
                ctx['error'] = 'Nywila mbili hazifanani. Jaribu tena.'
                return render(request, 'field_app/head_teacher_login.html', ctx)
            if not bm.school:
                ctx['error'] = 'Akaunti yako bado haijaunganishwa na shule. Wasiliana na DEO wako.'
                return render(request, 'field_app/head_teacher_login.html', ctx)

            bm.user.set_password(password1)
            bm.user.save()
            login(request, bm.user, backend='field_app.backends.EmailBackend')
            messages.success(request, f'Karibu {bm.full_name or email}! Nywila yako imewekwa.')
            return redirect('board_head_teacher', school_id=bm.school.id)

        elif mode == 'head_reset_step1':
            email = request.POST.get('email', '').strip().lower()
            ctx = {'show_reset': True, 'reset_step': 1, 'prefill_reset_email': email}
            if not email:
                ctx['reset_error'] = 'Weka barua pepe yako.'
                return render(request, 'field_app/head_teacher_login.html', ctx)
            bm = _head_only_bm(email)
            if not bm:
                ctx['reset_error'] = 'Barua pepe hii haipo kwenye mfumo wa wakuu wa shule, au ina ruhusa nyingine. Wasiliana na DEO wako.'
                return render(request, 'field_app/head_teacher_login.html', ctx)
            return render(request, 'field_app/head_teacher_login.html', {
                'show_reset': True, 'reset_step': 2, 'prefill_reset_email': email,
            })

        elif mode == 'head_reset_step2':
            email = request.POST.get('email', '').strip().lower()
            password1 = request.POST.get('password1', '')
            password2 = request.POST.get('password2', '')
            ctx = {'show_reset': True, 'reset_step': 2, 'prefill_reset_email': email}
            if len(password1) < 6:
                ctx['reset_error'] = 'Nywila iwe na herufi 6 au zaidi.'
                return render(request, 'field_app/head_teacher_login.html', ctx)
            if password1 != password2:
                ctx['reset_error'] = 'Nywila mbili hazifanani. Jaribu tena.'
                return render(request, 'field_app/head_teacher_login.html', ctx)
            bm = _head_only_bm(email)
            if not bm:
                ctx['reset_error'] = 'Hitilafu ya usalama: barua pepe haikutambuliwa. Anza upya.'
                ctx['reset_step'] = 1
                return render(request, 'field_app/head_teacher_login.html', ctx)
            if not bm.school:
                ctx['reset_error'] = 'Akaunti yako bado haijaunganishwa na shule. Wasiliana na DEO wako.'
                return render(request, 'field_app/head_teacher_login.html', ctx)
            bm.user.set_password(password1)
            bm.user.save()
            login(request, bm.user, backend='field_app.backends.EmailBackend')
            messages.success(request, 'Nywila imebadilishwa. Umeingia mfumoni.')
            return redirect('board_head_teacher', school_id=bm.school.id)

        else:  # head_login
            email = request.POST.get('email', '').strip().lower()
            password = request.POST.get('password', '')
            school_id = request.POST.get('school_id', '').strip()
            school = School.objects.filter(id=school_id).first() if school_id else None
            ctx = {'prefill_email': email, 'prefill_school_id': school_id, 'school': school}

            bm = _head_only_bm(email)
            if not bm:
                ctx['error'] = 'Barua pepe hii haipo kwenye orodha ya wakuu wa shule, au ina ruhusa nyingine.'
                return render(request, 'field_app/head_teacher_login.html', ctx)

            user = authenticate(request, username=email, password=password,
                                backend='field_app.backends.EmailBackend')
            if not user:
                ctx['error'] = 'Nywila si sahihi. Jaribu tena.'
                return render(request, 'field_app/head_teacher_login.html', ctx)

            # Final role check after authenticate — belt-and-suspenders
            confirmed_bm = _head_only_bm(user.email)
            if not confirmed_bm or not confirmed_bm.school:
                ctx['error'] = 'Hitilafu ya usalama. Wasiliana na msimamizi.'
                return render(request, 'field_app/head_teacher_login.html', ctx)

            login(request, user, backend='field_app.backends.EmailBackend')
            return redirect('board_head_teacher', school_id=confirmed_bm.school.id)

    school = School.objects.filter(id=prefill_school_id).first() if prefill_school_id else None
    return render(request, 'field_app/head_teacher_login.html', {
        'prefill_email': prefill_email,
        'prefill_school_id': prefill_school_id,
        'first_time': first_time,
        'school': school,
        'submitted_request': submitted_request,
    })


def board_login(request):
    if request.user.is_authenticated:
        bm = _get_board_member(request)
        if bm and bm.role == 'head_teacher':
            # Head teacher tried to use board login — force logout, send to correct page
            logout(request)
            messages.warning(request, 'Tafadhali ingia kupitia ukurasa wa Wakuu wa Shule.')
            return redirect('head_login')
        if bm and bm.role != 'head_teacher':
            return redirect('board_home')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        user = authenticate(request, username=email, password=password,
                            backend='field_app.backends.EmailBackend')
        if user:
            try:
                bm = user.board_member
                if bm and bm.is_active:
                    if bm.role == 'head_teacher':
                        messages.error(request, 'Wewe ni Mkuu wa Shule. Ingia kupitia ukurasa wa Wakuu wa Shule.')
                    else:
                        login(request, user, backend='field_app.backends.EmailBackend')
                        return redirect('board_home')
                else:
                    messages.error(request, 'Akaunti yako imezimwa. Wasiliana na msimamizi.')
            except Exception:
                messages.error(request, 'Barua pepe au nywila si sahihi.')
        else:
            messages.error(request, 'Barua pepe au nywila si sahihi.')

    return render(request, 'field_app/board_login.html', {})


def board_logout(request):
    bm = _get_board_member(request)
    is_head = bm and bm.role == 'head_teacher'
    logout(request)
    return redirect('head_login' if is_head else 'board_login')


@board_login_required
def board_home(request):
    bm = _get_board_member(request)
    if not bm:
        messages.error(request, 'Huna ruhusa ya Bodi ya Walimu.')
        return redirect('board_login')

    # DEO → redirect directly to their district (skip region selection)
    if bm.role == 'deo':
        if bm.district:
            return redirect('board_school_list', district_id=bm.district.id)
        messages.warning(request, 'Akaunti yako ya DEO haina wilaya iliyowekwa. Wasiliana na msimamizi.')

    # REO → redirect directly to their region
    if bm.role == 'reo':
        if bm.region:
            return redirect('board_district_list', region_id=bm.region.id)
        messages.warning(request, 'Akaunti yako ya REO haina mkoa iliyowekwa. Wasiliana na msimamizi.')

    # Head Teacher → redirect to their school dashboard
    if bm.role == 'head_teacher':
        if bm.school:
            return redirect('board_head_teacher', school_id=bm.school.id)
        messages.warning(request, 'Akaunti yako haina shule iliyowekwa. Wasiliana na msimamizi.')

    from datetime import date as _date
    today = _date.today()
    seven_days_ago = today - timedelta(days=7)

    # Chair/Inspector see all regions; others see only accessible ones
    if bm.role in ('chair', 'inspector', 'member'):
        regions_qs = Region.objects.all()
    else:
        regions_qs = Region.objects.none()

    regions = regions_qs.order_by('name').annotate(
        student_count=Count('district__school__studentteacher',
                            filter=Q(district__school__studentteacher__selected_school__isnull=False),
                            distinct=True),
        district_count=Count('district', distinct=True),
    )
    yr_qs = _active_year_students()
    total_students = yr_qs.filter(selected_school__isnull=False).count()
    total_schools = School.objects.filter(
        studentteacher__in=yr_qs, studentteacher__isnull=False
    ).distinct().count()
    active_this_week = LogbookEntry.objects.filter(
        date__gte=seven_days_ago, student__in=yr_qs
    ).values('student').distinct().count()
    inactive_count = yr_qs.filter(
        selected_school__isnull=False
    ).exclude(
        logbookentry__date__gte=seven_days_ago
    ).distinct().count()

    return render(request, 'field_app/board_home.html', {
        'bm': bm,
        'regions': regions,
        'total_students': total_students,
        'total_schools': total_schools,
        'active_this_week': active_this_week,
        'inactive_count': inactive_count,
        'total_regions': regions.count(),
    })


@board_login_required
def board_district_list(request, region_id):
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')
    region = get_object_or_404(Region, id=region_id)

    # DEO should not be browsing region pages — send to their district directly
    if bm.role == 'deo' and bm.district:
        return redirect('board_school_list', district_id=bm.district.id)

    # Access check — REO can only view their own region
    if not _can_access_region(bm, region):
        messages.error(request, f'Huna ruhusa ya kuona mkoa wa {region.name}.')
        return redirect('board_home')

    current_year = _cached_active_year()

    # REO sees only their region's districts; others see all districts in region
    districts = District.objects.filter(region=region).order_by('name').annotate(
        school_count=Count('school', distinct=True),
        student_count=Count('school__studentteacher',
                            filter=Q(school__studentteacher__selected_school__isnull=False),
                            distinct=True),
    )

    alloc_qs = DistrictAllocation.objects.filter(district__region=region)
    if current_year:
        alloc_qs = alloc_qs.filter(academic_year=current_year)
    alloc_map = {a.district_id: a for a in alloc_qs}
    for d in districts:
        d.allocation = alloc_map.get(d.id)

    # Maombi ya wakuu wa shule kwa mkoa huu (REO anaona, hawezi kubadilisha)
    region_requests = SchoolHeadRequest.objects.filter(
        district__region=region
    ).select_related('school', 'district', 'reviewed_by').order_by('-submitted_at')
    if current_year:
        region_requests = region_requests.filter(academic_year=current_year)

    return render(request, 'field_app/board_district_list.html', {
        'bm': bm,
        'region': region,
        'districts': districts,
        'region_requests': region_requests,
        'pending_count': region_requests.filter(status='pending').count(),
        'applied_count': region_requests.filter(status='applied').count(),
    })


@board_login_required
def board_school_list(request, district_id):
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')
    district = get_object_or_404(District, id=district_id)

    if not _can_access_district(bm, district):
        messages.error(request, f'Huna ruhusa ya kuona wilaya ya {district.name}.')
        return redirect('board_home')

    schools = School.objects.filter(
        district=district,
        studentteacher__isnull=False
    ).distinct().order_by('level', 'name').annotate(
        student_count=Count('studentteacher', distinct=True),
        logbook_count=Count('logbookentry', distinct=True),
    )
    def _lb_first_lesson(entry):
        if entry and entry.lessons_data:
            return entry.lessons_data[0]
        return {}

    from datetime import date as _date
    today = _date.today()

    students_data = []
    for school in schools:
        sts = _active_year_students().filter(selected_school=school).select_related('user')
        for st in sts:
            lb_count = LogbookEntry.objects.filter(student=st).count()
            latest_lb = LogbookEntry.objects.filter(student=st).order_by('-date').first()
            latest_lp = LessonPlan.objects.filter(student=st, school=school).first()
            first_lesson = _lb_first_lesson(latest_lb)
            display_subject = (
                first_lesson.get('subject') or
                (latest_lb.subject_taught.name if latest_lb and latest_lb.subject_taught else '') or
                (latest_lp.subject.name if latest_lp else '')
            )
            display_topic = (
                first_lesson.get('main_topic') or
                (latest_lb.topic_taught if latest_lb else '') or
                (latest_lp.topic if latest_lp else '')
            )
            display_class = first_lesson.get('class') or (latest_lb.class_taught if latest_lb else '')
            display_present = first_lesson.get('present') or (latest_lb.num_students_present if latest_lb else '')
            display_activity = first_lesson.get('activity_type') or (latest_lb.activity_type if latest_lb else '')
            last_lb_date = latest_lb.date if latest_lb else None
            days_inactive = (today - last_lb_date).days if last_lb_date else None
            inactive_alert = days_inactive is not None and days_inactive >= 7
            has_scheme = SchemeOfWork.objects.filter(student=st).exists()
            has_lesson_plan = LessonPlan.objects.filter(student=st).exists()
            students_data.append({
                'student': st,
                'school': school,
                'logbook_count': lb_count,
                'latest_logbook': latest_lb,
                'latest_lesson': latest_lp,
                'display_subject': display_subject,
                'display_topic': display_topic,
                'display_class': display_class,
                'display_present': display_present,
                'display_activity': display_activity,
                'days_inactive': days_inactive,
                'inactive_alert': inactive_alert,
                'has_scheme': has_scheme,
                'has_lesson_plan': has_lesson_plan,
                'last_lb_date': last_lb_date,
            })
    inactive_count = sum(1 for item in students_data if item.get('inactive_alert'))

    # Group students by school for template iteration (avoids O(n*m) nested filtering)
    schools_with_students = []
    for school in schools:
        school_students = [item for item in students_data if item['school'].id == school.id]
        schools_with_students.append({'school': school, 'students': school_students, '_school_id': school.id})

    current_year = _cached_active_year()
    _da_qs = DistrictAllocation.objects.filter(district=district)
    if current_year:
        _da_qs = _da_qs.filter(academic_year=current_year)
    district_alloc = _da_qs.first()
    school_alloc_map = {}
    if district_alloc:
        school_alloc_map = {
            sa.school_id: sa
            for sa in SchoolAllocation.objects.filter(district_allocation=district_alloc)
        }

    # Build subject data from SchoolSubjectCapacity (source of truth after DEO applies)
    # Covers all schools in the district that have capacities set
    all_school_ids_in_district = set(
        School.objects.filter(district=district).values_list('id', flat=True)
    )
    school_subject_caps = {}  # {school_id: [SchoolSubjectCapacity, ...]}
    for cap in SchoolSubjectCapacity.objects.filter(
        school__district=district
    ).select_related('subject'):
        school_subject_caps.setdefault(cap.school_id, []).append(cap)

    # Approved applications per school per subject_id for fill count
    from django.db.models import Count as _Count
    approved_apps_qs = (
        StudentApplication.objects
        .filter(school__district=district, status='approved')
        .values('school_id', 'subject_id')
        .annotate(cnt=_Count('id'))
    )
    fill_map = {}  # {(school_id, subject_id): filled_count}
    for row in approved_apps_qs:
        fill_map[(row['school_id'], row['subject_id'])] = row['cnt']

    # Attach subject_data to each school entry using SchoolSubjectCapacity
    for entry in schools_with_students:
        sid = entry['_school_id']
        caps = school_subject_caps.get(sid, [])
        subj_list = []
        for cap in caps:
            filled = fill_map.get((sid, cap.subject_id), 0)
            subj_list.append({
                'name': cap.subject.name,
                'needed': cap.max_students,
                'filled': filled,
                'full': filled >= cap.max_students,
            })
        entry['subject_data'] = subj_list

    # Also build subject_data for schools that have capacities but no students yet
    # (so they show up in schools_alloc_list with correct data)
    alloc_school_subject_data = {}  # {school_id: subj_list}
    for sid, caps in school_subject_caps.items():
        subj_list = []
        for cap in caps:
            filled = fill_map.get((sid, cap.subject_id), 0)
            subj_list.append({
                'name': cap.subject.name,
                'needed': cap.max_students,
                'filled': filled,
                'full': filled >= cap.max_students,
            })
        alloc_school_subject_data[sid] = subj_list

    # Maombi ya wakuu wa shule (SchoolHeadRequest) — hizi ndizo zinaundwa na /ombi/ form
    head_req_qs = SchoolHeadRequest.objects.filter(
        district=district
    ).select_related('school').order_by('-submitted_at')
    if current_year:
        head_req_qs = head_req_qs.filter(academic_year=current_year)

    # Kwa kila shule, pata ombi la hivi karibuni
    latest_req_map = {}  # school_id → latest SchoolHeadRequest
    for req in head_req_qs:
        sid = req.school_id if req.school_id else req.school_name_submitted
        if sid not in latest_req_map:
            latest_req_map[sid] = req

    # Tengeneza orodha — shule zenye maombi tu + allocation zao
    schools_alloc_list = []
    seen_schools = set()
    for req in head_req_qs:
        if req.school_id and req.school_id not in seen_schools:
            seen_schools.add(req.school_id)
            sa = school_alloc_map.get(req.school_id)
            schools_alloc_list.append({
                'school': req.school,
                'alloc': sa,
                'requested': req.students_needed,
                'quota': sa.quota if sa else 0,
                'notes': req.notes,
                'status': req.status,
                'submitted_at': req.submitted_at,
                'head_name': req.head_name,
                'has_request': True,
                'subjects_needed': req.subjects_needed or {},
                'subject_data': alloc_school_subject_data.get(req.school_id, []),
            })
        elif not req.school_id and req.school_name_submitted not in seen_schools:
            # Ombi bila shule iliyolinganishwa
            seen_schools.add(req.school_name_submitted)
            schools_alloc_list.append({
                'school': None,
                'school_name': req.school_name_submitted,
                'alloc': None,
                'requested': req.students_needed,
                'quota': 0,
                'notes': req.notes,
                'status': req.status,
                'submitted_at': req.submitted_at,
                'head_name': req.head_name,
                'has_request': True,
            })

    pending_req_count  = head_req_qs.filter(status='pending').count()
    applied_req_count  = head_req_qs.filter(status='applied').count()
    rejected_req_count = head_req_qs.filter(status='rejected').count()

    return render(request, 'field_app/board_school_list.html', {
        'bm': bm,
        'district': district,
        'schools': schools,
        'schools_with_students': schools_with_students,
        'students_data': students_data,
        'today': today,
        'inactive_count': inactive_count,
        'district_alloc': district_alloc,
        'school_alloc_map': school_alloc_map,
        'schools_alloc_list': schools_alloc_list,
        'pending_req_count': pending_req_count,
        'applied_req_count': applied_req_count,
        'rejected_req_count': rejected_req_count,
        'current_year': current_year,
    })


@board_login_required
def board_student_progress(request, student_id):
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')
    student = get_object_or_404(StudentTeacher, id=student_id)
    school = student.selected_school

    # Access check — must be in accessible district
    if school and not _can_access_district(bm, school.district):
        messages.error(request, 'Huna ruhusa ya kuona mwanafunzi huyu.')
        return redirect('board_home')

    logbook_entries = LogbookEntry.objects.filter(student=student).select_related('subject_taught').order_by('-date')[:30]
    lesson_plans = LessonPlan.objects.filter(student=student).order_by('-date')[:10]
    schemes = SchemeOfWork.objects.filter(student=student).order_by('-created_at')[:5]
    applications = StudentApplication.objects.filter(student=student, status='approved').select_related('subject', 'school')
    board_comments = BoardComment.objects.filter(student=student).select_related('board_member').order_by('-created_at')

    from datetime import date as _date
    today = _date.today()
    month_entries = LogbookEntry.objects.filter(
        student=student, date__year=today.year, date__month=today.month,
    )
    total_entries = LogbookEntry.objects.filter(student=student).count()

    # Build enriched logbook list — extract lessons_data for display
    logbook_display = []
    for lb in logbook_entries:
        lessons = lb.lessons_data or []
        if lessons:
            first = lessons[0]
            disp_subject = first.get('subject', '') or (lb.subject_taught.name if lb.subject_taught else '—')
            disp_topic   = first.get('main_topic', '') or lb.topic_taught or '—'
            disp_class   = first.get('class', '') or lb.class_taught or '—'
            disp_present = first.get('present', '') or lb.num_students_present or '—'
            disp_activity = first.get('activity_type', '') or lb.activity_type or '—'
            num_periods  = len(lessons)
        else:
            disp_subject  = lb.subject_taught.name if lb.subject_taught else '—'
            disp_topic    = lb.topic_taught or '—'
            disp_class    = lb.class_taught or '—'
            disp_present  = lb.num_students_present or '—'
            disp_activity = lb.activity_type or '—'
            num_periods   = 0
        logbook_display.append({
            'entry': lb,
            'subject': disp_subject,
            'topic': disp_topic,
            'class': disp_class,
            'present': disp_present,
            'activity': disp_activity,
            'num_periods': num_periods,
            'lessons': lessons,
        })

    # Topics covered — from lessons_data first, fallback to old fields
    topics_covered = []
    seen = set()
    for lb in LogbookEntry.objects.filter(student=student).order_by('-date')[:50]:
        if lb.lessons_data:
            for lesson in lb.lessons_data:
                key = (lesson.get('subject',''), lesson.get('main_topic',''))
                if key not in seen and (key[0] or key[1]):
                    seen.add(key)
                    topics_covered.append({'subject': key[0], 'topic': key[1], 'date': lb.date})
        elif lb.topic_taught:
            key = (lb.subject_taught.name if lb.subject_taught else '', lb.topic_taught)
            if key not in seen:
                seen.add(key)
                topics_covered.append({'subject': key[0], 'topic': key[1], 'date': lb.date})
        if len(topics_covered) >= 20:
            break

    last_entry_for_inactive = LogbookEntry.objects.filter(student=student).order_by('-date').first()
    days_inactive = (today - last_entry_for_inactive.date).days if last_entry_for_inactive else None
    inactive_alert = days_inactive is not None and days_inactive >= 7

    lesson_plans_all = LessonPlan.objects.filter(student=student).order_by('-date')
    raw_schemes = SchemeOfWork.objects.filter(student=student).order_by('-year', '-term')

    # Normalize scheme_data rows — KitabuSmart uses spaced keys ('Main Competence',
    # 'Week', 'Periods' …). The template expects snake_case keys. Build a mapping
    # so any saved format is displayed correctly without raising VariableDoesNotExist.
    def _normalize_row(row):
        if not isinstance(row, dict):
            return {}
        get = lambda *keys: next((str(row[k]) for k in keys if k in row and row[k] not in (None, '')), '')
        return {
            'week':       get('week', 'Week'),
            'month':      get('month', 'Month'),
            'topic':      get('topic', 'main_topic', 'Main Competence', 'Learning Activities'),
            'subtopic':   get('subtopic', 'sub_topic', 'Specific Competence', 'Specific Learning Activities'),
            'activities': get('activities', 'learning_activities', 'Learning Activities', 'Specific Learning Activities'),
            'resources':  get('resources', 'teaching_resources', 'Teaching & Learning Resources'),
            'assessment': get('assessment', 'assessment_criteria', 'Assessment Tools'),
            'periods':    get('periods', 'Periods'),
            'remarks':    get('remarks', 'Remarks'),
            'reference':  get('reference', 'Reference'),
            'methods':    get('methods', 'Teaching & Learning Methods'),
        }

    schemes_all = []
    for scheme in raw_schemes:
        normalized_data = [_normalize_row(r) for r in (scheme.scheme_data or [])]
        schemes_all.append({
            'obj': scheme,
            'data': normalized_data,
        })

    return render(request, 'field_app/board_student_progress.html', {
        'bm': bm,
        'student': student,
        'school': school,
        'logbook_entries': logbook_entries,
        'logbook_display': logbook_display,
        'lesson_plans': lesson_plans,
        'lesson_plans_all': lesson_plans_all,
        'schemes': schemes,
        'schemes_all': schemes_all,
        'applications': applications,
        'board_comments': board_comments,
        'month_entry_count': month_entries.count(),
        'total_entries': total_entries,
        'topics_covered': topics_covered,
        'today': today,
        'days_inactive': days_inactive,
        'inactive_alert': inactive_alert,
    })


@board_login_required
def board_add_comment(request):
    if request.method != 'POST':
        return redirect('board_home')
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')

    student_id = request.POST.get('student_id', '').strip()
    comment_text = request.POST.get('comment', '').strip()
    status = request.POST.get('status', 'good')

    if not student_id or not comment_text:
        messages.error(request, 'Jaza maoni yote yanayohitajika.')
        return redirect(request.META.get('HTTP_REFERER', 'board_home'))

    student = get_object_or_404(StudentTeacher, id=student_id)
    current_year = get_current_academic_year()

    BoardComment.objects.create(
        board_member=bm,
        student=student,
        school=student.selected_school,
        comment=comment_text,
        status=status,
        academic_year=current_year,
    )
    messages.success(request, f'Maoni yametumwa kwa {student.full_name}.')
    return redirect('board_student_progress', student_id=student.id)


@board_login_required
def board_head_teacher(request, school_id):
    """Dashboard ya Mkuu wa Shule - management kamili ya walimu wanafunzi."""
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')

    school = get_object_or_404(School, id=school_id)

    # Head teacher: only their own school
    if bm.role == 'head_teacher' and (not bm.school or bm.school_id != school.id):
        messages.error(request, 'Huna ruhusa ya kuona shule hii.')
        return redirect('board_home')
    # DEO: only schools in their district
    if bm.role == 'deo' and (not bm.district or bm.district_id != school.district_id):
        messages.error(request, 'Huna ruhusa ya kuona shule hii.')
        return redirect('board_home')

    current_year = _cached_active_year()
    today = timezone.now().date()

    # POST: ongeza maoni ya mwanafunzi
    if request.method == 'POST' and request.POST.get('action') == 'add_comment':
        student_id = request.POST.get('student_id')
        comment_text = request.POST.get('comment', '').strip()
        status_val = request.POST.get('status', 'good')
        if student_id and comment_text:
            student_obj = StudentTeacher.objects.filter(id=student_id, selected_school=school).first()
            if student_obj:
                BoardComment.objects.create(
                    board_member=bm, student=student_obj, school=school,
                    comment=comment_text, status=status_val, academic_year=current_year
                )
                messages.success(request, f'Maoni kwa {student_obj.full_name} yamehifadhiwa.')
        return redirect('board_head_teacher', school_id=school.id)

    # Wanafunzi wote wa shule hii (mwaka wa sasa tu)
    students = _active_year_students().filter(
        selected_school=school
    ).select_related('user').order_by('full_name')

    total = students.count()
    approved_count = students.filter(approval_status='approved').count()
    pending_count  = students.filter(approval_status='pending').count()

    # Waliofika leo (GPS check-in)
    today_checkins = set(
        LogbookEntry.objects.filter(school=school, date=today, morning_check_in__isnull=False)
        .values_list('student_id', flat=True)
    )
    present_today = len(today_checkins)

    # Logbook compliance ya wiki hii
    week_ago = today - timedelta(days=7)
    recent_entries = LogbookEntry.objects.filter(
        school=school, date__gte=week_ago
    ).values('student_id', 'date').distinct().count()
    working_days = sum(1 for i in range(7) if (today - timedelta(days=i)).weekday() < 5)
    expected = max(1, total * working_days)
    compliance_pct = min(100, int(recent_entries / expected * 100))

    # Data ya kina kwa kila mwanafunzi
    latest_logs = {
        e['student_id']: e['date']
        for e in LogbookEntry.objects.filter(school=school)
        .values('student_id').annotate(date=models.Max('date')).values('student_id', 'date')
    }
    logbook_counts = {
        e['student_id']: e['cnt']
        for e in LogbookEntry.objects.filter(school=school)
        .values('student_id').annotate(cnt=models.Count('id'))
    }
    scheme_counts = {
        e['student_id']: e['cnt']
        for e in SchemeOfWork.objects.filter(school=school)
        .values('student_id').annotate(cnt=models.Count('id'))
    }
    lp_counts = {
        e['student_id']: e['cnt']
        for e in LessonPlan.objects.filter(school=school)
        .values('student_id').annotate(cnt=models.Count('id'))
    }
    last_comments = {}
    if BoardComment.objects.filter(school=school).exists():
        last_comments = {
            c.student_id: c
            for c in BoardComment.objects.filter(school=school)
            .select_related('board_member').order_by('student_id', '-created_at')
            .distinct('student_id')
        }
    # Approved applications per student
    approved_apps = {}
    for app in StudentApplication.objects.filter(school=school, status='approved').select_related('subject'):
        approved_apps.setdefault(app.student_id, []).append(app.subject.name)

    # Internship length: start of current academic year to today
    year_start = current_year.start_date if current_year and hasattr(current_year, 'start_date') else None
    total_working_days = 0
    if year_start:
        d = year_start
        while d <= today:
            if d.weekday() < 5:
                total_working_days += 1
            d += timedelta(days=1)
    total_working_days = max(1, total_working_days)

    students_data = []
    for st in students:
        last_log  = latest_logs.get(st.id)
        days_since = (today - last_log).days if last_log else None
        lb_count   = logbook_counts.get(st.id, 0)
        pct = min(100, int(lb_count / total_working_days * 100)) if total_working_days > 0 else 0
        students_data.append({
            'obj': st,
            'present_today': st.id in today_checkins,
            'last_log': last_log,
            'days_since': days_since,
            'log_status': 'ok' if days_since is not None and days_since <= 1
                         else ('warn' if days_since is not None and days_since <= 3 else 'late'),
            'last_comment': last_comments.get(st.id),
            'logbook_count': lb_count,
            'scheme_count': scheme_counts.get(st.id, 0),
            'lp_count': lp_counts.get(st.id, 0),
            'progress_pct': pct,
            'subjects': approved_apps.get(st.id, []),
        })

    # DEO Allocation
    alloc = None
    if current_year:
        try:
            dist_alloc = DistrictAllocation.objects.filter(
                district=school.district, academic_year=current_year
            ).first()
            if dist_alloc:
                alloc = SchoolAllocation.objects.filter(
                    district_allocation=dist_alloc, school=school
                ).first()
        except Exception:
            pass

    head_requests = SchoolHeadRequest.objects.filter(school=school).order_by('-submitted_at')[:5]
    current_month = today.strftime('%B %Y')

    if bm.role == 'deo' and bm.district:
        back_url = reverse('board_school_list', args=[bm.district.id])
    elif bm.role in ('reo', 'chair', 'inspector', 'member'):
        back_url = reverse('board_school_list', args=[school.district_id])
    else:
        back_url = None  # head_teacher has no back — this is their home

    return render(request, 'field_app/board_head_teacher.html', {
        'bm': bm,
        'school': school,
        'students_data': students_data,
        'total': total,
        'approved_count': approved_count,
        'pending_count': pending_count,
        'present_today': present_today,
        'compliance_pct': compliance_pct,
        'alloc': alloc,
        'head_requests': head_requests,
        'today': today,
        'current_month': current_month,
        'can_edit': bm.role in ('head_teacher', 'deo', 'chair'),
        'back_url': back_url,
    })


@board_login_required
def board_final_assessment(request, student_id):
    """Mkuu wa Shule/DEO anaingiza tathmini ya mwisho ya mwanafunzi."""
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')

    student = get_object_or_404(StudentTeacher, id=student_id)
    school = student.selected_school
    if not school:
        messages.error(request, 'Mwanafunzi huyu hana shule iliyochaguliwa.')
        return redirect('board_home')

    # Ruhusa: HT wa shule hiyo, DEO wa wilaya hiyo, au Chair/Inspector
    if bm.role == 'head_teacher' and (not bm.school or bm.school_id != school.id):
        messages.error(request, 'Huna ruhusa ya kutathmini mwanafunzi huyu.')
        return redirect('board_home')
    if bm.role == 'deo' and (not bm.district or bm.district_id != school.district_id):
        messages.error(request, 'Huna ruhusa ya kutathmini mwanafunzi huyu.')
        return redirect('board_home')

    current_year = _cached_active_year()
    fa, _ = FinalAssessment.objects.get_or_create(
        student=student,
        defaults={'school': school, 'academic_year': current_year, 'assessed_by': bm}
    )

    SCORE_FIELDS = [
        ('kuhudhuria',        'Kuhudhuria',        'Mwanafunzi alihudhuria vizuri darasani na shuleni'),
        ('daftari_la_kazi',   'Daftari la Kazi',   'Ubora wa daftari la kazi (logbook)'),
        ('mpango_wa_kazi',    'Mpango wa Kazi',     'Ubora wa Scheme of Work'),
        ('mpango_wa_somo',    'Mpango wa Somo',     'Ubora wa Lesson Plans'),
        ('utendaji_darasani', 'Utendaji Darasani',  'Ujuzi wa kufundisha darasani'),
    ]

    error = None
    if request.method == 'POST' and not fa.is_final:
        action = request.POST.get('action', 'save')
        scores = {}
        for fname, _, _ in SCORE_FIELDS:
            try:
                v = int(request.POST.get(fname, 0))
                if not (0 <= v <= 20):
                    raise ValueError
                scores[fname] = v
            except ValueError:
                error = f'Alama za "{fname}" lazima ziwe kati ya 0 na 20.'
                break

        if not error:
            for fname, v in scores.items():
                setattr(fa, fname, v)
            fa.maoni = request.POST.get('maoni', '').strip()
            fa.assessed_by = bm
            if action == 'finalize':
                from django.utils import timezone
                fa.is_final = True
                fa.finalized_at = timezone.now()
            fa.save()
            if fa.is_final:
                msg = 'Tathmini imekamilishwa na kufungwa. Subiri DEO wa wilaya aidhibiti cheti.'
            else:
                msg = 'Tathmini imehifadhiwa.'
            messages.success(request, msg)
            return redirect('board_final_assessment', student_id=student.id)

    # Back URL
    back_url = reverse('board_head_teacher', args=[school.id])

    return render(request, 'field_app/final_assessment_form.html', {
        'bm': bm,
        'student': student,
        'school': school,
        'fa': fa,
        'score_fields': SCORE_FIELDS,
        'back_url': back_url,
        'error': error,
    })


@board_login_required
def board_deo_report(request, district_id):
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')
    district = get_object_or_404(District, id=district_id)

    if not _can_access_district(bm, district):
        messages.error(request, f'Huna ruhusa ya kuona wilaya ya {district.name}.')
        return redirect('board_home')

    HOLIDAY_MONTHS = {5, 8, 12}  # Mei, Agosti, Desemba
    now = timezone.now()
    selected_month = int(request.GET.get('month', now.month))
    selected_year = int(request.GET.get('year', now.year))

    existing = MonthlyReport.objects.filter(
        district=district, month=selected_month, year=selected_year
    ).first()

    if request.method == 'POST' and 'generate' in request.POST:
        if selected_month in HOLIDAY_MONTHS:
            messages.error(request, 'Ripoti haizalishwi kwa miezi ya likizo (Mei, Agosti, Desemba).')
            return redirect(request.path + f'?month={selected_month}&year={selected_year}')

        entries = LogbookEntry.objects.filter(
            date__month=selected_month,
            date__year=selected_year,
            school__district=district,
        ).select_related('student', 'subject_taught', 'school')

        if not entries.exists():
            messages.warning(request, 'Hakuna rekodi za logbook kwa mwezi huu katika wilaya hii.')
            return redirect(request.path + f'?month={selected_month}&year={selected_year}')

        # Build summary data per student
        from collections import defaultdict
        student_summary = defaultdict(lambda: {
            'name': '', 'school': '', 'level': '', 'subject': '',
            'topics': [], 'days_recorded': 0,
        })
        for entry in entries:
            sid = entry.student_id
            st = entry.student
            student_summary[sid]['name'] = st.full_name
            student_summary[sid]['school'] = entry.school.name if entry.school else ''
            student_summary[sid]['level'] = entry.school.level if entry.school else ''
            student_summary[sid]['days_recorded'] += 1
            if entry.lessons_data:
                for lesson in entry.lessons_data:
                    if lesson.get('main_topic'):
                        student_summary[sid]['topics'].append(lesson['main_topic'])
                    if not student_summary[sid]['subject'] and lesson.get('subject'):
                        student_summary[sid]['subject'] = lesson['subject']
            elif entry.topic_taught:
                student_summary[sid]['topics'].append(entry.topic_taught)
                if not student_summary[sid]['subject'] and entry.subject_taught:
                    student_summary[sid]['subject'] = entry.subject_taught.name

        # Months remaining in year
        months_remaining = 12 - selected_month

        summary_text = ""
        for sid, data in student_summary.items():
            topics_count = len(data['topics'])
            unique_topics = list(dict.fromkeys(data['topics']))[:10]
            summary_text += (
                f"- {data['name']} | Shule: {data['school']} ({data['level']}) | "
                f"Somo: {data['subject'] or 'Haijabainishwa'} | "
                f"Mada {topics_count} | Siku {data['days_recorded']} | "
                f"Mada za mwisho: {', '.join(unique_topics[:5]) or 'Hakuna'}\n"
            )

        month_name_map = dict(MonthlyReport.MONTH_CHOICES)
        prompt = f"""Wewe ni mshauri wa elimu kwa Tanzania. Toa ripoti ya kina kwa DEO (Afisa Elimu wa Wilaya) ya wilaya ya {district.name} kwa mwezi wa {month_name_map[selected_month]} {selected_year}.

Data ya walimu wanafunzi (student teachers) waliofanya kazi mwezi huu:
{summary_text}

Miezi iliyobaki mwaka huu: {months_remaining}

Toa ripoti ifuatayo kwa muundo wa JSON:
{{
  "muhtasari": "Muhtasari mfupi wa mwezi (2-3 sentensi)",
  "secondary": [
    {{
      "nafasi": 1,
      "jina": "Jina la mwalimu mwanafunzi",
      "shule": "Jina la shule",
      "somo": "Somo analofundisha",
      "mada_zote": 10,
      "siku": 20,
      "hali": "vizuri|wastani|nyuma",
      "mapendekezo": "Pendekezo fupi la kibinafsi kulingana na miezi iliyobaki"
    }}
  ],
  "primary": [
    {{
      "nafasi": 1,
      "jina": "Jina la mwalimu mwanafunzi",
      "shule": "Jina la shule",
      "somo": "Somo analofundisha",
      "mada_zote": 8,
      "siku": 18,
      "hali": "vizuri|wastani|nyuma",
      "mapendekezo": "Pendekezo fupi la kibinafsi"
    }}
  ],
  "hitimisho": "Hitimisho na mapendekezo ya jumla kwa DEO (3-4 sentensi)"
}}

Panga walimu kwa secondary na primary tofauti. Mpanga kutoka mwenye mada nyingi zaidi hadi chache. Mwalimu mwenye mada nyingi zaidi 'vizuri', wastani 'wastani', chini ya wastani 'nyuma'. Jibu kwa JSON tu bila maelezo mengine."""

        try:
            from .ai_utils import client, model_name as ai_model
            response = client.models.generate_content(model=ai_model, contents=prompt)
            raw = response.text.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            ai_data = json.loads(raw)
        except Exception as e:
            messages.error(request, f'Hitilafu ya AI: {e}')
            return redirect(request.path + f'?month={selected_month}&year={selected_year}')

        report, _ = MonthlyReport.objects.update_or_create(
            district=district, month=selected_month, year=selected_year,
            defaults={'ai_content': ai_data, 'generated_by': bm},
        )
        existing = report
        messages.success(request, 'Ripoti imezalishwa kwa mafanikio.')

    available_months = [
        (m, n) for m, n in MonthlyReport.MONTH_CHOICES if m not in HOLIDAY_MONTHS
    ]
    past_reports = MonthlyReport.objects.filter(district=district).order_by('-year', '-month')

    available_years = list(range(2024, 2046))

    return render(request, 'field_app/board_deo_report.html', {
        'bm': bm,
        'district': district,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'existing': existing,
        'available_months': available_months,
        'available_years': available_years,
        'past_reports': past_reports,
        'holiday_months': HOLIDAY_MONTHS,
        'is_holiday': selected_month in HOLIDAY_MONTHS,
        'month_name': dict(MonthlyReport.MONTH_CHOICES).get(selected_month, ''),
    })


@board_login_required
def deo_approve_district_certificates(request, district_id):
    """DEO anaidhibiti vyeti vya wanafunzi wote wa wilaya (POST tu)."""
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')
    if bm.role not in ('deo', 'chair', 'inspector'):
        messages.error(request, 'Ni DEO tu anayeweza kuidhibiti vyeti.')
        return redirect('board_school_list', district_id=district_id)

    district = get_object_or_404(District, id=district_id)
    if not _can_access_district(bm, district):
        messages.error(request, f'Huna ruhusa ya wilaya ya {district.name}.')
        return redirect('board_home')

    if request.method == 'POST':
        from django.utils import timezone as tz
        # Approve all finalized (is_final=True) but not yet deo_approved in this district
        to_approve = FinalAssessment.objects.filter(
            student__selected_school__district=district,
            is_final=True,
            deo_approved=False,
        )
        count = to_approve.count()
        to_approve.update(
            deo_approved=True,
            deo_approved_at=tz.now(),
            deo_approved_by=bm,
        )
        messages.success(request, f'Vyeti vya wanafunzi {count} vimeidhibitiwa. Wanaweza kupakua sasa.')
    return redirect('board_school_list', district_id=district_id)


@board_login_required
def head_teacher_monthly_report(request, school_id):
    """Ripoti ya mwezi — mkuu wa shule anaweza kuona na kuchapisha."""
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')

    school = get_object_or_404(School, id=school_id)
    # Head teacher: only their own school
    if bm.role == 'head_teacher' and (not bm.school or bm.school_id != school.id):
        messages.error(request, 'Huna ruhusa ya kuona shule hii.')
        return redirect('board_home')
    # DEO: only schools in their district
    if bm.role == 'deo' and (not bm.district or bm.district_id != school.district_id):
        messages.error(request, 'Huna ruhusa ya kuona shule hii.')
        return redirect('board_home')

    today = timezone.now().date()
    current_year = _cached_active_year()
    month_name = request.GET.get('month', today.strftime('%B %Y'))

    students = _active_year_students().filter(
        selected_school=school, approval_status='approved'
    ).select_related('user').order_by('full_name')

    year_start = current_year.start_date if current_year and hasattr(current_year, 'start_date') else None
    total_working_days = 0
    if year_start:
        d = year_start
        while d <= today:
            if d.weekday() < 5:
                total_working_days += 1
            d += timedelta(days=1)
    total_working_days = max(1, total_working_days)

    approved_apps = {}
    for app in StudentApplication.objects.filter(school=school, status='approved').select_related('subject'):
        approved_apps.setdefault(app.student_id, []).append(app.subject.name)

    logbook_counts = {
        e['student_id']: e['cnt']
        for e in LogbookEntry.objects.filter(school=school)
        .values('student_id').annotate(cnt=models.Count('id'))
    }
    scheme_counts = {
        e['student_id']: e['cnt']
        for e in SchemeOfWork.objects.filter(school=school)
        .values('student_id').annotate(cnt=models.Count('id'))
    }
    lp_counts = {
        e['student_id']: e['cnt']
        for e in LessonPlan.objects.filter(school=school)
        .values('student_id').annotate(cnt=models.Count('id'))
    }
    last_comments = {}
    if BoardComment.objects.filter(school=school).exists():
        last_comments = {
            c.student_id: c
            for c in BoardComment.objects.filter(school=school)
            .select_related('board_member').order_by('student_id', '-created_at')
            .distinct('student_id')
        }

    report_data = []
    for st in students:
        lb = logbook_counts.get(st.id, 0)
        pct = min(100, int(lb / total_working_days * 100))
        comment = last_comments.get(st.id)
        report_data.append({
            'name': st.full_name,
            'email': st.user.email if st.user else '—',
            'subjects': ', '.join(approved_apps.get(st.id, [])) or '—',
            'logbook_days': lb,
            'scheme_count': scheme_counts.get(st.id, 0),
            'lp_count': lp_counts.get(st.id, 0),
            'progress_pct': pct,
            'status': comment.get_status_display() if comment else '—',
            'comment': comment.comment if comment else '',
        })

    if bm.role == 'head_teacher':
        back_url = reverse('board_head_teacher', args=[school.id])
    elif bm.role == 'deo' and bm.district:
        back_url = reverse('board_school_list', args=[bm.district.id])
    else:
        back_url = reverse('board_school_list', args=[school.district_id])

    return render(request, 'field_app/head_teacher_monthly_report.html', {
        'bm': bm,
        'school': school,
        'report_data': report_data,
        'month_name': month_name,
        'today': today,
        'total_students': len(report_data),
        'avg_pct': int(sum(r['progress_pct'] for r in report_data) / max(1, len(report_data))),
        'back_url': back_url,
    })


@board_login_required
def final_assessment_pdf(request, student_id):
    """Chapisha cheti cha tathmini ya mwisho kwa PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    import io

    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')

    student = get_object_or_404(StudentTeacher, id=student_id)
    fa = get_object_or_404(FinalAssessment, student=student)

    # Access check
    school = student.selected_school
    if bm.role == 'head_teacher' and (not bm.school or bm.school_id != school.id):
        return redirect('board_home')
    if bm.role == 'deo' and (not bm.district or bm.district_id != school.district_id):
        return redirect('board_home')

    NAVY  = colors.HexColor('#0A2B5E')
    GOLD  = colors.HexColor('#C8900A')
    LIGHT = colors.HexColor('#EEF1F6')
    WHITE = colors.white

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2.2*cm, rightMargin=2.2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    hdr_bold = ParagraphStyle('hb', fontSize=9, fontName='Helvetica-Bold',
                              alignment=TA_CENTER, leading=13)
    hdr_norm = ParagraphStyle('hn', fontSize=8.5, fontName='Helvetica',
                              alignment=TA_CENTER, leading=12)
    title_s  = ParagraphStyle('tt', fontSize=14, fontName='Helvetica-Bold',
                              textColor=NAVY, alignment=TA_CENTER, spaceAfter=4)
    sub_s    = ParagraphStyle('ss', fontSize=9, fontName='Helvetica',
                              textColor=GOLD, alignment=TA_CENTER)
    cell_s   = ParagraphStyle('cs', fontSize=9, fontName='Helvetica', leading=12)
    cell_b   = ParagraphStyle('cb', fontSize=9, fontName='Helvetica-Bold', leading=12)

    SCORE_LABELS = [
        ('kuhudhuria',        'Kuhudhuria'),
        ('daftari_la_kazi',   'Daftari la Kazi'),
        ('mpango_wa_kazi',    'Mpango wa Kazi'),
        ('mpango_wa_somo',    'Mpango wa Somo'),
        ('utendaji_darasani', 'Utendaji Darasani'),
    ]
    GRADE_COLOR = {'A': colors.HexColor('#059669'), 'B': colors.HexColor('#0891B2'),
                   'C': colors.HexColor('#D97706'), 'F': colors.HexColor('#DC2626')}

    story = []

    # Gov header
    story.append(Paragraph('JAMHURI YA MUUNGANO WA TANZANIA', hdr_bold))
    story.append(Paragraph('WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA', hdr_norm))
    story.append(Paragraph('MFUMO WA USIMAMIZI WA MAZOEZI YA KUFUNDISHA', hdr_norm))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width='100%', thickness=2, color=NAVY))
    story.append(HRFlowable(width='100%', thickness=1, color=GOLD, spaceAfter=10))

    story.append(Paragraph('CHETI CHA TATHMINI YA MWISHO', title_s))
    story.append(Paragraph('TEACHING PRACTICE FINAL ASSESSMENT CERTIFICATE', sub_s))
    story.append(Spacer(1, 14))

    # Student info table
    yr = fa.academic_year.year if fa.academic_year else '—'
    info_data = [
        [Paragraph('Jina la Mwanafunzi:', cell_b), Paragraph(student.full_name.upper(), cell_s),
         Paragraph('Mwaka wa Masomo:', cell_b), Paragraph(yr, cell_s)],
        [Paragraph('Shule ya Mazoezi:', cell_b), Paragraph(fa.school.name, cell_s),
         Paragraph('Wilaya:', cell_b), Paragraph(fa.school.district.name, cell_s)],
        [Paragraph('Mkoa:', cell_b), Paragraph(fa.school.district.region.name, cell_s),
         Paragraph('Tarehe ya Tathmini:', cell_b), Paragraph(fa.updated_at.strftime('%d %B %Y'), cell_s)],
    ]
    info_tbl = Table(info_data, colWidths=[3.5*cm, 5.5*cm, 3.5*cm, 4.5*cm])
    info_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 14))

    # Scores table
    scores_data = [[
        Paragraph('KIPENGELE', ParagraphStyle('th', fontSize=8.5, fontName='Helvetica-Bold',
                                              textColor=WHITE, alignment=TA_CENTER)),
        Paragraph('ALAMA ZA JUU', ParagraphStyle('th2', fontSize=8.5, fontName='Helvetica-Bold',
                                                  textColor=WHITE, alignment=TA_CENTER)),
        Paragraph('ALAMA ZILIZOPEWA', ParagraphStyle('th3', fontSize=8.5, fontName='Helvetica-Bold',
                                                      textColor=WHITE, alignment=TA_CENTER)),
    ]]
    for fname, label in SCORE_LABELS:
        scores_data.append([
            Paragraph(label, cell_s),
            Paragraph('20', ParagraphStyle('c', fontSize=9, fontName='Helvetica', alignment=TA_CENTER)),
            Paragraph(str(getattr(fa, fname)), ParagraphStyle('c', fontSize=9, fontName='Helvetica-Bold', alignment=TA_CENTER)),
        ])
    scores_data.append([
        Paragraph('JUMLA', cell_b),
        Paragraph('100', ParagraphStyle('c', fontSize=9, fontName='Helvetica-Bold', alignment=TA_CENTER)),
        Paragraph(str(fa.jumla), ParagraphStyle('c', fontSize=11, fontName='Helvetica-Bold',
                                                 alignment=TA_CENTER, textColor=NAVY)),
    ])

    s_tbl = Table(scores_data, colWidths=[10*cm, 3.5*cm, 3.5*cm])
    s_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('BACKGROUND', (0,-1), (-1,-1), LIGHT),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [WHITE, colors.HexColor('#F9FAFB')]),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LINEABOVE', (0,-1), (-1,-1), 1.5, GOLD),
    ]))
    story.append(s_tbl)
    story.append(Spacer(1, 14))

    # Grade box
    gc = GRADE_COLOR.get(fa.daraja, NAVY)
    grade_data = [[
        Paragraph(f'DARAJA: {fa.daraja}', ParagraphStyle('grd', fontSize=22, fontName='Helvetica-Bold',
                                                          textColor=WHITE, alignment=TA_CENTER)),
        Paragraph(f'{fa.daraja_maana}\n{fa.jumla}/100', ParagraphStyle('grd2', fontSize=11, fontName='Helvetica-Bold',
                                                                         textColor=WHITE, alignment=TA_CENTER, leading=16)),
    ]]
    g_tbl = Table(grade_data, colWidths=[9*cm, 8*cm])
    g_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), gc),
        ('PADDING', (0,0), (-1,-1), 12),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(g_tbl)

    if fa.maoni:
        story.append(Spacer(1, 10))
        story.append(Paragraph(f'<b>Maoni:</b> {fa.maoni}',
                                ParagraphStyle('mn', fontSize=9, fontName='Helvetica',
                                               borderColor=colors.HexColor('#CBD5E0'),
                                               borderWidth=0.5, borderPadding=6,
                                               backColor=LIGHT, leading=13)))

    story.append(Spacer(1, 20))

    # Signature block
    sig_data = [[
        Paragraph('___________________________<br/><b>Sahihi ya Mkuu wa Shule</b><br/>'
                  f'{fa.school.name}', ParagraphStyle('sg', fontSize=8.5, fontName='Helvetica',
                                                       alignment=TA_CENTER, leading=13)),
        Paragraph('___________________________<br/><b>Tarehe</b><br/>'
                  f'{fa.updated_at.strftime("%d / %m / %Y")}', ParagraphStyle('sg2', fontSize=8.5,
                                                                                fontName='Helvetica',
                                                                                alignment=TA_CENTER, leading=13)),
    ]]
    sig_tbl = Table(sig_data, colWidths=[8.5*cm, 8.5*cm])
    sig_tbl.setStyle(TableStyle([('PADDING', (0,0), (-1,-1), 8), ('VALIGN', (0,0), (-1,-1), 'BOTTOM')]))
    story.append(sig_tbl)

    doc.build(story)
    buf.seek(0)
    fname_safe = student.full_name.replace(' ', '_')
    resp = HttpResponse(buf.read(), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="Tathmini_{fname_safe}.pdf"'
    return resp


@board_login_required
def deo_allocation(request):
    """Redirect DEO to their district's allocation page."""
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')
    if bm.district:
        return redirect('deo_district_allocation', district_id=bm.district.id)
    messages.error(request, 'Akaunti yako haina wilaya. Wasiliana na msimamizi.')
    return redirect('board_home')


@board_login_required
def deo_district_allocation(request, district_id):
    """DEO/Chair anaweka idadi ya walimu wanafunzi kwa wilaya maalumu."""
    bm = _get_board_member(request)
    if not bm:
        messages.error(request, 'Huna ruhusa ya Bodi ya Walimu.')
        return redirect('board_login')

    district = get_object_or_404(District, id=district_id)

    # Chair can edit any district; DEO can edit only their own district; others view-only
    can_edit = (
        bm.role == 'chair' or
        (bm.role == 'deo' and bm.district_id == district.id)
    )

    current_year = _cached_active_year()

    allocation, _ = DistrictAllocation.objects.get_or_create(
        district=district,
        academic_year=current_year,
        defaults={'uploaded_by': bm}
    )

    schools = School.objects.filter(district=district).order_by('level', 'name')
    school_alloc_map = {
        sa.school_id: sa
        for sa in SchoolAllocation.objects.filter(district_allocation=allocation).select_related('school')
    }

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'set_totals':
            allocation.primary_needed = int(request.POST.get('primary_needed', 0) or 0)
            allocation.secondary_needed = int(request.POST.get('secondary_needed', 0) or 0)
            allocation.notes = request.POST.get('notes', '').strip()
            if 'document' in request.FILES:
                allocation.document = request.FILES['document']
            allocation.uploaded_by = bm
            allocation.save()
            messages.success(request, 'Mahitaji ya wilaya yamehifadhiwa.')
            return redirect('deo_district_allocation', district_id=district.id)

        elif action == 'set_school_quotas':
            all_subjects_map = {s.name.lower(): s for s in Subject.objects.all()}
            for school in schools:
                sid = school.id
                quota_val = int(request.POST.get(f'quota_{sid}', 0) or 0)

                # Parse subject rows for this school: subj_name_{sid}_{N}, subj_count_{sid}_{N}
                subj_breakdown = {}
                n = 1
                while True:
                    sname = request.POST.get(f'subj_name_{sid}_{n}', '').strip()
                    if not sname:
                        break
                    try:
                        scount = max(1, int(request.POST.get(f'subj_count_{sid}_{n}', 1) or 1))
                    except ValueError:
                        scount = 1
                    subj_breakdown[sname] = scount
                    n += 1

                # Auto-set quota from sum of subjects if subjects provided and quota not set manually
                if subj_breakdown and quota_val == 0:
                    quota_val = sum(subj_breakdown.values())

                SchoolAllocation.objects.update_or_create(
                    district_allocation=allocation,
                    school=school,
                    defaults={
                        'quota': quota_val,
                        'subjects_breakdown': subj_breakdown or {},
                    }
                )
                if quota_val > 0:
                    School.objects.filter(id=sid).update(capacity=quota_val)

                # Unda/sasisha SchoolSubjectCapacity records
                for sname, scount in subj_breakdown.items():
                    subj_obj = all_subjects_map.get(sname.lower())
                    if subj_obj:
                        SchoolSubjectCapacity.objects.update_or_create(
                            school=school,
                            subject=subj_obj,
                            defaults={'max_students': scount},
                        )

            messages.success(request, 'Mgawanyo na masomo ya shule zote zimehifadhiwa.')
            return redirect('deo_district_allocation', district_id=district.id)

        elif action == 'ai_parse':
            if not allocation.document:
                messages.error(request, 'Pakia hati kwanza kabla ya kutumia AI.')
                return redirect('deo_district_allocation', district_id=district.id)
            result = _ai_parse_allocation_document(allocation)
            if result.get('success'):
                allocation.primary_needed = result.get('primary_needed', allocation.primary_needed)
                allocation.secondary_needed = result.get('secondary_needed', allocation.secondary_needed)
                allocation.ai_parsed = True
                allocation.save()
                for school_data in result.get('schools', []):
                    school_name = school_data.get('name', '').strip().lower()
                    quota = int(school_data.get('quota', 0) or 0)
                    matched = next(
                        (s for s in schools if school_name in s.name.lower() or s.name.lower() in school_name),
                        None
                    )
                    if matched and quota > 0:
                        SchoolAllocation.objects.update_or_create(
                            district_allocation=allocation,
                            school=matched,
                            defaults={'quota': quota}
                        )
                messages.success(
                    request,
                    f'AI imechambua hati. Msingi: {result.get("primary_needed", 0)}, '
                    f'Sekondari: {result.get("secondary_needed", 0)}'
                )
            else:
                messages.warning(
                    request,
                    f'AI haikuweza kuchambua hati: {result.get("error", "")}. Weka idadi wewe mwenyewe.'
                )
            return redirect('deo_district_allocation', district_id=district.id)

    # Rebuild after possible POST changes
    school_alloc_map = {
        sa.school_id: sa
        for sa in SchoolAllocation.objects.filter(district_allocation=allocation).select_related('school')
    }

    # Load existing subject capacities per school
    school_caps_map = {}  # {school_id: [{name, max_students}, ...]}
    for cap in SchoolSubjectCapacity.objects.filter(
        school__district=district
    ).select_related('subject').order_by('subject__name'):
        school_caps_map.setdefault(cap.school_id, []).append({
            'name': cap.subject.name,
            'max': cap.max_students,
        })

    schools_with_alloc = []
    for school in schools:
        sa = school_alloc_map.get(school.id)
        filled = sa.filled if sa else StudentApplication.objects.filter(
            school=school, status='approved'
        ).values('student').distinct().count()
        quota = sa.quota if sa else 0
        schools_with_alloc.append({
            'school': school,
            'quota': quota,
            'filled': filled,
            'remaining': max(0, quota - filled),
            'pct': min(100, round(filled / quota * 100)) if quota > 0 else 0,
            'ht_requested': sa.head_teacher_requested if sa else 0,
            'ht_notes': sa.head_teacher_notes if sa else '',
            'subject_caps': school_caps_map.get(school.id, []),
        })

    return render(request, 'field_app/deo_allocation.html', {
        'allocation': allocation,
        'district': district,
        'schools_with_alloc': schools_with_alloc,
        'current_year': current_year,
        'can_edit': can_edit,
        'bm': bm,
        'primary_schools': [s for s in schools_with_alloc if s['school'].level == 'Primary'],
        'secondary_schools': [s for s in schools_with_alloc if s['school'].level == 'Secondary'],
    })


@board_login_required
def deo_review_requests(request, district_id):
    """DEO anaona na kusimamia maombi ya wakuu wa shule."""
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')

    district = get_object_or_404(District, id=district_id)
    current_year = _cached_active_year()
    _rqs = SchoolHeadRequest.objects.filter(district=district)
    if current_year:
        _rqs = _rqs.filter(academic_year=current_year)
    requests_qs = _rqs.select_related('school', 'reviewed_by')

    # Chair or DEO of this district can edit; others view-only
    can_edit = bm.role == 'chair' or (bm.role == 'deo' and bm.district_id == district.id)

    if request.method == 'POST' and can_edit:
        action = request.POST.get('action')

        if action == 'reject':
            req_id = request.POST.get('request_id')
            SchoolHeadRequest.objects.filter(id=req_id, district=district).update(
                status='rejected', reviewed_by=bm, reviewed_at=timezone.now()
            )
            # AJAX reject returns JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            messages.success(request, 'Ombi limekataliwa.')

        elif action == 'apply_selected':
            selected_ids = request.POST.getlist('selected_requests')
            if not selected_ids:
                messages.error(request, 'Chagua maombi kwanza.')
            else:
                allocation, _ = DistrictAllocation.objects.get_or_create(
                    district=district, academic_year=current_year,
                    defaults={'uploaded_by': bm}
                )
                applied = 0
                school_capacity_map = {}  # {school_id: capacity} — bulk update baadaye

                reqs = list(SchoolHeadRequest.objects.filter(
                    id__in=selected_ids, district=district
                ).select_related('school'))

                # Pre-load all Subject objects for name matching (case-insensitive)
                all_subjects = {s.name.lower(): s for s in Subject.objects.all()}

                for req in reqs:
                    if req.school:
                        SchoolAllocation.objects.update_or_create(
                            district_allocation=allocation,
                            school=req.school,
                            defaults={
                                'quota': req.students_needed,
                                'subjects_breakdown': req.subjects_needed or {},
                            }
                        )
                        school_capacity_map[req.school_id] = req.students_needed

                        # Weka SchoolSubjectCapacity mpya kutoka request (futa za zamani kwanza)
                        if req.subjects_needed:
                            # Futa caps za zamani za shule hii
                            SchoolSubjectCapacity.objects.filter(school=req.school).delete()
                            # Unda mpya kutoka subjects_needed
                            for sname, scount in req.subjects_needed.items():
                                subj_obj = all_subjects.get(sname.lower())
                                if subj_obj:
                                    SchoolSubjectCapacity.objects.create(
                                        school=req.school,
                                        subject=subj_obj,
                                        max_students=scount,
                                        current_students=0,
                                    )

                    req.status = 'applied'
                    req.reviewed_by = bm
                    req.reviewed_at = timezone.now()
                    applied += 1

                # Bulk save requests (moja kwa moja — si save() ndani ya loop)
                SchoolHeadRequest.objects.bulk_update(reqs, ['status', 'reviewed_by', 'reviewed_at'])

                # Sasisha School.capacity kwa mara moja nje ya loop
                if school_capacity_map:
                    from django.db.models import Case, When, IntegerField
                    School.objects.filter(id__in=school_capacity_map.keys()).update(
                        capacity=Case(
                            *[When(id=sid, then=cap) for sid, cap in school_capacity_map.items()],
                            output_field=IntegerField(),
                        )
                    )

                # Recalculate district totals
                all_applied = SchoolHeadRequest.objects.filter(district=district, status='applied')
                if current_year:
                    all_applied = all_applied.filter(academic_year=current_year)
                allocation.primary_needed = sum(r.students_needed for r in all_applied if r.level == 'Primary')
                allocation.secondary_needed = sum(r.students_needed for r in all_applied if r.level == 'Secondary')
                allocation.uploaded_by = bm
                allocation.save(update_fields=['primary_needed', 'secondary_needed', 'uploaded_by', 'updated_at'])
                messages.success(request, f'Maombi {applied} yamewekwa. Quota ya shule zimesasishwa.')

        elif action == 'ai_format_pdf':
            return _generate_requests_pdf(requests_qs, district, current_year)

        return redirect('deo_review_requests', district_id=district.id)

    pending = requests_qs.filter(status='pending')
    applied_list = requests_qs.filter(status='applied')
    rejected_list = requests_qs.filter(status='rejected')

    # Summary counts
    primary_pending = sum(r.students_needed for r in pending if r.level == 'Primary')
    secondary_pending = sum(r.students_needed for r in pending if r.level == 'Secondary')
    primary_applied = sum(r.students_needed for r in applied_list if r.level == 'Primary')
    secondary_applied = sum(r.students_needed for r in applied_list if r.level == 'Secondary')

    total_rejected = rejected_list.count()
    return render(request, 'field_app/deo_review_requests.html', {
        'bm': bm,
        'district': district,
        'pending': pending,
        'applied_list': applied_list,
        'rejected_list': rejected_list,
        'can_edit': can_edit,
        'current_year': current_year,
        'total_pending': pending.count(),
        'total_applied': applied_list.count(),
        'total_rejected': total_rejected,
        'primary_pending': primary_pending,
        'secondary_pending': secondary_pending,
        'primary_applied': primary_applied,
        'secondary_applied': secondary_applied,
    })


@board_login_required
def deo_student_pdf(request, district_id):
    """DEO downloads PDF ya walimu wanafunzi waliochaguliwa kwenye wilaya yake."""
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')
    district = get_object_or_404(District, id=district_id)
    if not _can_access_district(bm, district):
        messages.error(request, f'Huna ruhusa ya kuona wilaya ya {district.name}.')
        return redirect('board_home')

    current_year = _cached_active_year()

    # DEO quota
    _da_qs = DistrictAllocation.objects.filter(district=district)
    if current_year:
        _da_qs = _da_qs.filter(academic_year=current_year)
    district_alloc = _da_qs.first()

    # Walimu wanafunzi waliochaguliwa kwenye wilaya hii (approved applications)
    approved_apps = (
        StudentApplication.objects
        .filter(school__district=district, status='approved')
        .select_related('student', 'school', 'subject')
        .order_by('school__level', 'school__name', 'student__full_name')
    )

    primary_apps = [a for a in approved_apps if a.school.level == 'Primary']
    secondary_apps = [a for a in approved_apps if a.school.level == 'Secondary']

    # Pia angalia walimu wenye selected_school kwenye wilaya hii (waliopata idhini)
    if not approved_apps.exists():
        yr_students = _active_year_students().filter(
            selected_school__district=district,
            approval_status='approved'
        ).select_related('selected_school').order_by('selected_school__level', 'selected_school__name', 'full_name')
        primary_apps = [
            type('App', (), {
                'student': st, 'school': st.selected_school, 'subject': None
            })() for st in yr_students if st.selected_school and st.selected_school.level == 'Primary'
        ]
        secondary_apps = [
            type('App', (), {
                'student': st, 'school': st.selected_school, 'subject': None
            })() for st in yr_students if st.selected_school and st.selected_school.level == 'Secondary'
        ]

    # Build PDF
    import io as _io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors as rl_colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    buffer = _io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    navy = rl_colors.HexColor('#0A2B5E')
    gold = rl_colors.HexColor('#C8900A')
    light = rl_colors.HexColor('#EEF1F6')
    green = rl_colors.HexColor('#059669')
    purple = rl_colors.HexColor('#5b21b6')

    title_s = ParagraphStyle('T', parent=styles['Heading1'], fontSize=15, textColor=navy,
                              spaceAfter=4, alignment=TA_CENTER, fontName='Helvetica-Bold')
    sub_s = ParagraphStyle('S', parent=styles['Normal'], fontSize=9, textColor=gold,
                            spaceAfter=2, alignment=TA_CENTER)
    sec_s = ParagraphStyle('Sec', parent=styles['Heading2'], fontSize=11, textColor=navy,
                            spaceBefore=12, spaceAfter=4, fontName='Helvetica-Bold')
    body_s = ParagraphStyle('B', parent=styles['Normal'], fontSize=8.5, spaceAfter=3)

    yr_label = current_year.year if current_year else '—'
    story = []
    story.append(Paragraph('JAMHURI YA MUUNGANO WA TANZANIA', sub_s))
    story.append(Paragraph('Wizara ya Elimu, Sayansi na Teknolojia', sub_s))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width='100%', thickness=3, color=gold))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph('ORODHA YA WALIMU WANAFUNZI WALIOCHAGULIWA', title_s))
    story.append(Paragraph(f'Wilaya ya {district.name} — Mwaka {yr_label}', sub_s))
    story.append(Spacer(1, 0.2*cm))
    story.append(HRFlowable(width='100%', thickness=1, color=navy))
    story.append(Spacer(1, 0.4*cm))

    # Quota summary table
    pq = district_alloc.primary_needed if district_alloc else 0
    sq = district_alloc.secondary_needed if district_alloc else 0
    pf = len(primary_apps)
    sf = len(secondary_apps)
    quota_data = [
        ['Kiwango', 'Quota (DEO)', 'Wamejaa', 'Wanobaki'],
        ['Msingi (Primary)', str(pq), str(pf), str(max(0, pq - pf))],
        ['Sekondari (Secondary)', str(sq), str(sf), str(max(0, sq - sf))],
        ['JUMLA', str(pq + sq), str(pf + sf), str(max(0, (pq + sq) - (pf + sf)))],
    ]
    qt = Table(quota_data, colWidths=[6*cm, 3*cm, 3*cm, 3*cm])
    qt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), navy),
        ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [rl_colors.white, light]),
        ('BACKGROUND', (0, -1), (-1, -1), navy),
        ('TEXTCOLOR', (0, -1), (-1, -1), rl_colors.white),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.HexColor('#CBD5E0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(Paragraph('Muhtasari wa Quota', sec_s))
    story.append(qt)
    story.append(Spacer(1, 0.5*cm))

    def make_student_table(apps, level_label, level_color):
        if not apps:
            story.append(Paragraph(f'Shule za {level_label}', sec_s))
            story.append(Paragraph('Hakuna walimu wanafunzi waliochaguliwa bado.', body_s))
            story.append(Spacer(1, 0.3*cm))
            return
        story.append(Paragraph(f'Shule za {level_label}', sec_s))
        headers = ['#', 'Jina la Mwalimu Mwanafunzi', 'Shule', 'Somo']
        data = [headers]
        for i, app in enumerate(apps, 1):
            subj = app.subject.name if app.subject else '—'
            data.append([str(i), app.student.full_name, app.school.name, subj])
        data.append(['', f'JUMLA: {len(apps)}', '', ''])
        col_widths = [1*cm, 6*cm, 6.5*cm, 3.5*cm]
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), level_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [rl_colors.white, light]),
            ('BACKGROUND', (0, -1), (-1, -1), rl_colors.HexColor('#FEF3C7')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.HexColor('#CBD5E0')),
            ('FONTSIZE', (0, 1), (-1, -1), 8.5),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.5*cm))

    make_student_table(primary_apps, 'Msingi', green)
    make_student_table(secondary_apps, 'Sekondari', purple)

    story.append(HRFlowable(width='100%', thickness=1, color=navy))
    story.append(Spacer(1, 0.2*cm))
    from django.utils import timezone as _tz
    story.append(Paragraph(
        f'Imetengenezwa: {_tz.now().strftime("%d/%m/%Y %H:%M")} | DEO: {bm.full_name} | Mfumo wa IMS',
        body_s
    ))

    doc.build(story)
    buffer.seek(0)
    from django.http import HttpResponse as _HR
    fname = f'walimu_wanafunzi_{district.name.replace(" ", "_")}_{yr_label}.pdf'
    resp = _HR(buffer, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{fname}"'
    return resp


@board_login_required
def send_links_to_heads(request, district_id):
    """Tuma SMS ya link ya kujaza form kwa wakuu wa shule zote kwenye wilaya."""
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')

    district = get_object_or_404(District, id=district_id)
    can_edit = bm.role == 'chair' or (bm.role == 'deo' and bm.district_id == district.id)
    if not can_edit:
        messages.error(request, 'Huna ruhusa ya kutuma ujumbe.')
        return redirect('deo_review_requests', district_id=district.id)

    if request.method != 'POST':
        return redirect('deo_review_requests', district_id=district.id)

    # Build the submission link
    scheme = request.scheme
    host = request.get_host()
    submit_path = reverse('school_head_submit', args=[district.id])
    link = f'{scheme}://{host}{submit_path}'

    current_year = _cached_active_year()
    year_str = current_year.year if current_year else ''

    schools_with_phone = School.objects.filter(
        district=district
    ).exclude(head_phone='').order_by('level', 'name')

    schools_without_phone = School.objects.filter(
        district=district, head_phone=''
    ).count()

    sent, failed, skipped = [], [], []

    for school in schools_with_phone:
        # Filter by level if requested
        level_filter = request.POST.get('level', 'both')
        if level_filter != 'both' and school.level != level_filter:
            skipped.append(school.name)
            continue

        message = (
            f"Habari{' ' + school.head_name if school.head_name else ''},\n"
            f"Tafadhali jaza fomu ya mahitaji ya walimu wanafunzi "
            f"kwa mwaka {year_str} kwa Wilaya ya {district.name}:\n"
            f"{link}\n"
            f"- Mfumo wa IMS"
        )
        ok, err = _send_sms_africastalking(school.head_phone, message)
        if ok:
            sent.append(school.name)
        else:
            failed.append({'school': school.name, 'phone': school.head_phone, 'error': err})

    return render(request, 'field_app/send_links_result.html', {
        'district': district,
        'link': link,
        'sent': sent,
        'failed': failed,
        'skipped_count': skipped,
        'no_phone_count': schools_without_phone,
        'total': schools_with_phone.count(),
        'bm': bm,
    })
