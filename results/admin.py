# admin.py
from django.contrib import admin

from field_app.admin import custom_admin_site

from .models import (
    Exam,
    ExamResult,
    PaymentTransaction,
    PersonalUpload,
    ProcessedResult,
    School,
    SchoolSubject,
    SchoolSubscription,
    SpeechSubmissionEntry,
    SpeechSubmissionSession,
    Student,
    Subject,
    SubjectSubmission,
    SubscriptionPlan,
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
    list_select_related = ('student', 'exam', 'subject')


class ProcessedResultAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'division', 'average_score', 'position')
    list_filter = ('exam', 'division')
    search_fields = ('student__first_name', 'student__last_name')
    ordering = ('exam', 'position')
    list_select_related = ('student', 'exam')


class SpeechSubmissionSessionAdmin(admin.ModelAdmin):
    list_display = ('exam', 'subject', 'teacher_name', 'status', 'expected_student_count', 'submitted_count', 'created_at', 'finalized_at')
    list_filter = ('status', 'exam', 'subject')
    search_fields = ('teacher_name', 'exam__name', 'subject__name')
    ordering = ('-created_at',)
    readonly_fields = ('access_key', 'created_at', 'finalized_at', 'submitted_count', 'effective_expected_count', 'is_complete')
    list_select_related = ('exam', 'subject')


class SpeechSubmissionEntryAdmin(admin.ModelAdmin):
    list_display = ('session', 'student', 'score', 'match_confidence', 'explicit_update', 'created_at')
    list_filter = ('session__exam', 'session__subject', 'explicit_update')
    search_fields = ('student__first_name', 'student__last_name', 'raw_name_transcript', 'parsed_name')
    ordering = ('-created_at',)
    list_select_related = ('session', 'student')


class SubjectSubmissionAdmin(admin.ModelAdmin):
    list_display = ('exam', 'subject', 'status', 'submitted_by', 'approved_by', 'student_count', 'submitted_at', 'approved_at')
    list_filter = ('status', 'exam', 'subject')
    search_fields = ('exam__name', 'subject__name', 'submitted_by', 'approved_by')
    ordering = ('-submitted_at',)
    list_select_related = ('exam', 'subject')


class TeacherAccountAdmin(admin.ModelAdmin):
    list_display = ('email', 'full_name', 'role', 'school', 'is_active', 'created_at')
    list_filter = ('role', 'school', 'is_active')
    search_fields = ('email', 'full_name')
    filter_horizontal = ('subjects',)
    readonly_fields = ('password', 'last_login')
    autocomplete_fields = ('school',)
    actions = ['reset_password']
    list_select_related = ('school',)

    def save_model(self, request, obj, form, change):
        # New accounts created here (e.g. a school's first Academic, added
        # after they contact the system admin) get no usable password —
        # they activate themselves the normal way, by logging in with this
        # email for the first time and setting their own password.
        if not change:
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)

    @admin.action(description="Reset password (they set a new one on next login)")
    def reset_password(self, request, queryset):
        for account in queryset:
            account.set_unusable_password()
            account.save(update_fields=['password'])
        self.message_user(
            request,
            f"Password imeondolewa kwa akaunti {queryset.count()}. Waambie waingie na email yao "
            "kwenye /shule/ingia/ — mfumo utawataka waweke password mpya.",
        )


class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'region', 'district', 'created_at')
    list_filter = ('region', 'district')
    search_fields = ('name',)
    ordering = ('name',)


class SchoolSubjectAdmin(admin.ModelAdmin):
    list_display = ('school', 'subject', 'form_levels')
    list_filter = ('school', 'subject')
    search_fields = ('school__name', 'subject__name')
    list_select_related = ('school', 'subject')


class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_tzs', 'duration_days', 'is_active', 'sort_order')
    list_filter = ('is_active',)
    ordering = ('sort_order', 'duration_days')


class SchoolSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('school', 'plan', 'active_until', 'is_active')
    list_filter = ('plan',)
    search_fields = ('school__name',)
    autocomplete_fields = ('school',)
    list_select_related = ('school', 'plan')

    @admin.display(boolean=True)
    def is_active(self, obj):
        return obj.is_active


class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('school', 'plan', 'amount', 'phone_number', 'status', 'order_reference', 'created_at')
    list_filter = ('status', 'plan')
    search_fields = ('school__name', 'phone_number', 'order_reference', 'clickpesa_payment_id')
    readonly_fields = ('order_reference', 'clickpesa_payment_id', 'raw_response', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    list_select_related = ('school', 'plan')


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
custom_admin_site.register(SubscriptionPlan, SubscriptionPlanAdmin)
custom_admin_site.register(SchoolSubscription, SchoolSubscriptionAdmin)
custom_admin_site.register(PaymentTransaction, PaymentTransactionAdmin)
