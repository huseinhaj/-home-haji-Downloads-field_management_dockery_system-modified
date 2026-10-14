from django.contrib import admin

from .models import (AcademicCalendar, EssFillRun, MonthlyTarget, SubTask,
                     Task, TeacherProfile, WeekEntry, WeeklyTarget)


class SubTaskInline(admin.TabularInline):
    model = SubTask
    extra = 0


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


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'school', 'ess_username', 'ess_ready')
    search_fields = ('full_name', 'ess_username', 'user__email')


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


@admin.register(WeekEntry)
class WeekEntryAdmin(admin.ModelAdmin):
    list_display = ('subtask', 'week_no', 'date', 'amount', 'profile')
    list_filter = ('week_no',)


@admin.register(EssFillRun)
class EssFillRunAdmin(admin.ModelAdmin):
    list_display = ('profile', 'started', 'finished', 'kind', 'source', 'status',
                    'saved', 'skipped', 'not_found')
    list_filter = ('status', 'kind', 'source')