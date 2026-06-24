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


@login_required
def help_page(request):
    """Help and user guide page — shows relevant section based on user role."""
    user = request.user
    if user.is_staff:
        role = 'admin'
    elif Assessor.objects.filter(user=user).exists():
        role = 'assessor'
    elif BoardMember.objects.filter(user=user).exists():
        role = 'board'
    else:
        role = 'student'
    return render(request, 'field_app/help.html', {'role': role})


@staff_member_required
def admin_dashboard(request):
    pending_applications = StudentApplication.objects.filter(status='pending').select_related('student', 'subject', 'school')

    total_applications = StudentApplication.objects.count()
    approved_applications = StudentApplication.objects.filter(status='approved').count()
    rejected_applications = StudentApplication.objects.filter(status='rejected').count()
    pending_count = StudentApplication.objects.filter(status='pending').count()

    paginator = Paginator(pending_applications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    schools = School.objects.annotate(
        current_count=Count('studentteacher'),
        is_full=Case(
            When(capacity__lte=F('current_students'), then=Value(True)),
            default=Value(False),
            output_field=BooleanField()
        )
    )

    total_assessors = Assessor.objects.count()
    active_assessors = Assessor.objects.filter(is_active=True).count()

    total_school_assignments = SchoolAssessment.objects.count()
    completed_assessments = SchoolAssessment.objects.filter(is_completed=True).count()

    recent_assignments = SchoolAssessment.objects.select_related(
        'assessor', 'school'
    ).order_by('-assessment_date')[:10]

    # --- Chart data ---
    # 1. Applications by status (donut chart)
    chart_app_status = {
        'labels': ['Approved', 'Pending', 'Rejected'],
        'data': [approved_applications, pending_count, rejected_applications],
    }

    # 2. Students by region (bar chart)
    region_qs = Region.objects.annotate(
        student_count=Count('district__school__studentteacher', distinct=True)
    ).order_by('-student_count')[:10]
    chart_regions = {
        'labels': list(region_qs.values_list('name', flat=True)),
        'data': list(region_qs.values_list('student_count', flat=True)),
    }

    # 3. Logbook submissions – last 14 days (line chart)
    today = timezone.now().date()
    start_day = today - timedelta(days=13)
    from django.db.models.functions import TruncDate
    counts_by_date = {
        row['date']: row['count']
        for row in LogbookEntry.objects.filter(date__range=(start_day, today))
        .values('date').annotate(count=Count('id'))
    }
    logbook_dates = []
    logbook_counts = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        logbook_dates.append(day.strftime('%b %d'))
        logbook_counts.append(counts_by_date.get(day, 0))
    chart_logbook = {
        'labels': logbook_dates,
        'data': logbook_counts,
    }

    # 4. Assessment coverage (schools with vs without active assessor assignment)
    total_schools = School.objects.count()
    schools_with_assessor = SchoolAssessment.objects.values('school').distinct().count()
    schools_without_assessor = max(0, total_schools - schools_with_assessor)
    chart_coverage = {
        'labels': ['With Assessor', 'Without Assessor'],
        'data': [schools_with_assessor, schools_without_assessor],
    }

    context = {
        'pending_applications': pending_applications,
        'schools': schools,
        'total_applications': total_applications,
        'approved_applications': approved_applications,
        'rejected_applications': rejected_applications,
        'page_obj': page_obj,
        'total_assessors': total_assessors,
        'active_assessors': active_assessors,
        'total_school_assignments': total_school_assignments,
        'completed_assessments': completed_assessments,
        'recent_assignments': recent_assignments,
        'total_schools': total_schools,
        # Charts (JSON strings for template)
        'chart_app_status_json': json.dumps(chart_app_status),
        'chart_regions_json': json.dumps(chart_regions),
        'chart_logbook_json': json.dumps(chart_logbook),
        'chart_coverage_json': json.dumps(chart_coverage),
    }

    return render(request, 'field_app/admin_dashboard.html', context)


@staff_member_required
def approve_application(request, application_id):
    application = get_object_or_404(StudentApplication, id=application_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'approve':
            application.status = 'approved'
            application.approved_by = request.user
            application.approval_date = timezone.now()
            application.save()

            application.student.subjects.add(application.subject)

            try:
                capacity = SchoolSubjectCapacity.objects.get(
                    school=application.school,
                    subject=application.subject
                )
                capacity.current_students = F('current_students') + 1
                capacity.save()
            except SchoolSubjectCapacity.DoesNotExist:
                SchoolSubjectCapacity.objects.create(
                    school=application.school,
                    subject=application.subject,
                    current_students=1,
                    max_students=5
                )

            # Auto-send individual letter PDF via email
            student = application.student
            email_addr = student.user.email if student.user else None
            if email_addr:
                try:
                    from django.core.mail import EmailMessage as DjangoEmailMessage
                    pdf_bytes = _build_individual_letter_pdf(student)
                    fname_safe = student.full_name.replace(' ', '_')
                    msg = DjangoEmailMessage(
                        subject='Barua ya Idhini ya Mazoezi ya Kufundisha — IMS',
                        body=(
                            f'Ndugu {student.full_name},\n\n'
                            f'Hongera! Ombi lako la kufanya mazoezi ya kufundisha '
                            f'katika {application.school.name} limeidhinishwa.\n\n'
                            f'Tafadhali angalia barua iliyoambatanishwa na uiwasilishe '
                            f'Halmashauri ya {application.school.district.name} '
                            f'na Mkuu wa Shule unapofika.\n\n'
                            f'Unaweza pia kupakua barua wakati wowote kutoka kwenye akaunti yako.\n\n'
                            f'Mfumo wa IMS'
                        ),
                        to=[email_addr],
                    )
                    msg.attach(f'Barua_{fname_safe}.pdf', pdf_bytes, 'application/pdf')
                    msg.send(fail_silently=True)
                except Exception:
                    pass

            messages.success(request, f"Maombi ya {application.subject.name} yameidhinishwa. Barua imetumwa kwa {email_addr or '—'}.")

        elif action == 'reject':
            application.status = 'rejected'
            application.approved_by = request.user
            application.approval_date = timezone.now()
            application.save()
            messages.success(request, f"Application for {application.subject.name} rejected.")

        return redirect('admin_dashboard')

    return render(request, 'field_app/approve_application.html', {'application': application})


@staff_member_required
def download_backup(request):
    """Admin: export all IMS data as JSON and send as file download."""
    import json as _json
    from django.core import serializers as _ser
    from django.apps import apps as _apps
    from datetime import datetime as _dt

    BACKUP_MODELS = [
        'StudentTeacher', 'School', 'District', 'Region', 'Subject',
        'StudentApplication', 'LogbookEntry', 'SchemeOfWork', 'LessonPlan',
        'Assessor', 'SchoolAssessment', 'AcademicYear',
        'BoardMember', 'BoardComment', 'MonthlyReport',
    ]

    all_objects = []
    for name in BACKUP_MODELS:
        try:
            model = _apps.get_model('field_app', name)
            qs = model.objects.all()
            if qs.exists():
                all_objects.extend(_json.loads(_ser.serialize('json', qs)))
        except Exception:
            pass

    filename = f"ims_backup_{_dt.now().strftime('%Y%m%d_%H%M%S')}.json"
    payload = _json.dumps(all_objects, ensure_ascii=False, indent=2, default=str)
    response = HttpResponse(payload, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@staff_member_required
def assign_assessor(request):
    """Assign single assessor to school"""
    if request.method == 'POST':
        assessor_id = request.POST.get('assessor_id')
        school_id = request.POST.get('school_id')

        assessor = get_object_or_404(Assessor, id=assessor_id)
        school = get_object_or_404(School, id=school_id)

        existing = SchoolAssessment.objects.filter(assessor=assessor, school=school).first()
        if existing:
            messages.warning(request, f"Assessor {assessor.full_name} is already assigned to {school.name}")
            if not assessor.email:
                messages.error(request,
                    f"Assessor {assessor.full_name} has no email address! "
                    f"Cannot send credentials."
                )
                return redirect('assign_assessor')

            temp_password = None
            is_new_account = False

            if not assessor.user:
                temp_password = generate_random_password()

                try:
                    existing_user = User.objects.filter(email=assessor.email).first()
                    if existing_user:
                        user = existing_user
                        user.set_password(temp_password)
                        user.save()
                    else:
                        user = User.objects.create_user(
                            email=assessor.email,
                            password=temp_password,
                            is_staff=False,
                            is_superuser=False,
                            is_active=True
                        )
                    assessor.user = user
                    assessor.save()
                    is_new_account = True

                except Exception as e:
                    messages.error(request, f"Failed to create user account: {str(e)}")
                    return redirect('assign_assessor')

            school_assessment = SchoolAssessment.objects.create(
                assessor=assessor,
                school=school,
                assessment_date=timezone.now().date()
            )

            students = StudentTeacher.objects.filter(
                selected_school=school,
                approval_status='approved'
            )

            student_assessments_created = 0
            for student in students:
                StudentAssessment.objects.create(
                    assessor=assessor,
                    student=student,
                    school=school,
                    assessment_date=timezone.now().date()
                )
                student_assessments_created += 1

            try:
                login_url = request.build_absolute_uri(reverse('assessor_login'))

                subject = f'Field Placement Assessor Assignment - {school.name}'

                if is_new_account:
                    password_info = f"""
                    NEW ACCOUNT CREATED FOR YOU:

                    Login Email: {assessor.email}
                    Temporary Password: {temp_password}

                    Please change your password immediately after first login.
                    """
                    password_info = f"""
                    USE YOUR EXISTING ACCOUNT:

                    Login Email: {assessor.email}

                    If you forgot your password, use 'Forgot Password' on login page.
                    """

                message = f"""
                FIELD PLACEMENT ASSESSOR ASSIGNMENT
                {'=' * 50}

                Dear {assessor.full_name},

                You have been assigned as a Field Placement Assessor.

                ASSIGNMENT DETAILS:
                • School: {school.name}
                • District: {school.district.name}
                • Region: {school.district.region.name}
                • Assignment Date: {timezone.now().strftime('%d/%m/%Y')}
                • Number of Students: {student_assessments_created}

                YOUR LOGIN CREDENTIALS:
                {password_info}

                LOGIN URL: {login_url}

                AFTER LOGIN, YOU CAN:
                1. View assigned school details
                2. See list of students assigned to you
                3. Track student progress
                4. Submit assessment reports
                5. Monitor logbook entries

                IMPORTANT:
                • Login using your email address
                • First-time users must change password
                • Contact administrator if you face issues

                Best regards,
                Kitengo cha Uratibu wa Mafunzo ya Uwanjani
                Wizara ya Elimu, Sayansi na Teknolojia

                Ujumbe huu umetumwa kiotomatiki. Tafadhali usijibu.
                """

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[assessor.email],
                    fail_silently=False,
                )

                if is_new_account:
                    messages.success(request,
                        f"✅ Assessor {assessor.full_name} assigned successfully!<br>"
                        f"• Email sent to: {assessor.email}<br>"
                        f"• Temporary password: {temp_password}<br>"
                        f"• Assigned to: {school.name}<br>"
                        f"• Students: {student_assessments_created}"
                    )
                    messages.success(request,
                        f"✅ Assessor {assessor.full_name} assigned successfully!<br>"
                        f"• Email sent to: {assessor.email}<br>"
                        f"• Assigned to: {school.name}<br>"
                        f"• Students: {student_assessments_created}"
                    )

                print(f"📧 Email sent to assessor {assessor.email}")

            except Exception as e:
                error_msg = str(e)
                print(f"❌ Email failed for {assessor.email}: {error_msg}")

                if is_new_account:
                    messages.warning(request,
                        f"⚠️ Assessor assigned but email failed!<br>"
                        f"• Assessor: {assessor.full_name}<br>"
                        f"• School: {school.name}<br>"
                        f"• ERROR: {error_msg}<br>"
                        f"• <strong>MANUAL CREDENTIALS:</strong><br>"
                        f"Email: {assessor.email}<br>"
                        f"Password: {temp_password}"
                    )
                    messages.warning(request,
                        f"⚠️ Assessor assigned but email failed!<br>"
                        f"• Assessor: {assessor.full_name}<br>"
                        f"• School: {school.name}<br>"
                        f"• ERROR: {error_msg}"
                    )

        return redirect('admin_dashboard')

    # GET REQUEST
    assessors = Assessor.objects.filter(is_active=True).order_by('full_name')
    schools = School.objects.all().order_by('name')

    assessors_with_email = []
    assessors_without_email = []

    for assessor in assessors:
        if assessor.email and '@' in assessor.email:
            assessors_with_email.append(assessor)
            assessors_without_email.append(assessor)

    return render(request, 'field_app/assign_assessor.html', {
        'assessors_with_email': assessors_with_email,
        'assessors_without_email': assessors_without_email,
        'schools': schools,
    })


@staff_member_required
def bulk_assign_assessors(request):
    """Bulk assign assessors to schools - WITH ACADEMIC YEAR LOGIC"""

    if request.method == 'GET':
        # Get current academic year
        current_year = get_current_academic_year()
        if not current_year:
            messages.error(request, "⚠️ Hakuna mwaka wa masomo unaofanya kazi! Fungua mwaka mpya kwanza.")
            return redirect('admin_dashboard')

        # Get ALL assessors
        all_assessors = Assessor.objects.all().order_by('full_name')

        # Check each assessor's status for current year
        for assessor in all_assessors:
            if not assessor.user:
                # Assessor mpya kabisa - hana akaunti
                assessor.needs_new_credentials = True
                assessor.year_status = "Hakuna akaunti"
            elif not assessor.current_academic_year or assessor.current_academic_year != current_year:
                # Assessor ana akaunti lakini ni mwaka mpya
                assessor.needs_new_credentials = True
                assessor.year_status = f"Mpya kwa {current_year.year}"
            else:
                # Assessor ana akaunti na ni mwaka huohuo - shule tu zinaongezwa
                assessor.needs_new_credentials = False
                assessor.year_status = f"Tayari kwa {current_year.year}"

            assessor.schools_assigned = SchoolAssessment.objects.filter(
                assessor=assessor,
                academic_year=current_year
            ).count()

        # Search and pagination for schools
        search_query = request.GET.get('q', '')
        page_number = request.GET.get('page', 1)
        schools_per_page = 50

        schools_qs = School.objects.all().order_by('name')

        if search_query:
            schools_qs = schools_qs.filter(
                Q(name__icontains=search_query) |
                Q(district__name__icontains=search_query) |
                Q(district__region__name__icontains=search_query)
            )

        paginator = Paginator(schools_qs, schools_per_page)

        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        schools_on_page = list(page_obj.object_list)
        all_filtered_schools = list(schools_qs.values_list('id', flat=True))

        # Get stats for schools on current page
        school_ids_on_page = [school.id for school in schools_on_page]

        # Count assessors per school for current year
        assignment_counts = SchoolAssessment.objects.filter(
            school_id__in=school_ids_on_page,
            academic_year=current_year
        ).values('school_id').annotate(assessors_count=Count('assessor_id'))

        assignment_dict = {item['school_id']: item['assessors_count'] for item in assignment_counts}

        # Count students per school
        student_counts = StudentTeacher.objects.filter(
            selected_school_id__in=school_ids_on_page,
            approval_status='approved'
        ).values('selected_school_id').annotate(student_count=Count('id'))

        student_count_dict = {item['selected_school_id']: item['student_count'] for item in student_counts}

        for school in schools_on_page:
            school.assessors_count = assignment_dict.get(school.id, 0)
            school.student_count = student_count_dict.get(school.id, 0)

        # Get assessors without valid emails
        assessors_no_email = Assessor.objects.filter(
            Q(email__isnull=True) | Q(email='')
        ).values_list('full_name', flat=True)

        default_date = (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%d')

        return render(request, 'field_app/bulk_assign_assessors.html', {
            'all_assessors': all_assessors,
            'schools': schools_on_page,
            'page_obj': page_obj,
            'assessors_no_email': list(assessors_no_email),
            'total_assessors': all_assessors.count(),
            'total_schools': School.objects.count(),
            'available_assessors': all_assessors.exclude(
                Q(email__isnull=True) | Q(email='')
            ).count(),
            'default_date': default_date,
            'total_approved_students': StudentTeacher.objects.filter(
                approval_status='approved'
            ).count(),
            'search_query': search_query,
            'all_filtered_schools': all_filtered_schools,
            'current_year': current_year,
        })

    elif request.method == 'POST':
        # Get form data
        assessor_ids = request.POST.getlist('assessors')
        selected_schools_from_checkboxes = request.POST.getlist('schools[]')
        selected_schools_from_hidden = request.POST.get('selected_schools', '')
        assessment_date_str = request.POST.get('assessment_date', '')

        # Combine school selections
        school_ids = []
        if selected_schools_from_checkboxes:
            school_ids.extend(selected_schools_from_checkboxes)

        if selected_schools_from_hidden:
            hidden_ids = [sid.strip() for sid in selected_schools_from_hidden.split(',') if sid.strip()]
            school_ids.extend(hidden_ids)

        school_ids = list(set(school_ids))

        # Validate inputs
        if not assessor_ids:
            messages.error(request, "❌ Tafadhali chagua assessor mmoja au zaidi.")
            return redirect('bulk_assign_assessors')

        if not school_ids:
            messages.error(request, "❌ Tafadhali chagua shule moja au zaidi.")
            return redirect('bulk_assign_assessors')

        # Parse date
        try:
            assessment_date = datetime.strptime(assessment_date_str, '%Y-%m-%d').date()
        except ValueError:
            assessment_date = timezone.now().date()

        # Process assignment
        try:
            results = process_bulk_assignment_with_academic_year(
                assessor_ids, school_ids, assessment_date, request
            )

            request.session['bulk_assignment_results'] = results
            return redirect('bulk_assignment_results')

        except Exception as e:
            messages.error(request, f"❌ Hitilafu: {str(e)}")
            import traceback
            traceback.print_exc()
            return redirect('bulk_assign_assessors')

        return HttpResponseNotAllowed(['GET', 'POST'])


@staff_member_required
def bulk_assignment_results(request):
    """Show results of bulk assignment with credentials"""
    results = request.session.get('bulk_assignment_results')

    if not results:
        messages.info(request, "No assignment results found.")
        return redirect('admin_dashboard')

    # Clear session after showing results
    if 'bulk_assignment_results' in request.session:
        del request.session['bulk_assignment_results']

    return render(request, 'field_app/bulk_assignment_results.html', {
        'results': results
    })


@staff_member_required
def student_list(request):
    students = StudentTeacher.objects.all().select_related('user', 'selected_school')

    school_filter = request.GET.get('school')
    if school_filter:
        students = students.filter(selected_school__name__icontains=school_filter)

    status_filter = request.GET.get('status')
    if status_filter:
        students = students.filter(approval_status=status_filter)

    return render(request, 'field_app/student_list.html', {'students': students})


@staff_member_required
def approve_student(request, student_id):
    student = get_object_or_404(StudentTeacher, id=student_id)

    if request.method == 'POST':
        student.approval_status = 'approved'
        student.approval_date = timezone.now()
        student.save()
        invalidate_student_cache(student)
        messages.success(request, f'Student {student.full_name} approved successfully!')
        return redirect('student_list')

    return render(request, 'field_app/approve_student.html', {'student': student})


@staff_member_required
def manage_regions(request):
    """Main management page for regions and academic years"""
    current_year = get_current_academic_year()
    all_years = AcademicYear.objects.all().order_by('-year')
    all_regions = Region.objects.all().order_by('name')

    # Get pin status for each region
    hidden_count = 0
    for region in all_regions:
        pin = RegionPin.objects.filter(
            academic_year=current_year,
            region=region
        ).first()
        region.is_pinned = pin.is_pinned if pin else False
        if region.is_pinned:
            hidden_count += 1

    context = {
        'current_year': current_year,
        'all_years': all_years,
        'all_regions': all_regions,
        'hidden_count': hidden_count,
        'visible_count': all_regions.count() - hidden_count,
        'total_regions': all_regions.count(),
    }

    return render(request, 'field_app/manage_regions.html', context)


@staff_member_required
def toggle_region_pin(request, region_id):
    """Toggle region pin (hide/unhide) from admin interface"""
    if request.method == 'POST':
        current_year = get_current_academic_year()
        region = get_object_or_404(Region, id=region_id)

        # Get or create pin
        region_pin, created = RegionPin.objects.get_or_create(
            academic_year=current_year,
            region=region,
            defaults={'is_pinned': False}
        )

        # Toggle the pin status
        region_pin.is_pinned = not region_pin.is_pinned
        region_pin.save()

        # Also pin/unpin all schools in this region
        schools_in_region = School.objects.filter(district__region=region)

        if region_pin.is_pinned:
            # Pin all schools (hide)
            for school in schools_in_region:
                SchoolPin.objects.update_or_create(
                    academic_year=current_year,
                    school=school,
                    defaults={
                        'is_pinned': True,
                        'pin_reason': 'region_restricted',
                        'notes': f"Region {region.name} is restricted for {current_year.year}"
                    }
                )
            status = "HIDDEN"
            # Unpin all schools (show)
            SchoolPin.objects.filter(
                academic_year=current_year,
                school__in=schools_in_region
            ).delete()
            status = "VISIBLE"

        messages.success(
            request,
            f"✅ Region '{region.name}' is now {status} to students!"
        )

        return redirect('manage_regions')

    return redirect('manage_regions')


@staff_member_required
def reset_all_region_pins(request):
    """Make all regions visible (unpin everything)"""
    if request.method == 'POST':
        current_year = get_current_academic_year()

        # Delete all pins for current year
        region_deleted = RegionPin.objects.filter(academic_year=current_year).delete()
        school_deleted = SchoolPin.objects.filter(academic_year=current_year).delete()

        messages.success(
            request,
            f"✅ All {Region.objects.count()} regions are now VISIBLE to students!\n"
            f"Deleted {region_deleted[0]} region pins and {school_deleted[0]} school pins"
        )

        return redirect('manage_regions')

    return redirect('manage_regions')


@staff_member_required
def region_pinning_view(request):
    """
    Pin (hide) regions from students for a specific academic year.
    Regions entered in the form will be HIDDEN from students.
    """
    if request.method == 'POST':
        form = RegionFieldInputForm(request.POST)
        if form.is_valid():
            year_name = form.cleaned_data['academic_year']

            # Get regions to hide from form
            regions_data = form.cleaned_data['regions_to_hide']

            # Handle both string and list input
            if isinstance(regions_data, str):
                regions_to_hide_names = [
                    name.strip().lower() for name in regions_data.split(',') if name.strip()
                ]
                regions_to_hide_names = [name.strip().lower() for name in regions_data if name.strip()]

            print(f"📋 Regions to HIDE: {regions_to_hide_names}")

            # Validate regions exist
            existing_region_names = list(Region.objects.values_list('name', flat=True))
            existing_region_names_lower = [r.lower() for r in existing_region_names]

            invalid_regions = []
            valid_regions = []

            for region_name in regions_to_hide_names:
                if region_name in existing_region_names_lower:
                    # Find original case
                    for er in existing_region_names:
                        if er.lower() == region_name:
                            valid_regions.append(er)
                            break
                    invalid_regions.append(region_name)

            if invalid_regions:
                messages.error(
                    request,
                    f"❌ These regions don't exist: {', '.join(invalid_regions)}\n"
                    f"Available regions: {', '.join(existing_region_names[:20])}"
                )
                # Show current status
                current_year = get_current_academic_year()
                if current_year:
                    current_pins = RegionPin.objects.filter(
                        academic_year=current_year,
                        is_pinned=True
                    ).select_related('region')
                    currently_hidden = [pin.region.name for pin in current_pins]
                    currently_hidden = []

                return render(request, 'field_app/pin_regions_form.html', {
                    'form': form,
                    'current_year': current_year if 'current_year' in locals() else None,
                    'currently_hidden_regions': currently_hidden if 'currently_hidden' in locals() else [],
                    'total_regions': Region.objects.count(),
                })

            # Get or create academic year
            year, created = AcademicYear.objects.get_or_create(
                year=year_name,
                defaults={'is_active': True}
            )

            # Set this year as active
            if not year.is_active:
                year.is_active = True
                year.save()
                AcademicYear.objects.exclude(id=year.id).update(is_active=False)
                print(f"📅 Activated academic year: {year.year}")

            # ========== FIX: Clear old pins ==========
            # Delete ALL region pins for this academic year
            region_pins_deleted = RegionPin.objects.filter(academic_year=year).delete()

            # Delete ALL school pins for this academic year
            school_pins_deleted = SchoolPin.objects.filter(academic_year=year).delete()

            print(f"🗑️ Deleted {region_pins_deleted[0]} region pins, {school_pins_deleted[0]} school pins")

            # ========== FIX: Create RegionPin objects for ALL regions ==========
            all_regions = Region.objects.all()
            region_pins_to_create = []
            pinned_region_names = []
            visible_region_names = []

            for region in all_regions:
                # is_pinned = True if region should be HIDDEN from students
                is_pinned = region.name in valid_regions  # Use original case for comparison

                region_pins_to_create.append(RegionPin(
                    academic_year=year,
                    region=region,
                    is_pinned=is_pinned
                ))

                if is_pinned:
                    pinned_region_names.append(region.name)
                    visible_region_names.append(region.name)

            # Bulk create region pins
            if region_pins_to_create:
                RegionPin.objects.bulk_create(region_pins_to_create)
                print(f"✅ Created {len(region_pins_to_create)} region pins")
                print(f"   🔒 Pinned (Hidden): {len(pinned_region_names)}")
                print(f"   ✅ Visible: {len(visible_region_names)}")

            # ========== FIX: Pin schools ONLY in hidden regions ==========
            if pinned_region_names:
                # Get all schools in hidden regions
                schools_to_pin = School.objects.filter(
                    district__region__name__in=pinned_region_names
                ).select_related('district__region')

                school_pins_to_create = []
                for school in schools_to_pin:
                    school_pins_to_create.append(SchoolPin(
                        academic_year=year,
                        school=school,
                        is_pinned=True,
                        pin_reason='region_restricted',
                        notes=f"Region {school.district.region.name} is restricted for {year.year}"
                    ))

                if school_pins_to_create:
                    SchoolPin.objects.bulk_create(school_pins_to_create)
                    print(f"✅ Created {len(school_pins_to_create)} school pins for hidden regions")
                    print(f"ℹ️ No schools found in hidden regions")
                print(f"ℹ️ No hidden regions - no school pins created")
                school_pins_to_create = []

            # Store summary in session for success page
            request.session['pinning_summary'] = {
                'academic_year': year.year,
                'pinned_regions': pinned_region_names,
                'visible_regions': visible_region_names,
                'pinned_regions_count': len(pinned_region_names),
                'visible_regions_count': len(visible_region_names),
                'schools_pinned_count': len(school_pins_to_create),
                'is_new_year': created,
                'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            # Success message
            if len(pinned_region_names) == 0:
                message = f"✅ All {len(visible_region_names)} regions are now VISIBLE to students for {year.year}!"
                message = (
                    f"✅ Success for {year.year}!\n"
                    f"🔒 HIDDEN Regions ({len(pinned_region_names)}): {', '.join(pinned_region_names[:5])}"
                    f"{'...' if len(pinned_region_names) > 5 else ''}\n"
                    f"✅ VISIBLE Regions ({len(visible_region_names)}): {', '.join(visible_region_names[:5])}"
                    f"{'...' if len(visible_region_names) > 5 else ''}\n"
                    f"🏫 Schools Hidden: {len(school_pins_to_create)}"
                )

            messages.success(request, message)
            return redirect('pinning_success')
        else:
            messages.error(request, f"Please correct the errors below: {form.errors}")
    else:
        form = RegionFieldInputForm()

    # GET request or form errors - show current status
    current_year = get_current_academic_year()
    currently_hidden = []

    if current_year:
        current_pins = RegionPin.objects.filter(
            academic_year=current_year,
            is_pinned=True
        ).select_related('region')
        currently_hidden = [pin.region.name for pin in current_pins]

    return render(request, 'field_app/pin_regions_form.html', {
        'form': form,
        'current_year': current_year,
        'currently_hidden_regions': currently_hidden,
        'total_regions': Region.objects.count(),
        'hidden_count': len(currently_hidden),
        'visible_count': Region.objects.count() - len(currently_hidden),
    })


@login_required
def pinning_success_view(request):
    """Display summary after pinning regions"""
    summary = request.session.get('pinning_summary', {})

    context = {
        'summary': summary,
        'has_summary': bool(summary),
    }

    # Clear from session after displaying
    if 'pinning_summary' in request.session:
        del request.session['pinning_summary']

    return render(request, 'field_app/pinning_success.html', context)


@staff_member_required
def change_academic_year(request):
    """Change active academic year from admin interface"""
    if request.method == 'POST':
        year_id = request.POST.get('academic_year_id')

        if not year_id:
            messages.error(request, "Please select an academic year")
            return redirect('manage_regions')

        try:
            new_year = AcademicYear.objects.get(id=year_id)

            # Deactivate all years
            AcademicYear.objects.all().update(is_active=False)

            # Activate selected year
            new_year.is_active = True
            new_year.save()

            # Reset school occupancy counters for new intake
            School.objects.all().update(current_students=0)
            SchoolSubjectCapacity.objects.all().update(current_students=0)

            messages.success(
                request,
                f"✅ Mwaka wa masomo umebadilishwa hadi {new_year.year}. "
                f"Nafasi za shule zimewekwa upya kwa intake mpya."
            )

        except AcademicYear.DoesNotExist:
            messages.error(request, "Academic year not found")

        return redirect('manage_regions')

    return redirect('manage_regions')


@staff_member_required
def create_academic_year(request):
    """Create new academic year from admin interface"""
    if request.method == 'POST':
        year_name = request.POST.get('year_name', '').strip()

        if not year_name:
            messages.error(request, "Please enter academic year (e.g., 2027/2028)")
            return redirect('manage_regions')

        # Validate format
        if '/' not in year_name:
            messages.error(request, "Use format YYYY/YYYY (e.g., 2027/2028)")
            return redirect('manage_regions')

        # Check if exists
        if AcademicYear.objects.filter(year=year_name).exists():
            messages.warning(request, f"Academic year {year_name} already exists!")
            # Create new year (not active by default)
            AcademicYear.objects.create(
                year=year_name,
                is_active=False
            )
            messages.success(request, f"✅ Academic year {year_name} created successfully!")

        return redirect('manage_regions')

    return redirect('manage_regions')


@staff_member_required
def create_admin(request):
    User = get_user_model()
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        if not email or not password:
            messages.error(request, "Email na password zinahitajika.")
        elif User.objects.filter(email=email).exists():
            messages.error(request, f"Mtumiaji mwenye email '{email}' tayari yupo.")
        elif len(password) < 6:
            messages.error(request, "Password iwe na herufi 6 au zaidi.")
        else:
            User.objects.create_superuser(email=email, password=password)
            messages.success(request, f"✅ Admin '{email}' ametengenezwa.")
            return redirect('admin_dashboard')
    return render(request, 'field_app/create_admin.html')


@staff_member_required
def admin_report_pdf(request):
    """Generate comprehensive admin report PDF"""
    try:
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
    except ImportError as e:
        return HttpResponse(f"ReportLab library error: {e}", status=500)

    # Alias so rest of code uses rl_colors not module-level colors
    colors = rl_colors

    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        elements = []
        styles = getSampleStyleSheet()

        NAVY = colors.HexColor('#0A2B5E')
        GOLD = colors.HexColor('#C8900A')
        LIGHT = colors.HexColor('#EEF1F6')
        LIGHT2 = colors.HexColor('#FFF8ED')

        bold_style = ParagraphStyle('IMSBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14, spaceAfter=6, textColor=NAVY)
        sub_style  = ParagraphStyle('IMSSub',  parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, spaceAfter=4, textColor=GOLD)
        norm_style = ParagraphStyle('IMSNorm', parent=styles['Normal'], fontSize=9, spaceAfter=4)

        current_year = get_current_academic_year()
        report_date  = timezone.now().strftime('%d %B %Y')

        elements.append(Paragraph('INTERNSHIP MANAGEMENT SYSTEM (IMS)', bold_style))
        elements.append(Paragraph('Teacher Colleges in Tanzania', sub_style))
        elements.append(Paragraph(f'Comprehensive Report — {current_year.year if current_year else "N/A"} | Generated: {report_date}', norm_style))
        elements.append(HRFlowable(width="100%", thickness=2, color=NAVY))
        elements.append(Spacer(1, 0.3*cm))

        # ── Summary stats ──
        total_students    = StudentTeacher.objects.count()
        approved_students = StudentTeacher.objects.filter(approval_status='approved').count()
        pending_students  = StudentTeacher.objects.filter(approval_status='pending').count()
        total_assessors   = Assessor.objects.count()
        total_schools     = School.objects.count()
        total_logbooks    = LogbookEntry.objects.count()
        verified_logbooks = LogbookEntry.objects.filter(is_location_verified=True).count()

        elements.append(Paragraph('SUMMARY STATISTICS', sub_style))
        summary_data = [
            ['Metric', 'Count'],
            ['Total Students Registered', str(total_students)],
            ['Approved Students', str(approved_students)],
            ['Pending Students', str(pending_students)],
            ['Total Assessors', str(total_assessors)],
            ['Partner Schools', str(total_schools)],
            ['Total Logbook Entries', str(total_logbooks)],
            ['GPS Verified Entries', str(verified_logbooks)],
        ]
        summary_table = Table(summary_data, colWidths=[10*cm, 5*cm])
        sum_style_cmds = [
            ('BACKGROUND', (0,0), (-1,0), NAVY),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
            ('ALIGN', (1,0), (1,-1), 'CENTER'),
            ('PADDING', (0,0), (-1,-1), 6),
        ]
        for row_i in range(1, len(summary_data)):
            bg = LIGHT if row_i % 2 == 0 else colors.white
            sum_style_cmds.append(('BACKGROUND', (0,row_i), (-1,row_i), bg))
        summary_table.setStyle(TableStyle(sum_style_cmds))
        elements.append(summary_table)
        elements.append(Spacer(1, 0.5*cm))

        # ── Students table ──
        elements.append(Paragraph('STUDENTS LIST', sub_style))
        students = StudentTeacher.objects.select_related('user', 'selected_school', 'selected_school__district').order_by('full_name')
        student_data = [['#', 'Full Name', 'Registration No.', 'School', 'District', 'Status', 'Logbook']]
        for i, st in enumerate(students, 1):
            logbook_count = LogbookEntry.objects.filter(student=st).count()
            student_data.append([
                str(i),
                (st.full_name or '-')[:40],
                st.registration_number or '-',
                (st.selected_school.name if st.selected_school else 'Not Selected')[:30],
                (st.selected_school.district.name if st.selected_school and st.selected_school.district else '-')[:20],
                st.approval_status.title(),
                str(logbook_count),
            ])
        st_table = Table(student_data, colWidths=[0.8*cm, 4.5*cm, 3*cm, 3.5*cm, 2.5*cm, 2*cm, 1.5*cm])
        st_cmds = [
            ('BACKGROUND', (0,0), (-1,0), NAVY),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 7),
            ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#CBD5E0')),
            ('PADDING', (0,0), (-1,-1), 4),
            ('ALIGN', (0,0), (0,-1), 'CENTER'),
            ('ALIGN', (6,0), (6,-1), 'CENTER'),
        ]
        for row_i in range(1, len(student_data)):
            st_cmds.append(('BACKGROUND', (0,row_i), (-1,row_i), LIGHT if row_i % 2 == 0 else colors.white))
        st_table.setStyle(TableStyle(st_cmds))
        elements.append(st_table)
        elements.append(Spacer(1, 0.5*cm))

        # ── Assessors table ──
        elements.append(Paragraph('ASSESSORS LIST', sub_style))
        assessors = Assessor.objects.all().order_by('full_name')
        assessor_data = [['#', 'Full Name', 'Email', 'Phone', 'Academic Year', 'Schools']]
        for i, a in enumerate(assessors, 1):
            schools_count = SchoolAssessment.objects.filter(assessor=a, academic_year=current_year).count() if current_year else 0
            assessor_data.append([
                str(i),
                (a.full_name or '-')[:35],
                (a.email or '-')[:35],
                a.phone_number or '-',
                a.current_academic_year.year if a.current_academic_year else '-',
                str(schools_count),
            ])
        a_table = Table(assessor_data, colWidths=[0.8*cm, 4*cm, 5*cm, 3*cm, 3*cm, 2*cm])
        a_cmds = [
            ('BACKGROUND', (0,0), (-1,0), GOLD),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 7),
            ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#CBD5E0')),
            ('PADDING', (0,0), (-1,-1), 4),
            ('ALIGN', (0,0), (0,-1), 'CENTER'),
            ('ALIGN', (5,0), (5,-1), 'CENTER'),
        ]
        for row_i in range(1, len(assessor_data)):
            a_cmds.append(('BACKGROUND', (0,row_i), (-1,row_i), LIGHT2 if row_i % 2 == 0 else colors.white))
        a_table.setStyle(TableStyle(a_cmds))
        elements.append(a_table)

        doc.build(elements)
        buffer.seek(0)
        filename = f"IMS_Report_{timezone.now().strftime('%Y%m%d')}.pdf"
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        import traceback
        return HttpResponse(
            f"<h3>PDF Generation Error</h3><pre>{traceback.format_exc()}</pre>",
            status=500
        )


@staff_member_required
@login_required
def import_head_teachers(request):
    """Admin: import wakuu wa shule kwa CSV - school_identifier,email,jina
    school_identifier inaweza kuwa: school_code (S.0306) AU jina kamili la shule.
    """
    if not request.user.is_staff:
        return redirect('dashboard')

    User = get_user_model()
    results = []

    if request.method == 'POST':
        import csv, io
        mode = request.POST.get('mode', 'csv_text')

        if mode == 'csv_file' and request.FILES.get('csv_file'):
            f = request.FILES['csv_file']
            content = f.read().decode('utf-8', errors='ignore')
        else:
            content = request.POST.get('csv_text', '')

        reader = csv.reader(io.StringIO(content.strip()))
        for i, row in enumerate(reader, 1):
            if not row or row[0].strip().startswith('#'):
                continue
            parts = [p.strip() for p in row]
            if len(parts) < 2:
                results.append({'row': i, 'status': 'error', 'msg': f'Muundo mbaya: {",".join(parts)}'})
                continue

            school_identifier = parts[0]
            email = parts[1].lower()
            full_name = parts[2] if len(parts) > 2 else email.split('@')[0].replace('.', ' ').title()

            # Jaribu kupata shule kwa njia 4:
            # 1) school_code (S.0306, S0306)
            raw = school_identifier.upper().replace(' ', '').replace('-', '').replace('.', '')
            code = raw if re.match(r'^PS\d+$', raw) else re.sub(r'^([SP])(\d+)$', r'\1.\2', raw)
            school = School.objects.filter(school_code__iexact=code).first()
            # 2) jina kamili kama ilivyo
            if not school:
                school = School.objects.filter(name__iexact=school_identifier).first()
            # 3) jina bila suffix ya level (Secondary/Primary/Sekondari/Msingi)
            if not school:
                clean = re.sub(r'\s+(secondary|primary|sekondari|msingi|shule ya sekondari|shule ya msingi)$',
                               '', school_identifier, flags=re.IGNORECASE).strip()
                if clean != school_identifier:
                    school = School.objects.filter(name__iexact=clean).first()
            # 4) icontains — angalau sehemu ya jina
            if not school:
                school = School.objects.filter(name__icontains=school_identifier.split()[0]).first() \
                    if school_identifier.strip() else None
            if not school:
                results.append({'row': i, 'status': 'error', 'msg': f'Shule haikupatikana: "{school_identifier}"'})
                continue

            # Angalia kama tayari ipo
            if BoardMember.objects.filter(user__email__iexact=email, school=school, role='head_teacher').exists():
                results.append({'row': i, 'status': 'skip', 'msg': f'{school.name} — {email} tayari ipo'})
                continue

            # Unda user na BoardMember kwa bulk-efficient way
            user, created = User.objects.get_or_create(email=email)
            if created:
                user.set_unusable_password()
                user.save(update_fields=['password'])

            BoardMember.objects.create(
                user=user, full_name=full_name, role='head_teacher',
                school=school, district=school.district,
                region=school.district.region if school.district else None,
                is_active=True,
            )
            results.append({'row': i, 'status': 'ok', 'msg': f'{school.name} — {full_name} ({email})'})

    return render(request, 'field_app/import_head_teachers.html', {'results': results})


def create_board_member(request):
    """Admin: create board member - moja au bulk kwa wakuu wa shule."""
    User = get_user_model()
    regions = Region.objects.all().order_by('name')
    districts = District.objects.select_related('region').order_by('name')
    schools = School.objects.select_related('district__region').order_by('name')

    if request.method == 'POST':
        mode = request.POST.get('mode', 'single')

        if mode == 'bulk':
            # Bulk create: kila mstari = school_code,email,jina
            lines = request.POST.get('bulk_data', '').strip().splitlines()
            created, skipped = 0, []
            for line in lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) < 2:
                    skipped.append(f"Mstari mbaya: {line}")
                    continue
                school_code_raw = parts[0]
                email = parts[1].lower()
                full_name = parts[2] if len(parts) > 2 else email.split('@')[0]

                raw = school_code_raw.upper().replace(' ', '').replace('-', '').replace('.', '')
                code = raw if re.match(r'^PS\d+$', raw) else re.sub(r'^([SP])(\d+)$', r'\1.\2', raw)
                school = School.objects.filter(school_code__iexact=code).first()
                if not school:
                    skipped.append(f"Shule haikupatikana: {school_code_raw}")
                    continue
                if User.objects.filter(email=email).exists():
                    skipped.append(f"Email tayari ipo: {email}")
                    continue

                user = User.objects.create_user(email=email, password=None)
                user.set_unusable_password()
                user.save()
                BoardMember.objects.create(
                    user=user, full_name=full_name, role='head_teacher',
                    school=school, district=school.district,
                    region=school.district.region if school.district else None,
                )
                created += 1

            msg = f'Akaunti {created} zimeundwa.'
            if skipped:
                msg += f' Zilizoshindwa ({len(skipped)}): ' + '; '.join(skipped[:5])
            messages.success(request, msg)
            return redirect('admin_dashboard')

        else:
            # Single create
            full_name = request.POST.get('full_name', '').strip()
            email = request.POST.get('email', '').strip().lower()
            phone = request.POST.get('phone_number', '').strip()
            role = request.POST.get('role', 'member')
            password = request.POST.get('password', '').strip()
            region_id = request.POST.get('region') or None
            district_id = request.POST.get('district') or None
            school_id = request.POST.get('school') or None

            if not full_name or not email:
                messages.error(request, 'Jaza jina na barua pepe.')
            elif not password or len(password) < 6:
                messages.error(request, 'Weka nywila ya angalau herufi 6.')
            elif User.objects.filter(email=email).exists():
                messages.error(request, f"Email '{email}' tayari ipo.")
            else:
                user = User.objects.create_user(email=email, password=password)
                region = Region.objects.filter(id=region_id).first() if region_id else None
                district = District.objects.filter(id=district_id).first() if district_id else None
                school = School.objects.filter(id=school_id).first() if school_id else None
                bm_new = BoardMember.objects.create(
                    user=user, full_name=full_name, phone_number=phone,
                    role=role, region=region, district=district, school=school,
                )
                # Onyesha credentials kwa admin azitume
                return render(request, 'field_app/create_board_member.html', {
                    'regions': regions, 'districts': districts, 'schools': schools,
                    'role_choices': BoardMember.ROLE_CHOICES,
                    'created_credentials': {
                        'full_name': full_name,
                        'email': email,
                        'password': password,
                        'role': bm_new.get_role_display(),
                        'region': region.name if region else '—',
                        'district': district.name if district else '—',
                    },
                })

    return render(request, 'field_app/create_board_member.html', {
        'regions': regions,
        'districts': districts,
        'schools': schools,
        'role_choices': BoardMember.ROLE_CHOICES,
    })


@staff_member_required
def reset_assessors_for_new_year(request):
    """Reset all assessors for new academic year"""
    if request.method == 'POST':
        current_year = get_current_academic_year()
        if not current_year:
            messages.error(request, "No active academic year found!")
            return redirect('admin_dashboard')

        assessors = Assessor.objects.filter(is_active=True, user__isnull=False)

        results = []
        for assessor in assessors:
            if assessor.email and '@' in assessor.email:
                temp_password = generate_random_password()

                assessor.user.set_password(temp_password)
                assessor.user.save()

                assessor.current_academic_year = current_year
                assessor.save()

                results.append({
                    'name': assessor.full_name,
                    'email': assessor.email,
                    'password': temp_password,
                    'status': '✅ Password reset for new year'
                })

        request.session['new_year_credentials'] = results

        messages.success(request,
            f"✅ Reset {len(results)} assessors for new academic year {current_year.year}"
        )
        return redirect('new_year_credentials')

    return render(request, 'field_app/reset_new_year.html')


@staff_member_required
def new_year_credentials(request):
    """Show credentials after new year reset"""
    results = request.session.get('new_year_credentials', [])

    if not results:
        messages.info(request, "No credentials found. Please reset assessors first.")
        return redirect('reset_assessors_for_new_year')

    return render(request, 'field_app/new_year_credentials.html', {
        'results': results,
        'total': len(results)
    })


@login_required
def download_individual_letter(request):
    import io, os
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.utils import simpleSplit

    student = get_or_create_student_profile(request.user)
    approved_applications = StudentApplication.objects.filter(
        student=student, status='approved'
    ).select_related('subject', 'school')

    if not approved_applications.exists():
        messages.error(request, "Huna maombi yaliyoidhinishwa. Pakua barua baada ya kuidhinishwa.")
        return redirect('dashboard')

    school       = student.selected_school
    district     = school.district if school else None
    region       = district.region if district else None
    today        = timezone.now().date()

    from field_app.views.utils import _cached_active_year
    current_year = _cached_active_year()
    yr_str       = current_year.year if current_year else str(today.year)

    school_name  = school.name if school else '—'
    dist_name    = district.name if district else '—'
    region_name  = region.name if region else '—'
    date_str     = today.strftime('%d %B %Y')
    dist_code    = ''.join(ch for ch in dist_name.upper()[:5] if ch.isalpha())
    ref_no       = f"IMS.MAZOEZI/{today.year}/{dist_code}/{student.id:05d}"
    serial_no    = f"IMS/{today.year}/{dist_code}/{student.id:05d}"
    subj_list    = ", ".join(a.subject.name for a in approved_applications)

    # Determine school level for DEO signature label
    school_level = (school.level or '').lower() if school else ''
    if school_level == 'primary':
        deo_title = "AFISA ELIMU MSINGI WA WILAYA"
        deo_label = "Afisa Elimu Msingi wa Wilaya"
    else:
        deo_title = "AFISA ELIMU SEKONDARI WA WILAYA"
        deo_label = "Afisa Elimu Sekondari wa Wilaya"

    BLACK = rl_colors.black
    NAVY  = rl_colors.HexColor('#0A2B5E')

    # ── Coat of arms ─────────────────────────────────────────────────────────
    from django.conf import settings as _s
    from django.contrib.staticfiles import finders as _f
    _base  = getattr(_s, 'BASE_DIR', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _sroot = getattr(_s, 'STATIC_ROOT', '') or ''
    coat_img_path = next((p for p in [
        _f.find('images/tz_coat_of_arms.png'),
        os.path.join(_sroot, 'images', 'tz_coat_of_arms.png'),
        os.path.join(_base, 'field_app', 'static', 'images', 'tz_coat_of_arms.png'),
        os.path.join(_base, 'staticfiles', 'images', 'tz_coat_of_arms.png'),
    ] if p and os.path.exists(p)), None)

    buf = io.BytesIO()
    W, H = A4
    CX = W / 2
    LM = 2.0 * cm
    RM = W - 2.0 * cm

    c = rl_canvas.Canvas(buf, pagesize=A4)

    def _watermarks():
        micro = f"IMS MAZOEZI YA KUFUNDISHA • {serial_no} • HALISI •  "
        mw = c.stringWidth(micro, 'Helvetica', 5.5)
        c.saveState()
        c.setFont('Helvetica', 5.5); c.setFillColor(NAVY); c.setFillAlpha(0.05)
        ri, yp = 0, 4.0
        while yp < H + 9:
            xp = (-mw / 2) if ri % 2 else 0.0
            while xp < W + mw:
                c.drawString(xp, yp, micro); xp += mw
            yp += 9.0; ri += 1
        c.restoreState()
        c.saveState()
        c.setFont('Helvetica-Bold', 60); c.setFillColor(NAVY); c.setFillAlpha(0.03)
        c.translate(CX, H / 2); c.rotate(45)
        c.drawCentredString(0, 48, "IMS"); c.drawCentredString(0, -20, "HALISI")
        c.restoreState()

    _watermarks()

    # ── TITLE ─────────────────────────────────────────────────────────────────
    y = H - 1.6 * cm
    c.setFont('Helvetica-Bold', 14); c.setFillColor(BLACK)
    c.drawCentredString(CX, y, "JAMHURI YA MUUNGANO WA TANZANIA"); y -= 0.65 * cm
    c.setFont('Helvetica-Bold', 12)
    c.drawCentredString(CX, y, "OFISI YA RAIS"); y -= 0.38 * cm
    c.setStrokeColor(BLACK); c.setLineWidth(1.8)
    c.line(LM, y, RM, y); y -= 3
    c.setLineWidth(0.5); c.line(LM, y, RM, y); y -= 0.5 * cm

    # ── 3-COLUMN HEADER ───────────────────────────────────────────────────────
    sec_top = y
    coa_w, coa_h = 70, 85
    if coat_img_path:
        try:
            c.drawImage(coat_img_path, CX - coa_w / 2, sec_top - coa_h,
                        width=coa_w, height=coa_h, mask='auto')
        except Exception:
            pass

    # Left block
    ly = sec_top - 0.05 * cm
    for entry in [
        ('bold', f'Simu ya Upepo "{dist_name.upper()}"'),
        ('mix',  'Simu: ', '255 (0) —'),
        ('mix',  'Tovuti: ', 'www.tamisemi.go.tz'),
        ('mix',  'Baruapepe: ', 'elimu@tamisemi.go.tz'),
        ('bold', 'Unapojibu Taja:'),
    ]:
        if entry[0] == 'bold':
            c.setFont('Helvetica-Bold', 8.5); c.setFillColor(BLACK)
            c.drawString(LM, ly, entry[1])
        else:
            lbl, val = entry[1], entry[2]
            lw = c.stringWidth(lbl, 'Helvetica-Bold', 8.5)
            c.setFont('Helvetica-Bold', 8.5); c.drawString(LM, ly, lbl)
            c.setFont('Helvetica', 8.5); c.drawString(LM + lw, ly, val)
        ly -= 0.42 * cm

    # Right block
    right_col = CX + coa_w / 2 + 0.5 * cm
    ry = sec_top - 0.05 * cm
    for bold, line in [
        (False, f"Ofisi ya {deo_label},"),
        (False, f"Wilaya ya {dist_name},"),
        (False, f"Mkoa wa {region_name},"),
        (True,  f"{region_name.upper()}."),
    ]:
        fn = 'Helvetica-Bold' if bold else 'Helvetica'
        c.setFont(fn, 8.5); c.setFillColor(BLACK)
        c.drawString(right_col, ry, line)
        if bold:
            tw = c.stringWidth(line, fn, 8.5)
            c.setLineWidth(0.6); c.line(right_col, ry - 1.5, right_col + tw, ry - 1.5)
        ry -= 0.42 * cm

    y = sec_top - coa_h - 0.4 * cm
    c.setStrokeColor(BLACK); c.setLineWidth(1.8)
    c.line(LM, y, RM, y); y -= 3
    c.setLineWidth(0.5); c.line(LM, y, RM, y); y -= 0.6 * cm

    # ── REFERENCE + DATE ──────────────────────────────────────────────────────
    c.setFont('Helvetica-Bold', 9.5); c.setFillColor(BLACK)
    c.drawString(LM, y, f"Kumb. Na. {ref_no}")
    c.drawRightString(RM, y, date_str)
    y -= 1.0 * cm

    # ── RECIPIENT ─────────────────────────────────────────────────────────────
    c.setFont('Helvetica-Bold', 10); c.setFillColor(BLACK)
    c.drawString(LM, y, f"{student.full_name},"); y -= 0.50 * cm
    c.setFont('Helvetica', 10)
    c.drawString(LM, y, f"{school_name},"); y -= 0.50 * cm
    c.setFont('Helvetica-Bold', 10)
    dist_label = f"{dist_name.upper()}."
    c.drawString(LM, y, dist_label)
    dw = c.stringWidth(dist_label, 'Helvetica-Bold', 10)
    c.setLineWidth(0.8); c.line(LM, y - 1.5, LM + dw, y - 1.5)
    y -= 1.0 * cm

    # ── SUBJECT LINE ──────────────────────────────────────────────────────────
    subj_text = "YAH: KUPANGIWA KITUO CHA MAZOEZI YA KUFUNDISHA (TEACHING PRACTICE)"
    c.setFont('Helvetica-Bold', 10.5); c.setFillColor(BLACK)
    sw = c.stringWidth(subj_text, 'Helvetica-Bold', 10.5)
    c.drawCentredString(CX, y, subj_text)
    c.setLineWidth(0.9); c.line(CX - sw / 2, y - 2, CX + sw / 2, y - 2)
    y -= 1.1 * cm

    # ── BODY ──────────────────────────────────────────────────────────────────
    body_w = RM - LM - 1.4 * cm
    txt_x  = LM + 1.4 * cm
    num_x  = LM + 0.5 * cm

    def draw_para(num, text, cur_y):
        c.setFont('Helvetica', 10); c.setFillColor(BLACK)
        c.drawString(num_x, cur_y, f"{num}.")
        for line in simpleSplit(text, 'Helvetica', 10, body_w):
            c.drawString(txt_x, cur_y, line)
            cur_y -= 0.52 * cm
        return cur_y - 0.28 * cm

    y = draw_para("1", (
        f"Tafadhali rejea maombi yako ya kufanya mazoezi ya kufundisha ({subj_list}) "
        f"uliyoyaomba kupitia Mfumo wa Usimamizi wa Mazoezi ya Kufundisha (IMS) "
        f"kwa Mwaka wa Masomo {yr_str}. Ninayo furaha kukufahamisha kuwa umepangiwa "
        f"kufanya mazoezi yako katika {school_name} katika Halmashauri ya Wilaya ya {dist_name}."
    ), y)

    y = draw_para("2", (
        "Hivyo, upatapo barua hii unatakiwa kwanza kuripoti katika Ofisi ya "
        f"{deo_label} wa Wilaya ya {dist_name} ili barua hii ipate sahihi na muhuri "
        "wa uthibitisho, kisha ndo uende kuripoti katika kituo chako cha mazoezi "
        "ndani ya muda wa siku kumi na nne (14) kuanzia tarehe ya kupokea barua hii."
    ), y)

    y = draw_para("3", (
        "Ukishindwa kuripoti katika muda uliowekwa, nafasi yako itajazwa na mwanafunzi "
        "mwingine. Hivyo, unatakiwa kufuata taratibu hizi kwa wakati uliowekwa."
    ), y)

    y = draw_para("4", (
        "Aidha, unatakiwa kwenda na vyeti vyako halisi (Original Certificates) "
        "pamoja na barua hii ili viweze kuhakikiwa na Mkuu wa Shule "
        "kabla hujapewa darasa la kufundisha."
    ), y)

    y = draw_para("5", "Nakutakia kila la kheri katika mazoezi yako ya kufundisha.", y)

    # ── SCHOOL PRINCIPAL SECTION ───────────────────────────────────────────────
    y -= 0.3 * cm
    # Separator line
    c.setStrokeColor(NAVY); c.setLineWidth(1.0)
    c.line(LM, y, RM, y); y -= 0.02 * cm
    c.setLineWidth(0.4); c.line(LM, y, RM, y); y -= 0.45 * cm

    # Header kwa Mkuu wa Shule
    school_hdr = f"KWA: MKUU WA SHULE — {school_name.upper()}"
    c.setFont('Helvetica-Bold', 9.5); c.setFillColor(NAVY)
    c.drawString(LM, y, school_hdr)
    sh_w = c.stringWidth(school_hdr, 'Helvetica-Bold', 9.5)
    c.setLineWidth(0.7); c.line(LM, y - 1.5, LM + sh_w, y - 1.5)
    y -= 0.55 * cm

    # Maandishi kwa Mkuu wa Shule
    school_body_w = RM - LM
    c.setFont('Helvetica', 10); c.setFillColor(BLACK)
    school_msg = (
        f"Ndugu Mkuu wa Shule, tunakuomba umpokee mwanafunzi mwalimu "
        f"{student.full_name} ambaye amepangiwa kufanya mazoezi ya kufundisha "
        f"(Teaching Practice/Internship) katika shule yako kwa Mwaka wa Masomo {yr_str}. "
        f"Tafadhali mpe mazingira mazuri ya kufundisha na usimamizi unaohitajika "
        f"ili aweze kukamilisha mafunzo yake kwa ufanisi. "
        f"Ushirikiano wako ni muhimu sana katika kukamilisha mafunzo yake."
    )
    for line in simpleSplit(school_msg, 'Helvetica', 10, school_body_w):
        c.drawString(LM, y, line)
        y -= 0.52 * cm

    # ── IMS SIGNATURE ─────────────────────────────────────────────────────────
    y -= 0.4 * cm
    sig_x = CX - 3 * cm
    c.setFont('Helvetica-Oblique', 12); c.setFillColor(NAVY)
    c.drawString(sig_x, y, "Msimamizi wa IMS"); y -= 0.38 * cm
    c.setStrokeColor(BLACK); c.setLineWidth(0.7)
    c.line(sig_x, y, sig_x + 6.0 * cm, y); y -= 0.42 * cm
    c.setFont('Helvetica-Bold', 10); c.setFillColor(BLACK)
    c.drawString(sig_x, y, "MSIMAMIZI WA MFUMO (IMS)"); y -= 0.42 * cm
    c.drawString(sig_x, y, f"Wilaya ya {dist_name}")

    # ── DEO SIGN SECTION ──────────────────────────────────────────────────────
    # Box/separator
    y -= 0.8 * cm
    c.setStrokeColor(NAVY); c.setLineWidth(1.0)
    c.line(LM, y, RM, y); y -= 0.02 * cm
    c.setLineWidth(0.4); c.line(LM, y, RM, y); y -= 0.4 * cm

    # Section header
    hdr = f"KUTHIBITISHWA NA {deo_title} WA WILAYA YA {dist_name.upper()}"
    c.setFont('Helvetica-Bold', 9); c.setFillColor(NAVY)
    c.drawCentredString(CX, y, hdr); y -= 0.55 * cm

    # Three columns: Sahihi | Tarehe | Muhuri
    col1_x = LM
    col2_x = LM + 5.5 * cm
    col3_x = LM + 10.5 * cm
    dash_len = 4.5 * cm

    c.setStrokeColor(BLACK); c.setLineWidth(0.7)
    c.line(col1_x, y, col1_x + dash_len, y)
    c.line(col2_x, y, col2_x + dash_len, y)

    # Muhuri box
    muh_w, muh_h = 3.5 * cm, 1.6 * cm
    c.setLineWidth(0.5)
    c.rect(col3_x, y - muh_h + 0.15*cm, muh_w, muh_h)

    y -= 0.30 * cm
    c.setFont('Helvetica', 8); c.setFillColor(BLACK)
    c.drawString(col1_x, y, "Sahihi:")
    c.drawString(col2_x, y, "Tarehe: _____ / _____ / _______")
    c.drawCentredString(col3_x + muh_w / 2, y - 0.3 * cm, "MUHURI")
    y -= 0.45 * cm

    c.setFont('Helvetica', 8)
    c.drawString(col1_x, y, f"Jina: ________________________________"); y -= 0.42 * cm
    c.setFont('Helvetica-Bold', 8)
    c.drawString(col1_x, y, deo_title)

    # Footer
    fy = 1.3 * cm
    c.setStrokeColor(BLACK); c.setLineWidth(0.5)
    c.line(LM, fy + 0.55 * cm, RM, fy + 0.55 * cm)
    c.setFont('Helvetica', 7); c.setFillColor(rl_colors.HexColor('#333333'))
    c.drawString(LM, fy + 0.22 * cm, f"Kumb.: {serial_no}   |   Tarehe: {date_str}")
    c.drawRightString(RM, fy + 0.22 * cm, f"Hati Rasmi — IMS • {deo_label}")

    # ── PAGE 2 — NAKALA ───────────────────────────────────────────────────────
    c.showPage()
    _watermarks()

    ny = H - 2.5 * cm
    c.setFont('Helvetica-Bold', 9.5); c.setFillColor(BLACK)
    c.drawString(LM, ny, "Nakala:"); ny -= 0.15 * cm

    INDENT = LM + 3.5 * cm
    for block in [
        [
            f"{deo_label},",
            f"Wilaya ya {dist_name},",
            f"Mkoa wa {region_name}.",
        ],
        [
            f"Mkurugenzi Mtendaji,",
            f"Halmashauri ya Wilaya ya {dist_name},",
            f"Mkoa wa {region_name}.",
            "(Tafadhali mpokee na kukamilisha taratibu za mazoezi yake)",
        ],
        [
            "Mkuu wa Shule,",
            f"{school_name},",
            f"Wilaya ya {dist_name}.",
        ],
    ]:
        ny -= 0.25 * cm
        for line in block:
            is_city = line.isupper() and line.endswith('.')
            fn = 'Helvetica-Bold' if is_city else 'Helvetica'
            c.setFont(fn, 9.5); c.setFillColor(BLACK)
            c.drawString(INDENT, ny, line)
            if is_city:
                tw = c.stringWidth(line, fn, 9.5)
                c.setLineWidth(0.6); c.line(INDENT, ny - 1.5, INDENT + tw, ny - 1.5)
            ny -= 0.42 * cm
        ny -= 0.15 * cm

    c.save()
    buf.seek(0)
    safe_name = student.full_name.replace(' ', '_').replace('/', '_')
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Barua_Mazoezi_{safe_name}.pdf"'
    return response


@login_required
def download_group_letter(request):
    student = get_or_create_student_profile(request.user)

    if not student.selected_school:
        messages.error(request, "Huna shule uliyochagua.")
        return redirect('dashboard')

    school = student.selected_school
    group_letter_quota = 5

    approved_students_count = StudentApplication.objects.filter(
        school=school,
        status='approved'
    ).count()

    student_has_approved_application = StudentApplication.objects.filter(
        student=student,
        school=school,
        status='approved'
    ).exists()

    if approved_students_count < group_letter_quota:
        messages.error(request,
            f"Bado hatujafikia idadi ya wanafunzi {group_letter_quota} walioidhinishwa. "
            f"Kwa sasa kuna {approved_students_count}/{group_letter_quota}."
        )
        return redirect('dashboard')

    if not student_has_approved_application:
        messages.error(request,
            "Huwezi kupata barua ya kikundi kwa sababu huna maombi yaliyoidhinishwa kwenye shule hii."
        )
        return redirect('dashboard')

    buffer = BytesIO()
    p = canvas.Canvas(buffer)

    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, "BARUA YA UTHIBITISHO WA KIKUNDI")
    p.drawString(100, 780, "Taasisi ya Ualimu Tanzania")

    p.setFont("Helvetica", 12)
    p.drawString(100, 750, f"Jina la Shule: {school.name}")
    p.drawString(100, 730, f"Wilaya: {school.district.name}")
    p.drawString(100, 710, f"Mkoa: {school.district.region.name}")
    p.drawString(100, 690, f"Idadi ya Wanafunzi Inayohitajika: {group_letter_quota}")
    p.drawString(100, 670, f"Wanafunzi Walioidhinishwa: {approved_students_count}")

    p.drawString(100, 640, "Orodha ya Wanafunzi Walioidhinishwa:")
    y_position = 620

    approved_applications = StudentApplication.objects.filter(
        school=school,
        status='approved'
    ).select_related('student').distinct()

    for idx, application in enumerate(approved_applications, 1):
        student_name = application.student.full_name
        subject_name = application.subject.name
        p.drawString(120, y_position, f"{idx}. {student_name} - {subject_name}")
        y_position -= 20
        if y_position < 100:
            p.showPage()
            p.setFont("Helvetica", 12)
            y_position = 780

    p.drawString(100, y_position - 40, "Barua hii inathibitisha kuwa shule imefikia idadi ya wanafunzi 5")
    p.drawString(100, y_position - 60, "wa kufanya mafunzo ya ualimu kwenye uwanja kama kikundi.")
    p.drawString(100, y_position - 80, f"Imetolewa tarehe: {timezone.now().strftime('%Y-%m-%d %H:%M')}")

    p.showPage()
    p.save()

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="barua_kikundi_{school.name}.pdf"'
    messages.success(request, "Barua ya kikundi imepakuliwa kikamilifu!")
    return response


@staff_member_required
def send_test_email_api(request):
    """Send a test email to verify SMTP is working — staff only."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    recipient = request.POST.get('email') or request.user.email
    if not recipient:
        return JsonResponse({'error': 'Hakuna email iliyotolewa'}, status=400)

    try:
        send_mail(
            subject='✅ IMS Test Email — SMTP Inafanya Kazi',
            message=(
                f'Hii ni email ya majaribio kutoka IMS.\n\n'
                f'Kama unaona ujumbe huu maana yake SMTP inafanya kazi vizuri.\n\n'
                f'Imetumwa kwa: {recipient}\n'
                f'Kutoka: {settings.DEFAULT_FROM_EMAIL}\n'
                f'Backend: {settings.EMAIL_BACKEND}\n'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=f"""
<div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;padding:24px;
     border:2px solid #0A2B5E;border-radius:12px;">
  <h2 style="color:#0A2B5E;margin:0 0 16px;">✅ IMS Test Email</h2>
  <p>Email hii ni ya majaribio ya mfumo wa IMS.</p>
  <p>Kama unaipokea maana yake <strong>SMTP inafanya kazi vizuri!</strong></p>
  <hr style="border-color:#C8900A;">
  <small style="color:#666;">
    Imetumwa kwa: {recipient}<br>
    Backend: {settings.EMAIL_BACKEND}
  </small>
</div>""",
            fail_silently=False,
        )
        return JsonResponse({
            'success': True,
            'message': f'Email imetumwa kwa {recipient}. Angalia inbox (na Spam folder).',
            'backend': settings.EMAIL_BACKEND,
            'from': settings.DEFAULT_FROM_EMAIL,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'backend': settings.EMAIL_BACKEND,
            'from': settings.DEFAULT_FROM_EMAIL,
        }, status=500)
