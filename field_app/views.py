# views.py - COMPLETE UPDATED VERSION
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.contrib.gis.geos import Point
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.gis.db.models.functions import Distance
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Prefetch
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
#from .models import AcademicYear
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Case, When, Value, BooleanField, F, Q
from django.http import HttpResponse, JsonResponse
from django.core.mail import send_mail
from django.http import HttpResponseNotAllowed
from django.urls import reverse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import csv
import io
import secrets
import string
import json
from io import BytesIO
from reportlab.pdfgen import canvas

from .forms import (
    CustomLoginForm, StudentRegistrationForm, StudentTeacherForm, 
    LogbookForm, AssessorLoginForm, BulkAssignForm, RegionFieldInputForm
)
from .models import (
    Assessor, School, SchoolAssignment, StudentTeacher, 
    StudentAssessment, SchoolAssessment, SchoolRequirement, 
    StudentApplication, Region, RegionPin, SchoolPin, 
    Region, District, Subject, SchoolSubjectCapacity, 
    LogbookEntry, ApprovalLetter, AcademicYear
)
from geopy.distance import geodesic
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model

User = get_user_model()

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
            <h3 style="margin-top: 0; color: #d97706;">🆕 NEW ASSESSOR ACCOUNT</h3>
            <p style="margin: 10px 0;"><strong>📧 Email:</strong> {assessor.email}</p>
            <p style="margin: 10px 0;"><strong>🔑 Temporary Password:</strong> <code style="background-color: #fff3cd; padding: 4px 8px; border-radius: 4px; font-size: 16px;">{temp_password}</code></p>
            <p style="margin: 10px 0; color: #856404;">⚠️ Please change your password immediately after first login</p>
        </div>
        """
    else:
        credential_html = f"""
        <div style="background-color: #e3f2fd; border-left: 4px solid #2196f3; padding: 20px; margin: 20px 0; border-radius: 8px;">
            <h3 style="margin-top: 0; color: #1976d2;">🔄 NEW ACADEMIC YEAR {assessor.current_academic_year.year if assessor.current_academic_year else '2024/2025'}</h3>
            <p style="margin: 10px 0;"><strong>📧 Email:</strong> {assessor.email}</p>
            <p style="margin: 10px 0;"><strong>🔑 New Password:</strong> <code style="background-color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 16px;">{temp_password}</code></p>
            <p style="margin: 10px 0; color: #d32f2f;">🔐 Your password has been reset for the new academic year</p>
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
                
                # Use email only - NO username field
                user = User.objects.create_user(
                    email=assessor.email,
                    password=temp_password,
                    is_staff=False,
                    is_active=True
                )
                
                assessor.user = user
                assessor.current_academic_year = current_academic_year
                assessor.save()
                
                print(f"✅ Account created with email: {assessor.email}")
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
            else:
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
        else:
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
    """Hakikisha kila user ana StudentTeacher profile"""
    try:
        return StudentTeacher.objects.get(user=user)
    except StudentTeacher.DoesNotExist:
        email_username = user.email.split('@')[0] if user.email else user.username
        return StudentTeacher.objects.create(
            user=user,
            full_name=email_username,
            phone_number='Not provided'
        )

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
            login(request, user)
            
            try:
                assessor = Assessor.objects.get(user=user)
                messages.warning(request, 
                    f"You are registered as an assessor. Please use the assessor login page."
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
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    
    # Check if user was an assessor (based on session or referer)
    referer = request.META.get('HTTP_REFERER', '')
    
    if 'assessor' in referer or 'assessor_dashboard' in referer:
        return redirect('assessor_login')
    else:
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
                else:
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
            login(request, user)
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
                login(request, user)
                
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
    
    # Check if user is assessor
    try:
        assessor = Assessor.objects.get(user=request.user)
        messages.info(request, "Redirecting to assessor dashboard")
        return redirect('assessor_dashboard')
    except Assessor.DoesNotExist:
        pass
    
    student = get_or_create_student_profile(request.user)
    current_year = AcademicYear.objects.filter(is_active=True).first()

    if current_year:
        pinned_region_ids = RegionPin.objects.filter(
            academic_year=current_year,
            is_pinned=True
        ).values_list('region_id', flat=True)
        pinned_regions = Region.objects.filter(id__in=pinned_region_ids)
    else:
        pinned_regions = Region.objects.none()
    
    assessors = []
    if student.selected_school:
        school_assessments = SchoolAssessment.objects.filter(
            school=student.selected_school
        ).select_related('assessor')
        
        for assessment in school_assessments:
            assessors.append({
                'assessor': assessment.assessor,
                'assignment_date': assessment.assessment_date,
                'is_completed': assessment.is_completed
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
        logbook_entries = LogbookEntry.objects.filter(student=student).order_by('-date')[:5]

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
    
    return render(request, 'field_app/assessor_dashboard.html', {
        'assessor': assessor,
        'schools_data': schools_data,
        'total_schools': school_assignments.count(),
        'total_students': total_students_all_schools,
        'current_year': current_year,
        #'hide_navbar': True,  # 
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
    request.session['selected_region_id'] = region.id
    return render(request, 'field_app/select_district.html', {'districts': districts, 'region': region})

@login_required
def select_school(request, district_id):
    district = get_object_or_404(District, id=district_id)
    current_year = AcademicYear.objects.filter(is_active=True).first()
    
    # ========== FIX: Get ALL pinned schools for this year ==========
    pinned_school_ids = []
    pinned_schools_info = {}
    
    if current_year:
        # Get ALL pinned schools for this academic year
        pinned_schools = SchoolPin.objects.filter(
            academic_year=current_year,
            is_pinned=True
        ).select_related('problem_details')
        
        for pin in pinned_schools:
            pinned_school_ids.append(pin.school_id)
            pinned_schools_info[pin.school_id] = {
                'reason': pin.get_pin_reason_display() if hasattr(pin, 'get_pin_reason_display') else 'Manual',
                'notes': pin.notes
            }
    
    # Base queryset - all schools in this district
    search_query = request.GET.get('q', '')
    selected_level = request.GET.get('level', 'Secondary')
    raw_schools = School.objects.filter(district=district, level=selected_level)
    
    if search_query:
        raw_schools = raw_schools.filter(name__icontains=search_query)
    
    # Process schools
    schools = []
    for school in raw_schools:
        # Check if school is pinned
        school.is_pinned = school.id in pinned_school_ids
        
        # Store pin info if pinned
        if school.is_pinned:
            school.pin_info = pinned_schools_info.get(school.id, {})
            school.pin_reason = school.pin_info.get('reason', 'Manual Pin')
            school.pin_notes = school.pin_info.get('notes', 'This school is temporarily unavailable')
        else:
            school.pin_reason = ''
            school.pin_notes = ''
        
        # 🔴 FIX: A school is selectable ONLY IF:
        # 1. NOT pinned AND
        # 2. Has capacity available
        school.is_selectable = (not school.is_pinned) and (school.current_students < school.capacity)
        
        # Calculate occupancy
        if school.capacity > 0:
            occupancy = round((school.current_students / school.capacity) * 100)
        else:
            occupancy = 0
        school.occupancy_percentage = occupancy
        
        schools.append(school)
    
    # Statistics
    total_schools = len(schools)
    pinned_schools_count = sum(1 for s in schools if s.is_pinned)
    available_schools_count = sum(1 for s in schools if s.is_selectable)
    full_schools_count = sum(1 for s in schools if not s.is_pinned and not s.is_selectable)
    
    # Get selected school from session
    selected_school_id = request.session.get('selected_school_id')
    selected_school = School.objects.filter(id=selected_school_id, district=district).first() if selected_school_id else None
    
    # Handle POST actions
    if request.method == 'POST':
        action = request.POST.get('action')
        school_id = request.POST.get('school_id')
        
        if action == 'cancel':
            if selected_school:
                # Decrement counter
                School.objects.filter(id=selected_school.id).update(current_students=F('current_students') - 1)
                request.session.pop('selected_school_id', None)
                messages.success(request, 'You have cancelled your selected school.')
                return redirect('select_school', district_id=district.id)
        
        elif action == 'confirm':
            if selected_school:
                student = get_or_create_student_profile(request.user)
                student.selected_school = selected_school
                student.save()
                
                messages.success(request, 'School confirmed. Now select your teaching subjects.')
                return redirect('select_subjects', school_id=selected_school.id)
            else:
                messages.error(request, 'No school selected to confirm.')
        
        elif action == 'select':
            school = get_object_or_404(School, id=school_id, district=district)
            
            # 🔴 FIX: Check if school is pinned again (for security)
            is_pinned = school.id in pinned_school_ids
            
            if is_pinned:
                # Get pin reason
                pin_info = pinned_schools_info.get(school.id, {})
                pin_notes = pin_info.get('notes', 'This school is temporarily unavailable')
                messages.error(request, f'This school is currently unavailable. Reason: {pin_notes}')
                return redirect('select_school', district_id=district.id)
            
            # Check capacity
            if school.current_students >= school.capacity:
                messages.error(request, 'This school is already full.')
                return redirect('select_school', district_id=district.id)
            
            # Check if already selected another school
            if selected_school:
                messages.error(request, 'You have already selected a school. Cancel it first.')
            else:
                # Select the school
                request.session['selected_school_id'] = school.id
                School.objects.filter(id=school.id).update(current_students=F('current_students') + 1)
                messages.success(request, f'You selected {school.name}. Confirm or Cancel?')
                return redirect('select_school', district_id=district.id)
    
    return render(request, 'field_app/select_school.html', {
        'district': district,
        'schools': schools,
        'selected_school': selected_school,
        'query': search_query,
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
                messages.info(request, f"You have already applied for {subject.name}")
            else:
                if capacity.current_students >= capacity.max_students:
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
    
    # Get or create today's logbook entry
    logbook_entry, created = LogbookEntry.objects.get_or_create(
        student=student,
        date=today,
        defaults={
            'school': school,
            'morning_check_in': timezone.now()
        }
    )
    
    if request.method == 'POST':
        form = LogbookForm(request.POST, instance=logbook_entry)
        
        # Get location data from POST
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        is_location_verified_str = request.POST.get('is_location_verified', 'false')
        
        print(f"\n📍 LOCATION DEBUG:")
        print(f"   Latitude: {latitude}")
        print(f"   Longitude: {longitude}")
        print(f"   is_location_verified from form: {is_location_verified_str}")
        
        # ========== FIX 1: Check if location verification is TRUE ==========
        is_location_verified = is_location_verified_str == 'true'
        
        if not is_location_verified:
            messages.error(request, 
                "❌ Hujaweza kujaza logbook. Lazima uthibitishe eneo lako la Dodoma kwanza.\n"
                "Bonyeza kitufe cha 'Thibitisha Eneo Langu' kabla ya kuwasilisha logbook."
            )
            # Re-render with form and error
            days_swahili = {
                0: 'Jumatatu', 1: 'Jumanne', 2: 'Jumatano',
                3: 'Alhamisi', 4: 'Ijumaa'
            }
            return render(request, 'field_app/logbook.html', {
                'form': form,
                'student': student,
                'logbook_entry': logbook_entry,
                'today': today,
                'today_name': days_swahili.get(today.weekday(), 'Leo'),
                'school': school,
                'location_error': True,  # Add flag for template
            })
        
        # ========== FIX 2: Validate coordinates exist ==========
        if not latitude or not longitude:
            messages.error(request, 
                "❌ Eneo halikupatikana. Tafadhali:\n"
                "1. Hakikisha umewasha GPS kwenye simu yako\n"
                "2. Ruhusu tovuti kutumia eneo lako\n"
                "3. Bonyeza 'Thibitisha Eneo Langu' tena"
            )
            days_swahili = {
                0: 'Jumatatu', 1: 'Jumanne', 2: 'Jumatano',
                3: 'Alhamisi', 4: 'Ijumaa'
            }
            return render(request, 'field_app/logbook.html', {
                'form': form,
                'student': student,
                'logbook_entry': logbook_entry,
                'today': today,
                'today_name': days_swahili.get(today.weekday(), 'Leo'),
                'school': school,
                'location_error': True,
            })
        
        try:
            # Save coordinates
            logbook_entry.latitude = float(latitude)
            logbook_entry.longitude = float(longitude)
            logbook_entry.location_address = request.POST.get('location_address', '')
            
            lat = logbook_entry.latitude
            lng = logbook_entry.longitude
            
            # ========== FIX 3: Correct Dodoma coordinates check ==========
            # Dodoma city coordinates: Approximately -6.162959, 35.751607
            # Make bounding box a bit larger to be forgiving
            # Dodoma region bounds: Latitude -4.0 to -7.5, Longitude 33.5 to 37.0
            
            # More accurate Dodoma Urban/West bounds
            is_in_dodoma = (-6.5 <= lat <= -5.5) and (35.0 <= lng <= 36.5)
            
            print(f"   Checking Dodoma bounds:")
            print(f"      Lat {lat} is between -6.5 and -5.5? {-6.5 <= lat <= -5.5}")
            print(f"      Lng {lng} is between 35.0 and 36.5? {35.0 <= lng <= 36.5}")
            print(f"      Result: {is_in_dodoma}")
            
            if is_in_dodoma:
                logbook_entry.is_location_verified = True
                logbook_entry.is_at_school = True
                print(f"   ✅ Location VERIFIED - in Dodoma")
            else:
                logbook_entry.is_location_verified = False
                logbook_entry.is_at_school = False
                print(f"   ⚠️ Location NOT in Dodoma - lat={lat}, lng={lng}")
                
        except (ValueError, TypeError) as e:
            print(f"   ❌ Location conversion error: {e}")
            messages.error(request, f"Hitilafu katika usajili wa eneo: {str(e)}")
            days_swahili = {
                0: 'Jumatatu', 1: 'Jumanne', 2: 'Jumatano',
                3: 'Alhamisi', 4: 'Ijumaa'
            }
            return render(request, 'field_app/logbook.html', {
                'form': form,
                'student': student,
                'logbook_entry': logbook_entry,
                'today': today,
                'today_name': days_swahili.get(today.weekday(), 'Leo'),
                'school': school,
            })
        
        # Validate form
        if form.is_valid():
            entry = form.save(commit=False)
            
            # Auto-set afternoon check-out if activity is filled
            if entry.afternoon_activity and not entry.afternoon_check_out:
                entry.afternoon_check_out = timezone.now()
            
            # Save with location data
            entry.latitude = logbook_entry.latitude
            entry.longitude = logbook_entry.longitude
            entry.is_location_verified = logbook_entry.is_location_verified
            entry.is_at_school = logbook_entry.is_at_school
            entry.location_address = logbook_entry.location_address
            entry.save()
            
            if entry.is_location_verified:
                messages.success(request, "✅ Logbook imesajiliwa kikamilifu! Eneo lako limehakikiwa.")
            else:
                messages.warning(request, 
                    f"⚠️ Logbook imesajiliwa lakini eneo lako halipo Dodoma.\n"
                    f"Mahali ulipo: Lat {lat:.4f}, Lng {lng:.4f}"
                )
            
            return redirect('logbook_history')
        else:
            messages.error(request, "Tafadhali kagua makosa yaliyomo kwenye fomu.")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = LogbookForm(instance=logbook_entry)
    
    days_swahili = {
        0: 'Jumatatu',
        1: 'Jumanne', 
        2: 'Jumatano',
        3: 'Alhamisi',
        4: 'Ijumaa'
    }
    
    return render(request, 'field_app/logbook.html', {
        'form': form,
        'student': student,
        'logbook_entry': logbook_entry,
        'today': today,
        'today_name': days_swahili.get(today.weekday(), 'Leo'),
        'school': school,
    })
@login_required
def logbook_history(request):
    student = get_or_create_student_profile(request.user)
    
    week_filter = request.GET.get('week')
    month_filter = request.GET.get('month')
    
    entries = LogbookEntry.objects.filter(student=student)
    
    if week_filter:
        try:
            year, week = map(int, week_filter.split('-W'))
            start_date = datetime.strptime(f'{year}-W{week}-1', "%Y-W%W-%w").date()
            end_date = start_date + timedelta(days=6)
            entries = entries.filter(date__range=[start_date, end_date])
        except ValueError:
            messages.error(request, "Tarehe ya wiki si sahihi.")
    
    if month_filter:
        try:
            year, month = map(int, month_filter.split('-'))
            entries = entries.filter(date__year=year, date__month=month)
        except ValueError:
            messages.error(request, "Tarehe ya mwezi si sahihi.")
    
    if not week_filter and not month_filter:
        today = timezone.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=4)
        entries = entries.filter(date__range=[start_of_week, end_of_week])
    
    entries = entries.order_by('-date')
    
    return render(request, 'field_app/logbook_history.html', {
        'entries': entries,
        'student': student,
    })

@login_required
def download_logbook_pdf(request, period=None, period_type=None):
    """Download logbook as PDF - Flexible parameter handling"""
    student = get_or_create_student_profile(request.user)
    
    # Handle both parameter names
    period_value = period or period_type or 'week'
    
    today = timezone.now().date()
    start_date = end_date = today
    
    if period_value == 'today':
        entries = LogbookEntry.objects.filter(student=student, date=today)
        filename = f"logbook_{today}.pdf"
        title = f"Logbook ya {today}"
        
    elif period_value == 'week':
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=4)
        entries = LogbookEntry.objects.filter(
            student=student, 
            date__range=[start_of_week, end_of_week]
        )
        filename = f"logbook_week_{start_of_week}_to_{end_of_week}.pdf"
        title = f"Logbook ya Wiki ya {start_of_week} mpaka {end_of_week}"
        
    elif period_value == 'month':
        start_of_month = today.replace(day=1)
        next_month = today.replace(day=28) + timedelta(days=4)
        end_of_month = next_month - timedelta(days=next_month.day)
        entries = LogbookEntry.objects.filter(
            student=student,
            date__range=[start_of_month, end_of_month]
        )
        filename = f"logbook_month_{today.year}_{today.month}.pdf"
        title = f"Logbook ya Mwezi {today.month}/{today.year}"
        
    elif period_value == 'all':
        entries = LogbookEntry.objects.filter(student=student)
        filename = f"logbook_all_{today}.pdf"
        title = f"Logbook Zote - {today}"
        
    else:
        entries = LogbookEntry.objects.filter(student=student)
        filename = f"logbook_all_{today}.pdf"
        title = f"Logbook Zote - {today}"
    
    # Rest of your PDF generation code remains the same...
    entries = entries.order_by('date')
    
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, title)
    p.setFont("Helvetica", 10)
    p.drawString(100, 780, f"Jina: {student.full_name}")
    p.drawString(100, 765, f"Shule: {student.selected_school.name if student.selected_school else 'Haijachaguliwa'}")
    p.drawString(400, 780, f"Tarehe: {today}")
    
    y_position = 740
    for entry in entries:
        if y_position < 100:
            p.showPage()
            y_position = 800
            p.setFont("Helvetica-Bold", 12)
            p.drawString(100, y_position, title + " (Endelea...)")
            y_position = 780
        
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, y_position, f"Siku: {entry.get_day_of_week_display()} - {entry.date}")
        y_position -= 20
        
        p.setFont("Helvetica", 10)
        p.drawString(120, y_position, "Shughuli za Asubuhi:")
        y_position -= 15
        p.setFont("Helvetica", 9)
        morning_text = entry.morning_activity or "Hakuna data"
        for line in morning_text.split('\n'):
            if y_position < 100:
                p.showPage()
                y_position = 800
                p.setFont("Helvetica", 9)
            p.drawString(140, y_position, line[:80])
            y_position -= 12
        
        y_position -= 5
        p.setFont("Helvetica", 10)
        p.drawString(120, y_position, "Shughuli za Mchana:")
        y_position -= 15
        p.setFont("Helvetica", 9)
        afternoon_text = entry.afternoon_activity or "Hakuna data"
        for line in afternoon_text.split('\n'):
            if y_position < 100:
                p.showPage()
                y_position = 800
                p.setFont("Helvetica", 9)
            p.drawString(140, y_position, line[:80])
            y_position -= 12
        
        y_position -= 5
        p.setFont("Helvetica", 10)
        p.drawString(120, y_position, "Changamoto:")
        y_position -= 15
        p.setFont("Helvetica", 9)
        challenges_text = entry.challenges_faced or "Hakuna data"
        for line in challenges_text.split('\n'):
            if y_position < 100:
                p.showPage()
                y_position = 800
                p.setFont("Helvetica", 9)
            p.drawString(140, y_position, line[:80])
            y_position -= 12
        
        y_position -= 5
        p.setFont("Helvetica", 10)
        p.drawString(120, y_position, "Mafunzo:")
        y_position -= 15
        p.setFont("Helvetica", 9)
        lessons_text = entry.lessons_learned or "Hakuna data"
        for line in lessons_text.split('\n'):
            if y_position < 100:
                p.showPage()
                y_position = 800
                p.setFont("Helvetica", 9)
            p.drawString(140, y_position, line[:80])
            y_position -= 12
        
        y_position -= 10
        status = "Imehakikiwa" if entry.is_location_verified else "Haijahakikiwa"
        p.drawString(120, y_position, f"Eneo: {status}")
        y_position -= 20
        
        p.line(100, y_position, 500, y_position)
        y_position -= 20
    
    p.showPage()
    p.save()
    
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
        else:
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
                
                username = assessor.email.split('@')[0]
                
                counter = 1
                original_username = username
                while User.objects.filter(username=username).exists():
                    username = f"{original_username}_{counter}"
                    counter += 1
                
                try:
                    user = User.objects.create_user(
                        username=username,
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
                else:
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
                else:
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
                else:
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
        else:
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
            if not assessor.current_academic_year or assessor.current_academic_year != current_year:
                assessor.needs_new_credentials = True
                assessor.year_status = f"Mpya kwa {current_year.year}"
            elif not assessor.user:
                assessor.needs_new_credentials = True
                assessor.year_status = "Hakuna akaunti"
            else:
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
    
    else:
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
            else:
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
                else:
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
                else:
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
                else:
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
                else:
                    print(f"ℹ️ No schools found in hidden regions")
            else:
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
            else:
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
            # Fall through to GET handling to show form with errors
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
    
    # 🔴 FIX: Filter by academic_year
    if current_year:
        school_assessments = SchoolAssessment.objects.filter(
            school=school,
            academic_year=current_year  # ← MUHIMU: Filter kwa mwaka wa sasa
        ).select_related('assessor')
        
        print(f"   Found {school_assessments.count()} assessors for {current_year.year}")
    else:
        school_assessments = SchoolAssessment.objects.none()
        print(f"   No active academic year found!")
    
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
        else:
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
        else:
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
        else:
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
        else:
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
            
            send_mail(
                subject='🔐 Password Reset - Field Placement System',
                message=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[assessor.email],
                html_message=html_content,
                fail_silently=False,
            )
            
            messages.success(request, 
                f'✅ A new temporary password has been sent to {assessor.email}. '
                f'Please check your inbox and spam folder.'
            )
            return redirect('assessor_login')
            
        except Assessor.DoesNotExist:
            messages.error(request, f'No assessor found with email: {email}')
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
