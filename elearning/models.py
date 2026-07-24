from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator



class LearnerProfile(models.Model):
    """Profile linking CustomUser to the e-learning platform."""
    ROLE_CHOICES = [
        ('student', 'Mwanafunzi'),
        ('teacher', 'Mwalimu'),
        ('admin', 'Msimamizi'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learner_profile',
    )
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='elearning/avatars/', blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"


class Course(models.Model):
    LEVEL_CHOICES = [
        ('beginner', 'Mwanzo'),
        ('intermediate', 'Wastani'),
        ('advanced', 'Juu'),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to='elearning/thumbnails/', blank=True, null=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='beginner')
    subject = models.CharField(max_length=100, blank=True, help_text="Somo (e.g. Hisabati, Kiswahili)")
    education_level = models.CharField(max_length=50, blank=True, help_text="Kiwango cha elimu (e.g. Sekondari, Msingi)")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_courses',
    )
    is_published = models.BooleanField(default=False)
    is_free = models.BooleanField(default=True)
    price_tzs = models.PositiveIntegerField(default=0, blank=True)
    enrollment_count = models.PositiveIntegerField(default=0, editable=False)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Kozi"
        verbose_name_plural = "Kozi"

    def __str__(self):
        return self.title

    @property
    def total_modules(self):
        return self.modules.count()

    @property
    def total_lessons(self):
        return Lesson.objects.filter(module__course=self).count()

    @property
    def total_duration_minutes(self):
        total = Lesson.objects.filter(module__course=self).aggregate(
            total=models.Sum('duration_minutes')
        )['total']
        return total or 0

    @property
    def total_enrolled(self):
        return self.enrollments.count()


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']
        unique_together = ['course', 'order']
        verbose_name = "Moduli"
        verbose_name_plural = "Moduli"

    def __str__(self):
        return f"{self.course.title} — {self.title}"


class Lesson(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('text', 'Maandishi'),
        ('video', 'Video'),
        ('document', 'Hati'),
        ('embed', 'Video Iliyopachikwa'),
    ]

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, default='text')
    content = models.TextField(blank=True, help_text="Maandishi ya somo (Rich Text)")
    video_url = models.URLField(blank=True, help_text="URL ya video (YouTube, Vimeo)")
    video_embed = models.TextField(blank=True, help_text="Embed code ya video")
    document = models.FileField(upload_to='elearning/documents/', blank=True, null=True)
    duration_minutes = models.PositiveIntegerField(default=10)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']
        unique_together = ['module', 'order']
        verbose_name = "Somo"
        verbose_name_plural = "Masomo"

    def __str__(self):
        return f"{self.module.title} — {self.title}"


class Enrollment(models.Model):
    STATUS_CHOICES = [
        ('active', 'Inaendelea'),
        ('completed', 'Imekamilika'),
        ('dropped', 'Imeacha'),
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    completed_at = models.DateTimeField(null=True, blank=True)
    progress_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    last_accessed = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'course']
        verbose_name = "Uandikishaji"
        verbose_name_plural = "Uandikishaji"

    def __str__(self):
        return f"{self.student.email} → {self.course.title}"

    def update_progress(self):
        """Calculate and update progress based on completed lessons."""
        total = Lesson.objects.filter(module__course=self.course, is_published=True).count()
        if total == 0:
            self.progress_percent = 0
        else:
            completed = LessonProgress.objects.filter(
                student=self.student,
                lesson__module__course=self.course,
                is_completed=True,
            ).count()
            self.progress_percent = round((completed / total) * 100, 2)

            if self.progress_percent >= 100:
                self.status = 'completed'
                self.completed_at = timezone.now()

        self.save(update_fields=['progress_percent', 'status', 'completed_at'])


class LessonProgress(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lesson_progress',
    )
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='progress')
    is_completed = models.BooleanField(default=False)
    watched_seconds = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'lesson']
        verbose_name = "Maendeleo ya Somo"
        verbose_name_plural = "Maendeleo ya Masomo"

    def __str__(self):
        return f"{self.student.email} — {self.lesson.title} ({'✓' if self.is_completed else '○'})"


class Quiz(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='quizzes')
    module = models.ForeignKey(
        Module, on_delete=models.SET_NULL, null=True, blank=True, related_name='quizzes'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    time_limit_minutes = models.PositiveIntegerField(default=10)
    pass_percentage = models.PositiveIntegerField(default=50, validators=[MinValueValidator(0), MaxValueValidator(100)])
    max_attempts = models.PositiveIntegerField(default=3)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Mtihani"
        verbose_name_plural = "Mitihani"

    def __str__(self):
        return f"{self.course.title} — {self.title}"

    @property
    def total_questions(self):
        return self.questions.count()

    @property
    def total_points(self):
        return self.questions.aggregate(total=models.Sum('points'))['total'] or 0


class Question(models.Model):
    TYPE_CHOICES = [
        ('multiple_choice', 'Chaguo Nyingi'),
        ('true_false', 'Kweli/Si Kweli'),
        ('short_answer', 'Jibu Fupi'),
    ]

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='multiple_choice')
    text = models.TextField()
    options = models.JSONField(default=list, blank=True,
        help_text='JSON ya chaguo: ["Chaguo A", "Chaguo B", "Chaguo C", "Chaguo D"]')
    correct_answer = models.TextField(blank=True,
        help_text="Jibu sahihi (kwa multiple_choice weka index ya chaguo, kwa true_false weka True/False)")
    explanation = models.TextField(blank=True, help_text="Maelezo ya jibu sahihi")
    points = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "Swali"
        verbose_name_plural = "Maswali"

    def __str__(self):
        return f"{self.quiz.title} — Swali {self.order + 1}"


class QuizAttempt(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quiz_attempts',
    )
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    attempt_number = models.PositiveIntegerField(default=1)
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_points = models.PositiveIntegerField(default=0)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    passed = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_taken_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-started_at']
        unique_together = ['student', 'quiz', 'attempt_number']
        verbose_name = "Jaribio la Mtihani"
        verbose_name_plural = "Majaribio ya Mtihani"

    def __str__(self):
        return f"{self.student.email} — {self.quiz.title} (Jaribio {self.attempt_number}: {self.percentage}%)"


class QuizAnswer(models.Model):
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_answer = models.TextField(blank=True)
    is_correct = models.BooleanField(default=False)
    points_earned = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['attempt', 'question']
        verbose_name = "Jibu la Mtihani"
        verbose_name_plural = "Majibu ya Mtihani"

    def __str__(self):
        return f"{self.attempt} — {self.question}"


class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='assignments')
    module = models.ForeignKey(
        Module, on_delete=models.SET_NULL, null=True, blank=True, related_name='assignments'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True, help_text="Maagizo ya kazi")
    due_date = models.DateTimeField(null=True, blank=True)
    max_points = models.PositiveIntegerField(default=100)
    file_required = models.BooleanField(default=False)
    allow_late_submission = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Kazi"
        verbose_name_plural = "Kazi"

    def __str__(self):
        return f"{self.course.title} — {self.title}"

    @property
    def is_past_due(self):
        if not self.due_date:
            return False
        return timezone.now() > self.due_date


class AssignmentSubmission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assignment_submissions',
    )
    file = models.FileField(upload_to='elearning/submissions/', blank=True, null=True)
    text_content = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_late = models.BooleanField(default=False)
    score = models.PositiveIntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='graded_submissions',
    )
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['assignment', 'student']
        ordering = ['-submitted_at']
        verbose_name = "Uwasilishaji wa Kazi"
        verbose_name_plural = "Uwasilishaji wa Kazi"

    def __str__(self):
        return f"{self.student.email} — {self.assignment.title}"


class Discussion(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='discussions')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='discussions',
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']
        verbose_name = "Mjadala"
        verbose_name_plural = "Majadala"

    def __str__(self):
        return f"{self.course.title} — {self.title}"

    @property
    def reply_count(self):
        return self.replies.count()


class DiscussionReply(models.Model):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='replies')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='discussion_replies',
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "Jibu la Mjadala"
        verbose_name_plural = "Majibu ya Majadala"

    def __str__(self):
        return f"{self.user.email} → {self.discussion.title}"


class Resource(models.Model):
    """Ziada za masomo — vitabu, PDF, madaftari, n.k."""
    TYPE_CHOICES = [
        ('pdf', 'PDF'),
        ('document', 'Hati'),
        ('video', 'Video'),
        ('link', 'Kiungo'),
        ('other', 'Nyingine'),
    ]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='resources')
    title = models.CharField(max_length=255)
    resource_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='pdf')
    file = models.FileField(upload_to='elearning/resources/', blank=True, null=True)
    url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    is_free = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Nyongeza"
        verbose_name_plural = "Nyongeza"

    def __str__(self):
        return f"{self.course.title} — {self.title}"


class CourseReview(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='course_reviews',
    )
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['course', 'user']
        ordering = ['-created_at']
        verbose_name = "Maoni ya Kozi"
        verbose_name_plural = "Maoni ya Kozi"

    def __str__(self):
        return f"{self.user.email} — {self.course.title} ({self.rating}★)"


class Announcement(models.Model):
    """Matangazo kwa wanafunzi waliojisajili kwenye kozi."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='announcements')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='announcements',
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_important = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_important', '-created_at']
        verbose_name = "Tangazo"
        verbose_name_plural = "Matangazo"

    def __str__(self):
        return f"{self.course.title} — {self.title}"
