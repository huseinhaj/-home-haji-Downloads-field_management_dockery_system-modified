from django.contrib import admin

from .models import EssFillRun, SubTask, Task, TeacherProfile, WeekEntry


class SubTaskInline(admin.TabularInline):
    model = SubTask
    extra = 0


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
    list_display = ('profile', 'started', 'finished', 'status', 'saved', 'skipped', 'not_found')
    list_filter = ('status',)