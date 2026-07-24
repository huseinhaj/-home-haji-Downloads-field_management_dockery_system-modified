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
