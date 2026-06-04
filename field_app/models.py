from django.db import models
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.contrib.auth import get_user_model

# =========================
# Custom User
# =========================

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.email

# =========================
# Student Profile
# =========================

# =========================
# Student Profile (UPDATED with school change tracking)
# =========================

class StudentTeacher(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15)
    selected_school = models.ForeignKey('School', null=True, blank=True, on_delete=models.SET_NULL)
    
    APPROVAL_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    approval_status = models.CharField(max_length=10, choices=APPROVAL_STATUS_CHOICES, default='pending')

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='approved_students',
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    approval_date = models.DateTimeField(null=True, blank=True)
    subjects = models.ManyToManyField('Subject', blank=True)
    
    # ========== NEW FIELDS FOR SCHOOL CHANGE TRACKING ==========
    initial_school_selection_date = models.DateTimeField(null=True, blank=True, 
        help_text="Tarehe ya kwanza mwanafunzi alipochagua shule")
    school_change_count = models.IntegerField(default=0, 
        help_text="Idadi ya mara mwanafunzi amebadili shule")
    last_school_change_date = models.DateTimeField(null=True, blank=True,
        help_text="Tarehe ya mwisho kubadili shule")

    def __str__(self):
        return self.full_name
    
    # ========== HELPER PROPERTIES FOR SCHOOL CHANGE ==========
    @property
    def can_change_school(self):
        """
        Check if student can still change school:
        - Must have initial selection date
        - Within 7 days of initial selection
        - Less than 3 changes made
        """
        if not self.initial_school_selection_date:
            # First time selection - they can change
            return True
        
        days_passed = (timezone.now() - self.initial_school_selection_date).days
        return days_passed <= 7 and self.school_change_count < 3
    
    @property
    def days_remaining_to_change(self):
        """Days remaining to change school (max 7 days total)"""
        if not self.initial_school_selection_date:
            return 7
        
        days_passed = (timezone.now() - self.initial_school_selection_date).days
        return max(0, 7 - days_passed)
    
    @property
    def changes_remaining(self):
        """Number of changes remaining (max 3 total)"""
        return max(0, 3 - self.school_change_count)
    
    @property
    def has_change_window_expired(self):
        """Check if 7-day window has expired"""
        if not self.initial_school_selection_date:
            return False
        days_passed = (timezone.now() - self.initial_school_selection_date).days
        return days_passed > 7
# =========================
# Geography
# =========================
# =========================
# HELPER FUNCTION - Get Current Academic Year
# =========================

def get_current_academic_year():
    """Get current academic year based on current date"""
    from django.utils import timezone
    
    current_date = timezone.now().date()
    current_year = current_date.year
    current_month = current_date.month
    
    if current_month >= 8:  # August to December
        academic_year_string = f"{current_year}/{current_year + 1}"
    else:  # January to July
        academic_year_string = f"{current_year - 1}/{current_year}"
    
    # Get OR create academic year
    try:
        academic_year = AcademicYear.objects.get(year=academic_year_string)
        # Ensure it's active
        if not academic_year.is_active:
            academic_year.is_active = True
            academic_year.save()
            # Deactivate others
            AcademicYear.objects.exclude(id=academic_year.id).update(is_active=False)
    except AcademicYear.DoesNotExist:
        # Deactivate all existing years
        AcademicYear.objects.all().update(is_active=False)
        
        # Create new year
        academic_year = AcademicYear.objects.create(
            year=academic_year_string,
            is_active=True
        )
    
    return academic_year
class Region(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class District(models.Model):
    name = models.CharField(max_length=100)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, db_index=True)

    def __str__(self):
        return f"{self.name} ({self.region.name})"

# =========================
# School & Subjects
# =========================

class School(models.Model):
    SCHOOL_LEVEL_CHOICES = [
        ('Primary', 'Primary School'),
        ('Secondary', 'Secondary School'),
    ]

    name = models.CharField(max_length=200)
    school_code = models.CharField(max_length=20, blank=True, default='', db_index=True, help_text="Namba ya usajili e.g. S.0123 au P.4567")
    district = models.ForeignKey(District, on_delete=models.CASCADE, db_index=True)
    level = models.CharField(max_length=10, choices=SCHOOL_LEVEL_CHOICES)
    capacity = models.PositiveIntegerField(default=10)
    current_students = models.PositiveIntegerField(default=0)

    head_name = models.CharField(max_length=255, blank=True, default='')
    head_phone = models.CharField(max_length=20, blank=True, default='')

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    address = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} - {self.get_level_display()}"

class Subject(models.Model):
    LEVEL_CHOICES = [
        ('primary', 'Primary'),
        ('secondary', 'Secondary'),
    ]

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='secondary')

    def __str__(self):
        return f"{self.name} ({self.level})"

class SchoolSubjectCapacity(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    max_students = models.PositiveIntegerField(default=2)
    current_students = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('school', 'subject')

    def __str__(self):
        return f"{self.school.name} - {self.subject.name}"

# =========================
# Academic Year & Pinning
# =========================

class AcademicYear(models.Model):
    year = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return self.year

# =========================
# Problematic Schools Model
# =========================

class ProblematicSchool(models.Model):
    PROBLEM_CHOICES = [
        ('no_electricity', 'Hakuna Umeme'),
        ('water_issues', 'Matatizo ya Maji'),
        ('headmaster_refusal', 'Mkuu wa Shule Hakubali'),
        ('infrastructure', 'Matatizo ya Miundombinu'),
        ('security', 'Matatizo ya Usalama'),
        ('other', 'Nyingine'),
    ]
    
    academic_year = models.ForeignKey(
        AcademicYear, 
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    problem_type = models.CharField(max_length=50, choices=PROBLEM_CHOICES)
    description = models.TextField(help_text="Maelezo ya kina kuhusu shida")
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reported_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        related_name='resolved_schools', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL
    )
    resolution_notes = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = ['academic_year', 'school']
        verbose_name_plural = "Problematic Schools"
    
    def __str__(self):
        return f"{self.school.name} - {self.get_problem_type_display()}"

class RegionPin(models.Model):
    academic_year = models.ForeignKey(
        AcademicYear, 
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    region = models.ForeignKey(Region, on_delete=models.CASCADE)
    is_pinned = models.BooleanField(default=True)

    class Meta:
        unique_together = ('academic_year', 'region')

class SchoolPin(models.Model):
    PIN_REASON_CHOICES = [
        ('manual', 'Manual Pin'),
        ('problematic', 'Shule Yenye Shida'),
        ('capacity', 'Ujazo Kamili'),
        ('other', 'Nyingine'),
    ]
    
    academic_year = models.ForeignKey(
        AcademicYear, 
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    is_pinned = models.BooleanField(default=True)
    pin_reason = models.CharField(max_length=20, choices=PIN_REASON_CHOICES, default='manual')
    problem_details = models.ForeignKey(
        ProblematicSchool, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='school_pins'
    )
    pinned_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    pinned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('academic_year', 'school')

    def __str__(self):
        return f"{self.school.name} - {self.get_pin_reason_display()}"

# =========================
# Logbook
# =========================

class LogbookEntry(models.Model):
    DAY_CHOICES = [
        ('monday', 'Jumatatu'),
        ('tuesday', 'Jumanne'),
        ('wednesday', 'Jumatano'),
        ('thursday', 'Alhamisi'),
        ('friday', 'Ijumaa'),
    ]
    
    student = models.ForeignKey(StudentTeacher, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    day_of_week = models.CharField(max_length=10, choices=DAY_CHOICES)
    
    # Teaching record fields
    subject_taught = models.ForeignKey(
        'Subject', on_delete=models.SET_NULL, null=True, blank=True, related_name='logbook_entries'
    )
    topic_taught = models.CharField(max_length=200, blank=True, null=True)
    class_taught = models.CharField(max_length=50, blank=True, null=True, help_text="e.g. Form 2A, Standard 5")
    num_students_present = models.IntegerField(null=True, blank=True)
    activity_type = models.CharField(
        max_length=20,
        choices=[
            ('theory', 'Somo la Nadharia'),
            ('practical', 'Vitendo/Maabara'),
            ('revision', 'Mapitio'),
            ('assessment', 'Tathmini/Mtihani'),
            ('preparation', 'Maandalizi ya Somo'),
            ('other', 'Nyingine'),
        ],
        blank=True, null=True
    )

    # TIE format: per-period lesson records stored as JSON list
    lessons_data = models.JSONField(default=list, blank=True)
    # General daily record
    other_activities = models.TextField(blank=True, null=True)
    supervisor_remarks = models.TextField(blank=True, null=True)
    head_teacher_remarks = models.TextField(blank=True, null=True)

    # Legacy fields (kept for backward compatibility)
    morning_activity = models.TextField(blank=True, null=True)
    afternoon_activity = models.TextField(blank=True, null=True)
    challenges_faced = models.TextField(blank=True, null=True)
    lessons_learned = models.TextField(blank=True, null=True)
    
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    location_address = models.CharField(max_length=255, blank=True, null=True)
    is_location_verified = models.BooleanField(default=False)
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    is_at_school = models.BooleanField(default=False)
    
    morning_check_in = models.DateTimeField(blank=True, null=True)
    afternoon_check_out = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['student', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['student', 'date']),
            models.Index(fields=['student', '-date']),
        ]
    
    def __str__(self):
        return f"{self.student.full_name} - {self.date}"
    
    def save(self, *args, **kwargs):
        if self.date:
            days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            self.day_of_week = days[self.date.weekday()]
        
        if not self.school and self.student.selected_school:
            self.school = self.student.selected_school
            
        super().save(*args, **kwargs)

# =========================
# Approval Letters
# =========================

class ApprovalLetter(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    students = models.ManyToManyField(StudentTeacher)
    generated_date = models.DateTimeField(auto_now_add=True)
    letter_file = models.FileField(upload_to='approval_letters/')

    def __str__(self):
        return f"Approval Letter for {self.school.name}"

# =========================
# School Requirements
# =========================

class SchoolRequirement(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    subject = models.CharField(max_length=100)
    year = models.IntegerField()
    required_students = models.IntegerField()

# =========================
# File Uploads
# =========================

class SchoolUpdateFile(models.Model):
    file = models.FileField(upload_to='uploads/school_updates/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Update file {self.file.name} uploaded at {self.uploaded_at}"

# =========================
# Student Applications
# =========================

class StudentApplication(models.Model):
    APPLICATION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    student = models.ForeignKey(StudentTeacher, on_delete=models.CASCADE, related_name='applications')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    application_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, 
        choices=APPLICATION_STATUS_CHOICES, 
        default='pending'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='approved_applications',
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    approval_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('student', 'subject', 'school')
        ordering = ['-application_date']

    def __str__(self):
        return f"{self.student.full_name} - {self.subject.name} at {self.school.name} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.student_id:
            raise ValueError("Application must have a student")
        if not self.school_id:
            raise ValueError("Application must have a school")
        super().save(*args, **kwargs)

# =========================
# Assessor Model
# =========================

class Assessor(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    full_name = models.CharField(max_length=200)
    email = models.EmailField(unique=True, blank=True, null=True)
    phone_number = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    credentials_sent = models.BooleanField(default=False)
    
    current_academic_year = models.ForeignKey(
        'AcademicYear', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assessors_current_year',
        verbose_name="Mwaka wa Masomo wa Akaunti"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.full_name} ({self.email})"
    
    @property
    def needs_credentials_for_year(self):
        if not self.current_academic_year:
            return True
        
        current_year = AcademicYear.objects.filter(is_active=True).first()
        if not current_year:
            return False
        
        if self.current_academic_year.id != current_year.id:
            return True
        
        if not self.user:
            return True
        
        return False

# =========================
# School Assessment Model (FIXED)
# =========================

# models.py - FIX SchoolAssessment model
class SchoolAssessment(models.Model):
    assessor = models.ForeignKey(Assessor, on_delete=models.CASCADE)
    school = models.ForeignKey('School', on_delete=models.CASCADE)
    assigned_date = models.DateField(default=timezone.now)
    assessment_date = models.DateField()
    is_completed = models.BooleanField(default=False)
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='supervised_assessments'
    )
    
    academic_year = models.ForeignKey(
        AcademicYear, 
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        #default=get_current_academic_year  # ⬅️ HAPA
    )
    
    class Meta:
        unique_together = ['assessor', 'school', 'academic_year']
    
    def __str__(self):
        year = self.academic_year.year if self.academic_year else "No Year"
        return f"{self.assessor} - {self.school} ({year})"
    
    def save(self, *args, **kwargs):
        # 🔴 CRITICAL FIX: Ensure academic_year is ALWAYS set
        if not self.academic_year:
            try:
                # First, try to get current academic year
                current_year = AcademicYear.objects.filter(is_active=True).first()
                
                # If no active year, create one
                if not current_year:
                    from django.utils import timezone
                    current_date = timezone.now().date()
                    current_year_num = current_date.year
                    current_month = current_date.month
                    
                    if current_month >= 8:  # August to December
                        academic_year_string = f"{current_year_num}/{current_year_num + 1}"
                    else:  # January to July
                        academic_year_string = f"{current_year_num - 1}/{current_year_num}"
                    
                    current_year, created = AcademicYear.objects.get_or_create(
                        year=academic_year_string,
                        defaults={'is_active': True}
                    )
                
                self.academic_year = current_year
                
            except Exception as e:
                # If everything fails, get ANY academic year
                any_year = AcademicYear.objects.first()
                if any_year:
                    self.academic_year = any_year
                else:
                    # Last resort: create a default year
                    default_year = AcademicYear.objects.create(
                        year="2025/2026",
                        is_active=True
                    )
                    self.academic_year = default_year
        
        super().save(*args, **kwargs)

class StudentAssessment(models.Model):
    ASSESSMENT_STATUS = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]
    
    assessor = models.ForeignKey(Assessor, on_delete=models.CASCADE)
    student = models.ForeignKey('StudentTeacher', on_delete=models.CASCADE, db_index=True)
    school = models.ForeignKey('School', on_delete=models.CASCADE, db_index=True)

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_assessments'
    )

    assessment_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=ASSESSMENT_STATUS, default='pending')
    score = models.CharField(max_length=10, blank=True, default='')
    comments = models.TextField(blank=True, default='')

    class Meta:
        unique_together = ['assessor', 'student', 'school', 'academic_year']
    
    def __str__(self):
        year = self.academic_year.year if self.academic_year else "No Year"
        return f"{self.assessor} - {self.student} ({year})"
    
    def save(self, *args, **kwargs):
        if not self.academic_year:
            try:
                current_year = AcademicYear.objects.filter(is_active=True).first()
                if current_year:
                    self.academic_year = current_year
            except Exception as e:
                print(f"⚠️ Error setting academic year: {e}")
        
        super().save(*args, **kwargs)

# =========================
# School Assignment Model
# =========================

class SchoolAssignment(models.Model):
    assessor = models.ForeignKey(Assessor, on_delete=models.CASCADE, db_index=True)
    school = models.ForeignKey('School', on_delete=models.CASCADE, db_index=True)
    assigned_date = models.DateField(auto_now_add=True)
    assessment_date = models.DateField()
    is_completed = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['assessor', 'school']
    
    def __str__(self):
        return f"{self.assessor} -> {self.school}"

# =========================
# Additional models
# =========================

class SchoolSummary(models.Model):
    academic_year = models.ForeignKey(
        AcademicYear, 
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['academic_year', 'school']
    
    def __str__(self):
        year = self.academic_year.year if self.academic_year else "No Year"
        return f"{self.school.name} Summary ({year})"

class RegionalSummary(models.Model):
    academic_year = models.ForeignKey(
        AcademicYear, 
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    region = models.ForeignKey(Region, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ('academic_year', 'region')
    
    def __str__(self):
        year = self.academic_year.year if self.academic_year else "No Year"
        return f"{self.region.name} Summary ({year})"

class SchoolData(models.Model):
    academic_year = models.ForeignKey(
        AcademicYear, 
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ('academic_year', 'school')
    
    def __str__(self):
        year = self.academic_year.year if self.academic_year else "No Year"
        return f"{self.school.name} Data ({year})"
# =========================
# SCHEME OF WORK (MUUNDO WA KAZI)
# =========================

class SchemeOfWork(models.Model):
    TERM_CHOICES = [
        ('I', 'Term I'),
        ('II', 'Term II'),
        ('III', 'Term III'),
    ]
    
    LEVEL_CHOICES = [
        ('primary', 'Primary School'),
        ('ordinary', 'Ordinary Level'),
        ('advanced', 'Advanced Level'),
    ]
    
    # Relation to student and school
    student = models.ForeignKey(StudentTeacher, on_delete=models.CASCADE, related_name='schemes')
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='schemes')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='schemes')
    
    # Basic info
    education_level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    class_name = models.CharField(max_length=50)  # e.g., "Form 2"
    term = models.CharField(max_length=10, choices=TERM_CHOICES)
    year = models.IntegerField(default=2026)
    syllabus = models.CharField(max_length=100, default='New Syllabus')
    
    # Schedule info
    total_weeks = models.IntegerField(default=12)
    periods_per_week = models.IntegerField(default=8)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    # Teacher info
    teacher_name = models.CharField(max_length=200)
    reference_source = models.CharField(max_length=500, blank=True, null=True)
    
    # Reference file upload
    reference_file = models.FileField(upload_to='scheme_references/', blank=True, null=True)
    
    # Generated data (JSON) - stores the table rows
    scheme_data = models.JSONField(default=list, help_text="Generated scheme of work data")
    
    # Breaks (holidays/exams) stored as JSON
    breaks = models.JSONField(default=list, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    generated_by_ai = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-year', '-created_at']
        unique_together = ['student', 'subject', 'term', 'year']
    
    def __str__(self):
        return f"{self.subject.name} - {self.class_name} - Term {self.term} {self.year}"
    
    @property
    def total_entries(self):
        return len(self.scheme_data) if self.scheme_data else 0


# =========================
# LESSON PLAN (MPANGO WA KIPINDI)
# =========================

class LessonPlan(models.Model):
    EDUCATION_LEVEL_CHOICES = [
        ('primary', 'Primary School'),
        ('ordinary', 'Ordinary Level'),
        ('advanced', 'Advanced Level'),
    ]
    
    TERM_CHOICES = [
        ('I', 'Term I'),
        ('II', 'Term II'),
        ('III', 'Term III'),
    ]
    
    # Relation to student and school
    student = models.ForeignKey(StudentTeacher, on_delete=models.CASCADE, related_name='lesson_plans')
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='lesson_plans')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='lesson_plans')
    scheme = models.ForeignKey(SchemeOfWork, on_delete=models.SET_NULL, null=True, blank=True, related_name='lesson_plans')
    logbook_entry = models.ForeignKey(LogbookEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='lesson_plans')
    
    # Basic lesson info
    education_level = models.CharField(max_length=20, choices=EDUCATION_LEVEL_CHOICES)
    class_name = models.CharField(max_length=50)
    term = models.CharField(max_length=10, choices=TERM_CHOICES)
    year = models.IntegerField(default=2026)
    
    topic = models.CharField(max_length=200)
    subtopic = models.CharField(max_length=200, blank=True, null=True)
    date = models.DateField(default=timezone.now)
    duration = models.IntegerField(default=40, help_text="Duration in minutes")
    
    # Teacher info
    teacher_name = models.CharField(max_length=200)
    council_name = models.CharField(max_length=200, blank=True, null=True)
    region_name = models.CharField(max_length=200, blank=True, null=True)
    office_name = models.CharField(max_length=200, blank=True, null=True)
    
    # Student attendance
    total_students = models.IntegerField(default=0, blank=True, null=True)
    present_students = models.IntegerField(default=0, blank=True, null=True)
    
    # Reference source
    reference_source = models.CharField(max_length=500, blank=True, null=True)
    reference_file = models.FileField(upload_to='lesson_references/', blank=True, null=True)
    
    # Competences
    main_competence = models.TextField(blank=True, null=True)
    specific_competence = models.TextField(blank=True, null=True)
    previous_knowledge = models.TextField(blank=True, null=True)
    
    # Learning objectives and methods (stored as JSON arrays)
    learning_objectives = models.JSONField(default=list, help_text="List of learning objectives")
    teaching_methods = models.JSONField(default=list, help_text="List of teaching methods")
    teaching_resources = models.JSONField(default=list, help_text="List of teaching resources")
    
    # Lesson development (stored as JSON)
    # Structure: [{"time": "5 min", "stage": "Introduction", "teacher_activities": "...", "student_activities": "...", "assessment_criteria": "..."}]
    lesson_development = models.JSONField(default=list)
    
    # Remarks
    remarks = models.TextField(blank=True, null=True)
    
    # AI generation info
    generated_by_ai = models.BooleanField(default=True)
    ai_model_used = models.CharField(max_length=50, default='gemini-1.5-flash', blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.subject.name} - {self.topic} ({self.date})"
    
    def save(self, *args, **kwargs):
        # Auto-set teacher name from student if not provided
        if not self.teacher_name and self.student:
            self.teacher_name = self.student.full_name
        
        # Auto-set school from student if not provided
        if not self.school and self.student and self.student.selected_school:
            self.school = self.student.selected_school
        
        super().save(*args, **kwargs)


# =========================
# UPLOADED REFERENCES (For tracking uploaded files)
# =========================

class UploadedReference(models.Model):
    REFERENCE_TYPE_CHOICES = [
        ('scheme', 'Scheme of Work'),
        ('lesson', 'Lesson Plan'),
        ('textbook', 'Textbook'),
        ('syllabus', 'Syllabus'),
        ('other', 'Other'),
    ]
    
    user = models.ForeignKey(StudentTeacher, on_delete=models.CASCADE, related_name='uploaded_references')
    file = models.FileField(upload_to='references/%Y/%m/')
    original_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20, choices=REFERENCE_TYPE_CHOICES, default='other')
    description = models.TextField(blank=True, null=True)
    file_size = models.IntegerField(default=0, help_text="File size in bytes")
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.original_name} - {self.user.full_name}"
    
    def save(self, *args, **kwargs):
        if self.file and not self.file_size:
            self.file_size = self.file.size
        super().save(*args, **kwargs)


# =========================
# AI GENERATION LOG (For tracking and debugging)
# =========================

class AIGenerationLog(models.Model):
    GENERATION_TYPE_CHOICES = [
        ('scheme_of_work', 'Scheme of Work'),
        ('lesson_plan', 'Lesson Plan'),
    ]
    
    user = models.ForeignKey(StudentTeacher, on_delete=models.CASCADE, null=True, blank=True)
    generation_type = models.CharField(max_length=20, choices=GENERATION_TYPE_CHOICES)
    
    # Input data (JSON)
    input_data = models.JSONField(default=dict)
    
    # Output data (JSON)
    output_data = models.JSONField(default=dict, null=True, blank=True)
    
    # Prompt sent to AI
    prompt_sent = models.TextField(blank=True, null=True)
    
    # Response from AI
    ai_response = models.TextField(blank=True, null=True)
    
    # Status and timing
    was_successful = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, null=True)
    
    generation_time_ms = models.IntegerField(default=0, help_text="Generation time in milliseconds")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.get_generation_type_display()} - {self.created_at}"        
# =========================
# EDUCATION LEVELS & CLASSES
# =========================

class EducationLevel(models.Model):
    name = models.CharField(max_length=50, unique=True)  # Primary, Ordinary Level, Advanced Level
    code = models.CharField(max_length=20, unique=True)
    order = models.IntegerField(default=0)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['order']

class ClassLevel(models.Model):
    education_level = models.ForeignKey(EducationLevel, on_delete=models.CASCADE, related_name='classes')
    name = models.CharField(max_length=50)  # e.g., "Form 1", "Standard 1", "Form 5"
    code = models.CharField(max_length=20)
    order = models.IntegerField(default=0)
    
    def __str__(self):
        return f"{self.education_level.name} - {self.name}"
    
    class Meta:
        ordering = ['education_level', 'order']
        unique_together = ['education_level', 'name']

# =========================
# TEXTBOOKS / REFERENCES
# =========================

class Textbook(models.Model):
    LEVEL_CHOICES = [
        ('primary', 'Primary School'),
        ('ordinary', 'Ordinary Level'),
        ('advanced', 'Advanced Level'),
    ]
    
    title = models.CharField(max_length=200)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True)
    education_level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    class_level = models.ForeignKey(ClassLevel, on_delete=models.CASCADE, null=True, blank=True)
    publisher = models.CharField(max_length=100, default='TIE')
    year = models.IntegerField(null=True, blank=True)
    isbn = models.CharField(max_length=50, blank=True, null=True)
    file = models.FileField(upload_to='textbooks/', blank=True, null=True)
    cover_image = models.ImageField(upload_to='textbook_covers/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.title} ({self.get_education_level_display()})"


# =========================
# BODI YA WALIMU — Board Member & Comments
# =========================

class BoardMember(models.Model):
    ROLE_CHOICES = [
        ('inspector', 'Mkaguzi wa Shule'),
        ('head_teacher', 'Mkuu wa Shule'),
        ('deo', 'Afisa Elimu wa Wilaya (DEO)'),
        ('reo', 'Afisa Elimu wa Mkoa (REO)'),
        ('chair', 'Mwenyekiti wa Bodi'),
        ('member', 'Mjumbe wa Bodi'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='board_member'
    )
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    region = models.ForeignKey(
        'Region', on_delete=models.SET_NULL, null=True, blank=True, related_name='board_members'
    )
    district = models.ForeignKey(
        'District', on_delete=models.SET_NULL, null=True, blank=True, related_name='board_members'
    )
    school = models.ForeignKey(
        'School', on_delete=models.SET_NULL, null=True, blank=True, related_name='board_members'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"


class BoardComment(models.Model):
    STATUS_CHOICES = [
        ('excellent', 'Vizuri Sana — Endelea Hivyo'),
        ('good', 'Vizuri — Kazi Nzuri'),
        ('average', 'Wastani — Boresha'),
        ('behind', 'Nyuma — Akazane'),
        ('critical', 'Muhimu — Hatua ya Haraka'),
    ]

    board_member = models.ForeignKey(
        BoardMember, on_delete=models.CASCADE, related_name='comments'
    )
    student = models.ForeignKey(
        StudentTeacher, on_delete=models.CASCADE, related_name='board_comments'
    )
    school = models.ForeignKey('School', on_delete=models.CASCADE)
    comment = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='good')
    is_read = models.BooleanField(default=False)
    academic_year = models.ForeignKey(
        'AcademicYear', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', '-created_at']),
        ]

    def __str__(self):
        return f"{self.board_member.full_name} → {self.student.full_name} ({self.status})"


# =========================
# DEO Monthly AI Report
# =========================

class MonthlyReport(models.Model):
    MONTH_CHOICES = [
        (1, 'Januari'), (2, 'Februari'), (3, 'Machi'), (4, 'Aprili'),
        (5, 'Mei'), (6, 'Juni'), (7, 'Julai'), (8, 'Agosti'),
        (9, 'Septemba'), (10, 'Oktoba'), (11, 'Novemba'), (12, 'Desemba'),
    ]

    district = models.ForeignKey(
        'District', on_delete=models.CASCADE, related_name='monthly_reports'
    )
    month = models.PositiveSmallIntegerField(choices=MONTH_CHOICES)
    year = models.PositiveSmallIntegerField()
    generated_by = models.ForeignKey(
        'BoardMember', on_delete=models.SET_NULL, null=True, blank=True
    )
    ai_content = models.JSONField(default=dict)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('district', 'month', 'year')
        ordering = ['-year', '-month']
        indexes = [
            models.Index(fields=['district', 'year', 'month']),
        ]

    def __str__(self):
        return f"Ripoti {self.get_month_display()} {self.year} — {self.district.name}"


# =========================
# District Student Teacher Allocation (DEO)
# =========================

class DistrictAllocation(models.Model):
    """DEO anaweka idadi ya walimu wanafunzi wanaohitajika katika wilaya yake"""
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='allocations')
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE,
        null=True, blank=True, related_name='district_allocations'
    )
    primary_needed = models.PositiveIntegerField(default=0, help_text="Walimu wanafunzi wa shule za msingi")
    secondary_needed = models.PositiveIntegerField(default=0, help_text="Walimu wanafunzi wa shule za sekondari")
    notes = models.TextField(blank=True, help_text="Maelezo ya ziada kutoka DEO")
    document = models.FileField(upload_to='allocations/', blank=True, null=True, help_text="Hati ya mahitaji (PDF/Word)")
    uploaded_by = models.ForeignKey(
        'BoardMember', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='allocations'
    )
    ai_parsed = models.BooleanField(default=False, help_text="AI ilitumika kuchambua document")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('district', 'academic_year')
        ordering = ['-created_at']

    @property
    def primary_filled(self):
        return StudentApplication.objects.filter(
            school__district=self.district,
            school__level='Primary',
            status='approved',
        ).values('student').distinct().count()

    @property
    def secondary_filled(self):
        return StudentApplication.objects.filter(
            school__district=self.district,
            school__level='Secondary',
            status='approved',
        ).values('student').distinct().count()

    @property
    def primary_remaining(self):
        return max(0, self.primary_needed - self.primary_filled)

    @property
    def secondary_remaining(self):
        return max(0, self.secondary_needed - self.secondary_filled)

    @property
    def total_needed(self):
        return self.primary_needed + self.secondary_needed

    @property
    def total_filled(self):
        return self.primary_filled + self.secondary_filled

    def __str__(self):
        return f"{self.district.name} — {self.academic_year or 'No Year'}"


class SchoolAllocation(models.Model):
    """Mgawanyo wa idadi kwa kila shule ndani ya wilaya"""
    district_allocation = models.ForeignKey(
        DistrictAllocation, on_delete=models.CASCADE, related_name='school_allocations'
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='allocations')
    quota = models.PositiveIntegerField(default=0, help_text="Idadi iliyoidhinishwa na DEO")
    head_teacher_requested = models.PositiveIntegerField(default=0, help_text="Idadi iliyoombwa na Mkuu wa Shule")
    head_teacher_notes = models.TextField(blank=True, help_text="Maelezo ya Mkuu wa Shule")

    class Meta:
        unique_together = ('district_allocation', 'school')

    @property
    def filled(self):
        return StudentApplication.objects.filter(
            school=self.school, status='approved'
        ).values('student').distinct().count()

    @property
    def remaining(self):
        return max(0, self.quota - self.filled)

    @property
    def is_full(self):
        return self.filled >= self.quota

    def __str__(self):
        return f"{self.school.name}: {self.quota}"


# =========================
# School Head Requirement Requests
# =========================

class SchoolHeadRequest(models.Model):
    """Mkuu wa shule anatuma idadi ya walimu wanafunzi wanaohitajika."""
    STATUS_CHOICES = [
        ('pending', 'Inasubiri'),
        ('reviewed', 'Imepitiwa na DEO'),
        ('applied', 'Imewekwa kwenye Allocation'),
        ('rejected', 'Imekataliwa'),
    ]
    LEVEL_CHOICES = [
        ('Primary', 'Shule ya Msingi'),
        ('Secondary', 'Shule ya Sekondari'),
    ]

    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='head_requests', db_index=True)
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, null=True, blank=True
    )
    # School matching — submitted text + matched FK
    school_name_submitted = models.CharField(max_length=255, help_text="Jina la shule kama ilivyoandikwa na mkuu")
    school = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='head_requests', help_text="Shule iliyolinganishwa na AI"
    )
    head_name = models.CharField(max_length=255)
    head_phone = models.CharField(max_length=20, blank=True)
    submitter_email = models.EmailField(blank=True, help_text="Email ya mkuu aliyetuma ombi")
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    students_needed = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        'BoardMember', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_requests'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.head_name} — {self.school_name_submitted} ({self.students_needed})"
