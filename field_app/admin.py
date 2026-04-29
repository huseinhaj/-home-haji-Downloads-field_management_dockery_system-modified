from django.contrib import admin
from django.contrib.admin import AdminSite
from django.urls import path, reverse
from django.shortcuts import render, redirect
from django.contrib import messages
from django import forms

from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator

import csv
import io
from django.utils import timezone
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.db.models import F
import pdfplumber
from docx import Document
import openai
from .models import Assessor, SchoolAssessment, StudentAssessment

import json
import os
from dotenv import load_dotenv

from .models import (
    CustomUser, StudentTeacher, Region, District, School, Subject,
    SchoolSubjectCapacity, LogbookEntry, ApprovalLetter,
    SchoolUpdateFile, SchoolRequirement, StudentApplication,
    AcademicYear, RegionPin, SchoolPin
)

# OpenAI configuration
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

class CustomAdminSite(AdminSite):
    site_header = "Field Management Admin"
    site_title = "Field Panel"
    index_title = "Karibu Admin"
    index_template = 'admin/index.html'

    def each_context(self, request):
        context = super().each_context(request)
        if request.user.is_staff:
            context['region_pinning_url'] = reverse('pin_regions')
        return context

custom_admin_site = CustomAdminSite(name='custom_admin')

# 🔥 ONGEZA: CSV Upload Form kwa Admin
class CsvImportForm(forms.Form):
    csv_file = forms.FileField()

# =========================
# ASSESSOR ADMIN - REKEBISHWA KWA CSV UPLOAD
# =========================

# field_app/admin.py - SIMPLE VERSION 
# field_app/admin.py - CORRECTED ASSESSOR ADMIN
# field_app/admin.py - SIMPLE VERSION 
# admin.py - FIXED AssessorAdmin

class AssessorAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'get_email', 'phone_number', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['full_name', 'phone_number', 'email']
    readonly_fields = ['created_at']
    
    # Use this to show email from the model field
    def get_email(self, obj):
        return obj.email or "No email"
    get_email.short_description = 'Email'
    
    # Fields to show in admin form
    fieldsets = (
        ('Basic Information', {
            'fields': ('full_name', 'email', 'phone_number', 'is_active')
        }),
        ('User Account', {
            'fields': ('user',),
            'description': 'User account will be auto-created if email is provided'
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def get_urls(self):
        from django.urls import path
        from django.http import HttpResponse
        
        urls = super().get_urls()
        my_urls = [
            path('import-csv/', self.import_csv_view, name='import_csv'),
        ]
        return my_urls + urls

    def import_csv_view(self, request):
        from django.shortcuts import render
        import csv
        import io
        from django.contrib import messages
        
        if request.method == "POST" and request.FILES.get("csv_file"):
            csv_file = request.FILES["csv_file"]
            
            try:
                # Read CSV file
                data_set = csv_file.read().decode('UTF-8')
                io_string = io.StringIO(data_set)
                reader = csv.DictReader(io_string)
                
                success_count = 0
                error_count = 0
                
                for row_num, row in enumerate(reader, 1):
                    try:
                        full_name = row.get('full_name', '').strip()
                        phone_number = row.get('phone_number', '').strip()
                        email = row.get('email', '').strip()
                        
                        # Validate required fields
                        if not full_name:
                            messages.error(request, f"Row {row_num}: Missing full_name")
                            error_count += 1
                            continue
                        
                        if not phone_number:
                            phone_number = "Not provided"
                        
                        # Check if email already exists
                        if email and Assessor.objects.filter(email=email).exists():
                            messages.warning(request, f"Row {row_num}: Email '{email}' already exists")
                            error_count += 1
                            continue
                        
                        # Create assessor
                        assessor = Assessor.objects.create(
                            full_name=full_name,
                            email=email or None,
                            phone_number=phone_number,
                            is_active=True
                        )
                        
                        success_count += 1
                        messages.success(request, f"✅ Created assessor: {full_name}")
                        
                    except Exception as e:
                        messages.error(request, f"Row {row_num}: Error - {str(e)}")
                        error_count += 1
                
                if success_count > 0:
                    messages.success(request, f'✅ Successfully imported {success_count} assessors')
                if error_count > 0:
                    messages.warning(request, f'⚠️ Failed to import {error_count} assessors')
                
                return redirect("..")
                
            except Exception as e:
                messages.error(request, f"Error processing CSV: {str(e)}")
        
        # GET request - show form
        context = {
            'title': 'Import Assessors from CSV',
        }
        return render(request, 'admin/import_csv.html', context)
# CUSTOM USER ADMIN
# =========================
class CustomUserAdmin(BaseUserAdmin):
    ordering = ['email']
    list_display = ['email', 'is_staff', 'is_active']
    list_filter = ['is_staff', 'is_active']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Permissions'), {'fields': ('is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )

    search_fields = ('email',)

# =========================
# STUDENT TEACHER ADMIN
# =========================
class StudentTeacherAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'user', 'phone_number', 'selected_school', 'approval_status', 'approval_date']
    list_filter = ['approval_status', 'selected_school', 'approval_date']
    search_fields = ['full_name', 'phone_number', 'user__email']
    readonly_fields = ['approval_date', 'approved_by']

    actions = ['approve_selected', 'reject_selected']

    def approve_selected(self, request, queryset):
        updated = queryset.filter(approval_status='pending').update(
            approval_status='approved',
            approval_date=timezone.now(),
            approved_by=request.user
        )
        self.message_user(request, f"{updated} student(s) approved successfully.")

    def reject_selected(self, request, queryset):
        updated = queryset.filter(approval_status='pending').update(
            approval_status='rejected',
            approval_date=timezone.now(),
            approved_by=request.user
        )
        self.message_user(request, f"{updated} student(s) rejected successfully.")

    approve_selected.short_description = "Approve selected students"
    reject_selected.short_description = "Reject selected students"

# =========================
# STUDENT APPLICATION ADMIN
# =========================
class StudentApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'student', 
        'subject', 
        'school', 
        'application_date', 
        'status', 
        'approved_by', 
        'approval_date'
    ]
    list_filter = ['status', 'application_date', 'school', 'subject']
    search_fields = ['student__full_name', 'subject__name', 'school__name']
    readonly_fields = ['application_date', 'approval_date']
    actions = ['approve_applications', 'reject_applications']
    
    def approve_applications(self, request, queryset):
        for application in queryset:
            if application.status != 'approved':
                application.status = 'approved'
                application.approved_by = request.user
                application.approval_date = timezone.now()
                application.save()
                
                # Add subject to student
                application.student.subjects.add(application.subject)
                
                # Update school subject capacity
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
                    
        self.message_user(request, f"{queryset.count()} applications approved successfully.")
    
    def reject_applications(self, request, queryset):
        updated = queryset.update(
            status='rejected', 
            approved_by=request.user, 
            approval_date=timezone.now()
        )
        self.message_user(request, f"{updated} applications rejected successfully.")
    
    approve_applications.short_description = "✅ Approve selected applications"
    reject_applications.short_description = "❌ Reject selected applications"

# =========================
# SCHOOL UPDATE FILE ADMIN
# =========================
class SchoolUpdateFileForm(forms.ModelForm):
    class Meta:
        model = SchoolUpdateFile
        fields = ['file']

    def clean_file(self):
        f = self.cleaned_data.get('file')
        if not (f.name.endswith('.pdf') or f.name.endswith('.docx')):
            raise forms.ValidationError("File lazima iwe PDF au DOCX")
        return f

class SchoolUpdateFileAdmin(admin.ModelAdmin):
    form = SchoolUpdateFileForm
    list_display = ('file', 'uploaded_at')
    readonly_fields = ('uploaded_at',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        filepath = obj.file.path

        if filepath.endswith('.pdf'):
            text = self.extract_text_from_pdf(filepath)
        else:
            text = self.extract_text_from_docx(filepath)

        print("Extracted text:", text[:300])

        data_json = self.parse_text_with_ai(text)

        print("Data JSON returned from AI:", data_json)

        self.update_database_from_json(data_json)

    def extract_text_from_pdf(self, filepath):
        text = ''
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + '\n'
        return text

    def extract_text_from_docx(self, filepath):
        doc = Document(filepath)
        return '\n'.join([p.text for p in doc.paragraphs])

    def parse_text_with_ai(self, text):
        prompt = f"""
Extract the school data including year, school name, number of students required per school, and if available, number of students needed per subject. 
Output the data as JSON with keys: year, schools (list of objects with name, total_students, subjects (dictionary)).
Text:
{text}
"""
        try:
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            result_json = response.choices[0].message.content
            print("Raw AI response:", result_json)
            data = json.loads(result_json)
            return data
        except Exception as e:
            print(f"Error parsing text with AI: {e}")
            return None

    def update_database_from_json(self, data):
        if not data:
            print("No data to update in database.")
            return

        year = data.get('year')
        schools = data.get('schools', [])

        print(f"Year: {year}, number of schools: {len(schools)}")

        for school in schools:
            name = school.get('name')
            total_students = school.get('total_students')
            subjects = school.get('subjects', {})

            print(f"Processing school: {name}, total_students: {total_students}, subjects: {subjects}")

            obj, created = SchoolRequirement.objects.update_or_create(
                school__name=name,
                year=year,
                defaults={
                    'required_students': total_students,
                    'subject': list(subjects.keys())[0] if subjects else 'General'
                }
            )
            if created:
                print(f"Created SchoolRequirement for {name} ({year})")
            else:
                print(f"Updated SchoolRequirement for {name} ({year})")

# =========================
# REGION ADMIN
# =========================
class RegionAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

# =========================
# DISTRICT ADMIN
# =========================
class DistrictAdmin(admin.ModelAdmin):
    list_display = ['name', 'region']
    list_filter = ['region']
    search_fields = ['name']

# =========================
# SCHOOL ADMIN
# =========================
class SchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'district', 'level', 'capacity', 'current_students']
    list_filter = ['level', 'district__region']
    search_fields = ['name']

# =========================
# SUBJECT ADMIN
# =========================
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'level']
    list_filter = ['level']
    search_fields = ['name', 'code']

# =========================
# SCHOOL SUBJECT CAPACITY ADMIN
# =========================
class SchoolSubjectCapacityAdmin(admin.ModelAdmin):
    list_display = ['school', 'subject', 'max_students', 'current_students']
    list_filter = ['school', 'subject']
    search_fields = ['school__name', 'subject__name']

# =========================
# LOGBOOK ENTRY ADMIN
# =========================
class LogbookEntryAdmin(admin.ModelAdmin):
    list_display = [
        'student', 
        'date', 
        'day_of_week', 
        'is_location_verified',
        'is_at_school',
        'morning_check_in'
    ]
    list_filter = [
        'date',
        'day_of_week',
        'is_location_verified',
        'is_at_school'
    ]
    search_fields = ['student__full_name']
    readonly_fields = ['created_at', 'updated_at']

# =========================
# APPROVAL LETTER ADMIN
# =========================
class ApprovalLetterAdmin(admin.ModelAdmin):
    list_display = ['school', 'generated_date']
    filter_horizontal = ['students']
    search_fields = ['school__name']
    readonly_fields = ['generated_date']

# =========================
# ACADEMIC YEAR ADMIN
# =========================
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ['year', 'is_active']
    list_filter = ['is_active']
    search_fields = ['year']

# =========================
# REGION PIN ADMIN
# =========================
class RegionPinAdmin(admin.ModelAdmin):
    list_display = ['academic_year', 'region', 'is_pinned']
    list_filter = ['academic_year', 'is_pinned']
    search_fields = ['region__name']

# =========================
# SCHOOL PIN ADMIN
# =========================
@admin.action(description="Mark selected schools as pinned")
def mark_pinned(modeladmin, request, queryset):
    queryset.update(is_pinned=True)

@admin.action(description="Mark selected schools as unpinned")
def mark_unpinned(modeladmin, request, queryset):
    queryset.update(is_pinned=False)

class SchoolPinAdmin(admin.ModelAdmin):
    list_display = ['academic_year', 'school', 'is_pinned', 'pin_reason', 'pinned_at']
    list_filter = ['academic_year', 'is_pinned', 'pin_reason']
    search_fields = ['school__name']
    actions = [mark_pinned, mark_unpinned, 'delete_selected']

# =========================
# SCHOOL REQUIREMENT ADMIN
# =========================
class SchoolRequirementAdmin(admin.ModelAdmin):
    list_display = ['school', 'subject', 'year', 'required_students']
    list_filter = ['year', 'school']
    search_fields = ['school__name', 'subject']

class SchoolAssessmentAdmin(admin.ModelAdmin):
    list_display = ['assessor', 'school', 'assigned_date', 'assessment_date', 'is_completed']
    list_filter = ['is_completed', 'assessment_date']
    search_fields = ['assessor__full_name', 'school__name']

class StudentAssessmentAdmin(admin.ModelAdmin):
    list_display = ['assessor', 'student', 'school', 'assessment_date', 'status', 'score']
    list_filter = ['status', 'assessment_date']
    search_fields = ['assessor__full_name', 'student__full_name', 'school__name']

# =========================
# REGISTER ALL MODELS WITH CUSTOM ADMIN SITE
# =========================
custom_admin_site.register(CustomUser, CustomUserAdmin)
custom_admin_site.register(StudentTeacher, StudentTeacherAdmin)
custom_admin_site.register(StudentApplication, StudentApplicationAdmin)
custom_admin_site.register(Region, RegionAdmin)
custom_admin_site.register(District, DistrictAdmin)
custom_admin_site.register(School, SchoolAdmin)
custom_admin_site.register(Subject, SubjectAdmin)
custom_admin_site.register(SchoolSubjectCapacity, SchoolSubjectCapacityAdmin)
custom_admin_site.register(LogbookEntry, LogbookEntryAdmin)
custom_admin_site.register(ApprovalLetter, ApprovalLetterAdmin)
custom_admin_site.register(AcademicYear, AcademicYearAdmin)
custom_admin_site.register(RegionPin, RegionPinAdmin)
custom_admin_site.register(SchoolPin, SchoolPinAdmin)
custom_admin_site.register(SchoolRequirement, SchoolRequirementAdmin)
custom_admin_site.register(SchoolUpdateFile, SchoolUpdateFileAdmin)

# 🔥 SAJILI ASSESSOR MODELS KWA CUSTOM ADMIN SITE
custom_admin_site.register(Assessor, AssessorAdmin)
custom_admin_site.register(SchoolAssessment, SchoolAssessmentAdmin)
custom_admin_site.register(StudentAssessment, StudentAssessmentAdmin)

# =========================
# DEFAULT ADMIN SITE REGISTRATIONS (for backup)
# =========================
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(StudentTeacher, StudentTeacherAdmin)
admin.site.register(StudentApplication, StudentApplicationAdmin)
admin.site.register(Region, RegionAdmin)
admin.site.register(District, DistrictAdmin)
admin.site.register(School, SchoolAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(SchoolSubjectCapacity, SchoolSubjectCapacityAdmin)
admin.site.register(LogbookEntry, LogbookEntryAdmin)
admin.site.register(ApprovalLetter, ApprovalLetterAdmin)
admin.site.register(AcademicYear, AcademicYearAdmin)
admin.site.register(RegionPin, RegionPinAdmin)
admin.site.register(SchoolPin, SchoolPinAdmin)
admin.site.register(SchoolRequirement, SchoolRequirementAdmin)
admin.site.register(SchoolUpdateFile, SchoolUpdateFileAdmin)

# 🔥 SAJILI ASSESSOR MODELS KWA DEFAULT ADMIN SITE
admin.site.register(Assessor, AssessorAdmin)
admin.site.register(SchoolAssessment, SchoolAssessmentAdmin)
admin.site.register(StudentAssessment, StudentAssessmentAdmin)
