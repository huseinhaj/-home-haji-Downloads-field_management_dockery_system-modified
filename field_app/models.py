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
    region = models.ForeignKey(Region, on_delete=models.CASCADE)

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
    district = models.ForeignKey(District, on_delete=models.CASCADE)
    level = models.CharField(max_length=10, choices=SCHOOL_LEVEL_CHOICES)
    capacity = models.PositiveIntegerField(default=10)
    current_students = models.PositiveIntegerField(default=0)
    
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
    student = models.ForeignKey('StudentTeacher', on_delete=models.CASCADE)
    school = models.ForeignKey('School', on_delete=models.CASCADE)
    
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
        unique_together = ['assessor', 'student', 'academic_year']
    
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
    assessor = models.ForeignKey(Assessor, on_delete=models.CASCADE)
    school = models.ForeignKey('School', on_delete=models.CASCADE)
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
