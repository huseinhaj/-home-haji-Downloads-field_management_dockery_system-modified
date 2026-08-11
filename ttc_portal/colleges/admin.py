from django.contrib import admin
from django import forms
from .models import College, Program, CollegeAdmin


class ProgramInline(admin.TabularInline):
    model = Program
    extra = 1


@admin.register(College)
class CollegeModelAdmin(admin.ModelAdmin):
    list_display = ('short_name', 'name', 'region', 'district', 'student_count', 'is_active')
    list_filter = ('region', 'is_active')
    search_fields = ('name', 'short_name', 'code', 'region', 'district')
    prepopulated_fields = {'code': ('short_name',)}
    inlines = [ProgramInline]
    ordering = ('name',)


@admin.register(Program)
class ProgramModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'college', 'code', 'duration_years', 'student_count')
    list_filter = ('college',)
    search_fields = ('name', 'college__name', 'code')


class CollegeAdminProfileForm(forms.ModelForm):
    class Meta:
        model = CollegeAdmin
        fields = '__all__'

    def save(self, commit=True):
        instance = super().save(commit=False)
        user = instance.user
        user.role = 'college_admin'
        if commit:
            user.save()
            instance.save()
        return instance


@admin.register(CollegeAdmin)
class CollegeAdminProfileAdmin(admin.ModelAdmin):
    form = CollegeAdminProfileForm
    list_display = ('full_name', 'college', 'title', 'phone_number')
    list_filter = ('college',)
    search_fields = ('full_name', 'college__name', 'user__username', 'phone_number')
