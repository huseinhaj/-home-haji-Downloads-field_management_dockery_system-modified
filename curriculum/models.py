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
