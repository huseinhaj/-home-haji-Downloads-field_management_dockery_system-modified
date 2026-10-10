from django.conf import settings
from django.db import models
from django.utils import timezone

from .crypto import decrypt_password, encrypt_password

MODE_CHOICES = [
    ('annual', 'Mwaka mzima (100% mwisho wa mwaka)'),
    ('periods', 'Vipindi kwa wiki (vipindi_kwa_wiki x wiki)'),
    ('manual', 'Actual / Target'),
]

RUN_STATUS_CHOICES = [
    ('running', 'Inajaza...'),
    ('done', 'Imekamilika'),
    ('error', 'Hitilafu'),
]


class TeacherProfile(models.Model):
    """Wasifu wa mwalimu kwenye app (kwa ajili ya e-Tendaji + ESS auto-fill)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ess_profile')
    full_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    school = models.ForeignKey(
        'field_app.School', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ess_profiles')
    ess_username = models.CharField(
        max_length=255, blank=True,
        help_text='Jina au barua pepe unayotumia kuingia ESS (e-Tendaji)')
    ess_password = models.CharField(max_length=512, blank=True)
    ess_ready = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.full_name or self.user.email

    @property
    def ess_password_plain(self) -> str:
        return decrypt_password(self.ess_password)

    def set_ess_password(self, raw: str) -> None:
        self.ess_password = encrypt_password(raw)

    def save(self, *args, **kwargs):
        self.ess_ready = bool(self.ess_username and self.ess_password)
        super().save(*args, **kwargs)


class Task(models.Model):
    """TASK moja ya mwaka (mf. 'kutekeleza majukumu ya ufundishaji ...')."""

    profile = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='tasks')
    name = models.CharField(max_length=400)
    somo = models.CharField(max_length=100)
    kidato = models.CharField(max_length=100, blank=True)
    start = models.DateField()
    end = models.DateField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start', '-created_at']

    def __str__(self):
        return f'{self.name} ({self.start} - {self.end})'


class SubTask(models.Model):
    """Sub task moja kati ya 1..7 (au custom) chini ya Task."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='subtasks')
    position = models.PositiveSmallIntegerField()
    description = models.CharField(max_length=400)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='manual')
    target = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vila_per_week = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    week_count = models.PositiveSmallIntegerField(default=0)
    actual_base = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position']
        unique_together = [('task', 'position')]

    def __str__(self):
        return f'{self.position}. {self.description[:60]}'


class WeekEntry(models.Model):
    """Kumbukumbu ya mwalimu kwa siku moja kwa sub task moja (kiingio kimoja = submission).

    Mwalimu anaweza kuweka viingilio vingi kwa wiki (mara 2-3+ kwa siku
    tofauti); kila siku kimoja kwa sub task. Jumla ya viingilio ndiyo
    'actual' kwenye hesabu ya asilimia.
    """

    subtask = models.ForeignKey(SubTask, on_delete=models.CASCADE, related_name='entries')
    profile = models.ForeignKey(
        TeacherProfile, on_delete=models.CASCADE, related_name='week_entries')
    week_no = models.PositiveSmallIntegerField(default=1)
    date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    note = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'week_no']
        unique_together = [('subtask', 'date')]

    def __str__(self):
        return f'{self.date}: {self.amount} ({self.subtask_id})'


class EssFillRun(models.Model):
    """Rekodi ya jaribio la kujaza ESS (mtiririko wa Celery)."""

    profile = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='fill_runs')
    started = models.DateTimeField(auto_now_add=True)
    finished = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=RUN_STATUS_CHOICES, default='running')
    saved = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    not_found = models.IntegerField(default=0)
    required = models.IntegerField(default=0)
    log = models.TextField(blank=True)
    task_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ['-started']

    def __str__(self):
        return f'{self.profile} #{self.id} {self.status}'