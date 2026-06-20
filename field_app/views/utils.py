"""
Shared utilities, cache helpers, email templates, and helper functions
used across multiple view modules.
"""
import csv
import io
import json
import os
import re
import secrets
import string
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

# =========================
# CACHE HELPERS
# =========================

def _cached_active_year():
    """Cache the active AcademicYear for 5 minutes."""
    key = 'active_academic_year'
    yr = cache.get(key)
    if yr is None:
        yr = AcademicYear.objects.filter(is_active=True).first()
        cache.set(key, yr, 300)
    return yr

def _cached_subjects(student):
    """Return all subjects grouped by level. Always show all so teacher can record any subject."""
    key = 'all_subjects_list'
    subs = cache.get(key)
    if subs is None:
        subs = list(Subject.objects.order_by('level', 'name'))
        cache.set(key, subs, 600)
    return subs


def _cached_today_logbook(student, school, today):
    """Return today's logbook entry if it exists, else None. Does NOT auto-create."""
    key = f'logbook_today_{student.id}_{today}'
    cached = cache.get(key, '__miss__')
    if cached == '__miss__':
        entry = LogbookEntry.objects.filter(student=student, date=today).first()
        cache.set(key, entry, 30)
        return entry
    return cached


def _invalidate_today_logbook(student, today):
    cache.delete(f'logbook_today_{student.id}_{today}')


def _cached_schools_by_district(district_id):
    """Cache schools za district fulani kwa dakika 10 - inatumiwa mara nyingi kwenye ombi/DEO views."""
    key = f'schools_district_{district_id}'
    schools = cache.get(key)
    if schools is None:
        schools = list(
            School.objects.filter(district_id=district_id)
            .select_related('district__region')
            .order_by('name')
        )
        cache.set(key, schools, 600)
    return schools


def _cached_all_districts():
    """Cache districts zote kwa dakika 15 - data haitabadilika mara kwa mara."""
    key = 'all_districts_list'
    districts = cache.get(key)
    if districts is None:
        districts = list(District.objects.select_related('region').order_by('name'))
        cache.set(key, districts, 900)
    return districts


def _cached_all_regions():
    """Cache regions zote kwa dakika 30."""
    key = 'all_regions_list'
    regions = cache.get(key)
    if regions is None:
        regions = list(Region.objects.order_by('name'))
        cache.set(key, regions, 1800)
    return regions

# =========================
# HELPER FUNCTIONS
# =========================
# =========================
# EMAIL TEMPLATES - Add this at the top of views.py
# =========================

def get_assessor_email_template(assessor, school, temp_password, is_new_account, assignments_count, login_url):
    """Generate beautiful HTML email for assessor - Tanzania Teacher Colleges"""

    if is_new_account:
        credential_html = f"""
        <div style="background-color: #fef9e6; border-left: 4px solid #f59e0b; padding: 20px; margin: 20px 0; border-radius: 8px;">
            <h3 style="margin-top: 0; color: #d97706;">🆕 AKAUNTI MPYA YA ASSESSOR</h3>
            <p style="margin: 10px 0;"><strong>📧 Email:</strong> {assessor.email}</p>
            <p style="margin: 10px 0;"><strong>🔑 Nywila ya Muda:</strong> <code style="background-color: #fff3cd; padding: 4px 8px; border-radius: 4px; font-size: 16px;">{temp_password}</code></p>
            <p style="margin: 10px 0; color: #856404;">⚠️ Badilisha nywila yako mara tu baada ya kuingia mara ya kwanza</p>
        </div>
        """
    else:
        credential_html = f"""
        <div style="background-color: #e3f2fd; border-left: 4px solid #2196f3; padding: 20px; margin: 20px 0; border-radius: 8px;">
            <h3 style="margin-top: 0; color: #1976d2;">🔄 MWAKA MPYA WA MASOMO {assessor.current_academic_year.year if assessor.current_academic_year else '2024/2025'}</h3>
            <p style="margin: 10px 0;"><strong>📧 Email:</strong> {assessor.email}</p>
            <p style="margin: 10px 0;"><strong>🔑 Nywila Mpya:</strong> <code style="background-color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 16px;">{temp_password}</code></p>
            <p style="margin: 10px 0; color: #d32f2f;">🔐 Nywila yako imebadilishwa kwa mwaka mpya wa masomo</p>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Tanzania Teacher Colleges - Field Placement</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                margin: 0;
                padding: 0;
                background-color: #f0f2f5;
            }}
            .container {{
                max-width: 600px;
                margin: 20px auto;
                background: white;
                border-radius: 16px;
                overflow: hidden;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }}
            .header {{
                background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
            }}
            .header p {{
                margin: 8px 0 0;
                opacity: 0.9;
            }}
            .content {{
                padding: 30px;
            }}
            .info-card {{
                background: #f8f9fa;
                border-radius: 12px;
                padding: 20px;
                margin: 20px 0;
                border: 1px solid #e9ecef;
            }}
            .button {{
                display: inline-block;
                background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
                color: white;
                text-decoration: none;
                padding: 12px 30px;
                border-radius: 8px;
                margin: 20px 0;
                font-weight: bold;
                text-align: center;
            }}
            .footer {{
                background: #f8f9fa;
                padding: 20px;
                text-align: center;
                font-size: 11px;
                color: #6c757d;
                border-top: 1px solid #e9ecef;
            }}
            @media only screen and (max-width: 600px) {{
                .content {{
                    padding: 20px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏫 Tanzania Teacher Colleges</h1>
                <p>Field Placement Management System</p>
            </div>

            <div class="content">
                <h2>Dear {assessor.full_name},</h2>

                <p>You have been assigned as a <strong>Field Placement Assessor</strong> for the academic year <strong>{assessor.current_academic_year.year if assessor.current_academic_year else '2024/2025'}</strong>.</p>

                <div class="info-card">
                    <h3 style="margin-top: 0;">📋 Assignment Details</h3>
                    <p><strong>🏫 College/School:</strong> {school.name}</p>
                    <p><strong>📍 District:</strong> {school.district.name}</p>
                    <p><strong>🗺️ Region:</strong> {school.district.region.name}</p>
                    <p><strong>📅 Assignment Date:</strong> {timezone.now().strftime('%d/%m/%Y')}</p>
                    <p><strong>👥 Student Teachers:</strong> {assignments_count}</p>
                </div>

                {credential_html}

                <div style="text-align: center;">
                    <a href="{login_url}" class="button" style="color: white; text-decoration: none;">
                        🔐 LOGIN TO YOUR DASHBOARD
                    </a>
                </div>

                <div class="info-card" style="background: #e7f3ff;">
                    <h3 style="margin-top: 0;">✅ After Login You Can:</h3>
                    <ul>
                        <li>📊 View assigned college/school details</li>
                        <li>👨‍🎓 See list of student teachers</li>
                        <li>📝 Track teaching practice logbooks</li>
                        <li>📋 Submit assessment reports</li>
                        <li>📈 Monitor student progress</li>
                    </ul>
                </div>

                <p style="margin-top: 30px;">Best regards,<br>
                <strong>Field Placement Coordination Unit</strong><br>
                Tanzania Teacher Colleges</p>

                <p style="font-size: 11px; color: #999; margin-top: 20px;">
                    📧 This is an automated message. Please do not reply.
                </p>
            </div>

            <div class="footer">
                <p>© {timezone.now().year} Tanzania Teacher Colleges - Field Placement System</p>
                <p>📍 Empowering Future Educators | Tanzania</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
TANZANIA TEACHER COLLEGES - FIELD PLACEMENT SYSTEM
{'='*60}

Dear {assessor.full_name},

You have been assigned as a Field Placement Assessor.

ASSIGNMENT DETAILS:
• College/School: {school.name}
• District: {school.district.name}
• Region: {school.district.region.name}
• Assignment Date: {timezone.now().strftime('%d/%m/%Y')}
• Student Teachers: {assignments_count}

{'='*60}
LOGIN CREDENTIALS:
Login URL: {login_url}
Email: {assessor.email}
Password: {temp_password if is_new_account else 'Use your existing password (reset for new year)'}

After login you can:
1. View assigned college/school details
2. See list of student teachers
3. Track teaching practice logbooks
4. Submit assessment reports

IMPORTANT:
• Change your password immediately after first login
• Contact your college coordinator if you face issues

Best regards,
Field Placement Coordination Unit
Tanzania Teacher Colleges
"""

    return html_content, text_content
# =========================
# UPDATED BULK ASSIGNMENT FUNCTION WITH HTML EMAIL
# =========================

def process_bulk_assignment_with_academic_year(assessor_ids, school_ids, assessment_date, request):
    """
    Create assignments ONLY - NO NEW CREDENTIALS UNLESS NEW ACADEMIC YEAR
    FIXED: No username field - uses email as USERNAME_FIELD
    WITH BEAUTIFUL HTML EMAIL
    """

    print(f"\n{'='*60}")
    print(f"📊 BULK ASSIGNMENT PROCESS STARTED")
    print(f"{'='*60}")
    print(f"👥 Assessors: {len(assessor_ids)}")
    print(f"🏫 Schools: {len(school_ids)}")
    print(f"📅 Assessment Date: {assessment_date}")

    # Get current academic year
    current_academic_year = get_current_academic_year()

    print(f"📚 Current Academic Year: {current_academic_year.year}")

    # Get all assessors and schools
    assessors = Assessor.objects.filter(id__in=assessor_ids).select_related('user')
    schools = School.objects.filter(id__in=school_ids).select_related('district', 'district__region')

    print(f"✅ Found {assessors.count()} assessors")
    print(f"✅ Found {schools.count()} schools")

    # Process each assessor
    email_results = []
    new_accounts_count = 0
    new_year_resets = 0
    assignments_created = 0
    email_sent_count = 0

    for assessor in assessors:
        print(f"\n{'─'*50}")
        print(f"👤 Processing: {assessor.full_name}")
        print(f"📧 Email: {assessor.email}")
        print(f"📚 Current Academic Year in DB: {assessor.current_academic_year}")

        # Validate email
        if not assessor.email or '@' not in assessor.email:
            email_results.append({
                'assessor': assessor.full_name,
                'status': '❌ Skipped - Invalid email',
                'email': assessor.email or 'No email',
                'credentials': 'N/A',
                'is_new': False,
                'is_new_year': False
            })
            print(f"❌ Invalid email - skipped")
            continue

        temp_password = None
        credential_action = ""
        is_new = False
        is_new_year = False
        send_email = False

        # ========== LOGIC 1: New assessor (no user account) ==========
        if not assessor.user:
            print("🆕 SCENARIO 1: New assessor - CREATING ACCOUNT")

            try:
                temp_password = generate_random_password()
                credential_action = "New account created"
                is_new = True
                new_accounts_count += 1
                send_email = True

                print(f"🔐 Generated password: {temp_password}")

                # Check if user with this email already exists
                existing_user = User.objects.filter(email=assessor.email).first()
                if existing_user:
                    user = existing_user
                    user.set_password(temp_password)
                    user.save()
                    print(f"♻️ Reusing existing user account: {assessor.email}")
                else:
                    user = User.objects.create_user(
                        email=assessor.email,
                        password=temp_password,
                        is_staff=False,
                        is_active=True
                    )
                    print(f"✅ Account created with email: {assessor.email}")

                assessor.user = user
                assessor.current_academic_year = current_academic_year
                assessor.save()

                print(f"✅ Academic year set: {current_academic_year.year}")

            except Exception as e:
                print(f"❌ ACCOUNT CREATION FAILED: {e}")
                email_results.append({
                    'assessor': assessor.full_name,
                    'status': f'❌ Account creation failed: {str(e)[:100]}',
                    'email': assessor.email,
                    'credentials': 'FAILED',
                    'is_new': False,
                    'is_new_year': False,
                    'error': str(e)[:100]
                })
                continue

        # ========== LOGIC 2: Existing assessor ==========
        elif assessor.user:
            print(f"🔄 SCENARIO 2: Existing assessor - CHECKING ACADEMIC YEAR")

            if not assessor.current_academic_year or assessor.current_academic_year != current_academic_year:
                print(f"📅 New academic year detected - NEEDS NEW CREDENTIALS")

                try:
                    temp_password = generate_random_password()
                    credential_action = f"New credentials for {current_academic_year.year}"
                    is_new_year = True
                    new_year_resets += 1
                    send_email = True

                    print(f"🔐 New password generated: {temp_password}")

                    assessor.user.set_password(temp_password)
                    assessor.user.save()

                    assessor.current_academic_year = current_academic_year
                    assessor.save()

                    print(f"✅ Password reset for new academic year: {current_academic_year.year}")

                except Exception as e:
                    print(f"❌ PASSWORD RESET FAILED: {e}")
                    email_results.append({
                        'assessor': assessor.full_name,
                        'status': f'❌ Password reset failed: {str(e)[:100]}',
                        'email': assessor.email,
                        'credentials': 'FAILED',
                        'is_new': False,
                        'is_new_year': False,
                        'error': str(e)[:100]
                    })
                    continue
                print(f"✅ Already has credentials for {current_academic_year.year}")
                credential_action = f"Already has credentials for {current_academic_year.year}"
                send_email = False

        # ========== CREATE ASSIGNMENTS FOR THIS ASSESSOR ==========
        assignments_for_this_assessor = 0
        skipped_assignments = 0

        for school in schools:
            try:
                print(f"\n📝 Processing school: {school.name} (ID: {school.id})")

                assignment, created = SchoolAssessment.objects.get_or_create(
                    assessor=assessor,
                    school=school,
                    academic_year=current_academic_year,
                    defaults={
                        'assigned_date': timezone.now().date(),
                        'assessment_date': assessment_date,
                        'is_completed': False,
                        'supervisor': request.user if request.user.is_authenticated else None
                    }
                )

                if created:
                    assignments_created += 1
                    assignments_for_this_assessor += 1
                    print(f"✅ NEW assignment created: {assessor.full_name} -> {school.name}")
                    print(f"   Assignment ID: {assignment.id}")

                    approved_students = StudentTeacher.objects.filter(
                        selected_school=school,
                        approval_status='approved'
                    )

                    student_assessments_created = 0
                    for student in approved_students:
                        sa, sa_created = StudentAssessment.objects.get_or_create(
                            assessor=assessor,
                            student=student,
                            school=school,
                            academic_year=current_academic_year,
                            defaults={
                                'assessment_date': assessment_date,
                                'status': 'pending'
                            }
                        )
                        if sa_created:
                            student_assessments_created += 1
                            print(f"   ✓ Created student assessment: {student.full_name}")

                    if student_assessments_created > 0:
                        print(f"   📊 Total student assessments: {student_assessments_created}")
                    else:
                        print(f"   ℹ️ No new student assessments needed")
                else:
                    skipped_assignments += 1
                    print(f"⚠️ SKIPPED: Assignment already exists for {assessor.full_name} -> {school.name}")

            except Exception as e:
                print(f"❌ Assignment failed for {school.name}: {e}")
                import traceback
                traceback.print_exc()
                continue

        print(f"\n📊 This assessor: {assignments_for_this_assessor} NEW assignments, {skipped_assignments} SKIPPED")

        # ========== SEND BEAUTIFUL HTML EMAIL ==========
        if send_email and temp_password:
            try:
                login_url = request.build_absolute_uri(reverse('assessor_login'))

                # Build schools list for email
                assigned_schools_list = ""
                school_counter = 0
                for school in schools:
                    if SchoolAssessment.objects.filter(
                        assessor=assessor,
                        school=school,
                        academic_year=current_academic_year
                    ).exists():
                        school_counter += 1
                        assigned_schools_list += f"{school_counter}. {school.name} ({school.district.name})\n"

                # Create beautiful HTML email
                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Field Placement Credentials</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 20px; background: #f0f2f5; }}
        .container {{ max-width: 550px; margin: 0 auto; background: white; border-radius: 20px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .header p {{ margin: 8px 0 0; opacity: 0.9; }}
        .content {{ padding: 30px; }}
        .greeting {{ font-size: 20px; font-weight: 600; margin-bottom: 20px; }}
        .credential-box {{ background: #fef9e6; border-left: 4px solid #f59e0b; padding: 20px; margin: 20px 0; border-radius: 12px; }}
        .schools-box {{ background: #e7f3ff; padding: 20px; margin: 20px 0; border-radius: 12px; }}
        .button {{ display: block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; padding: 14px 24px; border-radius: 50px; text-align: center; margin: 24px 0; font-weight: 600; }}
        .footer {{ background: #f8f9fa; padding: 20px; text-align: center; font-size: 11px; color: #888; border-top: 1px solid #e9ecef; }}
        code {{ background: #fff3cd; padding: 4px 8px; border-radius: 6px; font-size: 14px; }}
        @media only screen and (max-width: 480px) {{ .content {{ padding: 20px; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎓 Mfumo wa Ufuatiliaji wa Walimu Wanafunzi</h1>
            <p>Wizara ya Elimu, Sayansi na Teknolojia</p>
        </div>
        <div class="content">
            <div class="greeting">👋 Dear {assessor.full_name},</div>
            <p>You have been assigned as a <strong>Field Placement Assessor</strong> for <strong>{current_academic_year.year}</strong>.</p>
            <div class="credential-box">
                <h3 style="margin: 0 0 15px 0;">🔐 YOUR LOGIN CREDENTIALS</h3>
                <p><strong>📧 Email:</strong> {assessor.email}</p>
                <p><strong>🔑 Password:</strong> <code>{temp_password}</code></p>
                <p style="margin: 15px 0 0 0; color: #856404;">⚠️ Change password after first login</p>
            </div>
            <div class="schools-box">
                <h3 style="margin: 0 0 15px 0;">🏫 ASSIGNED SCHOOLS ({assignments_for_this_assessor})</h3>
                <pre style="background: white; padding: 12px; border-radius: 8px; margin: 0; font-size: 14px;">{assigned_schools_list if assigned_schools_list else 'No new assignments'}</pre>
            </div>
            <a href="{login_url}" class="button">🔐 LOGIN TO YOUR DASHBOARD</a>
            <div style="background: #fff3e0; padding: 15px; border-radius: 12px;">
                <h3 style="margin: 0 0 8px 0;">✅ After Login You Can:</h3>
                <ul style="margin: 0; padding-left: 20px;">
                    <li>View assigned school details</li>
                    <li>See list of students</li>
                    <li>Track logbook entries</li>
                    <li>Submit assessment reports</li>
                </ul>
            </div>
        </div>
        <div class="footer">
            <p>Wizara ya Elimu, Sayansi na Teknolojia — IMS v2.1.0</p>
            <p>📧 Ujumbe huu umetumwa kiotomatiki. Tafadhali usijibu.</p>
        </div>
    </div>
</body>
</html>"""

                # Plain text fallback
                text_content = f"""
FIELD PLACEMENT ASSESSOR CREDENTIALS & ASSIGNMENTS
{'='*60}

Dear {assessor.full_name},

{'NEW ACCOUNT CREATED FOR YOU' if is_new else f'NEW CREDENTIALS FOR {current_academic_year.year}'}

ACADEMIC YEAR: {current_academic_year.year}

YOUR LOGIN DETAILS:
• Login URL: {login_url}
• Email: {assessor.email}
• Password: {temp_password}

YOUR ASSIGNMENTS ({assignments_for_this_assessor} schools):
{assigned_schools_list if assigned_schools_list else 'No new assignments created'}

IMPORTANT INSTRUCTIONS:
1. This is a temporary password
2. Change it immediately after first login
3. Login to see your assigned schools and students

Best regards,
Kitengo cha Uratibu wa Mafunzo ya Uwanjani
Wizara ya Elimu, Sayansi na Teknolojia
"""

                subject = f'🎓 Field Placement Credentials & Assignments - {current_academic_year.year}'

                # Send HTML email
                send_mail(
                    subject=subject,
                    message=text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[assessor.email],
                    html_message=html_content,
                    fail_silently=False,
                )

                email_sent_count += 1
                print(f"✅ HTML email sent successfully to: {assessor.email}")

                email_results.append({
                    'assessor': assessor.full_name,
                    'email': assessor.email,
                    'status': f'✅ HTML Credentials sent & {assignments_for_this_assessor} new assignments',
                    'credentials': temp_password,
                    'assignments_count': assignments_for_this_assessor,
                    'credential_action': credential_action,
                    'academic_year': current_academic_year.year,
                    'is_new': is_new,
                    'is_new_year': is_new_year,
                })

            except Exception as e:
                print(f"❌ EMAIL SEND FAILED: {e}")
                import traceback
                traceback.print_exc()

                email_results.append({
                    'assessor': assessor.full_name,
                    'email': assessor.email,
                    'status': f'⚠️ Email failed - {assignments_for_this_assessor} assignments created',
                    'credentials': temp_password,
                    'assignments_count': assignments_for_this_assessor,
                    'is_new': is_new,
                    'is_new_year': is_new_year,
                    'error': str(e)[:100],
                    'note': 'MANUALLY SHARE THESE CREDENTIALS'
                })
            status_msg = f'ℹ️ {assignments_for_this_assessor} new assignments created'
            if not send_email:
                status_msg += ' (no email - already has credentials)'
            elif assignments_for_this_assessor == 0:
                status_msg = f'⚠️ No new assignments - all {len(schools)} schools already assigned'

            email_results.append({
                'assessor': assessor.full_name,
                'email': assessor.email,
                'status': status_msg,
                'credentials': temp_password if temp_password else 'Existing credentials',
                'assignments_count': assignments_for_this_assessor,
                'credential_action': credential_action,
                'is_new': False,
                'is_new_year': False,
            })

    # ========== FINAL STATISTICS ==========
    sent_count = email_sent_count
    failed_count = len([r for r in email_results if '❌' in r.get('status', '')])
    warning_count = len([r for r in email_results if '⚠️' in r.get('status', '')])

    print(f"\n{'='*60}")
    print(f"✅ BULK ASSIGNMENT PROCESS COMPLETE!")
    print(f"{'='*60}")
    print(f"📊 New Accounts Created: {new_accounts_count}")
    print(f"📊 Password Resets for New Year: {new_year_resets}")
    print(f"📧 Emails Sent Successfully: {sent_count}")
    print(f"⚠️  Emails Failed: {failed_count + warning_count}")
    print(f"📝 TOTAL NEW ASSIGNMENTS CREATED: {assignments_created}")
    print(f"📚 Academic Year: {current_academic_year.year}")
    print(f"{'='*60}")

    return {
        'total_assessors': len(assessor_ids),
        'total_schools': len(school_ids),
        'email_results': email_results,
        'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
        'academic_year': current_academic_year.year,
        'sent_count': sent_count,
        'failed_count': failed_count,
        'warning_count': warning_count,
        'new_accounts_count': new_accounts_count,
        'new_year_resets': new_year_resets,
        'assignments_created': assignments_created,
        'note': f'Successfully created {assignments_created} new assignments for {current_academic_year.year}'
    }
def get_or_create_student_profile(user):
    """Hakikisha kila user ana StudentTeacher profile. Cached for 2 minutes."""
    cache_key = f'student_profile_{user.pk}'
    profile = cache.get(cache_key)
    if profile is not None:
        return profile
    try:
        profile = StudentTeacher.objects.select_related(
            'selected_school', 'selected_school__district', 'selected_school__district__region'
        ).get(user=user)
    except StudentTeacher.DoesNotExist:
        email_username = user.email.split('@')[0] if user.email else user.username
        profile = StudentTeacher.objects.create(
            user=user,
            full_name=email_username,
            phone_number='Not provided'
        )
    cache.set(cache_key, profile, 120)
    return profile


def invalidate_student_cache(student):
    """Call after saving student profile changes."""
    cache.delete(f'student_profile_{student.user_id}')
    cache.delete(f'student_subjects_{student.id}')

def is_assessor(user):
    """Check if user is an assessor"""
    return hasattr(user, 'assessor')

def generate_random_password(length=12):
    """Generate random password for new assessors"""
    alphabet = string.ascii_letters + string.digits + "@#$%"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def get_current_academic_year():
    """Get current academic year - FIXED: Jan-Dec = current_year/current_year+1"""
    current_date = timezone.now().date()
    current_year = current_date.year

    # LOGIC MPYA: Mwaka mzima (Jan-Dec) ni academic year current_year/current_year+1
    # Kwa mfano: Jan 2026 hadi Dec 2026 = 2026/2027
    academic_year_string = f"{current_year}/{current_year + 1}"

    print(f"🔍 Academic year based on {current_date}: {academic_year_string}")

    # Get OR create academic year
    try:
        academic_year = AcademicYear.objects.get(year=academic_year_string)
        print(f"✅ Found existing academic year: {academic_year.year}")
    except AcademicYear.DoesNotExist:
        print(f"⚠️ Academic year not found, creating: {academic_year_string}")
        academic_year = AcademicYear.objects.create(
            year=academic_year_string,
            is_active=True
        )
        # Set only this one as active
        AcademicYear.objects.exclude(id=academic_year.id).update(is_active=False)
        print(f"✅ Created new academic year: {academic_year.year}")

    # Double-check it's active
    if not academic_year.is_active:
        academic_year.is_active = True
        academic_year.save()
        print(f"🔧 Activated academic year: {academic_year.year}")

    return academic_year


# =========================
# _build_individual_letter_pdf — used in student.py and admin_views.py
# =========================

def _build_individual_letter_pdf(student):
    """Returns bytes of the individual approval letter PDF for a student."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, HRFlowable)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

    approved_applications = StudentApplication.objects.filter(
        student=student, status='approved'
    ).select_related('subject', 'school')

    school = student.selected_school
    current_year = _cached_active_year()
    today = timezone.now().date()
    ref_no = f"IMS/{today.year}/{student.id:04d}"

    NAVY  = colors.HexColor('#0A2B5E')
    GOLD  = colors.HexColor('#C8900A')
    LIGHT = colors.HexColor('#EEF1F6')
    WHITE = colors.white
    BLACK = colors.black

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=3*cm, rightMargin=2.5*cm,
                            topMargin=2*cm, bottomMargin=2.5*cm)

    def S(name, **kw):
        d = dict(fontName='Helvetica', fontSize=10, leading=14,
                 textColor=BLACK, alignment=TA_LEFT)
        d.update(kw)
        return ParagraphStyle(name, **d)

    story = []
    story.append(Paragraph('JAMHURI YA MUUNGANO WA TANZANIA', S('cb', fontName='Helvetica-Bold', alignment=TA_CENTER)))
    story.append(Paragraph('WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA', S('cn', alignment=TA_CENTER)))
    story.append(Paragraph('MFUMO WA USIMAMIZI WA MAZOEZI YA KUFUNDISHA (IMS)', S('csm', fontSize=8.5, alignment=TA_CENTER, textColor=colors.HexColor('#555'))))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width='100%', thickness=2.5, color=NAVY))
    story.append(HRFlowable(width='100%', thickness=1, color=GOLD, spaceAfter=10))

    ref_tbl = Table([[
        Paragraph(f'Kumb. Na.: <b>{ref_no}</b>', S('ln')),
        Paragraph(f'Tarehe: <b>{today.strftime("%d %B %Y")}</b>', S('rn', alignment=TA_RIGHT)),
    ]], colWidths=[8*cm, 8*cm])
    ref_tbl.setStyle(TableStyle([('PADDING', (0,0), (-1,-1), 0)]))
    story.append(ref_tbl)
    story.append(Spacer(1, 12))

    if school:
        district = school.district
        story.append(Paragraph('<b>Mkurugenzi wa Halmashauri,</b>', S('ln')))
        story.append(Paragraph(f'<b>Halmashauri ya {district.name},</b>', S('ln')))
        story.append(Paragraph(f'Mkoa wa {district.region.name}.', S('ln')))
        story.append(Spacer(1, 6))
        story.append(Paragraph('<b>NA:</b>', S('ln')))
        story.append(Paragraph('<b>Mkuu wa Shule,</b>', S('ln')))
        story.append(Paragraph(f'<b>{school.name},</b>', S('ln')))
        story.append(Paragraph(f'Wilaya ya {district.name}.', S('ln')))
    story.append(Spacer(1, 14))

    story.append(Paragraph(
        'BARUA YA UTHIBITISHO WA MWANAFUNZI MWALIMU — MAZOEZI YA KUFUNDISHA',
        S('subj', fontName='Helvetica-Bold', fontSize=10.5, alignment=TA_CENTER,
          textColor=NAVY, borderColor=NAVY, borderWidth=0.5, borderPadding=6)))
    story.append(Spacer(1, 14))

    story.append(Paragraph('Ndugu,', S('ln')))
    story.append(Spacer(1, 8))

    yr_str = current_year.year if current_year else str(today.year)
    story.append(Paragraph(
        f'Barua hii inathibitisha kuwa <b>{student.full_name.upper()}</b> '
        f'(Simu: {student.phone_number} | Barua pepe: {student.user.email}) '
        f'ameidhinishwa rasmi kufanya mazoezi ya kufundisha katika '
        f'<b>{school.name if school else "—"}</b>, Wilaya ya '
        f'<b>{school.district.name if school else "—"}</b>, '
        f'kwa mwaka wa masomo wa <b>{yr_str}</b>.',
        S('jn', alignment=TA_JUSTIFY, leading=15)))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        'Mwanafunzi huyu ameidhinishwa kufundisha masomo yafuatayo:',
        S('ln')))
    story.append(Spacer(1, 8))

    subj_data = [[
        Paragraph('Na.', S('th', fontName='Helvetica-Bold', fontSize=9, textColor=WHITE, alignment=TA_CENTER)),
        Paragraph('Somo', S('th', fontName='Helvetica-Bold', fontSize=9, textColor=WHITE)),
        Paragraph('Shule', S('th', fontName='Helvetica-Bold', fontSize=9, textColor=WHITE)),
        Paragraph('Tarehe ya Idhini', S('th', fontName='Helvetica-Bold', fontSize=9, textColor=WHITE, alignment=TA_CENTER)),
    ]]
    for i, app in enumerate(approved_applications, 1):
        approved_date = app.approval_date.strftime('%d/%m/%Y') if app.approval_date else '—'
        subj_data.append([
            Paragraph(str(i), S('c', fontSize=9, alignment=TA_CENTER)),
            Paragraph(app.subject.name, S('lsm', fontSize=9, leading=13)),
            Paragraph(app.school.name, S('lsm', fontSize=9, leading=13)),
            Paragraph(approved_date, S('c', fontSize=9, alignment=TA_CENTER)),
        ])
    s_tbl = Table(subj_data, colWidths=[1*cm, 5.5*cm, 6*cm, 3.5*cm])
    s_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, LIGHT]),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#CBD5E0')),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(s_tbl)
    story.append(Spacer(1, 12))

    story.append(Paragraph(
        'Tunaomba ushirikiano wa Halmashauri na Mkuu wa Shule kuhakikisha mwanafunzi '
        'huyu anapokewa na kupewa mazingira mazuri ya kufanya mazoezi ya kufundisha '
        'kwa mujibu wa kanuni za Wizara ya Elimu.',
        S('jn', alignment=TA_JUSTIFY, leading=15)))
    story.append(Spacer(1, 30))

    sig_tbl = Table([[
        Paragraph('___________________________', S('ln')),
        Paragraph('___________________________', S('rn', alignment=TA_RIGHT)),
    ],[
        Paragraph('<b>Msimamizi wa Mfumo (IMS)</b>', S('sm', fontSize=9)),
        Paragraph('<b>Tarehe ya Kupokea / Muhuri wa Halmashauri</b>', S('rsm', fontSize=9, alignment=TA_RIGHT)),
    ]], colWidths=[8*cm, 8*cm])
    sig_tbl.setStyle(TableStyle([('PADDING', (0,0), (-1,-1), 2)]))
    story.append(sig_tbl)

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#CBD5E0')))
    story.append(Paragraph(
        f'Hati hii imetolewa kwa njia ya mfumo wa IMS tarehe {today.strftime("%d/%m/%Y")}. Kumb.: {ref_no}',
        S('ft', fontSize=7.5, alignment=TA_CENTER, textColor=colors.HexColor('#999'))))

    doc.build(story)
    return buf.getvalue()


# ============================================================
# BODI YA WALIMU — Board helper functions
# ============================================================

def _active_year_students():
    """Return StudentTeacher queryset filtered to the current active academic year."""
    year = _cached_active_year()
    if year:
        return StudentTeacher.objects.filter(academic_year=year)
    return StudentTeacher.objects.all()


def _get_board_member(request):
    """Return BoardMember for current user or None."""
    try:
        return request.user.board_member
    except Exception:
        return None


def _can_access_region(bm, region):
    """Check if board member can view/access a region."""
    if bm.role in ('chair', 'inspector', 'member'):
        return True
    if bm.role == 'reo':
        return bm.region_id == region.id
    if bm.role == 'deo':
        return bm.district and bm.district.region_id == region.id
    if bm.role == 'head_teacher':
        return bm.district and bm.district.region_id == region.id
    return False


def _can_access_district(bm, district):
    """Check if board member can view/access a district."""
    if bm.role in ('chair', 'inspector', 'member'):
        return True
    if bm.role == 'reo':
        return bm.region_id == district.region_id
    if bm.role == 'deo':
        return bm.district_id == district.id
    if bm.role == 'head_teacher':
        return bm.district_id == district.id
    return False


def _normalize_school_code(raw):
    raw = raw.strip().upper().replace(' ', '').replace('-', '').replace('.', '')
    if re.match(r'^PS\d+$', raw):
        return raw
    return re.sub(r'^([SP])(\d+)$', r'\1.\2', raw)


def _ai_parse_allocation_document(allocation):
    """Tumia AI (Gemini) kuchambua hati ya mahitaji ya walimu wanafunzi."""
    try:
        doc_path = allocation.document.path
        text = ''

        if doc_path.lower().endswith('.pdf'):
            import pdfplumber
            with pdfplumber.open(doc_path) as pdf:
                for page in pdf.pages:
                    text += (page.extract_text() or '') + '\n'
        elif doc_path.lower().endswith(('.docx', '.doc')):
            from docx import Document as DocxDocument
            doc = DocxDocument(doc_path)
            text = '\n'.join(p.text for p in doc.paragraphs)
        else:
            return {'success': False, 'error': 'Aina ya faili haijulikani. Tumia PDF au Word.'}

        if not text.strip():
            return {'success': False, 'error': 'Hati haina maandishi yanayoweza kusomwa.'}

        from ai_utils import client, model_name
        prompt = f"""
Soma hati hii ya mahitaji ya walimu wanafunzi na utoe majibu kwa JSON tu.

HATI:
{text[:4000]}

Toa JSON katika muundo huu (numbers tu, bila maelezo):
{{
  "primary_needed": <jumla ya walimu wanafunzi wa shule za msingi>,
  "secondary_needed": <jumla ya walimu wanafunzi wa shule za sekondari>,
  "schools": [
    {{"name": "<jina la shule>", "level": "Primary|Secondary", "quota": <idadi>}},
    ...
  ]
}}

Kama hauwezi kupata idadi, weka 0. Jibu kwa JSON tu, bila maelezo mengine.
"""
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        raw = response.text.strip()
        # Extract JSON from response
        import re as _re, json as _json
        match = _re.search(r'\{.*\}', raw, _re.DOTALL)
        if match:
            data = _json.loads(match.group())
            data['success'] = True
            return data
        return {'success': False, 'error': 'AI haikutoa JSON sahihi.'}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def _generate_requests_pdf(requests_qs, district, current_year):
    """Generate a formatted PDF of school head requests using AI summary + ReportLab."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    # AI summary
    ai_summary = _ai_summarise_requests(requests_qs)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    navy = colors.HexColor('#0A2B5E')
    gold = colors.HexColor('#C8900A')
    light = colors.HexColor('#EEF1F6')

    title_style = ParagraphStyle('Title', parent=styles['Heading1'],
                                 fontSize=16, textColor=navy, spaceAfter=4,
                                 alignment=TA_CENTER, fontName='Helvetica-Bold')
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'],
                               fontSize=10, textColor=gold, spaceAfter=2, alignment=TA_CENTER)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=9, spaceAfter=4)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'],
                                   fontSize=11, textColor=navy, spaceBefore=12, spaceAfter=4,
                                   fontName='Helvetica-Bold')

    story = []
    story.append(Paragraph('JAMHURI YA MUUNGANO WA TANZANIA', sub_style))
    story.append(Paragraph('Wizara ya Elimu, Sayansi na Teknolojia', sub_style))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width='100%', thickness=3, color=gold))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f'MAHITAJI YA WALIMU WANAFUNZI', title_style))
    story.append(Paragraph(f'Wilaya ya {district.name} — Mwaka {current_year.year if current_year else "—"}', sub_style))
    story.append(Spacer(1, 0.2*cm))
    story.append(HRFlowable(width='100%', thickness=1, color=navy))
    story.append(Spacer(1, 0.4*cm))

    # AI Summary section
    if ai_summary:
        story.append(Paragraph('Muhtasari wa AI', section_style))
        story.append(Paragraph(ai_summary, body_style))
        story.append(Spacer(1, 0.4*cm))

    # Primary schools table
    primary_reqs = [r for r in requests_qs if r.level == 'Primary' and r.status != 'rejected']
    secondary_reqs = [r for r in requests_qs if r.level == 'Secondary' and r.status != 'rejected']

    def make_table(reqs, level_label):
        if not reqs:
            return
        story.append(Paragraph(f'Shule za {level_label}', section_style))
        headers = ['#', 'Jina la Shule', 'Mkuu wa Shule', 'Simu', 'Idadi', 'Hali']
        data = [headers]
        total = 0
        for i, r in enumerate(reqs, 1):
            school_name = r.school.name if r.school else r.school_name_submitted
            status_map = {'pending': 'Inasubiri', 'reviewed': 'Imepitiwa',
                          'applied': 'Imewekwa', 'rejected': 'Imekataliwa'}
            data.append([
                str(i), school_name, r.head_name,
                r.head_phone or '—', str(r.students_needed), status_map.get(r.status, r.status)
            ])
            total += r.students_needed
        data.append(['', 'JUMLA', '', '', str(total), ''])

        col_widths = [1*cm, 5*cm, 4*cm, 3*cm, 1.5*cm, 2.5*cm]
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), navy),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (4, 0), (4, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, light]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FEF3C7')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.5*cm))

    make_table(primary_reqs, 'Msingi')
    make_table(secondary_reqs, 'Sekondari')

    # Grand total
    all_reqs = primary_reqs + secondary_reqs
    grand_total = sum(r.students_needed for r in all_reqs)
    story.append(HRFlowable(width='100%', thickness=1, color=navy))
    story.append(Spacer(1, 0.2*cm))
    total_data = [
        ['Jumla — Msingi', str(sum(r.students_needed for r in primary_reqs))],
        ['Jumla — Sekondari', str(sum(r.students_needed for r in secondary_reqs))],
        ['JUMLA KUU', str(grand_total)],
    ]
    t2 = Table(total_data, colWidths=[12*cm, 5*cm])
    t2.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, -1), (-1, -1), navy),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t2)
    story.append(Spacer(1, 1*cm))
    from django.utils import timezone as tz
    story.append(Paragraph(f'Imetengenezwa: {tz.now().strftime("%d/%m/%Y %H:%M")} | Mfumo wa IMS — AI Generated', body_style))

    doc.build(story)
    buffer.seek(0)

    from django.http import HttpResponse
    filename = f'mahitaji_{district.name.replace(" ", "_")}_{(current_year.year if current_year else "")}.pdf'
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _send_sms_africastalking(phone, message):
    """Tuma SMS moja kupitia Africa's Talking API. Rudisha (True, '') au (False, error)."""
    import urllib.request
    import urllib.parse
    username = os.environ.get('AT_USERNAME', '')
    api_key = os.environ.get('AT_API_KEY', '')
    if not username or not api_key:
        return False, 'AT_USERNAME au AT_API_KEY hazijawekwa kwenye .env'

    # Normalize phone to +255XXXXXXXXX
    phone = phone.strip().replace(' ', '').replace('-', '')
    if phone.startswith('0') and len(phone) == 10:
        phone = '+255' + phone[1:]
    elif phone.startswith('255') and len(phone) == 12:
        phone = '+' + phone
    elif not phone.startswith('+'):
        phone = '+255' + phone

    data = urllib.parse.urlencode({
        'username': username,
        'to': phone,
        'message': message,
    }).encode()
    req = urllib.request.Request(
        'https://api.africastalking.com/version1/messaging',
        data=data,
        headers={
            'apiKey': api_key,
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            if '"status":"Success"' in body or '"Status":"Success"' in body:
                return True, ''
            return False, body
    except Exception as e:
        return False, str(e)


def _ai_summarise_requests(requests_qs):
    """Tumia AI kutoa muhtasari wa maombi."""
    try:
        from ai_utils import client, model_name
        lines = []
        for r in requests_qs:
            if r.status != 'rejected':
                sn = r.school.name if r.school else r.school_name_submitted
                lines.append(f"- {sn} ({r.level}): {r.students_needed} walimu wanafunzi — Mkuu: {r.head_name}")
        if not lines:
            return ''
        data_text = '\n'.join(lines)
        prompt = f"""Toa muhtasari mfupi (mistari 3-4) wa maombi haya ya walimu wanafunzi kwa ajili ya ripoti rasmi:

{data_text}

Andika kwa Kiswahili, muhtasari wa kitaalamu unaofaa ripoti rasmi ya serikali. Taja jumla na usambazaji kwa shule za msingi na sekondari."""
        resp = client.models.generate_content(model=model_name, contents=prompt)
        return resp.text.strip()
    except Exception:
        return ''


def _get_deo_for_district(district):
    from field_app.models import BoardMember
    return BoardMember.objects.filter(
        role='deo', district=district, is_active=True
    ).first()
