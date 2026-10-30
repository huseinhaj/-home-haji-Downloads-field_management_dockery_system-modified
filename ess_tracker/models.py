from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone

from .crypto import decrypt_password, encrypt_password

MODE_CHOICES = [
    ('annual', 'Mwaka mzima (100% mwisho wa mwaka)'),
    ('periods', 'Vipindi kwa wiki (vipindi_kwa_wiki x wiki)'),
    ('manual', 'Actual / Target'),
    ('events', 'Ratiba ya matukio (tarehe za kila jaribio/mtihani)'),
    ('count', 'Idadi (mwalimu ajaze nukuu X kati ya Y)'),
]

RUN_STATUS_CHOICES = [
    ('running', 'Inajaza...'),
    ('done', 'Imekamilika'),
    ('error', 'Hitilafu'),
]

RUN_KIND_CHOICES = [
    ('fill', 'Kujaza ESS'),
    ('sync', 'Sawazisha majina na ESS'),
    ('push', 'Tuma majina kwenye ESS'),
    ('read', 'Soma asilimia ESS'),
    ('approve', 'Kuidhinisha (verify) maendeleo ESS'),
]

RUN_SOURCE_CHOICES = [
    ('manual', 'Mwenyewe'),
    ('auto', 'Kiotomatiki'),
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
    school_open = models.DateField(
        null=True, blank=True,
        help_text='Tarehe shule inavyofunguliwa mwaka huu (mf. 2026-01-12)')
    school_close = models.DateField(
        null=True, blank=True,
        help_text='Tarehe shule inavyofungwa mwaka huu (mf. 2026-12-04)')
    entries_per_week = models.PositiveSmallIntegerField(
        default=3,
        help_text='Mara ngapi kwa wiki mfumo ujaze maendeleo yako (1–5)')
    auto_subtasks = models.TextField(
        blank=True,
        help_text='ID za sub-task za kujaza kiotomatiki (zikitenganishwa kwa '
                  'koma). Tupu = sub-task zote zinazohitaji.')
    auto_fill_enabled = models.BooleanField(
        default=True,
        help_text='Washa/kuzima kujaza kiotomatiki. Kikizimwa, mfumo haujazi '
                  'yenyewe; unaweza kujaza mwenyewe kwa kitufe cha "Jaza".')
    approver_enabled = models.BooleanField(
        default=False,
        help_text='Mkuu/kiongozi: washa ili mfumo uidhinishe (verify) maendeleo '
                  'SUBMITTED ya walimu walio chini yake kwenye e-Utendaji.')
    auto_approve_weeks = models.PositiveSmallIntegerField(
        default=0,
        choices=[(0, 'Kila siku (hazui mwisho)'), (1, 'Kwa wiki 1'),
                 (2, 'Kwa wiki mbili'), (4, 'Kwa mwezi 1'),
                 (9, 'Kwa miezi 2'), (13, 'Kwa miezi 3')],
        help_text='Mkuu/kiongozi: muda (kwa wiki) ambao mfumo wa moja kwa moja '
                  'unaweza kuendelea kwaweka kila siku (kujaza na kuidhinisha). '
                  'Mwisho wa muda: mfumo husimama hadi uweke upya.')
    ess_native = models.BooleanField(
        default=True,
        help_text='Njia ya ESS-native: mfumo hujipanga mwenyewe kutoka ESS '
                  '(mode, target, dirisha) bila mwalimu achosea chochote. '
                  'Wasimamizi wa kwanza walioipanga app zenyewe: washa vizuri.')
    auto_lease_until = models.DateTimeField(
        null=True, blank=True,
        help_text='Mwisho wa kipindi cha mchakato wa moja kwa moja (lease). '
                  'Mfungulwe kuweka muda (wiki) upya.')
    auto_lease_set_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Wakati ambapo kipindi kiliposhwa kwa mara ya mwisho.')
    holidays = models.ManyToManyField(
        'Holiday', blank=True, related_name='profiles',
        help_text='Likizo zilizochaguliwa — zinatolewa kwenye hesabu ya siku za shule (194)')
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

    def auto_subtask_ids(self) -> list[int]:
        """ID za sub-task zilizochaguliwa kujazwa kiotomatiki (tupu = zote)."""
        out = []
        for part in (self.auto_subtasks or '').split(','):
            part = part.strip()
            if part.isdigit():
                out.append(int(part))
        return out

    def save(self, *args, **kwargs):
        self.ess_ready = bool(self.ess_username and self.ess_password)
        # Wasifu mpya wa kiongozi: anza kipindi (lease) ili mfumo awache
        # kwa wiki ulizochagua.
        if (self._state.adding and self.approver_enabled
                and (self.auto_approve_weeks or 0) > 0
                and not self.auto_lease_until):
            from datetime import timedelta
            from django.utils import timezone
            now = timezone.now()
            self.auto_lease_set_at = now
            self.auto_lease_until = now + timedelta(weeks=self.auto_approve_weeks)
        super().save(*args, **kwargs)


class Holiday(models.Model):
    """Likizo (ya kitaifa au ya shule) inayotolewa kwenye hesabu ya siku za shule.

    profile tupu = likizo ya kitaifa (inapatikana kwa walimu wote); profile
    ikiwekwa = likizo ya shule/mwalimu huyo pekee.
    """

    name = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField()
    is_public = models.BooleanField(default=False, help_text='Likizo ya kitaifa')
    profile = models.ForeignKey(
        TeacherProfile, null=True, blank=True, on_delete=models.CASCADE,
        related_name='custom_holidays')

    class Meta:
        ordering = ['start_date', 'name']

    def __str__(self):
        return f'{self.name} ({self.start_date} - {self.end_date})'

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


class Task(models.Model):
    """TASK moja ya mwaka (mf. 'kutekeleza majukumu ya ufundishaji ...')."""

    profile = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='tasks')
    name = models.CharField(max_length=400)
    somo = models.CharField(max_length=100)
    kidato = models.CharField(max_length=100, blank=True)
    topics_total = models.PositiveSmallIntegerField(
        default=0, help_text='Jumla ya mada za somo kwa mwaka (hesabu ya nukuu)')
    topics_taught = models.PositiveSmallIntegerField(
        default=0, help_text='Jumla ya mada zilizofundishwa hadi sasa')
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
    official_pct = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Asilimia halisi kama inavyoonekana ESS official')
    official_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Muda asilimia ya ESS official iliposomwa mara ya mwisho')
    start = models.DateField(
        null=True, blank=True,
        help_text='Tarehe sub-task inaanza kwenye ESS (startDate)')
    end = models.DateField(
        null=True, blank=True,
        help_text='Tarehe sub-task inaisha kwenye ESS (endDate)')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position']
        unique_together = [('task', 'position')]

    def __str__(self):
        return f'{self.position}. {self.description[:60]}'


ANCHOR_CHOICES = [
    ('date', 'Tarehe maalum (mf. 2026-03-15)'),
    ('month', 'Mwezi (mf. Jaribio 1: Machi)'),
    ('term_week', 'Muhula + wiki (mf. Muhula 1, wiki ya 6)'),
]


class SubTaskEvent(models.Model):
    """Tukio moja la sub-task ya 'events' (jaribio/mtihani/tathmini).

    Mwalimu huweka ratiba ya kila tukio kwa njia moja kati ya tatu:
      - tarehe maalum (mf. 2026-03-15),
      - mwezi (mf. "Jaribio 1: Machi") — ukibaki bila tarehe halisi,
        inahesabika mwishoni mwa mwezi,
      - muhula + wiki ndani yake (mf. "Muhula 1, wiki ya 6") —
        mfumo huresibu tarehe kutoka kufungua/kufunga kwa shule.

    `due_date` daima ni tarehe ILIYOHESABIWA (resolved) kutoka anchor;
    cap, "inasubiri" na kujaza kiotomatiki vinatumia `due_date`.
    """

    subtask = models.ForeignKey(
        SubTask, on_delete=models.CASCADE, related_name='events')
    index = models.PositiveSmallIntegerField(
        help_text='Namba ya tukio (1, 2, 3...) kwa mujibu wa ratiba')
    anchor = models.CharField(
        max_length=10, choices=ANCHOR_CHOICES, default='date',
        help_text='Mwalimu achague: tarehe maalum, mwezi, au muhula + wiki.')
    month = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Mwezi (1-12) kama anchor=month (mf. 3 = Machi).')
    day = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Tarehe ndani ya mwezi (1-31, hiari). Bila hii — mwisho wa mwezi.')
    term = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=[(1, 'Muhula 1'), (2, 'Muhula 2')],
        help_text='Muhula kama anchor=term_week.')
    term_week = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Wiki ndani ya muhula (1, 2, 3...) kama anchor=term_week.')
    due_date = models.DateField(
        help_text='Tarehe iliyohesabiwa kutoka anchor (mfumo hutumia hii).')
    label = models.CharField(
        max_length=200, blank=True,
        help_text='Maelezo mafupi (mf. "Jaribio la 1 — Mtihani wa Muhula 1")')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date', 'index']
        unique_together = [('subtask', 'index')]
        verbose_name = 'Tukio la ratiba'
        verbose_name_plural = 'Matukio ya ratiba'

    def __str__(self):
        return f'{self.label or f"Tukio {self.index}"} ({self.due_date})'


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
    kind = models.CharField(max_length=10, choices=RUN_KIND_CHOICES, default='fill')
    source = models.CharField(max_length=10, choices=RUN_SOURCE_CHOICES, default='manual')
    saved = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    not_found = models.IntegerField(default=0)
    required = models.IntegerField(default=0)
    log = models.TextField(blank=True)
    error_step = models.CharField(
        max_length=64, blank=True,
        help_text='Hatua iliyoshindwa kwenye mtiririko wa ESS (mf. login, '
                  'subtasks_table, row_actions) — kutoka diagnostics.')
    artifacts = models.JSONField(
        null=True, blank=True,
        help_text='Njia za screenshot/HTML zilizohifadhiwa wakati wa hitilafu '
                  '(media/ess_artifacts/).')
    task_id = models.CharField(max_length=64, blank=True)
    only_subtasks = models.CharField(
        max_length=255, blank=True,
        help_text='ID za SubTask zilizochaguliwa kujazwa (mf. "12,15"). Tupu = zote.')

    class Meta:
        ordering = ['-started']

    def __str__(self):
        return f'{self.profile} #{self.id} {self.status}'


class PushSubscription(models.Model):
    """Arifa za kifaa (Web Push) za mwalimu mmoja.

    Kifaa kimoja (browser/phone) = subscription moja. Mwalimu anaweza kuwa
    na vifaa kadhaa. Tunatuma arifa siku za kujaza na baada ya kujaza.
    """

    profile = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE,
                                related_name='push_subscriptions')
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=300, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.profile} {self.endpoint[:40]}…'


MONTH_CHOICES = [
    (1, 'Januari'), (2, 'Februari'), (3, 'Machi'), (4, 'Aprili'),
    (5, 'Mei'), (6, 'Juni'), (7, 'Julai'), (8, 'Agosti'),
    (9, 'Septemba'), (10, 'Oktoba'), (11, 'Novemba'), (12, 'Desemba'),
]


def _clear_calendar_cache():
    try:
        from django.core.cache import cache
        cache.delete('ess:active_calendar')
    except Exception:
        pass


class AcademicCalendar(models.Model):
    """Kalenda ya mwaka wa shule inayodhibitiwa na admin.

    Ina tarehe za kufungua/kufunga na asilimia lengwa kwa kila mwezi.
    Kalenda MOJA tu huwa active; ikiwa active, mfumo (ESS asilimia, dirisha
    la mwaka, na alerts) hutumia hii kwa walimu WOTE. Hivyo admin akibadilisha
    kalenda, walimu wote wanapata mabadiliko kiotomatiki.
    """

    year = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(
        default=False, help_text='Kalenda inayotumika sasa kwa walimu wote.')
    school_open = models.DateField(null=True, blank=True)
    school_close = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-year']
        verbose_name = 'Kalenda ya mwaka'
        verbose_name_plural = 'Kalenda za miaka'

    def __str__(self):
        return f'Kalenda {self.year}' + (' (active)' if self.is_active else '')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            AcademicCalendar.objects.exclude(pk=self.pk).update(is_active=False)
        _clear_calendar_cache()

    def target_pct_for(self, d=None):
        """Asilimia lengwa (cumulative) kwa tarehe d, au None.

        Huchukua lengo la WIKI la karibu lililopita kama lipo (ratiba ya muhula,
        mf. PEPMIS); vinginevyo lengo la mwezi. Rudi None kama hakuna.
        """
        d = d or date.today()
        row = (self.weekly_targets.filter(week_start__lte=d)
               .order_by('-week_start').first())
        if row:
            return float(row.expected_pct)
        row = (self.monthly_targets.filter(month__lte=d.month)
               .order_by('-month').first())
        return float(row.expected_pct) if row else None


class MonthlyTarget(models.Model):
    """Asilimia lengwa (cumulative) ya mwezi mmoja kwenye kalenda."""

    calendar = models.ForeignKey(AcademicCalendar, on_delete=models.CASCADE,
                                 related_name='monthly_targets')
    month = models.PositiveSmallIntegerField(choices=MONTH_CHOICES)
    expected_pct = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        ordering = ['month']
        unique_together = [('calendar', 'month')]
        verbose_name = 'Lengo la mwezi'
        verbose_name_plural = 'Malengo ya miezi'

    def __str__(self):
        return f'{self.get_month_display()}: {self.expected_pct}%'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        _clear_calendar_cache()


class WeeklyTarget(models.Model):
    """Asilimia lengwa (cumulative) ya wiki moja kwenye kalenda.

    Hutumika kwa ratiba za muhula (mf. PEPMIS) zinazotoa asilimia kwa kila
    wiki. Kalenda ikiwa na malengo ya wiki, huyo huchukuliwa kwanza kabla ya
    lengo la mwezi.
    """

    calendar = models.ForeignKey(AcademicCalendar, on_delete=models.CASCADE,
                                 related_name='weekly_targets')
    week_start = models.DateField(
        help_text='Tarehe ya kuanza kwa wiki (mf. Jumatatu 2026-07-06)')
    expected_pct = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        ordering = ['week_start']
        unique_together = [('calendar', 'week_start')]
        verbose_name = 'Lengo la wiki'
        verbose_name_plural = 'Malengo ya wiki'

    def __str__(self):
        return f'{self.week_start}: {self.expected_pct}%'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        _clear_calendar_cache()