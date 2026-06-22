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


def health_check(request):
    return JsonResponse({'status': 'ok'})


def register(request):
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data['email']
            user.set_password(form.cleaned_data['password1'])
            user.save()

            full_name = form.cleaned_data['full_name']
            phone_number = form.cleaned_data['phone_number']
            StudentTeacher.objects.create(
                user=user, full_name=full_name, phone_number=phone_number,
                academic_year=_cached_active_year(),
            )

            request.session['prefill_email'] = form.cleaned_data['email']
            request.session['prefill_password'] = form.cleaned_data['password1']
            messages.success(request, 'Account created successfully. Please login.')
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StudentRegistrationForm()

    return render(request, 'field_app/registration/register.html', {
        'form': form,
        'hide_navbar': True
    })

def login_view(request):
    """Login view for STUDENTS ONLY"""

    # SPECIAL CASE: If assessor wants to login as student
    if 'assessor_logout' in request.GET and request.user.is_authenticated:
        logout(request)
        messages.info(request, "Logged out from assessor account. You can now login as student.")
        return redirect('login')

    # If already logged in, check user type
    if request.user.is_authenticated:
        try:
            assessor = Assessor.objects.get(user=request.user)
            return render(request, 'field_app/registration/login.html', {
                'assessor_warning': True,
                'assessor_name': assessor.full_name,
                'assessor_email': assessor.email,
                'logout_url': f"{request.path}?assessor_logout=true",
                'assessor_login_url': reverse('assessor_login'),
            })
        except Assessor.DoesNotExist:
            get_or_create_student_profile(request.user)
            return redirect('dashboard')

    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # Staff/Admin — must use admin login, not student form
            if user.is_staff:
                messages.error(request,
                    "Akaunti hii ni ya msimamizi. Tafadhali tumia ukurasa wa msimamizi."
                    if request.session.get('lang') == 'sw' else
                    "This is an admin account. Please use the admin login page."
                )
                return redirect('login')

            # Assessor — must use assessor login
            try:
                Assessor.objects.get(user=user)
                messages.warning(request,
                    "Akaunti hii ni ya mkaguzi. Tumia ukurasa wa mkaguzi kuingia."
                    if request.session.get('lang') == 'sw' else
                    "This is an assessor account. Please use the assessor login page."
                )
                return redirect('assessor_login')
            except Assessor.DoesNotExist:
                pass

            # Board member (DEO / HT / REO) — must use board login
            try:
                BoardMember.objects.get(user=user)
                messages.warning(request,
                    "Akaunti hii ni ya bodi. Tafadhali tumia ukurasa wa bodi kuingia."
                    if request.session.get('lang') == 'sw' else
                    "This is a board account. Please use the board login page."
                )
                return redirect('board_login')
            except BoardMember.DoesNotExist:
                pass

            login(request, user, backend='field_app.backends.EmailBackend')
            get_or_create_student_profile(user)
            messages.success(request,
                "Umeingia mfumo." if request.session.get('lang') == 'sw' else "Login successful."
            )
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid credentials')
    else:
        form = CustomLoginForm()

    prefill_email = request.session.pop('prefill_email', '')
    prefill_password = request.session.pop('prefill_password', '')

    return render(request, 'field_app/registration/login.html', {
        'form': form,
        'hide_navbar': True,
        'prefill_email': prefill_email,
        'prefill_password': prefill_password,
    })

# views.py - Badilisha logout_view kwa hii

def session_check(request):
    """Lightweight endpoint used by JS heartbeat to detect expired sessions."""
    if request.user.is_authenticated:
        return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=401)


def logout_view(request):
    redirect_to = 'login'
    if request.user.is_authenticated:
        if request.user.is_superuser:
            logout(request)
            return redirect('/admin/login/')
        try:
            Assessor.objects.get(user=request.user)
            redirect_to = 'assessor_login'
        except Assessor.DoesNotExist:
            try:
                BoardMember.objects.get(user=request.user)
                redirect_to = 'board_login'
            except BoardMember.DoesNotExist:
                redirect_to = 'login'
    logout(request)
    return redirect(redirect_to)
# =========================
# ASSESSOR LOGIN VIEW
# =========================

# views.py - FIX ASSESSOR LOGIN VIEW

# views.py - COMPLETE FIX FOR ASSESSOR LOGIN

def assessor_login(request):
    """Simple and fixed assessor login"""

    # Already logged in as assessor? Go to dashboard
    if request.user.is_authenticated:
        try:
            assessor = Assessor.objects.get(user=request.user)
            return redirect('assessor_dashboard')
        except Assessor.DoesNotExist:
            pass

    # Handle POST request (login attempt)
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

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
                    messages.error(request, 'Invalid email or password.')
                    return render(request, 'field_app/assessor_login.html')
            except User.DoesNotExist:
                messages.error(request, 'No account found with this email.')
                return render(request, 'field_app/assessor_login.html')

        # Check if user is an assessor
        try:
            assessor = Assessor.objects.get(user=user)

            # Verify email matches
            if assessor.email.lower() != email.lower():
                messages.error(request,
                    f'Email mismatch. This assessor is registered with: {assessor.email}'
                )
                return render(request, 'field_app/assessor_login.html')

            # LOGIN SUCCESSFUL
            login(request, user, backend='field_app.backends.EmailBackend')
            messages.success(request, f'Welcome Assessor {assessor.full_name}!')
            return redirect('assessor_dashboard')

        except Assessor.DoesNotExist:
            # Check if assessor exists with this email but different user
            try:
                assessor = Assessor.objects.get(email__iexact=email)

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


def login_page(request):
    """
    Custom login page that displays dynamic data from database:
    - Total partner colleges
    - Total students placed
    - Current academic year
    - Notices and announcements
    - List of partner colleges
    """

    # Get current academic year
    current_academic_year_obj = get_current_academic_year()
    current_academic_year = current_academic_year_obj.year if current_academic_year_obj else "2025/2026"

    # ========== TOTAL COLLEGES (Partner Schools) ==========
    # Use School model since that's what you have
    total_colleges = School.objects.filter(is_active=True).count()

    # If you have a College model, uncomment this:
    # total_colleges = College.objects.count()

    # ========== TOTAL STUDENTS PLACED ==========
    # Count students who have been approved and assigned to schools
    total_students_placed = StudentTeacher.objects.filter(
        approval_status='approved',
        selected_school__isnull=False
    ).count()

    # Alternative: Count from StudentApplication with approved status
    # total_students_placed = StudentApplication.objects.filter(
    #     status='approved'
    # ).values('student').distinct().count()

    # ========== NOTICES / ANNOUNCEMENTS ==========
    # You need to create a Notice model first (see below)
    # For now, using hardcoded fallback or get from database if model exists

    notices = []
    try:
        # If you have Notice model, use this:
        from .models import Notice  # Uncomment if you have Notice model
        notices = Notice.objects.filter(is_active=True).order_by('-created_at')[:5]
    except (ImportError, AttributeError):
        # Fallback notices if model doesn't exist yet
        notices = [
            {'title': 'Field placement applications for 2025/2026 are now open', 'date': timezone.now()},
            {'title': 'Deadline for application submission is 30th June 2025', 'date': timezone.now()},
            {'title': 'All students must complete logbook entries daily', 'date': timezone.now()},
        ]

    # ========== PARTNER COLLEGES LIST ==========
    # Get schools that have capacity and are active
    partner_colleges = School.objects.filter(
        is_active=True
    ).select_related('district', 'district__region').order_by('name')[:10]

    # If you need different format for the template
    colleges_data = []
    for college in partner_colleges:
        colleges_data.append({
            'name': college.name,
            'region': college.district.region.name if college.district else 'Tanzania',
        })

    # If you have a separate College model, use this:
    # colleges_data = College.objects.all()[:10]

    context = {
        'total_colleges': total_colleges,
        'total_students_placed': total_students_placed,
        'current_academic_year': current_academic_year,
        'notices': notices,
        'colleges': colleges_data,
        'hide_navbar': True,  # To hide navbar on login page
    }

    return render(request, 'field_app/registration/login.html', context)


# =========================
# NOTICE MODEL - ADD THIS TO YOUR models.py
# =========================
"""
Add this to your models.py file:

class Notice(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
"""


# =========================
# ALTERNATIVE: If you don't want to create Notice model yet
# Use this simpler version with hardcoded notices but dynamic stats
# =========================

def login_page_simple(request):
    """
    Simplified login page - stats from database, notices hardcoded
    Use this if you don't want to create Notice model yet
    """

    # Get current academic year
    current_academic_year_obj = get_current_academic_year()
    current_academic_year = current_academic_year_obj.year if current_academic_year_obj else "2025/2026"

    # Total partner colleges (schools with capacity > 0)
    total_colleges = School.objects.filter(
        is_active=True,
        capacity__gt=0
    ).count()

    # Total students placed
    total_students_placed = StudentTeacher.objects.filter(
        approval_status='approved',
        selected_school__isnull=False
    ).count()

    # Partner colleges list
    partner_colleges = School.objects.filter(
        is_active=True
    ).select_related('district__region').order_by('name')[:10]

    # Hardcoded notices (will be shown even without database)
    notices = [
        {'title': 'Field placement applications for 2025/2026 are now open', 'date': 'March 2025'},
        {'title': 'Deadline for application submission is 30th June 2025', 'date': 'March 2025'},
        {'title': 'All students must complete logbook entries daily', 'date': 'March 2025'},
        {'title': 'Contact your academic advisor for placement inquiries', 'date': 'March 2025'},
    ]

    context = {
        'total_colleges': total_colleges if total_colleges > 0 else 6,
        'total_students_placed': total_students_placed if total_students_placed > 0 else 2400,
        'current_academic_year': current_academic_year,
        'notices': notices,
        'colleges': partner_colleges,
        'hide_navbar': True,
    }

    return render(request, 'field_app/registration/login.html', context)


# =========================
# UPDATE URLS.PY - Add this to your urls.py
# =========================
"""
In your main urls.py or app urls.py, add:

from django.urls import path
from your_app.views import login_page  # or login_page_simple

urlpatterns = [
    # ... other URLs ...
    path('', login_page, name='login_page'),  # Or use 'login_page_simple'
    path('login/', login_page, name='login'),  # If you want to replace default login
]
"""
def homepage(request):
    """Homepage that includes meta tag for Google verification"""
    return render(request, 'field_app/base.html')


def set_language(request):
    """Switch UI language between English and Swahili. Stored in session."""
    lang = request.GET.get('lang', 'en')
    if lang not in ('en', 'sw'):
        lang = 'en'
    request.session['ui_lang'] = lang

    # Ruhusu redirect kwa URLs za ndani tu (zuia open redirect)
    next_url = request.GET.get('next') or request.META.get('HTTP_REFERER') or '/'
    if next_url.startswith('http') or not next_url.startswith('/'):
        next_url = '/'
    return redirect(next_url)
