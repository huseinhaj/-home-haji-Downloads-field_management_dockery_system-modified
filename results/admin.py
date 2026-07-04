# admin.py
from django.contrib import admin

from field_app.admin import custom_admin_site

from .models import (
    Exam,
    ExamResult,
    PersonalUpload,
    ProcessedResult,
    School,
    SchoolSubject,
    SpeechSubmissionEntry,
    SpeechSubmissionSession,
    Student,
    Subject,
    SubjectSubmission,
    TeacherAccount,
)


class ExamAdmin(admin.ModelAdmin):
    list_display = ('name', 'year', 'form', 'exam_type', 'date')
    list_filter = ('exam_type', 'year', 'form')
    search_fields = ('name',)
    ordering = ('-year', '-date')

    class Media:
        js = ('results/admin/exam_midterm_suggest.js',)


class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name',)


class StudentAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'gender')
    search_fields = ('first_name', 'last_name')
    list_filter = ('gender',)


class ExamResultAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'subject', 'score')
    list_filter = ('exam', 'subject')
    search_fields = ('student__first_name', 'student__last_name')


class ProcessedResultAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'division', 'average_score', 'position')
    list_filter = ('exam', 'division')
    search_fields = ('student__first_name', 'student__last_name')
    ordering = ('exam', 'position')


class SpeechSubmissionSessionAdmin(admin.ModelAdmin):
    list_display = ('exam', 'subject', 'teacher_name', 'status', 'expected_student_count', 'submitted_count', 'created_at', 'finalized_at')
    list_filter = ('status', 'exam', 'subject')
    search_fields = ('teacher_name', 'exam__name', 'subject__name')
    ordering = ('-created_at',)
    readonly_fields = ('access_key', 'created_at', 'finalized_at', 'submitted_count', 'effective_expected_count', 'is_complete')


class SpeechSubmissionEntryAdmin(admin.ModelAdmin):
    list_display = ('session', 'student', 'score', 'match_confidence', 'explicit_update', 'created_at')
    list_filter = ('session__exam', 'session__subject', 'explicit_update')
    search_fields = ('student__first_name', 'student__last_name', 'raw_name_transcript', 'parsed_name')
    ordering = ('-created_at',)


class SubjectSubmissionAdmin(admin.ModelAdmin):
    list_display = ('exam', 'subject', 'status', 'submitted_by', 'approved_by', 'student_count', 'submitted_at', 'approved_at')
    list_filter = ('status', 'exam', 'subject')
    search_fields = ('exam__name', 'subject__name', 'submitted_by', 'approved_by')
    ordering = ('-submitted_at',)


class TeacherAccountAdmin(admin.ModelAdmin):
    list_display = ('email', 'full_name', 'role', 'school', 'is_active', 'created_at')
    list_filter = ('role', 'school', 'is_active')
    search_fields = ('email', 'full_name')
    filter_horizontal = ('subjects',)
    readonly_fields = ('password', 'last_login')
    autocomplete_fields = ('school',)


class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'region', 'district', 'created_at')
    list_filter = ('region', 'district')
    search_fields = ('name',)
    ordering = ('name',)


class SchoolSubjectAdmin(admin.ModelAdmin):
    list_display = ('school', 'subject', 'form_levels')
    list_filter = ('school', 'subject')
    search_fields = ('school__name', 'subject__name')


custom_admin_site.register(Exam, ExamAdmin)
custom_admin_site.register(Subject, SubjectAdmin)
custom_admin_site.register(Student, StudentAdmin)
custom_admin_site.register(ExamResult, ExamResultAdmin)
custom_admin_site.register(ProcessedResult, ProcessedResultAdmin)
custom_admin_site.register(SpeechSubmissionSession, SpeechSubmissionSessionAdmin)
custom_admin_site.register(SpeechSubmissionEntry, SpeechSubmissionEntryAdmin)
custom_admin_site.register(SubjectSubmission, SubjectSubmissionAdmin)
custom_admin_site.register(TeacherAccount, TeacherAccountAdmin)
custom_admin_site.register(School, SchoolAdmin)
custom_admin_site.register(SchoolSubject, SchoolSubjectAdmin)
custom_admin_site.register(PersonalUpload)
