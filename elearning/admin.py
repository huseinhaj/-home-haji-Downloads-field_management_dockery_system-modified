from django.contrib import admin
from .models import (
    LearnerProfile, Course, Module, Lesson, Enrollment, LessonProgress,
    Quiz, Question, QuizAttempt, QuizAnswer,
    Assignment, AssignmentSubmission,
    Discussion, DiscussionReply, Resource, CourseReview, Announcement,
)


@admin.register(LearnerProfile)
class LearnerProfileAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'user', 'role', 'phone_number']
    list_filter = ['role']
    search_fields = ['full_name', 'user__email', 'phone_number']


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 1
    fields = ['title', 'order']


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    fields = ['title', 'module', 'order', 'duration_minutes', 'is_published']
    raw_id_fields = ['module']


class QuizInline(admin.TabularInline):
    model = Quiz
    extra = 0
    fields = ['title', 'time_limit_minutes', 'pass_percentage', 'is_published']
    show_change_link = True


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    fields = ['student', 'status', 'progress_percent']
    readonly_fields = ['progress_percent']
    raw_id_fields = ['student']
    can_delete = False


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'level', 'subject', 'is_published', 'enrollment_count', 'created_at']
    list_filter = ['is_published', 'level', 'subject', 'education_level']
    search_fields = ['title', 'short_description', 'description']
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ['created_by']
    inlines = [ModuleInline, EnrollmentInline]
    actions = ['make_published', 'make_unpublished']

    def make_published(self, request, queryset):
        queryset.update(is_published=True)
    make_published.short_description = "Chapisha kozi zilizochaguliwa"

    def make_unpublished(self, request, queryset):
        queryset.update(is_published=False)
    make_unpublished.short_description = "Ficha kozi zilizochaguliwa"


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'order', 'lesson_count']
    list_filter = ['course']
    search_fields = ['title', 'course__title']
    inlines = [LessonInline]

    def lesson_count(self, obj):
        return obj.lessons.count()
    lesson_count.short_description = "Idadi ya Masomo"


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ['title', 'module', 'content_type', 'duration_minutes', 'is_published']
    list_filter = ['content_type', 'is_published', 'module__course']
    search_fields = ['title', 'content']


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'status', 'progress_percent', 'enrolled_at']
    list_filter = ['status', 'course']
    search_fields = ['student__email', 'course__title']
    raw_id_fields = ['student']
    date_hierarchy = 'enrolled_at'


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ['student', 'lesson', 'is_completed', 'updated_at']
    list_filter = ['is_completed']
    search_fields = ['student__email', 'lesson__title']


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 3
    fields = ['text', 'question_type', 'points', 'order']
    ordering = ['order']


class QuizAttemptInline(admin.TabularInline):
    model = QuizAttempt
    extra = 0
    fields = ['student', 'attempt_number', 'percentage', 'passed', 'completed_at']
    readonly_fields = ['percentage', 'passed', 'completed_at']
    can_delete = False


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'total_questions', 'time_limit_minutes', 'is_published']
    list_filter = ['is_published', 'course']
    search_fields = ['title', 'course__title']
    inlines = [QuestionInline, QuizAttemptInline]

    def total_questions(self, obj):
        return obj.questions.count()
    total_questions.short_description = "Maswali"


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['text_preview', 'quiz', 'question_type', 'points', 'order']
    list_filter = ['question_type', 'quiz__course']
    search_fields = ['text', 'quiz__title']

    def text_preview(self, obj):
        return obj.text[:80] + ('...' if len(obj.text) > 80 else '')
    text_preview.short_description = "Swali"


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ['student', 'quiz', 'attempt_number', 'percentage', 'passed', 'completed_at']
    list_filter = ['passed', 'quiz__course']
    search_fields = ['student__email', 'quiz__title']
    date_hierarchy = 'started_at'


@admin.register(QuizAnswer)
class QuizAnswerAdmin(admin.ModelAdmin):
    list_display = ['attempt', 'question', 'is_correct', 'points_earned']
    list_filter = ['is_correct']


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'due_date', 'max_points', 'is_published']
    list_filter = ['is_published', 'course']
    search_fields = ['title', 'course__title']
    date_hierarchy = 'created_at'


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ['student', 'assignment', 'submitted_at', 'score', 'graded_at']
    list_filter = ['assignment__course']
    search_fields = ['student__email', 'assignment__title']
    date_hierarchy = 'submitted_at'


@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'user', 'reply_count', 'is_pinned', 'created_at']
    list_filter = ['is_pinned', 'course']
    search_fields = ['title', 'content', 'course__title']


@admin.register(DiscussionReply)
class DiscussionReplyAdmin(admin.ModelAdmin):
    list_display = ['discussion', 'user', 'created_at']
    list_filter = ['discussion__course']
    search_fields = ['content']


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'resource_type', 'is_free']
    list_filter = ['resource_type', 'is_free', 'course']
    search_fields = ['title', 'course__title']


@admin.register(CourseReview)
class CourseReviewAdmin(admin.ModelAdmin):
    list_display = ['course', 'user', 'rating', 'created_at']
    list_filter = ['rating', 'course']
    search_fields = ['comment', 'course__title', 'user__email']


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'author', 'is_important', 'created_at']
    list_filter = ['is_important', 'course']
    search_fields = ['title', 'content', 'course__title']
