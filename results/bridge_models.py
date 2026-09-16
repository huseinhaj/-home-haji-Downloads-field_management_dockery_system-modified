"""
Models za Sahishi Bridge — programu ndogo inayokaa PC ya shule (Ubuntu)
inuunganisha scanner ya ADF moja kwa moja na site.

Mtiririko:
  1. Mwalimu anabonyeza "🖨️ Scan kwa Bridge" kwenye site → ScanJob (PENDING)
  2. Bridge (PC ya shule) inauliza kazi mpya kila sekunde chache (poll)
  3. Bridge inascan ADF (scanimage) na kutuma picha kwenye site
  4. Site inasahihisha (QR + OMR) — mwalimu anaona progress live
"""
import secrets

from django.db import models

from .models import Exam, School, Subject
from .scan_models import ScanSheetBatch


def generate_bridge_token():
    return 'sb_' + secrets.token_urlsafe(32)


class SahishiBridge(models.Model):
    """Registration ya bridge moja (PC ya shule yenye scanner)."""
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name='sahishi_bridges',
    )
    name = models.CharField(max_length=100, help_text='Mf: Ofisi ya walimu')
    token = models.CharField(
        max_length=80, unique=True, db_index=True,
        default=generate_bridge_token,
        help_text='Inajitengeneza yenyewe. Badilisha kwa rotate_token().',
    )
    # Scanner iliyochaguliwa kwenye PC hiyo (scanimage device name)
    scanner_name = models.CharField(max_length=255, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Sahishi Bridge'
        verbose_name_plural = 'Sahishi Bridges'

    def __str__(self):
        return f'{self.name} @ {self.school.name}'

    def rotate_token(self):
        self.token = generate_bridge_token()
        self.save(update_fields=['token'])
        return self.token

    def save(self, *args, **kwargs):
        # Hakikisha token haipo tupu hata kama default haikutumika
        if not self.token:
            self.token = generate_bridge_token()
        super().save(*args, **kwargs)


class ScanJob(models.Model):
    """Kazi moja ya scanning iliyotolewa na mwalimu kwenye site."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Inasubiri bridge'
        CLAIMED = 'CLAIMED', 'Bridge inascan'
        UPLOADING = 'UPLOADING', 'Inatuma picha'
        DONE = 'DONE', 'Imekamilika'
        FAILED = 'FAILED', 'Imeshindikana'
        CANCELLED = 'CANCELLED', 'Imefutwa'

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name='sahishi_jobs', null=True, blank=True,
    )
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='sahishi_jobs')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='sahishi_jobs')
    batch = models.ForeignKey(
        ScanSheetBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='job',
    )
    bridge = models.ForeignKey(
        SahishiBridge, on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs',
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    pages = models.PositiveIntegerField(default=40, help_text='Idadi ya kurasa za ADF')
    duplex = models.BooleanField(default=False)
    # Mwalimu anataka nakala zenye alama nyekundu zichapishwe moja kwa moja
    print_marked = models.BooleanField(
        default=False,
        help_text='Bridge ichapishe nakala zenye alama nyekundu baada ya grading',
    )
    # Ripoti ya uchapishaji (mf. "Imechapisha kurasa 38/40")
    print_report = models.CharField(max_length=255, blank=True)
    dpi = models.PositiveIntegerField(default=300)
    note = models.CharField(max_length=200, blank=True)
    # Matokeo: "Karatasi 38: 35 graded, 3 review"
    result_message = models.CharField(max_length=255, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Sahishi scan job'
        verbose_name_plural = 'Sahishi scan jobs'

    def __str__(self):
        return f'Job #{self.pk} {self.exam} — {self.subject} [{self.status}]'
