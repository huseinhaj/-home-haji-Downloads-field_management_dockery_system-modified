# admin.py
from django.contrib import admin
from .models import (
    Exam,
    ExamResult,
    ProcessedResult,
    SpeechSubmissionEntry,
    SpeechSubmissionSession,
    Student,
    Subject,
)

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('name', 'year', 'form', 'exam_type', 'date')
    list_filter = ('exam_type', 'year', 'form')
    search_fields = ('name',)
    ordering = ('-year', '-date')

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name',)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'gender')
    search_fields = ('first_name', 'last_name')
    list_filter = ('gender',)

@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'subject', 'score')
    list_filter = ('exam', 'subject')
    search_fields = ('student__first_name', 'student__last_name')

@admin.register(ProcessedResult)
class ProcessedResultAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'division', 'average_score', 'position')
    list_filter = ('exam', 'division')
    search_fields = ('student__first_name', 'student__last_name')
    ordering = ('exam', 'position')


@admin.register(SpeechSubmissionSession)
class SpeechSubmissionSessionAdmin(admin.ModelAdmin):
    list_display = ('exam', 'subject', 'teacher_name', 'status', 'expected_student_count', 'submitted_count', 'created_at', 'finalized_at')
    list_filter = ('status', 'exam', 'subject')
    search_fields = ('teacher_name', 'exam__name', 'subject__name')
    ordering = ('-created_at',)
    readonly_fields = ('access_key', 'created_at', 'finalized_at', 'submitted_count', 'effective_expected_count', 'is_complete')


@admin.register(SpeechSubmissionEntry)
class SpeechSubmissionEntryAdmin(admin.ModelAdmin):
    list_display = ('session', 'student', 'score', 'match_confidence', 'explicit_update', 'created_at')
    list_filter = ('session__exam', 'session__subject', 'explicit_update')
    search_fields = ('student__first_name', 'student__last_name', 'raw_name_transcript', 'parsed_name')
    ordering = ('-created_at',)
