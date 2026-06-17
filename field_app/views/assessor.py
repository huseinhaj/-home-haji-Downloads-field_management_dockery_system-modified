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
from .decorators import board_login_required, assessor_login_required
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


def assessor_login(request):
    """Simple and fixed assessor login"""

    print(f"\n🔐 ASSESSOR LOGIN STARTED - Method: {request.method}")

    # Already logged in as assessor? Go to dashboard
    if request.user.is_authenticated:
        try:
            assessor = Assessor.objects.get(user=request.user)
            print(f"✅ Already logged in as: {assessor.full_name}")
            return redirect('assessor_dashboard')
        except Assessor.DoesNotExist:
            pass

    # Handle POST request (login attempt)
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        print(f"📧 Login attempt: {email}")

        if not email or not password:
            messages.error(request, 'Please enter both email and password.')
            return render(request, 'field_app/assessor_login.html')

        # Authenticate the user
        user = authenticate(request, username=email, password=password)

        if user is None:
            # Try finding user by email
            try:
                user = User.objects.get(email__iexact=email)
                if user.check_password(password):
                    print(f"✅ Password check passed")
                    messages.error(request, 'Invalid email or password.')
                    return render(request, 'field_app/assessor_login.html')
            except User.DoesNotExist:
                messages.error(request, 'No account found with this email.')
                return render(request, 'field_app/assessor_login.html')

        # Check if user is an assessor
        try:
            assessor = Assessor.objects.get(user=user)
            print(f"✅ User is assessor: {assessor.full_name}")

            # Verify email matches
            if assessor.email.lower() != email.lower():
                messages.error(request,
                    f'Email mismatch. This assessor is registered with: {assessor.email}'
                )
                return render(request, 'field_app/assessor_login.html')

            # LOGIN SUCCESSFUL
            login(request, user, backend='field_app.backends.EmailBackend')
            print(f"✅ Login successful, redirecting to dashboard")

            messages.success(request, f'Welcome Assessor {assessor.full_name}!')
            return redirect('assessor_dashboard')

        except Assessor.DoesNotExist:
            # Check if assessor exists with this email but different user
            try:
                assessor = Assessor.objects.get(email__iexact=email)
                print(f"⚠️ Assessor found but not linked: {assessor.email}")

                # Link assessor to this user
                assessor.user = user
                assessor.save()

                # Login
                login(request, user, backend='field_app.backends.EmailBackend')

                messages.success(request, f'Welcome Assessor {assessor.full_name}!')
                return redirect('assessor_dashboard')

            except Assessor.DoesNotExist:
                messages.error(request,
                    'This email is not registered as an assessor. '
                    'Please use the student login page.'
                )
                return render(request, 'field_app/assessor_login.html')  # 🔥 ADDED THIS RETURN

    # GET request or failed login
    return render(request, 'field_app/assessor_login.html')


@assessor_login_required
def assessor_dashboard(request):
    """Dashboard ya Assessor - FIXED FIELD ERROR"""
    try:
        assessor = Assessor.objects.get(user=request.user)
    except Assessor.DoesNotExist:
        messages.error(request, "You are not registered as an assessor.")
        return redirect('dashboard')

    current_year = get_current_academic_year()

    print(f"\n🔍 ASSESSOR DASHBOARD: {assessor.full_name}")

    # Get assignments for this assessor
    school_assignments = SchoolAssessment.objects.filter(
        assessor=assessor,
        academic_year=current_year
    ).select_related('school', 'school__district', 'school__district__region')

    schools_data = []
    total_students_all_schools = 0

    for assignment in school_assignments:
        school = assignment.school

        print(f"\n🏫 Processing school: {school.name}")

        # 🔴 FIX 1: Get students via TWO separate queries
        from django.db.models import Q

        # Method 1: Students who selected this school
        students_via_selected = StudentTeacher.objects.filter(
            selected_school=school
        )

        # Method 2: Students with approved applications for this school
        approved_app_student_ids = StudentApplication.objects.filter(
            school=school,
            status='approved'
        ).values_list('student_id', flat=True).distinct()

        students_via_applications = StudentTeacher.objects.filter(
            id__in=approved_app_student_ids
        )

        # Combine both querysets
        student_ids = set()

        for student in students_via_selected:
            student_ids.add(student.id)

        for student in students_via_applications:
            student_ids.add(student.id)

        # Get all unique students
        all_students = StudentTeacher.objects.filter(
            id__in=list(student_ids)
        ).select_related('user')

        print(f"   Found {len(student_ids)} unique students")

        # Get student assessments for this school by this assessor
        student_assessments = StudentAssessment.objects.filter(
            assessor=assessor,
            school=school,
            academic_year=current_year
        ).select_related('student')

        # Create assessment map
        assessment_map = {}
        for sa in student_assessments:
            if sa.student:
                assessment_map[sa.student.id] = sa

        # Prepare detailed student data
        students_data = []
        for student in all_students:
            # Get student's approved applications for this school
            approved_apps = StudentApplication.objects.filter(
                student=student,
                school=school,
                status='approved'
            ).select_related('subject')

            approved_subjects = [app.subject.name for app in approved_apps]

            # Check if student selected this school
            has_selected_school = (student.selected_school == school)

            # Get assessment
            assessment = assessment_map.get(student.id)

            # Logbook stats for this student
            logbook_entries = LogbookEntry.objects.filter(student=student)
            logbook_total = logbook_entries.count()
            logbook_verified = logbook_entries.filter(is_location_verified=True).count()
            logbook_this_week = logbook_entries.filter(
                date__gte=timezone.now().date() - timedelta(days=7)
            ).count()
            logbook_last = logbook_entries.order_by('-date').first()

            students_data.append({
                'student': student,
                'has_selected_school': has_selected_school,
                'has_approved_application': approved_apps.exists(),
                'approved_subjects': approved_subjects,
                'approved_apps_count': approved_apps.count(),
                'assessment': assessment,
                'is_completed': assessment.score is not None if assessment else False,
                'score': assessment.score if assessment else None,
                'email': student.user.email if student.user else "No email",
                'phone': student.phone_number or "Not provided",
                'logbook_total': logbook_total,
                'logbook_verified': logbook_verified,
                'logbook_this_week': logbook_this_week,
                'logbook_last_date': logbook_last.date if logbook_last else None,
            })

            # Debug print
            if has_selected_school or approved_apps.exists():
                print(f"   👤 {student.full_name}:")
                if has_selected_school:
                    print(f"      ✅ Selected this school")
                if approved_apps.exists():
                    print(f"      ✅ Approved subjects: {', '.join(approved_subjects)}")

        students_count = len(students_data)
        total_students_all_schools += students_count

        # Assessment counts
        completed_student_assessments = len([s for s in students_data if s['is_completed']])
        pending_student_assessments = students_count - completed_student_assessments

        # Get other assessors
        other_assessors = []
        if current_year:
            other_assignments = SchoolAssessment.objects.filter(
                school=school,
                academic_year=current_year
            ).exclude(assessor=assessor).select_related('assessor')

            for other_assignment in other_assignments:
                other_assessors.append({
                    'name': other_assignment.assessor.full_name,
                    'email': other_assignment.assessor.email,
                })

        schools_data.append({
            'school': school,
            'assignment': assignment,
            'students': students_data,
            'students_count': students_count,
            'other_assessors': other_assessors,
            'completed_student_assessments': completed_student_assessments,
            'pending_student_assessments': pending_student_assessments,
            'academic_year': current_year.year if current_year else "Not Set",
        })

    total_completed = sum(d['completed_student_assessments'] for d in schools_data)

    return render(request, 'field_app/assessor_dashboard.html', {
        'assessor': assessor,
        'schools_data': schools_data,
        'total_schools': school_assignments.count(),
        'total_students': total_students_all_schools,
        'total_completed': total_completed,
        'current_year': current_year,
    })


def assessor_password_reset(request):
    """Reset password for assessor - sends new temporary password via email"""

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()

        if not email:
            messages.error(request, 'Please enter your email address.')
            return redirect('assessor_login')

        try:
            assessor = Assessor.objects.get(email__iexact=email)
        except Assessor.DoesNotExist:
            messages.error(request, f'Hakuna assessor aliyepatikana na email: {email}')
            return redirect('assessor_login')

        # If assessor has no user account, create one automatically
        if not assessor.user:
            try:
                User = get_user_model()
                existing_user = User.objects.filter(email__iexact=email).first()
                if existing_user:
                    assessor.user = existing_user
                else:
                    new_user = User.objects.create_user(
                        email=email,
                        password=None,
                        is_staff=False,
                        is_active=True,
                    )
                    assessor.user = new_user
                assessor.save()
            except Exception as create_err:
                messages.error(request,
                    f'Imeshindwa kuunda akaunti: {str(create_err)[:100]}. '
                    f'Wasiliana na msimamizi.'
                )
                return redirect('assessor_login')

        # Generate new temp password and save it
        temp_password = generate_random_password()
        assessor.user.set_password(temp_password)
        assessor.user.save()

        # Send email
        login_url = request.build_absolute_uri(reverse('assessor_login'))
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Password Reset - Field Placement System</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 500px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #2c3e50; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .password {{ background: #fef9e6; padding: 15px; border-left: 4px solid #f59e0b; margin: 20px 0; }}
                .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #666; }}
                code {{ background: #f0f0f0; padding: 4px 8px; border-radius: 4px; font-size: 16px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🔐 Password Reset</h2>
                    <p>Mfumo wa Ufuatiliaji wa Walimu Wanafunzi (IMS)</p>
                </div>
                <div class="content">
                    <p>Dear <strong>{assessor.full_name}</strong>,</p>
                    <p>You requested to reset your password. Here are your new login credentials:</p>
                    <div class="password">
                        <p><strong>📧 Email:</strong> {assessor.email}</p>
                        <p><strong>🔑 New Password:</strong> <code>{temp_password}</code></p>
                    </div>
                    <p><strong>⚠️ Important:</strong> Please change this password immediately after logging in.</p>
                    <p style="margin-top: 20px;">
                        <a href="{login_url}" style="background: #2c3e50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                            Login to Dashboard
                        </a>
                    </p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply.</p>
                    <p>© {timezone.now().year} Wizara ya Elimu, Sayansi na Teknolojia — IMS v2.1.0</p>
                </div>
            </div>
        </body>
        </html>
        """
        text_content = (
            f"PASSWORD RESET - Field Placement System\n"
            f"{'='*50}\n\n"
            f"Dear {assessor.full_name},\n\n"
            f"Your new login credentials:\n"
            f"Email: {assessor.email}\n"
            f"Password: {temp_password}\n\n"
            f"Login URL: {login_url}\n\n"
            f"IMPORTANT: Change this password immediately after logging in.\n"
        )

        try:
            send_mail(
                subject='🔐 Badilisha Nywila - Field Placement System',
                message=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[assessor.email],
                html_message=html_content,
                fail_silently=False,
            )
            messages.success(request,
                f'✅ Nywila mpya ya muda imetumwa kwa {assessor.email}. '
                f'Angalia inbox na spam folder yako.'
            )
        except Exception as email_error:
            # Email failed — password is saved, show it on screen so admin can relay it.
            import logging
            logging.getLogger('django').error(
                f'Assessor password reset email failed for {assessor.email}: {email_error}'
            )
            messages.warning(request,
                f'Nywila mpya imewekwa lakini email imeshindwa kutumwa kwa {assessor.email}. '
                f'Nywila mpya ya muda ni: {temp_password} — toa kwa mkono kwa {assessor.full_name}. '
                f'(Hitilafu: {str(email_error)[:100]})'
            )

        return redirect('assessor_login')

    # GET request - redirect to login page
    return redirect('assessor_login')


def assessor_password_reset_done(request):
    """Show success message after password reset"""
    messages.success(request,
        'Password reset email has been sent. Please check your inbox.'
    )
    return redirect('assessor_login')


@assessor_login_required
def assessor_student_detail(request, school_id):
    """Assessor aone details za wanafunzi wa shule maalum"""
    try:
        assessor = Assessor.objects.get(user=request.user)
    except Assessor.DoesNotExist:
        messages.error(request, "You are not registered as an assessor.")
        return redirect('dashboard')

    school = get_object_or_404(School, id=school_id)

    # Check assignment
    school_assignment = SchoolAssessment.objects.filter(
        assessor=assessor,
        school=school
    ).first()

    if not school_assignment:
        messages.error(request, "You are not assigned to this school.")
        return redirect('assessor_dashboard')

    # ========== FIX: GET STUDENTS FROM BOTH SOURCES ==========

    # Method 1: Students who selected this school directly
    students_selected = StudentTeacher.objects.filter(
        selected_school=school,
        approval_status='approved'
    )

    # Method 2: Students with approved applications for this school
    approved_app_student_ids = StudentApplication.objects.filter(
        school=school,
        status='approved'
    ).values_list('student_id', flat=True).distinct()

    students_with_apps = StudentTeacher.objects.filter(
        id__in=approved_app_student_ids
    )

    # Combine both querysets
    student_ids = set()
    for student in students_selected:
        student_ids.add(student.id)
    for student in students_with_apps:
        student_ids.add(student.id)

    # Get all unique students
    students = StudentTeacher.objects.filter(
        id__in=list(student_ids)
    ).select_related('user')

    print(f"📊 Found {students.count()} students for school {school.name}")
    for student in students:
        print(f"   - {student.full_name}")

    # Get assessments
    student_assessments = StudentAssessment.objects.filter(
        assessor=assessor,
        school=school
    ).select_related('student')

    # Get other assessors
    other_assessors_assessments = SchoolAssessment.objects.filter(
        school=school
    ).exclude(assessor=assessor).select_related('assessor')

    other_assessors = [oa.assessor for oa in other_assessors_assessments]

    return render(request, 'field_app/assessor_student_detail.html', {
        'assessor': assessor,
        'school': school,
        'students': students,  # ← SASA ITAKUWA NA DATA
        'student_assessments': student_assessments,
        'school_assignment': school_assignment,
        'other_assessors': other_assessors,
    })


@assessor_login_required
def assessor_student_assessment(request, student_id):
    """Assessor assess specific student"""
    try:
        assessor = Assessor.objects.get(user=request.user)
    except Assessor.DoesNotExist:
        messages.error(request, "You are not registered as an assessor.")
        return redirect('dashboard')

    student = get_object_or_404(StudentTeacher, id=student_id)

    school_assignment = SchoolAssessment.objects.filter(
        assessor=assessor,
        school=student.selected_school
    ).first()

    if not school_assignment:
        messages.error(request, "You are not assigned to assess this student.")
        return redirect('assessor_dashboard')

    student_assessment, created = StudentAssessment.objects.get_or_create(
        assessor=assessor,
        student=student,
        school=student.selected_school,
        defaults={
            'assessment_date': timezone.now().date()
        }
    )

    if request.method == 'POST':
        student_assessment.attendance_score = request.POST.get('attendance_score')
        student_assessment.participation_score = request.POST.get('participation_score')
        student_assessment.teaching_skills_score = request.POST.get('teaching_skills_score')
        student_assessment.lesson_planning_score = request.POST.get('lesson_planning_score')
        student_assessment.classroom_management_score = request.POST.get('classroom_management_score')
        student_assessment.overall_score = request.POST.get('overall_score')
        student_assessment.comments = request.POST.get('comments')
        student_assessment.is_completed = True
        student_assessment.completed_date = timezone.now()
        student_assessment.save()

        messages.success(request, f"Assessment for {student.full_name} submitted successfully!")
        return redirect('assessor_student_detail', school_id=student.selected_school.id)

    logbook_entries = LogbookEntry.objects.filter(
        student=student
    ).order_by('-date')[:20]

    approved_subjects = student.subjects.all()

    return render(request, 'field_app/assessor_student_assessment.html', {
        'assessor': assessor,
        'student': student,
        'student_assessment': student_assessment,
        'logbook_entries': logbook_entries,
        'approved_subjects': approved_subjects,
        'school_assignment': school_assignment,
    })


@assessor_login_required
def assessor_add_logbook_remark(request, entry_id):
    """Assessor anaandika maoni kwenye logbook maalum ya mwanafunzi."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    try:
        assessor = Assessor.objects.get(user=request.user)
    except Assessor.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Hautambuliki kama msimamizi.'}, status=403)

    entry = get_object_or_404(LogbookEntry, id=entry_id)
    # Verify assessor is assigned to this student's school
    if not SchoolAssessment.objects.filter(assessor=assessor, school=entry.student.selected_school).exists():
        return JsonResponse({'ok': False, 'error': 'Huna ruhusa ya kuandika maoni hapa.'}, status=403)

    remarks = request.POST.get('remarks', '').strip()
    if not remarks:
        return JsonResponse({'ok': False, 'error': 'Maoni hayawezi kuwa matupu.'}, status=400)

    entry.supervisor_remarks = remarks
    entry.save(update_fields=['supervisor_remarks'])
    return JsonResponse({'ok': True, 'message': 'Maoni yamehifadhiwa.'})


@staff_member_required
def assessor_list(request):
    """List all assessors with their credentials"""
    assessors = Assessor.objects.filter(is_active=True).select_related('user')

    for assessor in assessors:
        assessor.assigned_schools = SchoolAssessment.objects.filter(
            assessor=assessor
        ).select_related('school')

        assessor.schools_count = assessor.assigned_schools.count()

        if assessor.user:
            assessor.has_account = True
            assessor.login_email = assessor.user.email
            assessor.password_info = "Use existing password"
            assessor.has_account = False
            assessor.login_email = assessor.email or "No email"
            assessor.password_info = "No account created yet"

    return render(request, 'field_app/assessor_list.html', {
        'assessors': assessors
    })


@staff_member_required
@csrf_exempt
def assessor_details_api(request, assessor_id):
    """API endpoint for assessor details"""
    if request.method == 'GET':
        assessor = get_object_or_404(Assessor, id=assessor_id)

        school_assignments = SchoolAssessment.objects.filter(assessor=assessor)
        schools_data = []
        for assignment in school_assignments:
            schools_data.append({
                'name': assignment.school.name,
                'district': assignment.school.district.name,
                'level': assignment.school.level,
                'assessment_date': assignment.assessment_date.strftime('%Y-%m-%d'),
            })

        data = {
            'id': assessor.id,
            'full_name': assessor.full_name,
            'email': assessor.email,
            'phone_number': assessor.phone_number,
            'is_active': assessor.is_active,
            'has_account': bool(assessor.user),
            'schools_count': len(schools_data),
            'schools': schools_data,
        }

        return JsonResponse(data)
    return JsonResponse({'error': 'Invalid method'}, status=405)
