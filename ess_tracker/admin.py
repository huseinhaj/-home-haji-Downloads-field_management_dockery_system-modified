from django import forms
from django.contrib import admin

from .models import (AcademicCalendar, EssFillRun, MonthlyTarget, SubTask,
                     SubTaskEvent, Task, TeacherProfile, WeekEntry, WeeklyTarget)


class SubTaskInline(admin.TabularInline):
    model = SubTask
    extra = 0


class SubTaskEventInline(admin.TabularInline):
    model = SubTaskEvent
    extra = 0
    fields = ('index', 'due_date', 'label')
    ordering = ('due_date', 'index')


class MonthlyTargetInline(admin.TabularInline):
    model = MonthlyTarget
    extra = 0
    fields = ('month', 'expected_pct')


class WeeklyTargetInline(admin.TabularInline):
    model = WeeklyTarget
    extra = 0
    fields = ('week_start', 'expected_pct')
    ordering = ('week_start',)


@admin.register(AcademicCalendar)
class AcademicCalendarAdmin(admin.ModelAdmin):
    list_display = ('year', 'is_active', 'school_open', 'school_close', 'updated_at')
    list_editable = ('is_active',)
    inlines = [WeeklyTargetInline, MonthlyTargetInline]


class TeacherProfileAdminForm(forms.ModelForm):
    """Fomu ya admin inayoweka password ya ESS kwa usimbaji sahihi.

    Badala ya ku-edit token ya `ess_password` (ambayo ni ya siri), admin
    huandika password mpya kwenye `new_ess_password`; tutaisimba kiotomatiki.
    """

    new_ess_password = forms.CharField(
        label='Weka password mpya ya ESS',
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='Jaza tu kubadilisha password. Ikiacha tupu, iliyopo haitabadilika.')

    class Meta:
        model = TeacherProfile
        fields = '__all__'

    def save(self, commit=True):
        obj = super().save(commit=False)
        raw = self.cleaned_data.get('new_ess_password')
        if raw:
            obj.set_ess_password(raw)
        if commit:
            obj.save()
        return obj


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    form = TeacherProfileAdminForm
    list_display = ('full_name', 'user', 'school', 'ess_username', 'ess_ready',
                    'approver_enabled')
    list_filter = ('approver_enabled',)
    search_fields = ('full_name', 'ess_username', 'user__email')
    readonly_fields = ('ess_password', 'ess_ready')
    actions = ('enable_approver', 'disable_approver')

    @admin.action(description='Washa kuidhinisha kwa waliochaguliwa')
    def enable_approver(self, request, queryset):
        n = queryset.update(approver_enabled=True)
        self.message_user(request, f'Wakuu {n} wamewashwa kuidhinisha.')

    @admin.action(description='Zima kuidhinisha kwa waliochaguliwa')
    def disable_approver(self, request, queryset):
        n = queryset.update(approver_enabled=False)
        self.message_user(request, f'Wakuu {n} wamezimwa kuidhinisha.')
    fieldsets = (
        (None, {'fields': ('user', 'full_name', 'phone', 'school')}),
        ('ESS (e-Tendaji)', {'fields': ('ess_username', 'new_ess_password',
                                        'ess_password', 'ess_ready')}),
        ('Ratiba ya shule', {'fields': ('school_open', 'school_close',
                                        'entries_per_week', 'holidays')}),
        ('Kujaza / Uidhinishaji', {'fields': ('auto_subtasks', 'auto_fill_enabled',
                                              'approver_enabled',
                                              'auto_approve_weeks')}),
    )


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('name', 'somo', 'kidato', 'start', 'end', 'profile')
    list_filter = ('somo', 'kidato')
    search_fields = ('name', 'somo', 'profile__full_name')
    inlines = [SubTaskInline]


@admin.register(SubTask)
class SubTaskAdmin(admin.ModelAdmin):
    list_display = ('position', 'description', 'task', 'mode', 'target')
    list_filter = ('mode',)
    search_fields = ('description',)
    inlines = [SubTaskEventInline]


@admin.register(WeekEntry)
class WeekEntryAdmin(admin.ModelAdmin):
    list_display = ('subtask', 'week_no', 'date', 'amount', 'profile')
    list_filter = ('week_no',)


@admin.register(EssFillRun)
class EssFillRunAdmin(admin.ModelAdmin):
    list_display = ('profile', 'started', 'finished', 'kind', 'source', 'status',
                    'saved', 'skipped', 'not_found')
    list_filter = ('status', 'kind', 'source')


# Mradi unatumia `field_app.admin.custom_admin_site` kwa `/admin/`, sio default
# `admin.site`. Bila kusajili hapa, models za ESS (TeacherProfile, n.k.)
# hazionekani kwenye ukurasa wa admin. Sajili pia kwenye custom site.
try:
    from field_app.admin import custom_admin_site
except Exception:  # noqa: BLE001 — endelea hata kama field_app haipo
    custom_admin_site = None

if custom_admin_site is not None:
    for _model, _model_admin in (
        (AcademicCalendar, AcademicCalendarAdmin),
        (TeacherProfile, TeacherProfileAdmin),
        (Task, TaskAdmin),
        (SubTask, SubTaskAdmin),
        (WeekEntry, WeekEntryAdmin),
        (EssFillRun, EssFillRunAdmin),
    ):
        if not custom_admin_site._registry.get(_model):
            custom_admin_site.register(_model, _model_admin)