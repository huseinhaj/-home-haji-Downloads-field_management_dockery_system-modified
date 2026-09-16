"""
Models za Sahishi (scan & auto-grade) — zinaishi kwenye app 'results'
ili zifuate database ya 'results' kupitia ResultsRouter.

Mzunguko:
  1. Mwalimu anachapisha karatasi za majibu (PDF zenye QR + bubbles)
  2. Wanafunzi wanajaza bubbles kwa pen
  3. Karatasi zinascaniwa (ADF) au picha zinapakiwa
  4. Mfumo unasoma QR (mwanafunzi) + OMR (majibu) → ExamResult
  5. Karatasi zenye shida zinaenda review queue
"""
from django.db import models

from .models import Exam, FormStudent, Subject


class ScanAnswerKey(models.Model):
    """Answer key ya somo moja ndani ya mtihani mmoja (jibu la kila swali)."""
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='scan_answer_keys')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    # {"1": "A", "2": "C", ...} — maswali ya kuchagua (A-D)
    key = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('exam', 'subject')
        verbose_name = 'Scan answer key'
        verbose_name_plural = 'Scan answer keys'

    def __str__(self):
        return f"{self.exam} — {self.subject} ({len(self.key)} maswali)"


class ScanSheetBatch(models.Model):
    """Stack moja ya kurasa zilizoscan (mf. kurasa 40 za ADF)."""
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='scan_batches')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True)
    scanned_at = models.DateTimeField(auto_now_add=True)
    image_count = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-scanned_at']
        verbose_name = 'Scan batch'
        verbose_name_plural = 'Scan batches'

    def __str__(self):
        return f"Batch #{self.pk} — {self.exam} ({self.image_count} kurasa)"


class ScanSheet(models.Model):
    """Karatasi moja ya majibu iliyoscaniwa."""

    class Status(models.TextChoices):
        SCANNED = 'SCANNED', 'Imescan (inasubiri)'
        GRADED = 'GRADED', 'Imesahihishwa'
        NEEDS_REVIEW = 'NEEDS_REVIEW', 'Inahitaji ukaguzi'
        IMPORTED = 'IMPORTED', 'Imeingizwa kwenye matokeo'

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='scan_sheets')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True)
    batch = models.ForeignKey(
        ScanSheetBatch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sheets',
    )
    student = models.ForeignKey(
        FormStudent, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scan_sheets',
    )
    page_number = models.PositiveIntegerField(default=1)
    image = models.ImageField(upload_to='scan_sheets/%Y/%m/%d/')
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCANNED, db_index=True,
    )
    # {"answers": {"1": "A", ...}, "qr": {...}, ...}
    result = models.JSONField(default=dict, blank=True)
    score = models.PositiveIntegerField(null=True, blank=True)
    total = models.PositiveIntegerField(null=True, blank=True)
    needs_review_reason = models.CharField(max_length=200, blank=True)
    # Ilimewekwa kwenye ExamResult na mwalimu (au automatiki)?
    imported_to_results = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['exam', 'student__first_name', 'page_number']
        verbose_name = 'Scan sheet'
        verbose_name_plural = 'Scan sheets'

    def __str__(self):
        student = self.student.full_name if self.student else 'Haijulikani'
        return f"{self.exam} — {student} — uk. {self.page_number}"


class MarkingScheme(models.Model):
    """Marking scheme ya somo moja ndani ya mtihani mmoja.

    Mwalimu anascan/upload scheme (karatasi zenye bubbles za majibu —
    na kwa masomo ya calculation: sehemu ya 'nenda kwa mfano' ya
    kila swali kwenye picha).

    AINA:
      CHOICE — scheme inasomwa kwa OMR → inakuwa ScanAnswerKey moja kwa moja
               (masomo ya kuchagua: History, Civics, Geography, Biology...)
      CALC   — scheme inasomwa bubbles kwa sehemu ya 'jibu fupi' + picha
               zinabaki kama MAREJEO kwa mwalimu (masomo ya calculation:
               Math, Physics, Chemistry...)
    """

    class Kind(models.TextChoices):
        CHOICE = 'CHOICE', 'Ya kuchagua (A–D) — auto-grade kamili'
        CALC = 'CALC', 'Ya calculation — scheme ni marejeleo kwa mwalimu'

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='marking_schemes')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='marking_schemes')
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CHOICE)

    # Jibu la kila swali kama lilivyosomwa kutoka scheme ("1": "A" ... au
    # "1": "42" kwa jibu fupi la calculation lililowekwa kwenye bubble-grid ya scheme)
    parsed_key = models.JSONField(default=dict, blank=True)
    # Maswali yaliyosomwa vizuri (kwa CALC: yale yenye jibu fupi tu)
    parsed_count = models.PositiveIntegerField(default=0)

    # Picha za kurasa za scheme (marejeleo kwa mwalimu / review)
    # pages zinapangwa kwa scheme_pages related_name

    uploaded_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('exam', 'subject')
        ordering = ['-created_at']

    def __str__(self):
        return f"Scheme: {self.exam} — {self.subject} ({self.parsed_count} maswali)"

    @property
    def is_choice(self):
        return self.kind == self.Kind.CHOICE


class MarkingSchemePage(models.Model):
    """Ukurasa mmoja wa scheme (picha) — kwa marejeleo na review."""
    scheme = models.ForeignKey(MarkingScheme, on_delete=models.CASCADE, related_name='pages')
    image = models.ImageField(upload_to='marking_schemes/%Y/%m/%d/')
    page_number = models.PositiveIntegerField(default=1)
    # Majibu yaliyosomwa kwenye ukurasa huu (kwa CALC: jibu fupi per swali)
    parsed = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['scheme', 'page_number']

    def __str__(self):
        return f"Scheme {self.scheme_id} — uk. {self.page_number}"

