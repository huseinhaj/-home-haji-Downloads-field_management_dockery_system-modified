from uuid import uuid4

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone
import pandas as pd
from django.http import HttpResponse


class School(models.Model):
    name = models.CharField(max_length=200)
    region = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Subject(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.name


class SchoolSubject(models.Model):
    """Masomo yanayofundishwa katika shule fulani."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='school_subjects')
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
    form_levels = models.CharField(max_length=20, default='1,2,3,4')  # e.g. "1,2,3,4" or "5,6"

    class Meta:
        unique_together = [('school', 'subject')]

    def __str__(self):
        return f"{self.school} — {self.subject}"


class Student(models.Model):
    GENDER_CHOICES = [('F', 'Female'), ('M', 'Male')]

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Exam(models.Model):
    EXAM_TYPE_CHOICES = [
        ('TEST', 'Test'),
        ('COMPETITION', 'Competition'),
        ('TERMINAL', 'Terminal'),
        ('MIDTERM', 'Midterm'),
        ('DECEMBER', 'December'),
        ('ANNUAL', 'Annual'),
        ('OTHER', 'Other'),
    ]

    name = models.CharField(max_length=100)
    year = models.PositiveIntegerField()
    form = models.PositiveIntegerField()  # Form 1, 2, etc.
    exam_type = models.CharField(
        max_length=20,
        choices=EXAM_TYPE_CHOICES,
        default='TERMINAL'
    )
    date = models.DateField(null=True, blank=True)
    school_name = models.CharField(max_length=200, blank=True)
    school = models.ForeignKey(
        'School', null=True, blank=True, on_delete=models.SET_NULL, related_name='exams'
    )

    def __str__(self):
        return f"{self.get_exam_type_display()} - {self.name} ({self.year})"

    def generate_processed_excel(self):
        """Generate Excel file for all processed results of this exam."""
        results = self.processedresult_set.select_related('student').order_by('position')

        data = []
        for res in results:
            data.append({
                "Jina la Mwanafunzi": f"{res.student.first_name} {res.student.middle_name} {res.student.last_name}".strip(),
                "Jumla ya Alama (Total Score)": res.total_score,
                "Wastani (Average Score)": float(res.average_score),
                "Points": res.points,
                "Division": res.division,
                "Position": res.position
            })

        df = pd.DataFrame(data)

        response = HttpResponse(content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = f'attachment; filename="processed_results_exam_{self.id}.xlsx"'
        df.to_excel(response, index=False)

        return response


class ExamResult(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    score = models.PositiveIntegerField()

    class Meta:
        unique_together = ('exam', 'student', 'subject')

    def __str__(self):
        return f"{self.student} - {self.subject}: {self.score}"


class ProcessedResult(models.Model):
    DIVISION_CHOICES = [
        ('I', 'Division I'),
        ('II', 'Division II'),
        ('III', 'Division III'),
        ('IV', 'Division IV'),
        ('0', 'Fail'),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    total_score = models.PositiveIntegerField()
    average_score = models.DecimalField(max_digits=5, decimal_places=2)
    position = models.PositiveIntegerField()
    points = models.PositiveIntegerField()
    division = models.CharField(max_length=3, choices=DIVISION_CHOICES)
    counted_subjects = models.CharField(
        max_length=500, blank=True,
        help_text="Masomo bora yaliyotumika kuhesabu Daraja (mf. 7 bora kwa CSEE, 3 kwa ACSEE).",
    )

    class Meta:
        unique_together = ('exam', 'student')

    def __str__(self):
        return f"{self.student} - {self.division}"


class SubjectSubmission(models.Model):
    METHOD_CHOICES = [('SPEECH', 'Speech Entry'), ('UPLOAD', 'File Upload')]
    STATUS_PENDING = 'PENDING'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_APPROVED, 'Approved'),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='subject_submissions')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='submissions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, blank=True)
    submitted_by = models.CharField(max_length=100, blank=True)
    submitted_by_user = models.ForeignKey(
        'TeacherAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    student_count = models.PositiveIntegerField(default=0)
    approved_by = models.CharField(max_length=100, blank=True)
    approved_by_user = models.ForeignKey(
        'TeacherAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)

    class Meta:
        unique_together = [('exam', 'subject')]
        ordering = ['subject__name']

    def __str__(self):
        return f"{self.exam} - {self.subject} ({self.status})"


class TeacherAccountManager(BaseUserManager):
    def create_pending(self, email, full_name='', role=None, subjects=None):
        """Academic officer pre-registers a teacher's email; account has no
        usable password until the teacher activates it themselves."""
        email = self.normalize_email(email)
        account = self.model(email=email, full_name=full_name, role=role or self.model.ROLE_TEACHER)
        account.set_unusable_password()
        account.save(using=self._db)
        if subjects:
            account.subjects.set(subjects)
        return account


class TeacherAccount(AbstractBaseUser):
    ROLE_ACADEMIC = 'ACADEMIC'
    ROLE_TEACHER = 'TEACHER'

    ROLE_CHOICES = [
        (ROLE_ACADEMIC, 'Academic'),
        (ROLE_TEACHER, 'Teacher'),
    ]

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_TEACHER)
    subjects = models.ManyToManyField(Subject, blank=True, related_name='teachers')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = TeacherAccountManager()

    def __str__(self):
        return f"{self.full_name or self.email} ({self.get_role_display()})"

    @property
    def is_academic(self):
        return self.role == self.ROLE_ACADEMIC

    @property
    def is_teacher(self):
        return self.role == self.ROLE_TEACHER

    @property
    def is_activated(self):
        return self.has_usable_password()


class PersonalUpload(models.Model):
    """A private, ad-hoc scoresheet a teacher uploads for their own use.

    Deliberately not linked to Exam/SubjectSubmission — it never feeds the
    school's official/general results, it's just a quick way for a teacher
    to turn a scoresheet into a results PDF for their own subject.
    """
    teacher = models.ForeignKey(TeacherAccount, on_delete=models.CASCADE, related_name='personal_uploads')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='personal_uploads')
    title = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} — {self.subject} ({self.teacher})"


class PersonalUploadResult(models.Model):
    upload = models.ForeignKey(PersonalUpload, on_delete=models.CASCADE, related_name='results')
    student_name = models.CharField(max_length=200)
    score = models.PositiveIntegerField()

    class Meta:
        ordering = ['-score']

    def __str__(self):
        return f"{self.student_name}: {self.score}"


class SpeechSubmissionSession(models.Model):
    STATUS_OPEN = 'OPEN'
    STATUS_FINALIZED = 'FINALIZED'

    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_FINALIZED, 'Finalized'),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher_name = models.CharField(max_length=150)
    access_key = models.UUIDField(default=uuid4, unique=True, editable=False)
    roster_student_ids = models.JSONField(default=list, blank=True)
    expected_student_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['exam', 'subject'], name='unique_speech_session_per_exam_subject'),
        ]

    def __str__(self):
        return f"{self.exam} - {self.subject} ({self.teacher_name})"

    @property
    def submitted_count(self):
        return self.entries.count()

    @property
    def effective_expected_count(self):
        if self.expected_student_count:
            return self.expected_student_count
        if self.roster_student_ids:
            return len(self.roster_student_ids)
        return None  # open mode — no fixed count

    @property
    def has_selected_roster(self):
        return bool(self.roster_student_ids)

    @property
    def is_complete(self):
        # open mode (no roster, no expected count) never auto-completes
        if self.effective_expected_count is None:
            return False
        return self.submitted_count >= self.effective_expected_count

    def mark_finalized(self):
        self.status = self.STATUS_FINALIZED
        self.finalized_at = timezone.now()
        self.save(update_fields=['status', 'finalized_at'])


class SpeechSubmissionEntry(models.Model):
    session = models.ForeignKey(SpeechSubmissionSession, on_delete=models.CASCADE, related_name='entries')
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    raw_name_transcript = models.TextField()
    parsed_name = models.CharField(max_length=255)
    score = models.PositiveIntegerField()
    match_confidence = models.DecimalField(max_digits=5, decimal_places=4)
    match_candidates = models.JSONField(default=list)
    explicit_update = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['session', 'student'], name='unique_speech_entry_per_session_student'),
        ]

    def __str__(self):
        return f"{self.session} - {self.student} ({self.score})"
