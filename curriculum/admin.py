from django.contrib import admin
from .models import (
    TLMTeacher, Testimonial, LessonNote, SubjectTopic, TopicSubtopic,
    TLMLogbookEntry, TLMTopicLogbook, GeneratedExam,
)

admin.site.register(TLMTeacher)
admin.site.register(Testimonial)
admin.site.register(LessonNote)
admin.site.register(SubjectTopic)
admin.site.register(TopicSubtopic)


@admin.register(TLMLogbookEntry)
class TLMLogbookEntryAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'date', 'day_of_week', 'is_location_verified', 'updated_at']
    list_filter = ['day_of_week', 'is_location_verified']
    search_fields = ['teacher__full_name']
    list_select_related = ['teacher', 'school']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(TLMTopicLogbook)
class TLMTopicLogbookAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'term', 'month', 'week', 'main_topic', 'subtopic', 'date_ended', 'updated_at']
    list_filter = ['term', 'month']
    search_fields = ['main_topic', 'subtopic', 'teacher__full_name']
    list_select_related = ['teacher', 'school', 'subject']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(GeneratedExam)
class GeneratedExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'class_name', 'subject_name', 'exam_type', 'year', 'question_count', 'created_at']
    list_filter = ['exam_type', 'education_level', 'year']
    search_fields = ['title', 'subject_name', 'teacher__full_name']
    list_select_related = ['teacher']
    readonly_fields = ['created_at', 'updated_at']
