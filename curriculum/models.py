"""
TLM Teacher model — lightweight registration for the Teaching & Learning Materials system.
No login/password needed. Teacher registers once via phone number + location, then
we remember them via session/cookie on subsequent visits.
"""
from django.db import models
from field_app.models import Region, District, School, Subject


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
    
    theme = models.CharField(
        max_length=20,
        choices=[
            ('classic', 'TIE Classic — Navy & Gold'),
            ('tanzania', 'Tanzania — Green & Yellow'),
            ('ocean', 'Ocean Blue — Blue & Teal'),
            ('royal', 'Royal Purple — Purple & Pink'),
            ('executive', 'Executive — Charcoal & Silver'),
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
