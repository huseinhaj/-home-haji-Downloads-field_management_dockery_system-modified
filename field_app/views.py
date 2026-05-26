import csv
import io
import json
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
from django.db.models import Count, Case, When, Value, BooleanField, F, Q, Prefetch
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
    BoardMember, BoardComment, LessonPlan,
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
    """Cache today's logbook entry for 30s to avoid get_or_create hit on every page load."""
    key = f'logbook_today_{student.id}_{today}'
    entry = cache.get(key)
    if entry is None:
        entry, _ = LogbookEntry.objects.get_or_create(
            student=student, date=today,
            defaults={'school': school, 'morning_check_in': timezone.now()}
        )
        cache.set(key, entry, 30)
    return entry


def _invalidate_today_logbook(student, today):
    cache.delete(f'logbook_today_{student.id}_{today}')

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
            <h1>🎓 Field Placement System</h1>
            <p>University of Dodoma</p>
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
            <p>University of Dodoma - Field Placement System</p>
            <p>📧 This is an automated message. Please do not reply.</p>
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
Field Placement Coordination System
University of Dodoma
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
# AUTHENTICATION VIEWS
# =========================

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
            StudentTeacher.objects.create(user=user, full_name=full_name, phone_number=phone_number)

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
            login(request, user, backend='field_app.backends.EmailBackend')

            try:
                assessor = Assessor.objects.get(user=user)
                messages.warning(request,
                    "You are registered as an assessor. Please use the assessor login page."
                )
                logout(request)
                return redirect('assessor_login')
            except Assessor.DoesNotExist:
                get_or_create_student_profile(user)
                messages.success(request, "Login successful!")
                return redirect('dashboard')
        else:
            messages.error(request, 'Invalid credentials')
    else:
        form = CustomLoginForm()

    return render(request, 'field_app/registration/login.html', {
        'form': form,
        'hide_navbar': True
    })

# views.py - Badilisha logout_view kwa hii

def logout_view(request):
    """Logout na upeleke kwenye appropriate login page based on user type"""
    was_staff = request.user.is_authenticated and request.user.is_staff
    was_assessor = request.user.is_authenticated and hasattr(request.user, 'assessor')
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    if was_staff:
        return redirect('/admin/login/')
    if was_assessor:
        return redirect('assessor_login')
    return redirect('login')
# =========================
# ASSESSOR LOGIN VIEW
# =========================

# views.py - FIX ASSESSOR LOGIN VIEW

# views.py - COMPLETE FIX FOR ASSESSOR LOGIN

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
# =========================
# DASHBOARD VIEWS
# =========================

@login_required
def dashboard(request):
    """Student dashboard"""

    # Staff users belong in admin dashboard
    if request.user.is_staff:
        return redirect('admin_dashboard')

    # Check if user is assessor
    try:
        assessor = Assessor.objects.get(user=request.user)
        messages.info(request, "Redirecting to assessor dashboard")
        return redirect('assessor_dashboard')
    except Assessor.DoesNotExist:
        pass
    
    student = get_or_create_student_profile(request.user)
    current_year = _cached_active_year()

    if current_year:
        pinned_region_ids = RegionPin.objects.filter(
            academic_year=current_year,
            is_pinned=True
        ).values_list('region_id', flat=True)
        pinned_regions = Region.objects.filter(id__in=pinned_region_ids)
        pinned_regions = Region.objects.none()
    
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
    school_has_completed_quota = False
    can_download_group_letter = False
    approved_students_count = 0
    group_letter_quota = 5
    
    if student:
        applications = StudentApplication.objects.filter(student=student).select_related('subject', 'school')
        approved_applications_count = applications.filter(status='approved').count()
        pending_applications_count = applications.filter(status='pending').count()
        has_approved_applications = approved_applications_count > 0
        
        if student.selected_school:
            school = student.selected_school
            
            approved_students_count = StudentApplication.objects.filter(
                school=school,
                status='approved'
            ).count()
            
            school_has_completed_quota = approved_students_count >= group_letter_quota
            can_download_group_letter = school_has_completed_quota and has_approved_applications

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

    return render(request, 'field_app/dashboard.html', {
        'regions': pinned_regions,
        'current_year': current_year,
        'student': student,
        'applications': applications,
        'approved_applications_count': approved_applications_count,
        'pending_applications_count': pending_applications_count,
        'has_approved_applications': has_approved_applications,
        'school_has_completed_quota': school_has_completed_quota,
        'can_download_group_letter': can_download_group_letter,
        'approved_students_count': approved_students_count,
        'group_letter_quota': group_letter_quota,
        'logbook_entries': logbook_entries,
        'assessors': assessors,
        'board_comments': board_comments,
    })

# views.py - SAHIHISHA SEHEMU YA ASSESSOR DASHBOARD

@login_required
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
    
    # ========== ADD REAL SCHOOL COUNTS FOR EACH DISTRICT ==========
    for district in districts:
        # Count schools in this district
        district.school_count = School.objects.filter(district=district).count()
        
        # Count students (optional - unaweza kuondoka "0" kama ni ngumu)
        # Kama hutaki kuonyesha wanafunzi, weka tu "0"
        district.student_count = 0  # Au uondoe kabisa kwenye template
    
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
    
    # Get schools
    schools_qs = School.objects.filter(district=district, level=selected_level)
    if search_query:
        schools_qs = schools_qs.filter(name__icontains=search_query)
    
    schools = []
    for school in schools_qs:
        school.is_pinned = school.id in pinned_school_ids
        school.is_selectable = (not school.is_pinned) and (school.current_students < school.capacity)
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
                    
                    if student.selected_school:
                        School.objects.filter(id=student.selected_school.id).update(current_students=F('current_students') - 1)
                    
                    student.selected_school = school
                    student.save()
                    invalidate_student_cache(student)
                    School.objects.filter(id=school.id).update(current_students=F('current_students') + 1)
                    
                    request.session.pop('temp_selected_school_id', None)
                    messages.success(request, f'Shule imethibitishwa: {school.name}')
                    return redirect('select_subjects', school_id=school.id)
                except:
                    messages.error(request, 'Shule haipo')
                messages.error(request, 'Hakuna shule iliyochaguliwa')
            return redirect(f"{request.path}?level={selected_level}&q={search_query}")
        
        elif action == 'cancel':
            request.session.pop('temp_selected_school_id', None)
            messages.success(request, 'Umeghairi uchaguzi wa shule')
            return redirect(f"{request.path}?level={selected_level}&q={search_query}")
    
    return render(request, 'field_app/select_school.html', {
        'district': district,
        'schools': schools,
        'selected_school': selected_school,
        'query': search_query,
        'selected_level': selected_level,
        'total_schools': total_schools,
        'pinned_schools_count': pinned_schools_count,
        'available_schools_count': available_schools_count,
        'full_schools_count': full_schools_count,
        'current_year': current_year,
    })
@login_required
def select_subjects(request, school_id):
    school = get_object_or_404(School, id=school_id)
    subject_capacities = SchoolSubjectCapacity.objects.filter(school=school).select_related('subject')
    
    student = get_or_create_student_profile(request.user)
    
    existing_applications = StudentApplication.objects.filter(
        student=student, 
        school=school
    ).select_related('subject')
    
    applied_subject_ids = {app.subject.id for app in existing_applications}

    if request.method == 'POST':
        subject_id = request.POST.get('subject_id')
        action = request.POST.get('action')

        if not subject_id:
            messages.error(request, "No subject selected.")
            return redirect('select_subjects', school_id=school.id)

        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            messages.error(request, "Subject does not exist.")
            return redirect('select_subjects', school_id=school.id)

        try:
            capacity = SchoolSubjectCapacity.objects.get(school=school, subject=subject)
        except SchoolSubjectCapacity.DoesNotExist:
            messages.error(request, f"{subject.name} is not available at this school.")
            return redirect('select_subjects', school_id=school.id)

        if action == 'apply':
            existing_application = StudentApplication.objects.filter(
                student=student,
                subject=subject,
                school=school
            ).first()

            if existing_application:
                messages.info(request, f"You have already applied for {subject.name}.")
            elif capacity.current_students >= capacity.max_students:
                messages.error(request, f"{subject.name} is already full.")
            else:
                StudentApplication.objects.create(
                    student=student,
                    subject=subject,
                    school=school,
                    status='pending'
                )
                messages.success(request,
                    f"✅ Application for {subject.name} submitted successfully! "
                    f"Waiting for Admin approval."
                )

        elif action == 'cancel_application':
            application = StudentApplication.objects.filter(
                student=student,
                subject=subject,
                school=school
            ).first()

            if application:
                application.delete()
                messages.success(request, f"Application for {subject.name} cancelled.")
            else:
                messages.error(request, f"Cannot cancel application for {subject.name}.")

        return redirect('select_subjects', school_id=school.id)

    return render(request, 'field_app/select_subjects.html', {
        'school': school,
        'subject_capacities': subject_capacities,
        'existing_applications': existing_applications,
        'applied_subject_ids': applied_subject_ids,
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

# =========================
# ADMIN VIEWS
# =========================

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
    logbook_dates = []
    logbook_counts = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        count = LogbookEntry.objects.filter(date=day).count()
        logbook_dates.append(day.strftime('%b %d'))
        logbook_counts.append(count)
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
            
            messages.success(request, f"Application for {application.subject.name} approved successfully!")
            
        elif action == 'reject':
            application.status = 'rejected'
            application.approved_by = request.user
            application.approval_date = timezone.now()
            application.save()
            messages.success(request, f"Application for {application.subject.name} rejected.")
        
        return redirect('admin_dashboard')
    
    return render(request, 'field_app/approve_application.html', {'application': application})

# =========================
# ASSESSOR MANAGEMENT VIEWS
# =========================

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
                Field Placement Coordination Unit
                University of Dodoma
                
                This is an automated message. Please do not reply.
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

# views.py - FIX BULK ASSIGNMENT FUNCTION

# views.py - FIX BULK ASSIGNMENT BUG

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

# =========================
# ASSESSOR ASSESSMENT VIEWS
# =========================

@login_required
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
@login_required
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


@login_required
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


# =========================
# STUDENT LIST VIEWS
# =========================

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

# =========================
# LETTER DOWNLOAD VIEWS
# =========================

@login_required
def download_individual_letter(request):
    student = get_or_create_student_profile(request.user)
    
    approved_applications = StudentApplication.objects.filter(
        student=student, 
        status='approved'
    )
    
    if not approved_applications.exists():
        messages.error(request, "You don't have any approved applications to download a letter.")
        return redirect('dashboard')

    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, "INDIVIDUAL FIELD PLACEMENT APPROVAL LETTER")
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 770, f"Student Name: {student.full_name}")
    p.drawString(100, 750, f"Student ID: {student.id}")
    p.drawString(100, 730, f"Phone: {student.phone_number}")
    p.drawString(100, 710, f"Email: {student.user.email}")
    
    if student.selected_school:
        p.drawString(100, 680, f"Assigned School: {student.selected_school.name}")
        p.drawString(100, 660, f"School District: {student.selected_school.district.name}")
        p.drawString(100, 640, f"School Region: {student.selected_school.district.region.name}")
    
    p.drawString(100, 610, "Approved Teaching Subjects:")
    y_position = 590
    for application in approved_applications:
        p.drawString(120, y_position, f"✓ {application.subject.name} at {application.school.name}")
        y_position -= 20
        if application.approval_date:
            p.drawString(140, y_position, f"Approved on: {application.approval_date.strftime('%Y-%m-%d')}")
            y_position -= 20
    
    p.drawString(100, 530, "This letter confirms that the above student has been approved")
    p.drawString(100, 510, "for field placement teaching practice.")
    p.drawString(100, 490, f"Generated on: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="individual_approval_{student.full_name}.pdf"'
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

# =========================
# AJAX AND API VIEWS
# =========================

@staff_member_required
@csrf_exempt
def ajax_search_schools(request):
    """AJAX endpoint for searching ALL schools"""
    search_query = request.GET.get('q', '').strip()
    
    if not search_query or len(search_query) < 2:
        return JsonResponse({'results': [], 'count': 0, 'error': 'Search term too short'})
    
    # Search in all schools
    schools = School.objects.filter(
        Q(name__icontains=search_query) |
        Q(district__name__icontains=search_query) |
        Q(district__region__name__icontains=search_query)
    ).select_related('district', 'district__region')[:100]
    
    results = []
    for school in schools:
        student_count = StudentTeacher.objects.filter(
            selected_school=school,
            approval_status='approved'
        ).count()
        
        assessor_count = SchoolAssessment.objects.filter(school=school).count()
        
        results.append({
            'id': school.id,
            'name': school.name,
            'district': school.district.name,
            'region': school.district.region.name,
            'level': school.level,
            'students': student_count,
            'assessors': assessor_count,
            'capacity': school.capacity,
            'current_students': school.current_students,
        })
    
    return JsonResponse({
        'results': results,
        'count': len(results),
        'search_term': search_query
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

# =========================
# REGION PINNING VIEWS
# =========================
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
# =========================
# PROFILE VIEWS
# =========================

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

# =========================
# MISCELLANEOUS VIEWS
# =========================

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
            old_school.current_students = F('current_students') - 1
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
# =========================
# SCHOOL CHANGE FUNCTIONALITY
# =========================




# =========================
# CHANGE SCHOOL - PERFORMANCE OPTIMIZED
# =========================



# =========================
# CHANGE SCHOOL - COMPLETE FIXED VERSION
# =========================

@login_required
def change_school(request):
    """Mwanafunzi anaweza kubadili shule ndani ya wiki moja - WITH COMPLETE DB UPDATE"""
    student = get_or_create_student_profile(request.user)
    
    # Check if student has selected a school
    if not student.selected_school:
        messages.error(request, "Hujachagua shule yoyote bado.")
        return redirect('select_region')
    
    # Set initial selection date if not set
    if not student.initial_school_selection_date:
        student.initial_school_selection_date = timezone.now()
        student.save()
        invalidate_student_cache(student)
    
    # Calculate days passed
    days_passed = (timezone.now() - student.initial_school_selection_date).days
    CAN_CHANGE_DAYS = 7
    MAX_CHANGES = 3
    
    can_change = days_passed <= CAN_CHANGE_DAYS and student.school_change_count < MAX_CHANGES
    
    # Get districts in current school's region (only same region for faster loading)
    current_district = student.selected_school.district
    current_region = current_district.region
    
    # Get all districts in the same region
    districts_in_region = District.objects.filter(region=current_region).select_related('region')
    
    remaining_days = max(0, CAN_CHANGE_DAYS - days_passed)
    remaining_changes = max(0, MAX_CHANGES - student.school_change_count)
    
    # ========== HANDLE POST REQUEST DIRECTLY (if not using AJAX) ==========
    if request.method == 'POST' and not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        new_school_id = request.POST.get('new_school_id')
        
        if not new_school_id:
            messages.error(request, "Tafadhali chagua shule mpya.")
            return redirect('change_school')
        
        # Process the change
        try:
            new_school = School.objects.select_related('district', 'district__region').get(id=new_school_id)
            old_school = student.selected_school
            
            # Validate
            if not can_change:
                messages.error(request, f"Huwezi kubadili shule tena. Umebadili tayari {student.school_change_count} mara.")
                return redirect('change_school')
            
            # Check capacity
            if new_school.current_students >= new_school.capacity:
                messages.error(request, f"Shule {new_school.name} imejaa. Hakuna nafasi.")
                return redirect('change_school')
            
            # Check if pinned
            current_year = get_current_academic_year()
            is_pinned = SchoolPin.objects.filter(
                school=new_school,
                academic_year=current_year,
                is_pinned=True
            ).exists()
            
            if is_pinned:
                messages.error(request, f"Shule {new_school.name} haipatikani kwa sasa.")
                return redirect('change_school')
            
            # ========== UPDATE DATABASE ==========
            print(f"\n🔄 CHANGING SCHOOL FOR: {student.full_name}")
            print(f"   OLD: {old_school.name} (ID: {old_school.id})")
            print(f"   NEW: {new_school.name} (ID: {new_school.id})")
            
            # 1. Decrease old school counter
            School.objects.filter(id=old_school.id).update(current_students=F('current_students') - 1)
            print(f"   ✅ Decreased old school: {old_school.name}")
            
            # 2. Increase new school counter
            School.objects.filter(id=new_school.id).update(current_students=F('current_students') + 1)
            print(f"   ✅ Increased new school: {new_school.name}")
            
            # 3. Update student record
            student.selected_school = new_school
            student.school_change_count = F('school_change_count') + 1
            student.last_school_change_date = timezone.now()
            student.save()
            invalidate_student_cache(student)
            
            # Refresh student to get updated count
            student.refresh_from_db()
            
            # 4. Delete pending applications for old school
            deleted_count, _ = StudentApplication.objects.filter(
                student=student,
                school=old_school,
                status='pending'
            ).delete()
            print(f"   ✅ Deleted {deleted_count} pending applications for old school")
            
            # 5. Clear any session cache
            if 'selected_school_id' in request.session:
                del request.session['selected_school_id']
            
            # 6. Clear cache for API
            cache_key = f'schools_district_{old_school.district_id}'
            cache.delete(cache_key)
            cache_key = f'schools_district_{new_school.district_id}'
            cache.delete(cache_key)
            
            print(f"   ✅ School change COMPLETE!")
            
            messages.success(
                request,
                f"✅ Umefanikiwa kubadili shule!\n"
                f"Shule mpya: {new_school.name}\n"
                f"Umesalia na {MAX_CHANGES - student.school_change_count} nafasi za kubadilisha."
            )
            
            return redirect('dashboard')
            
        except School.DoesNotExist:
            messages.error(request, "Shule haipatikani.")
            return redirect('change_school')
        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            messages.error(request, f"Hitilafu: {str(e)}")
            return redirect('change_school')
    
    # Render the template for GET request
    return render(request, 'field_app/change_school.html', {
        'student': student,
        'current_school': student.selected_school,
        'current_region': current_region,
        'districts': districts_in_region,
        'days_passed': days_passed,
        'remaining_days': remaining_days,
        'remaining_changes': remaining_changes,
        'max_change_days': CAN_CHANGE_DAYS,
        'max_changes': MAX_CHANGES,
        'initial_selection_date': student.initial_school_selection_date,
        'can_change': can_change,
    })


@login_required
def api_confirm_change_school(request):
    """API endpoint to confirm school change - SIMPLE WORKING VERSION"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        new_school_id = data.get('school_id')
    except:
        return JsonResponse({'error': 'Invalid data'}, status=400)
    
    if not new_school_id:
        return JsonResponse({'error': 'School ID required'}, status=400)
    
    student = get_or_create_student_profile(request.user)
    
    # Check if student can change school
    if not student.selected_school:
        return JsonResponse({'error': 'No school selected'}, status=400)
    
    if not student.initial_school_selection_date:
        student.initial_school_selection_date = timezone.now()
        student.save()
        invalidate_student_cache(student)
    
    days_passed = (timezone.now() - student.initial_school_selection_date).days
    if days_passed > 7:
        return JsonResponse({'error': 'Change window expired (only 7 days)'}, status=400)
    
    if student.school_change_count >= 3:
        return JsonResponse({'error': 'Maximum 3 changes allowed'}, status=400)
    
    try:
        new_school = School.objects.get(id=new_school_id)
        old_school = student.selected_school
        
        # Check capacity
        if new_school.current_students >= new_school.capacity:
            return JsonResponse({'error': f'Shule {new_school.name} imejaa'}, status=400)
        
        # Check if pinned
        current_year = get_current_academic_year()
        is_pinned = SchoolPin.objects.filter(
            school=new_school,
            academic_year=current_year,
            is_pinned=True
        ).exists()
        
        if is_pinned:
            return JsonResponse({'error': f'Shule {new_school.name} haipatikani'}, status=400)
        
        # ========== SIMPLE DATABASE UPDATE ==========
        # Use direct save instead of F() for better control
        old_school.current_students -= 1
        old_school.save()
        
        new_school.current_students += 1
        new_school.save()
        
        # Update student
        student.selected_school = new_school
        student.school_change_count += 1
        student.last_school_change_date = timezone.now()
        student.save()
        invalidate_student_cache(student)
        
        # Delete pending applications for old school
        StudentApplication.objects.filter(
            student=student,
            school=old_school,
            status='pending'
        ).delete()
        
        print(f"✅ SUCCESS: {student.full_name} changed from {old_school.name} to {new_school.name}")
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully changed to {new_school.name}',
            'new_school': {
                'id': new_school.id,
                'name': new_school.name,
                'district': new_school.district.name,
                'region': new_school.district.region.name,
                'current_students': new_school.current_students,
                'capacity': new_school.capacity,
            },
            'remaining_changes': 3 - student.school_change_count,
            'remaining_days': max(0, 7 - days_passed),
        })
        
    except School.DoesNotExist:
        return JsonResponse({'error': 'School not found'}, status=404)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
@login_required
def api_get_schools_for_change(request):
    """API endpoint for getting schools by district - FAST with caching"""
    
    student = get_or_create_student_profile(request.user)
    
    if not student.selected_school:
        return JsonResponse({'error': 'No school selected'}, status=400)
    
    # Get parameters
    district_id = request.GET.get('district_id')
    level = request.GET.get('level', 'Secondary')
    search = request.GET.get('search', '').strip()
    page = int(request.GET.get('page', 1))
    per_page = 12  # Schools per page
    
    # Validate district
    if not district_id:
        return JsonResponse({'error': 'District ID required'}, status=400)
    
    try:
        district = District.objects.get(id=district_id)
    except District.DoesNotExist:
        return JsonResponse({'error': 'District not found'}, status=404)
    
    # Get current academic year for pinned schools
    current_year = get_current_academic_year()
    
    # Get pinned school IDs (cache for 5 minutes)
    cache_key = f'pinned_schools_{current_year.id if current_year else "none"}'
    pinned_school_ids = cache.get(cache_key)
    if pinned_school_ids is None and current_year:
        pinned_school_ids = list(SchoolPin.objects.filter(
            academic_year=current_year,
            is_pinned=True
        ).values_list('school_id', flat=True))
        cache.set(cache_key, pinned_school_ids, 300)  # Cache for 5 minutes
    elif not current_year:
        pinned_school_ids = []
    
    # Base queryset - only schools in selected district
    schools_qs = School.objects.filter(
        district_id=district_id,
        level=level
    ).exclude(id=student.selected_school.id)
    
    # Exclude pinned schools
    if pinned_school_ids:
        schools_qs = schools_qs.exclude(id__in=pinned_school_ids)
    
    # Exclude full schools
    schools_qs = schools_qs.filter(current_students__lt=F('capacity'))
    
    # Apply search filter
    if search:
        schools_qs = schools_qs.filter(
            Q(name__icontains=search) |
            Q(district__name__icontains=search) |
            Q(district__region__name__icontains=search)
        )
    
    # Select related for efficiency
    schools_qs = schools_qs.select_related('district', 'district__region')
    
    # Count total (for pagination)
    total_count = schools_qs.count()
    
    # Apply pagination
    start = (page - 1) * per_page
    end = start + per_page
    schools = schools_qs[start:end]
    
    # Prepare data
    schools_data = []
    for school in schools:
        # Calculate occupancy
        if school.capacity > 0:
            occupancy = round((school.current_students / school.capacity) * 100)
            occupancy = 0
        
        schools_data.append({
            'id': school.id,
            'name': school.name,
            'district': school.district.name,
            'region': school.district.region.name,
            'level': school.level,
            'current_students': school.current_students,
            'capacity': school.capacity,
            'available_spots': school.capacity - school.current_students,
            'occupancy_percentage': occupancy,
            'is_available': school.current_students < school.capacity,
        })
    
    return JsonResponse({
        'success': True,
        'schools': schools_data,
        'total': total_count,
        'page': page,
        'total_pages': (total_count + per_page - 1) // per_page,
        'has_next': end < total_count,
        'has_previous': page > 1,
    })        
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
            
            messages.success(
                request,
                f"✅ Academic year changed to {new_year.year}\n"
                f"⚠️ Remember to set region pins for this new year!"
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
# =========================
# ASSESSOR PASSWORD RESET VIEWS - ONGEZA HIZI MWISHONI MWA VIEWS.PY
# =========================

def assessor_password_reset(request):
    """Reset password for assessor - sends new temporary password via email"""
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        
        if not email:
            messages.error(request, 'Please enter your email address.')
            return redirect('assessor_login')
        
        # Find assessor with this email
        try:
            assessor = Assessor.objects.get(email__iexact=email)
            
            if not assessor.user:
                messages.error(request, 
                    'Your account is not fully set up. Please contact the administrator.'
                )
                return redirect('assessor_login')
            
            # Generate new random password
            temp_password = generate_random_password()
            
            # Update user password
            assessor.user.set_password(temp_password)
            assessor.user.save()
            
            # Send email with new password
            login_url = request.build_absolute_uri(reverse('assessor_login'))
            
            # HTML Email content
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
                        <p>Field Placement System - University of Dodoma</p>
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
                        <p>© {timezone.now().year} University of Dodoma - Field Placement System</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_content = f"""
            PASSWORD RESET - Field Placement System
            {'='*50}
            
            Dear {assessor.full_name},
            
            You requested to reset your password.
            
            YOUR NEW LOGIN CREDENTIALS:
            Email: {assessor.email}
            Password: {temp_password}
            
            Login URL: {login_url}
            
            IMPORTANT: Change this password immediately after logging in.
            
            Best regards,
            Field Placement System
            University of Dodoma
            """
            
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
                # Email ilishindwa — rudisha password ya zamani ili assessor asikwame
                assessor.user.set_password(None)
                assessor.user.save()
                messages.error(request,
                    f'❌ Imeshindwa kutuma email kwa {assessor.email}. '
                    f'Wasiliana na msimamizi. ({str(email_error)[:80]})'
                )
            return redirect('assessor_login')

        except Assessor.DoesNotExist:
            messages.error(request, f'Hakuna assessor aliyepatikana na email: {email}')
            return redirect('assessor_login')
    
    # GET request - redirect to login page
    return redirect('assessor_login')


def assessor_password_reset_done(request):
    """Show success message after password reset"""
    messages.success(request, 
        'Password reset email has been sent. Please check your inbox.'
    )
    return redirect('assessor_login')                     
# ============================================================
# ADD THIS AT THE END OF YOUR views.py FILE
# ============================================================

# =========================
# LOGIN PAGE WITH DYNAMIC DATA FROM DATABASE
# =========================

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
# views.py


@login_required
def generate_scheme_view(request):
    from .models import EducationLevel

    form = SchemeOfWorkForm()
    education_levels = EducationLevel.objects.all().order_by('order')

    return render(request, 'field_app/generate_scheme.html', {
        'form': form,
        'education_levels': education_levels,
    })
@csrf_exempt
@login_required
def ajax_generate_scheme(request):
    """API ya AI kuzalisha Scheme of Work kwa format ya KitabuSmart"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Extract form data
            education_level = data.get('education_level')
            class_name = data.get('class_name')
            subject = data.get('subject')
            term = data.get('term')
            year = data.get('year')
            syllabus = data.get('syllabus', 'New Syllabus')
            total_weeks = data.get('total_weeks', 12)
            periods_per_week = data.get('periods_per_week', 8)
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            teacher_name = data.get('teacher_name')
            school_name = data.get('school_name')
            reference_source = data.get('reference_source', '')
            breaks = data.get('breaks', [])
            
            # Build breaks text for prompt
            breaks_text = ""
            if breaks:
                breaks_text = "\nBreaks (holidays/exams) to respect:\n"
                for b in breaks:
                    breaks_text += f"- {b.get('name', 'Break')}: {b.get('start', '')} to {b.get('end', '')}\n"
            
            # Prompt ya AI kufuata format ya KitabuSmart
            prompt = f"""
You are an AI assistant for Tanzanian teachers. Generate a complete Scheme of Work following EXACTLY the KitabuSmart format.

Input details:
- Education Level: {education_level}
- Class: {class_name}
- Subject: {subject}
- Term: {term} {year}
- Syllabus: {syllabus}
- Total Weeks: {total_weeks} weeks
- Periods per Week: {periods_per_week}
- Start Date: {start_date}
- End Date: {end_date}
- Teacher: {teacher_name}
- School: {school_name}
- Reference Source: {reference_source}
{breaks_text}
The output MUST be a JSON list of objects. Each object must have exactly these 12 keys (column names):
"Main Competence", "Specific Competence", "Learning Activities", "Specific Learning Activities", "Month", "Week", "Periods", "Reference", "Teaching & Learning Methods", "Teaching & Learning Resources", "Assessment Tools", "Remarks"

Requirements:
1. Distribute content across {total_weeks} weeks, respecting any breaks (skip weeks that fall on breaks).
2. For each week, assign appropriate Month (e.g., MAY, JUNE, JULY, AUGUST, SEPTEMBER, OCTOBER).
3. "Week" column should be like "1st", "2nd", "3rd", etc.
4. "Periods" should be {periods_per_week} for normal weeks.
5. "Reference" should include {reference_source} with page numbers (e.g., "ENGLISH_iv-vii.pdf, page 10-15").
6. "Main Competence" should be numbered like "1.0 Demonstrate mastery of BASIC MATHEMATICS fundamental principles".
7. Content must be realistic for {education_level} {class_name} {subject} in Tanzania.
8. After the last week, add a row with remarks about examination preparation if needed.
9. Return ONLY valid JSON, no extra text.
Example row:
{{"Main Competence": "1.0 Demonstrate mastery of concepts", "Specific Competence": "Understand numbers", "Learning Activities": "Group discussion", "Specific Learning Activities": "Define numbers", "Month": "MAY", "Week": "1st", "Periods": 8, "Reference": "book.pdf, page 5-10", "Teaching & Learning Methods": "Think-Pair-Share", "Teaching & Learning Resources": "Charts", "Assessment Tools": "Quizzes", "Remarks": "Emphasize basics"}}
"""
            
            # ========== CALL GEMINI AI ==========
            print("🤖 Calling Gemini AI...")
            
            response = client.models.generate_content(model=model_name, contents=prompt)
            response_text = response.text
            
            print(f"✅ Gemini response received ({len(response_text)} characters)")
            
            # Extract JSON
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                json_data = json_match.group()
            else:
                json_data = response_text
            
            try:
                scheme_data = json.loads(json_data)
            except Exception as e:
                print("JSON parse error:", e)
                scheme_data = []
            
            # Also save to database if needed (optional)
            # Save form data and scheme_data to SchemeOfWork model
            # ... (unaweza kuongeza hapa)
            
            return JsonResponse({'success': True, 'data': scheme_data})

        except Exception as e:
            import traceback
            error_msg = str(e)
            traceback.print_exc()  # Log full traceback to server console
            return JsonResponse({'success': False, 'error': error_msg}, status=500)
    
    return JsonResponse({'success': False}, status=400)

@login_required
def download_scheme_pdf(request):
    """Generate PDF ya Scheme of Work kwa mtindo wa KitabuSmart"""
    if request.method == 'POST':
        data = json.loads(request.body)
        scheme_data = data.get('scheme_data')
        subject = data.get('subject')
        class_name = data.get('class_name')
        term = data.get('term')
        year = data.get('year')
        syllabus = data.get('syllabus')
        teacher_name = data.get('teacher_name')
        school_name = data.get('school_name')
        total_weeks = data.get('total_weeks')
        
        buffer = BytesIO()
        # Use landscape orientation for wide table
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), 
                                rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=14, spaceAfter=10, alignment=1)
        elements.append(Paragraph(f"{subject} - {class_name} - {term} {year} - {syllabus}", title_style))
        elements.append(Spacer(1, 6))
        
        # Teacher and School info
        info_style = ParagraphStyle('InfoStyle', parent=styles['Normal'], fontSize=9)
        elements.append(Paragraph(f"Teacher: {teacher_name} | School: {school_name} | Total Weeks: {total_weeks}", info_style))
        elements.append(Spacer(1, 12))
        
        if scheme_data:
            headers = list(scheme_data[0].keys())
            # Wrap long header text
            wrapped_headers = [h.replace(' & ', '&\n') for h in headers]
            table_data = [wrapped_headers]
            
            for row in scheme_data:
                row_data = []
                for h in headers:
                    val = row.get(h, '')
                    # Convert to string and handle long text
                    row_data.append(str(val) if val else '')
                table_data.append(row_data)
            
            # Calculate column widths based on content
            col_widths = [70, 80, 70, 80, 50, 40, 40, 60, 70, 70, 60, 60]  # approximate
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 7),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 6),
                ('WORDWRAP', (0, 0), (-1, -1), True),
            ]))
            elements.append(table)
        
        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Scheme_of_Work_{subject}_{class_name}.pdf"'
        return response
    
    return HttpResponse("Invalid request", status=400)    
# views.py - Ongeza hizi

from django.http import JsonResponse
from .models import EducationLevel, ClassLevel, Subject, Textbook

def get_classes_by_level(request):
    """AJAX endpoint to get classes based on education level"""
    level_id = request.GET.get('level_id')
    if level_id:
        classes = ClassLevel.objects.filter(education_level_id=level_id).values('id', 'name')
        return JsonResponse(list(classes), safe=False)
    return JsonResponse([], safe=False)

def get_subjects_by_level(request):
    """AJAX endpoint to get subjects based on education level"""
    level_id = request.GET.get('level_id')
    if level_id:
        try:
            education_level = EducationLevel.objects.get(id=level_id)
            level_name = education_level.name.lower()
            
            # Filter subjects based on education level
            if 'primary' in level_name:
                subjects = Subject.objects.filter(level='primary')
            elif 'ordinary' in level_name or 'secondary' in level_name:
                subjects = Subject.objects.filter(level='secondary')
                subjects = Subject.objects.all()
            
            return JsonResponse(list(subjects.values('id', 'name')), safe=False)
        except:
            return JsonResponse([], safe=False)
    return JsonResponse([], safe=False)

def get_textbooks_by_level(request):
    """AJAX endpoint to get textbooks based on education level"""
    level_id = request.GET.get('level_id')
    if level_id:
        try:
            education_level = EducationLevel.objects.get(id=level_id)
            textbooks = Textbook.objects.filter(
                education_level=education_level.name.lower(),
                is_active=True
            ).values('id', 'title')
            return JsonResponse(list(textbooks), safe=False)
        except:
            return JsonResponse([], safe=False)
    return JsonResponse([], safe=False)    
# =========================
# LESSON PLAN GENERATOR VIEWS
# =========================

# =========================
# LESSON PLAN GENERATOR VIEWS - CLEAN VERSION
# =========================

@login_required
@login_required
def lesson_plan_view(request):
    """Display lesson plan generator form"""
    from .models import EducationLevel, Subject

    education_levels = EducationLevel.objects.all().order_by('order')
    subjects = Subject.objects.all().order_by('name')

    return render(request, 'field_app/lesson_plan.html', {
        'education_levels': education_levels,
        'subjects': subjects,
    })

@csrf_exempt
@login_required
def ajax_generate_lessonplan(request):
    """Generate lesson plan using AI"""
    if request.method == 'POST':
        try:
            import json as json_module
            import re
            
            data = json_module.loads(request.body)
            
            # Extract form data
            education_level = data.get('education_level', '')
            class_name = data.get('class_name', '')
            subject = data.get('subject', '')
            topic = data.get('topic', '')
            subtopic = data.get('subtopic', '')
            term = data.get('term', 'I')
            year = data.get('year', 2026)
            duration = data.get('duration', 40)
            total_students = data.get('total_students', '')
            present_students = data.get('present_students', '')
            learning_objectives = data.get('learning_objectives', '')
            teaching_methods = data.get('teaching_methods', '')
            reference_source = data.get('reference_source', '')
            
            # Build AI prompt
            prompt = f"""
You are an AI assistant for Tanzanian teachers. Generate a detailed LESSON PLAN following TIE Tanzania standards.

Input Details:
- Education Level: {education_level}
- Class: {class_name}
- Subject: {subject}
- Topic: {topic}
- Subtopic: {subtopic}
- Term: {term}
- Year: {year}
- Duration: {duration} minutes
- Total Students: {total_students}
- Present Students: {present_students}
- Learning Objectives: {learning_objectives}
- Teaching Methods: {teaching_methods}
- Reference Source: {reference_source}

Output MUST be ONLY valid JSON. Do not include any other text. Use this exact structure:
{{
    "lesson_title": "{subject} - {topic}",
    "date": "today's date",
    "main_competence": "Main competence here",
    "specific_competence": "Specific competence here",
    "previous_knowledge": "Previous knowledge here",
    "learning_objectives": ["Objective 1", "Objective 2"],
    "teaching_methods": ["Method 1", "Method 2"],
    "teaching_resources": ["Resource 1", "Resource 2"],
    "lesson_development": [
        {{"time": "5 min", "stage": "Introduction", "teacher_activities": "Activities", "student_activities": "Activities", "assessment_criteria": "Criteria"}},
        {{"time": "15 min", "stage": "Presentation", "teacher_activities": "Activities", "student_activities": "Activities", "assessment_criteria": "Criteria"}},
        {{"time": "15 min", "stage": "Practice", "teacher_activities": "Activities", "student_activities": "Activities", "assessment_criteria": "Criteria"}},
        {{"time": "5 min", "stage": "Conclusion", "teacher_activities": "Activities", "student_activities": "Activities", "assessment_criteria": "Criteria"}}
    ],
    "remarks": "Remarks here"
}}
"""
            from .ai_utils import client, model_name
            
            print("🤖 Calling Gemini AI for Lesson Plan...")
            
            response = client.models.generate_content(model=model_name, contents=prompt)
            response_text = response.text
            
            print(f"✅ Gemini response received ({len(response_text)} characters)")
            
            # Clean response
            cleaned_text = re.sub(r'```json\s*', '', response_text)
            cleaned_text = re.sub(r'```\s*', '', cleaned_text)
            cleaned_text = cleaned_text.strip()
            
            # Find JSON object
            start_idx = cleaned_text.find('{')
            end_idx = cleaned_text.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_data = cleaned_text[start_idx:end_idx + 1]
                lesson_data = json_module.loads(json_data)
                return JsonResponse({'success': True, 'data': lesson_data})
            else:
                # Fallback response
                lesson_data = {
                    "lesson_title": f"{subject} - {topic}",
                    "date": timezone.now().strftime('%Y-%m-%d'),
                    "main_competence": f"Demonstrate understanding of {topic}",
                    "specific_competence": f"Explain key concepts of {topic}",
                    "previous_knowledge": "Basic knowledge from previous lessons",
                    "learning_objectives": [f"Define {topic}", f"Explain {topic}", f"Apply {topic}"],
                    "teaching_methods": ["Lecture", "Discussion", "Question and Answer"],
                    "teaching_resources": ["Chalkboard", "Textbook", "Handouts"],
                    "lesson_development": [
                        {"time": "5 min", "stage": "Introduction", "teacher_activities": f"Introduce {topic}", "student_activities": "Listen and respond", "assessment_criteria": "Participation"},
                        {"time": "15 min", "stage": "Presentation", "teacher_activities": "Explain key concepts", "student_activities": "Take notes and ask questions", "assessment_criteria": "Understanding demonstrated"},
                        {"time": "15 min", "stage": "Practice", "teacher_activities": "Guide through examples", "student_activities": "Work on exercises", "assessment_criteria": "Correct answers"},
                        {"time": "5 min", "stage": "Conclusion", "teacher_activities": "Summarize key points", "student_activities": "Review and ask questions", "assessment_criteria": "Recall of main points"}
                    ],
                    "remarks": "Students participated well"
                }
                return JsonResponse({'success': True, 'data': lesson_data})
            
        except Exception as e:
            print(f"Lesson Plan generation error: {e}")
            import traceback
            traceback.print_exc()
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False}, status=400)
@login_required
def api_get_schools(request):
    """API endpoint for AJAX school search"""
    district_id = request.GET.get('district_id')
    level = request.GET.get('level', 'Secondary')
    query = request.GET.get('q', '').strip()
    
    if not district_id:
        return JsonResponse({'success': False, 'error': 'District ID required'})
    
    district = get_object_or_404(District, id=district_id)
    current_year = get_current_academic_year()
    
    # Get pinned schools
    pinned_school_ids = []
    if current_year:
        pinned_school_ids = list(SchoolPin.objects.filter(
            academic_year=current_year,
            is_pinned=True
        ).values_list('school_id', flat=True))
    
    # Base queryset
    schools_qs = School.objects.filter(district=district, level=level)
    
    if query:
        schools_qs = schools_qs.filter(name__icontains=query)
    
    # Process schools
    schools_data = []
    available_count = 0
    pinned_count = 0
    full_count = 0
    
    for school in schools_qs:
        is_pinned = school.id in pinned_school_ids
        is_selectable = (not is_pinned) and (school.current_students < school.capacity)
        
        if is_pinned:
            pinned_count += 1
        elif not is_selectable:
            full_count += 1
            available_count += 1
        
        occupancy = round((school.current_students / school.capacity) * 100) if school.capacity > 0 else 0
        
        schools_data.append({
            'id': school.id,
            'name': school.name,
            'level_display': school.get_level_display(),
            'current_students': school.current_students,
            'capacity': school.capacity,
            'occupancy_percentage': occupancy,
            'is_pinned': is_pinned,
            'is_selectable': is_selectable,
        })
    
    return JsonResponse({
        'success': True,
        'schools': schools_data,
        'total_schools': schools_qs.count(),
        'available_schools': available_count,
        'pinned_schools': pinned_count,
        'full_schools': full_count,
    })
@csrf_exempt
@login_required
def api_select_school_temp(request):
    """Temporarily store selected school in session"""
    if request.method == 'POST':
        data = json.loads(request.body)
        school_id = data.get('school_id')
        if school_id:
            request.session['temp_selected_school_id'] = school_id
            return JsonResponse({'success': True})
    return JsonResponse({'success': False})        
@csrf_exempt
@login_required
def api_clear_selected_school(request):
    """Clear selected school from session"""
    if request.method == 'POST':
        request.session.pop('temp_selected_school', None)
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})    
@login_required
def api_filter_schools(request):
    """API endpoint for filtering schools - shows only selected school"""
    district_id = request.GET.get('district_id')
    selected_school_id = request.GET.get('selected_school_id')
    
    if not district_id:
        return JsonResponse({'success': False, 'error': 'District ID required'})
    
    district = get_object_or_404(District, id=district_id)
    current_year = get_current_academic_year()
    
    # Get pinned schools
    pinned_school_ids = []
    if current_year:
        pinned_school_ids = list(SchoolPin.objects.filter(
            academic_year=current_year,
            is_pinned=True
        ).values_list('school_id', flat=True))
    
    # Get all schools first
    schools_qs = School.objects.filter(district=district)
    
    # If selected_school_id is provided, show ONLY that school
    if selected_school_id:
        schools_qs = schools_qs.filter(id=selected_school_id)
    
    schools_data = []
    for school in schools_qs:
        is_pinned = school.id in pinned_school_ids
        is_selectable = (not is_pinned) and (school.current_students < school.capacity)
        occupancy = round((school.current_students / school.capacity) * 100) if school.capacity > 0 else 0
        
        schools_data.append({
            'id': school.id,
            'name': school.name,
            'level_display': school.get_level_display(),
            'current_students': school.current_students,
            'capacity': school.capacity,
            'occupancy_percentage': occupancy,
            'is_pinned': is_pinned,
            'is_selectable': is_selectable,
        })
    
    return JsonResponse({
        'success': True,
        'schools': schools_data,
        'total_schools': schools_qs.count(),
    })    
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


# =========================
# ADMIN REPORTS
# =========================

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


# ============================================================
# BODI YA WALIMU — Teacher Board System
# ============================================================

def _get_board_member(request):
    """Return BoardMember for current user or None."""
    try:
        return request.user.board_member
    except Exception:
        return None


def board_login(request):
    if request.user.is_authenticated and _get_board_member(request):
        return redirect('board_home')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=email, password=password,
                            backend='field_app.backends.EmailBackend')
        if user:
            bm = None
            try:
                bm = user.board_member
            except Exception:
                pass
            if bm and bm.is_active:
                login(request, user, backend='field_app.backends.EmailBackend')
                return redirect('board_home')
        messages.error(request, 'Barua pepe au nywila si sahihi, au huna ruhusa ya Bodi ya Walimu.')

    return render(request, 'field_app/board_login.html')


def board_logout(request):
    logout(request)
    return redirect('board_login')


@login_required
def board_home(request):
    bm = _get_board_member(request)
    if not bm:
        messages.error(request, 'Huna ruhusa ya Bodi ya Walimu.')
        return redirect('board_login')

    regions = Region.objects.all().order_by('name').annotate(
        student_count=Count('district__school__studentteacher',
                            filter=Q(district__school__studentteacher__selected_school__isnull=False),
                            distinct=True),
        district_count=Count('district', distinct=True),
    )
    return render(request, 'field_app/board_home.html', {
        'bm': bm,
        'regions': regions,
    })


@login_required
def board_district_list(request, region_id):
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')
    region = get_object_or_404(Region, id=region_id)
    districts = District.objects.filter(region=region).order_by('name').annotate(
        school_count=Count('school', distinct=True),
        student_count=Count('school__studentteacher',
                            filter=Q(school__studentteacher__selected_school__isnull=False),
                            distinct=True),
    )
    return render(request, 'field_app/board_district_list.html', {
        'bm': bm,
        'region': region,
        'districts': districts,
    })


@login_required
def board_school_list(request, district_id):
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')
    district = get_object_or_404(District, id=district_id)
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

    students_data = []
    for school in schools:
        sts = StudentTeacher.objects.filter(selected_school=school).select_related('user')
        for st in sts:
            lb_count = LogbookEntry.objects.filter(student=st).count()
            latest_lb = LogbookEntry.objects.filter(student=st).first()
            latest_lp = LessonPlan.objects.filter(student=st, school=school).first()
            first_lesson = _lb_first_lesson(latest_lb)
            # Extract display fields — check lessons_data first, fallback to old fields
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
            })
    return render(request, 'field_app/board_school_list.html', {
        'bm': bm,
        'district': district,
        'schools': schools,
        'students_data': students_data,
    })


@login_required
def board_student_progress(request, student_id):
    bm = _get_board_member(request)
    if not bm:
        return redirect('board_login')
    student = get_object_or_404(StudentTeacher, id=student_id)
    school = student.selected_school

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

    return render(request, 'field_app/board_student_progress.html', {
        'bm': bm,
        'student': student,
        'school': school,
        'logbook_entries': logbook_entries,
        'logbook_display': logbook_display,
        'lesson_plans': lesson_plans,
        'schemes': schemes,
        'applications': applications,
        'board_comments': board_comments,
        'month_entry_count': month_entries.count(),
        'total_entries': total_entries,
        'topics_covered': topics_covered,
        'today': today,
    })


@login_required
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


@staff_member_required
def create_board_member(request):
    """Admin: create a board member account."""
    User = get_user_model()
    regions = Region.objects.all().order_by('name')
    districts = District.objects.all().order_by('name')

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        phone = request.POST.get('phone_number', '').strip()
        role = request.POST.get('role', 'member')
        region_id = request.POST.get('region') or None
        district_id = request.POST.get('district') or None

        if not full_name or not email or not password:
            messages.error(request, 'Jaza jina, barua pepe, na nywila.')
        elif User.objects.filter(email=email).exists():
            messages.error(request, f"Mtumiaji mwenye email '{email}' tayari yupo.")
        elif len(password) < 6:
            messages.error(request, 'Nywila iwe na herufi 6 au zaidi.')
        else:
            user = User.objects.create_user(email=email, password=password)
            user.is_staff = False
            user.save()
            region = Region.objects.filter(id=region_id).first() if region_id else None
            district = District.objects.filter(id=district_id).first() if district_id else None
            BoardMember.objects.create(
                user=user,
                full_name=full_name,
                phone_number=phone,
                role=role,
                region=region,
                district=district,
            )
            messages.success(request, f'Mjumbe wa Bodi "{full_name}" ametengenezwa.')
            return redirect('admin_dashboard')

    return render(request, 'field_app/create_board_member.html', {
        'regions': regions,
        'districts': districts,
        'role_choices': BoardMember.ROLE_CHOICES,
    })
