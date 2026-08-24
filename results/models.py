import uuid
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
    school_logo = models.ImageField(upload_to='school_logos/', blank=True, null=True,
        help_text="School logo — appears on the left side of the PDF header")
    district_logo = models.ImageField(upload_to='district_logos/', blank=True, null=True,
        help_text="District logo — appears on the right side of the PDF header")
    school_logo_b64 = models.TextField(blank=True, default='',
        help_text="School logo stored as base64 — persists on Railway")
    district_logo_b64 = models.TextField(blank=True, default='',
        help_text="District logo stored as base64 — persists on Railway")
    coat_of_arms = models.ImageField(upload_to='coat_of_arms/', blank=True, null=True,
        help_text="Coat of Arms logo — appears in the center of the header")
    coat_of_arms_b64 = models.TextField(blank=True, default='',
        help_text="Coat of arms stored as base64 — persists on Railway")
    source_school_id = models.PositiveIntegerField(
        null=True, blank=True, unique=True,
        help_text="PK of the matching field_app.School record (nationwide master list). "
                  "Used so self-registration never creates a duplicate row for the same school.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Subject(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.name


class SchoolSubject(models.Model):
    """Subjects taught at a particular school."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='school_subjects')
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
    form_levels = models.CharField(max_length=20, default='1,2,3,4')  # e.g. "1,2,3,4" or "5,6"

    class Meta:
        unique_together = [('school', 'subject')]

    def __str__(self):
        return f"{self.school} — {self.subject}"


class FormStudent(models.Model):
    """A student in a particular form at a school.
    This is a school-wide list — not tied to a specific exam.
    The Academic Officer uploads the list; every teacher sees their own students."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='form_students')
    form = models.PositiveIntegerField()  # 1, 2, 3, 4, 5, 6
    admission_no = models.CharField(max_length=50, blank=True)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=1, choices=[('F', 'Female'), ('M', 'Male')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('school', 'form', 'admission_no')]
        ordering = ['form', 'last_name', 'first_name']

    def __str__(self):
        return f"Form {self.form} — {self.first_name} {self.last_name} ({self.school})"

    @property
    def full_name(self):
        return ' '.join(p for p in [self.first_name, self.middle_name or '', self.last_name] if p)


class TeacherFormAssignment(models.Model):
    """A teacher assigned to teach a specific subject for a specific form.
    The Academic Officer assigns teachers to form + subject."""
    teacher = models.ForeignKey('TeacherAccount', on_delete=models.CASCADE, related_name='form_assignments')
    form = models.PositiveIntegerField()
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='teacher_assignments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('teacher', 'form', 'subject')]
        ordering = ['form', 'subject__name']

    def __str__(self):
        return f"{self.teacher} — Form {self.form} {self.subject}"


class Student(models.Model):
    GENDER_CHOICES = [('F', 'Female'), ('M', 'Male')]

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)

    class Meta:
        indexes = [
            models.Index(fields=['first_name', 'last_name']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Exam(models.Model):
    EXAM_TYPE_CHOICES = [
        ('TEST', 'Test'),
        ('MONTHLY', 'Monthly Test'),
        ('QUIZ', 'Quiz'),
        ('MIDTERM', 'Midterm'),
        ('TERMINAL', 'Terminal'),
        ('MOCK', 'Mock'),
        ('ANNUAL', 'Annual'),
        ('DECEMBER', 'December'),
        ('COMPETITION', 'Competition'),
        ('OTHER', 'Other'),
    ]

    STREAM_CHOICES = [
        ('A', 'Stream A'),
        ('B', 'Stream B'),
        ('C', 'Stream C'),
        ('D', 'Stream D'),
        ('E', 'Stream E'),
        ('F', 'Stream F'),
    ]
    FORM_LABELS = {
        1: 'Form I', 2: 'Form II', 3: 'Form III',
        4: 'Form IV', 5: 'Form V', 6: 'Form VI',
    }

    name = models.CharField(max_length=100)
    year = models.PositiveIntegerField()
    form = models.PositiveIntegerField()  # Form 1, 2, etc.
    stream = models.CharField(
        max_length=2, choices=STREAM_CHOICES, blank=True, default='',
        help_text="Stream / Class division within the form (A, B, C, …).",
    )
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

    class Meta:
        indexes = [
            models.Index(fields=['school', 'year', 'form']),
        ]

    def __str__(self):
        label = self.FORM_LABELS.get(self.form, f'Form {self.form}')
        if self.stream:
            label += f' {self.stream}'
        return f"{self.get_exam_type_display()} - {self.name} ({label}, {self.year})"

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
    share_token = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False,
        help_text="Unique token for anonymous public access to this student's result.",
    )

    class Meta:
        unique_together = ('exam', 'student')

    def __str__(self):
        return f"{self.student} - {self.division}"


class SubjectSubmission(models.Model):
    METHOD_CHOICES = [
        ('MANUAL', 'Marks Entry (Manual)'),
        ('SPEECH', 'Speech Entry'),
        ('UPLOAD', 'File Upload'),
    ]
    STATUS_PENDING = 'PENDING'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_RETURNED = 'RETURNED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_RETURNED, 'Returned'),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='subject_submissions')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='submissions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
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
    # ── Returned / Revision fields ──
    return_notes = models.TextField(
        blank=True,
        help_text="Comment ya mtaaluma anaporudisha submission kwa mwalimu.",
    )
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_by = models.CharField(max_length=100, blank=True)
    returned_by_user = models.ForeignKey(
        'TeacherAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    revision_number = models.PositiveIntegerField(
        default=1,
        help_text="Idadi ya marudio — revision 1 = awali, 2 = ya pili, n.k.",
    )

    class Meta:
        unique_together = [('exam', 'subject')]
        ordering = ['subject__name']

    def __str__(self):
        rev = f" rev{self.revision_number}" if self.revision_number > 1 else ''
        return f"{self.exam} - {self.subject} ({self.status}{rev})"

    @property
    def is_returned(self):
        return self.status == self.STATUS_RETURNED

    @property
    def has_return_notes(self):
        return bool(self.return_notes and self.return_notes.strip())


class PrintSubmission(models.Model):
    """A results PDF the Academic Officer has handed off to the Printing
    Secretary. The PDF itself is never stored — it's regenerated on demand
    from the exam, same as everywhere else in this app; this row just
    tracks the handoff (who submitted it, who printed it, when)."""
    STATUS_PENDING = 'PENDING'
    STATUS_PRINTED = 'PRINTED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PRINTED, 'Printed'),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='print_submissions')
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='print_submissions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    submitted_by = models.ForeignKey(
        'TeacherAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    printed_by = models.ForeignKey(
        'TeacherAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    printed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.exam} — {self.get_status_display()}"


class TimetablePrintSubmission(models.Model):
    """A timetable PDF the Academic Officer has handed off to the Printing
    Secretary. The PDF itself is regenerated on demand; this row just
    tracks the handoff."""
    STATUS_PENDING = 'PENDING'
    STATUS_PRINTED = 'PRINTED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PRINTED, 'Printed'),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='timetable_print_submissions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    submitted_by = models.ForeignKey(
        'TeacherAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    printed_by = models.ForeignKey(
        'TeacherAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    printed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"Timetable — {self.get_status_display()}"


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
    ROLE_PRINTING_SECRETARY = 'PS'

    ROLE_CHOICES = [
        (ROLE_ACADEMIC, 'Academic'),
        (ROLE_TEACHER, 'Teacher'),
        (ROLE_PRINTING_SECRETARY, 'Printing Secretary'),
    ]

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_TEACHER, db_index=True)
    school = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, blank=True, related_name='teacher_accounts',
        help_text="The school this account belongs to. All exams, subjects and teachers this account "
                  "can see are scoped to this school.",
    )
    subjects = models.ManyToManyField(Subject, blank=True, related_name='teachers')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # This project's AUTHENTICATION_BACKENDS include both ResultsAuthBackend
    # and the main site's backends, so a TeacherAccount can legitimately end
    # up as request.user on ANY page, including /admin/ (e.g. someone logged
    # into /shule/ in the same browser session navigating to the Django
    # admin). Django's AdminSite.has_permission() checks
    # `request.user.is_active and request.user.is_staff` unconditionally —
    # without these, that check raises AttributeError instead of just
    # denying access. TeacherAccount is never a staff/superuser account.
    is_staff = False
    is_superuser = False

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = TeacherAccountManager()

    def __str__(self):
        return f"{self.full_name or self.email} ({self.get_role_display()})"

    # Minimal no-op stand-ins for PermissionsMixin's API (we don't need real
    # Django permissions here, just to satisfy admin/permission checks that
    # may run against this model when it ends up as request.user — see the
    # is_staff/is_superuser comment above).
    def has_perm(self, perm, obj=None):
        return False

    def has_perms(self, perm_list, obj=None):
        return False

    def has_module_perms(self, app_label):
        return False

    @property
    def is_academic(self):
        return self.role == self.ROLE_ACADEMIC

    @property
    def is_teacher(self):
        return self.role == self.ROLE_TEACHER

    @property
    def is_printing_secretary(self):
        return self.role == self.ROLE_PRINTING_SECRETARY

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


class StoredRoster(models.Model):
    """Orodha ya wanafunzi iliyopakiwa na kuhifadhiwa.

    Inatumika ku-store orodha ya darasa ili mwalimu aweze kuona na kurekebisha
    alama bila kila mara kupitia PDF/CSV. Inapatikana kwenye dashboard ya mwalimu.
    """
    teacher = models.ForeignKey(TeacherAccount, on_delete=models.CASCADE, related_name='stored_rosters')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='stored_rosters')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='stored_rosters')
    students = models.JSONField(default=list, help_text='List of {id, name} dicts')
    student_count = models.PositiveIntegerField(default=0)
    source_file = models.CharField(max_length=255, blank=True, help_text='Jina la faili la asili')
    source_format = models.CharField(max_length=10, default='pdf', help_text='pdf, csv, excel')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('teacher', 'exam', 'subject')]

    def __str__(self):
        return f"Roster: {self.subject.name} — {self.exam.name} ({self.student_count} students)"


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


# ── Billing (ClickPesa mobile money subscriptions) ───────────────────────────

class SubscriptionPlan(models.Model):
    """A billing tier a school can subscribe to (e.g. monthly / 6 months /
    annual). Prices are set by the system admin in Django admin — not
    hardcoded — so they can be changed without a code deploy."""
    name = models.CharField(max_length=100)
    duration_days = models.PositiveIntegerField(help_text="How many days this plan grants access for.")
    price_tzs = models.PositiveIntegerField(help_text="Price in Tanzanian Shillings.")
    is_active = models.BooleanField(default=True, help_text="Uncheck to hide this plan from schools without deleting it.")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'duration_days']

    def __str__(self):
        return f"{self.name} — {self.price_tzs:,} TZS / {self.duration_days} days"


class SchoolSubscription(models.Model):
    """A school's current billing state. Generating official/general results
    (finalize, PDF, Excel) is gated on this being active."""
    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, null=True, blank=True, on_delete=models.SET_NULL)
    active_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.school} — until {self.active_until or 'never'}"

    @property
    def is_active(self):
        return bool(self.active_until and self.active_until > timezone.now())


class PaymentTransaction(models.Model):
    """One ClickPesa USSD-push attempt. Status is updated by ClickPesa's
    webhook, not by us — we only know a payment succeeded once ClickPesa
    tells us so."""
    STATUS_PENDING = 'PENDING'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_FAILED = 'FAILED'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='payments')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    initiated_by = models.ForeignKey('TeacherAccount', on_delete=models.SET_NULL, null=True, blank=True)
    phone_number = models.CharField(max_length=20, help_text="255XXXXXXXXX format, as sent to ClickPesa.")
    order_reference = models.CharField(max_length=100, unique=True)
    clickpesa_payment_id = models.CharField(max_length=100, blank=True)
    amount = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.school} — {self.amount} TZS ({self.status})"


# =============================================================================
# CLASS TIMETABLE — weekly teaching schedule (generated, then edited as needed)
# =============================================================================

class TimeSlot(models.Model):
    """One row of the daily period grid for a school — either a teaching
    period or a fixed non-teaching block (break, lunch, parade, etc).
    Every school defines its own, since start times/period lengths differ
    school to school."""
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='time_slots')
    day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES)
    order = models.PositiveSmallIntegerField(help_text="Period order for the day, starting from 0.")
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_teaching_slot = models.BooleanField(
        default=True,
        help_text="Turn off for non-teaching periods (break, lunch, cleanliness/parade).",
    )
    label = models.CharField(
        max_length=50, blank=True,
        help_text="For non-teaching periods only — e.g. 'Break', 'Lunch', 'Cleanliness & Parade'.",
    )

    class Meta:
        unique_together = [('school', 'day_of_week', 'order')]
        ordering = ['day_of_week', 'order']

    def __str__(self):
        return f"{self.get_day_of_week_display()} {self.start_time}-{self.end_time}"


class TeachingAssignment(models.Model):
    """A teacher teaches a particular subject for a particular class (form+stream)
    a set number of times per week — this is the 'demand' that the timetable
    generator places into clash-free slots."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='teaching_assignments')
    form = models.PositiveIntegerField()
    stream = models.CharField(max_length=2, blank=True, default='')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey('TeacherAccount', on_delete=models.CASCADE, related_name='teaching_assignments')
    periods_per_week = models.PositiveSmallIntegerField(default=4)
    double_period = models.BooleanField(
        default=True,
        help_text="Schedule 2 consecutive periods per session (e.g. Chemistry 8:00-9:20), "
                  "instead of scattered single periods. If periods_per_week is odd, "
                  "one extra single period remains on its own.",
    )

    class Meta:
        unique_together = [('school', 'form', 'stream', 'subject')]
        ordering = ['form', 'stream', 'subject__name']

    def __str__(self):
        label = f"Form {self.form}{self.stream}" if self.stream else f"Form {self.form}"
        return f"{label} — {self.subject} ({self.teacher}) x{self.periods_per_week}/wk"


class ClassTimetableEntry(models.Model):
    """One filled cell of the standing weekly timetable — (form, stream,
    time_slot) -> (subject, teacher). This is the 'constant until changed'
    schedule itself: generation replaces the rows for the classes it
    covers; a single cell can also be hand-edited without touching the
    rest."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='class_timetable_entries')
    form = models.PositiveIntegerField()
    stream = models.CharField(max_length=2, blank=True, default='')
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, related_name='timetable_entries')
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    teacher = models.ForeignKey('TeacherAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('school', 'form', 'stream', 'time_slot')]
        ordering = ['time_slot__day_of_week', 'time_slot__order', 'form', 'stream']

    def __str__(self):
        label = f"Form {self.form}{self.stream}" if self.stream else f"Form {self.form}"
        return f"{label} @ {self.time_slot} — {self.subject or '—'}"
