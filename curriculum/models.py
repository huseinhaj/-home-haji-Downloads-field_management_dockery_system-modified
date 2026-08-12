"""
TLM Teacher model — lightweight registration for the Teaching & Learning Materials system.
No login/password needed. Teacher registers once via phone number + location, then
we remember them via session/cookie on subsequent visits.
"""
from django.db import models
from django.utils import timezone
from field_app.models import Region, District, School, Subject

import re


class TLMTeacher(models.Model):
    """A teacher registered to use TLM tools (Scheme of Work, Lesson Plan)."""
    full_name = models.CharField(max_length=200, verbose_name="Jina Kamili")
    phone_number = models.CharField(
        max_length=15, unique=True, verbose_name="Namba ya Simu",
        help_text="Namba ya simu itakayotumika kukutambua ukirudi"
    )
    region = models.ForeignKey(
        Region, on_delete=models.SET_NULL, null=True, verbose_name="Mkoa"
    )
    district = models.ForeignKey(
        District, on_delete=models.SET_NULL, null=True, verbose_name="Wilaya"
    )
    school = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, verbose_name="Shule"
    )
    
    # New fields for auto-fill in lesson plan / scheme
    class_name = models.CharField(max_length=50, blank=True, default='', verbose_name="Darasa")
    stream = models.CharField(max_length=10, blank=True, default='', verbose_name="Stream/Section")
    total_boys = models.PositiveIntegerField(default=0, verbose_name="Wavulana (Registered)")
    total_girls = models.PositiveIntegerField(default=0, verbose_name="Wasichana (Registered)")
    
    preferred_language = models.CharField(
        max_length=10,
        choices=[
            ('auto', 'Auto (Otomatiki — kulingana na somo)'),
            ('english', 'English'),
            ('kiswahili', 'Kiswahili'),
        ],
        default='auto',
        verbose_name="Lugha / Language",
        help_text="Chagua lugha ya Scheme na Lesson Plan zako",
    )

    theme = models.CharField(
        max_length=20,
        choices=[
            ('classic', 'TIE Classic — Navy & Gold'),
            ('tanzania', 'Tanzania — Green & Yellow'),
            ('ocean', 'Ocean Blue — Blue & Teal'),
            ('royal', 'Royal Purple — Purple & Pink'),
            ('executive', 'Executive — Charcoal & Silver'),
            ('sunset', 'Sunset — Warm Orange & Coral'),
            ('forest', 'Forest — Deep Green & Emerald'),
            ('midnight', 'Midnight — Dark Blue & Indigo'),
            ('cherry', 'Cherry — Red & Pink Blossom'),
            ('safari', 'Safari — Brown & Amber'),
            ('dawn', 'Dawn — Soft Pink & Lavender'),
        ],
        default='classic',
        verbose_name="Rangi / Theme",
        help_text="Chagua rangi za PDF zako (Scheme & Lesson Plan)",
    )
    
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, verbose_name="Somo"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Mwalimu (TLM)"
        verbose_name_plural = "Walimu (TLM)"

    def __str__(self):
        return f"{self.full_name} — {self.phone_number}"


class Testimonial(models.Model):
    """Real testimonial/feedback from a teacher who has used TLM tools."""
    teacher = models.ForeignKey(
        TLMTeacher, on_delete=models.CASCADE, null=True, blank=True,
        verbose_name="Mwalimu"
    )
    teacher_name = models.CharField(max_length=200, verbose_name="Jina la Mwalimu")
    school_name = models.CharField(max_length=300, verbose_name="Jina la Shule", blank=True)
    message = models.TextField(verbose_name="Ujumbe / Maoni")
    role = models.CharField(max_length=100, verbose_name="Wadhifa",
                            default="Mwalimu", blank=True)
    is_approved = models.BooleanField(default=True, verbose_name="Imeidhinishwa")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Testimonial"
        verbose_name_plural = "Testimonials"

    def __str__(self):
        return f"{self.teacher_name}: {self.message[:60]}"


class LessonNote(models.Model):
    """Standalone lesson notes — teachers write their own reflections, methods, challenges."""
    EDUCATION_LEVEL_CHOICES = [
        ('primary', 'Primary School'),
        ('ordinary', 'Ordinary Level'),
        ('advanced', 'Advanced Level'),
        ('technical', 'Technical / VETA'),
    ]
    
    teacher = models.ForeignKey(
        TLMTeacher, on_delete=models.CASCADE, null=True, blank=True,
        verbose_name="Mwalimu"
    )
    teacher_name = models.CharField(max_length=200, verbose_name="Jina la Mwalimu")
    school = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Shule"
    )
    school_name = models.CharField(max_length=300, verbose_name="Jina la Shule", blank=True)
    education_level = models.CharField(
        max_length=20, choices=EDUCATION_LEVEL_CHOICES, default='ordinary',
        verbose_name="Ngazi ya Elimu"
    )
    class_name = models.CharField(max_length=50, verbose_name="Darasa", blank=True)
    subject = models.CharField(max_length=200, verbose_name="Somo", blank=True)
    topic = models.CharField(max_length=300, verbose_name="Mada / Topic", blank=True)
    content = models.TextField(verbose_name="Maelezo ya Somo (Lesson Notes)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Lesson Note"
        verbose_name_plural = "Lesson Notes"

    def __str__(self):
        return f"{self.teacher_name} — {self.subject or 'N/A'} ({self.created_at.strftime('%d %b %Y')})"


class SubjectTopic(models.Model):
    """
    Official TIE syllabus topics for a subject and class level.
    E.g., Mathematics Form 1 has topics like "Numbers", "Algebra", etc.
    """
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name='topics',
        verbose_name="Somo"
    )
    class_name = models.CharField(
        max_length=50, verbose_name="Darasa",
        help_text="e.g. Form 1, Form 2, Standard 5"
    )
    name = models.CharField(max_length=300, verbose_name="Jina la Topic / Mada Kuu")
    order = models.PositiveIntegerField(default=0, verbose_name="Mpangilio")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['subject', 'class_name', 'order']
        unique_together = ['subject', 'class_name', 'name']
        verbose_name = "Topic (Syllabus)"
        verbose_name_plural = "Topics (Syllabus)"

    def __str__(self):
        return f"{self.subject.name} {self.class_name} — {self.name}"


class TopicSubtopic(models.Model):
    """
    Subtopics under a main topic from the TIE syllabus.
    E.g., under "Numbers" (Mathematics Form 1): "Rational numbers", "Irrational numbers", etc.
    """
    topic = models.ForeignKey(
        SubjectTopic, on_delete=models.CASCADE, related_name='subtopics',
        verbose_name="Mada Kuu (Topic)"
    )
    name = models.CharField(max_length=300, verbose_name="Jina la Subtopic / Mada Ndogo")
    order = models.PositiveIntegerField(default=0, verbose_name="Mpangilio")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['topic', 'order']
        unique_together = ['topic', 'name']
        verbose_name = "Subtopic (Syllabus)"
        verbose_name_plural = "Subtopics (Syllabus)"

    def __str__(self):
        return f"{self.topic.name} → {self.name}"


class TLMLogbookEntry(models.Model):
    """
    Official TIE Logbook for TLM teachers (session-based, no Django login needed).
    Data is auto-saved like lessons: each period is stored in `lessons_data` JSON
    exactly like the IMS LogbookEntry, but scoped to a TLMTeacher so teachers
    are NOT redirected to the student dashboard.
    """
    DAY_CHOICES = [
        ('monday', 'Jumatatu'),
        ('tuesday', 'Jumanne'),
        ('wednesday', 'Jumatano'),
        ('thursday', 'Alhamisi'),
        ('friday', 'Ijumaa'),
    ]

    teacher = models.ForeignKey(
        TLMTeacher, on_delete=models.CASCADE, related_name='logbook_entries',
        verbose_name="Mwalimu (TLM)"
    )
    school = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Shule"
    )
    date = models.DateField(default=timezone.now)
    day_of_week = models.CharField(max_length=10, choices=DAY_CHOICES, default='monday')

    # Per-period lesson records stored as JSON list (TIE official format)
    lessons_data = models.JSONField(default=list, blank=True)
    other_activities = models.TextField(blank=True, null=True)
    challenges_faced = models.TextField(blank=True, null=True)
    lessons_learned = models.TextField(blank=True, null=True)
    supervisor_remarks = models.TextField(blank=True, null=True)
    head_teacher_remarks = models.TextField(blank=True, null=True)
    is_location_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        unique_together = ['teacher', 'date']
        verbose_name = "Logbook (TLM)"
        verbose_name_plural = "Logbooks (TLM)"

    def __str__(self):
        return f"{self.teacher.full_name} — {self.date}"


class GeneratedExam(models.Model):
    """
    AI-generated exam paper in NECTA format (Test, Quiz, Midterm, Terminal, Annual...).
    Supports Primary, O-Level and A-Level. Questions stored as JSON:
      [{"section": "A", "instructions": "...", "questions": [
          {"number": 1, "text": "...", "marks": 2, "answer": "...", "topic": "..."}, ...
      ]}, ...]
    """
    EXAM_TYPE_CHOICES = [
        ('TEST', 'Test'),
        ('QUIZ', 'Quiz'),
        ('MIDTERM', 'Midterm'),
        ('TERMINAL', 'Terminal'),
        ('ANNUAL', 'Annual'),
        ('COMPETITION', 'Competition'),
        ('OTHER', 'Nyingine'),
    ]
    EDUCATION_LEVEL_CHOICES = [
        ('primary', 'Primary School'),
        ('ordinary', 'Ordinary Level (O-Level)'),
        ('advanced', 'Advanced Level (A-Level)'),
    ]
    LANGUAGE_CHOICES = [
        ('english', 'English'),
        ('kiswahili', 'Kiswahili'),
    ]

    teacher = models.ForeignKey(
        TLMTeacher, on_delete=models.CASCADE, related_name='generated_exams',
        verbose_name="Mwalimu (TLM)"
    )
    school = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Shule"
    )
    title = models.CharField(max_length=300, verbose_name="Jina la Mtihani")
    education_level = models.CharField(
        max_length=20, choices=EDUCATION_LEVEL_CHOICES, default='ordinary',
        verbose_name="Ngazi ya Elimu"
    )
    class_name = models.CharField(max_length=50, verbose_name="Darasa", help_text="e.g. Form 2, Standard 5")
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Somo"
    )
    subject_name = models.CharField(max_length=200, blank=True, verbose_name="Jina la Somo")
    exam_type = models.CharField(
        max_length=20, choices=EXAM_TYPE_CHOICES, default='TEST', verbose_name="Aina ya Mtihani"
    )
    term = models.CharField(max_length=10, blank=True, default='', verbose_name="Muhula")
    year = models.PositiveIntegerField(default=2026, verbose_name="Mwaka")
    duration_minutes = models.PositiveIntegerField(default=120, verbose_name="Muda (Dakika)")
    total_marks = models.PositiveIntegerField(default=100, verbose_name="Alama Zote")
    instructions = models.TextField(blank=True, verbose_name="Maagizo ya Jumla")
    language = models.CharField(
        max_length=10, choices=LANGUAGE_CHOICES, default='english', verbose_name="Lugha"
    )
    questions = models.JSONField(default=list, blank=True, verbose_name="Maswali")
    topics_covered = models.JSONField(default=list, blank=True, verbose_name="Mada Zilizohusika")
    generated_by_ai = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Mtihani (Generated)"
        verbose_name_plural = "Mitihani (Generated)"

    def __str__(self):
        return f"{self.title} — {self.class_name} ({self.get_exam_type_display()})"

    @property
    def question_count(self):
        count = 0
        for section in self.questions or []:
            count += len(section.get('questions', []) or [])
        return count

    @property
    def sections(self):
        return self.questions or []

    @property
    def duration_display(self):
        """NECTA-style time label, e.g. 150 → '2:30 Hours' / 'Saa 2:30'.
        Under one hour → '45 minutes' / 'Dakika 45'."""
        hours = self.duration_minutes // 60
        mins = self.duration_minutes % 60
        if not hours:
            return f"Dakika {mins}" if self.language == 'kiswahili' else f"{mins} minutes"
        time_str = f"{hours}:{mins:02d}"
        if self.language == 'kiswahili':
            return f"Saa {time_str}"
        return f"{time_str} Hours"

    @property
    def assessment_name(self):
        """NECTA assessment this paper belongs to: SFNA / PSLE / FTNA / CSEE / ACSEE."""
        cls = (self.class_name or '').lower()
        if self.education_level == 'primary':
            if re.search(r'\b(std|standard|darasa(?:\s+la)?)\s*\.?\s*[1-4]\b', cls):
                return 'SFNA'
            return 'PSLE'
        if any(x in cls for x in ('form 5', 'form 6', 'form five', 'form six')):
            return 'ACSEE'
        if any(x in cls for x in ('form 1', 'form 2', 'form one', 'form two')):
            return 'FTNA'
        return 'CSEE'

    @property
    def necta_header_lines(self):
        """Official NECTA paper header lines — depends on level & language.
        Secondary → English header (CSEE/FTNA/ACSEE), Primary → Kiswahili (PSLE/SFNA).
        Lower primary (Std 1-4) → SFNA, Upper primary (Std 5-7) → PSLE."""
        sw = self.language == 'kiswahili'
        assessment = self.assessment_name
        # Official bilingual assessment names used by NECTA
        _ENG = {
            'SFNA': 'STANDARD FOUR NATIONAL ASSESSMENT (SFNA)',
            'PSLE': 'PRIMARY SCHOOL LEAVING EXAMINATION (PSLE)',
            'FTNA': 'FORM TWO NATIONAL ASSESSMENT (FTNA)',
            'CSEE': 'CERTIFICATE OF SECONDARY EDUCATION EXAMINATION (CSEE)',
            'ACSEE': 'ADVANCED CERTIFICATE OF SECONDARY EDUCATION EXAMINATION (ACSEE)',
        }
        _SW = {
            'SFNA': 'TAFITI YA TAIFA YA DARASA LA NNE (SFNA)',
            'PSLE': 'MTIHANI WA KUMALIZA ELIMU YA MSINGI (PSLE)',
            'FTNA': 'TAFITI YA TAIFA YA KIDATO CHA PILI (FTNA)',
            'CSEE': 'CERTIFICATE OF SECONDARY EDUCATION EXAMINATION (CSEE)',
            'ACSEE': 'ADVANCED CERTIFICATE OF SECONDARY EDUCATION EXAMINATION (ACSEE)',
        }
        name = _SW[assessment] if sw else _ENG[assessment]
        if sw:
            return [
                "JAMHURI YA MUUNGANO WA TANZANIA",
                "WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA",
                "BARAZA LA MITIHANI LA TANZANIA",
                name,
            ]
        return [
            "THE UNITED REPUBLIC OF TANZANIA",
            "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY",
            "NATIONAL EXAMINATIONS COUNCIL OF TANZANIA",
            name,
        ]
