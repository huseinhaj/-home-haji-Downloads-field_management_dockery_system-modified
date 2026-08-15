from django.db import models
from django.conf import settings


class Student(models.Model):
    """Mwanafunzi wa ualimu (Student Teacher) aliyejiandikisha katika chuo."""

    GENDER_CHOICES = [
        ('M', 'Mume (Male)'),
        ('F', 'Mke (Female)'),
    ]

    ENROLLMENT_CHOICES = [
        ('active', 'Anasoma (Active)'),
        ('graduated', 'Alihitimu (Graduated)'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_profile',
        verbose_name='Mtumiaji',
    )
    college = models.ForeignKey(
        'colleges.College', on_delete=models.CASCADE, related_name='students',
        verbose_name='Chuo',
    )
    program = models.ForeignKey(
        'colleges.Program', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='students', verbose_name='Programu',
    )
    full_name = models.CharField(max_length=255, verbose_name='Jina Kamili')
    registration_number = models.CharField(
        max_length=50, unique=True, verbose_name='Namba ya Usajili',
        help_text='mfano: KAS/2026/014',
    )
    admission_year = models.IntegerField(
        default=2026, verbose_name='Mwaka wa Kujiunga',
    )
    year_of_study = models.IntegerField(
        default=1, verbose_name='Mwaka wa Masomo',
        help_text='1 = Mwaka wa kwanza, 2 = Mwaka wa pili (Diploma = miaka 2)',
    )
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, verbose_name='Jinsia')
    phone_number = models.CharField(max_length=15, blank=True, verbose_name='Namba ya Simu')
    email = models.EmailField(blank=True, verbose_name='Barua Pepe')
    enrollment_status = models.CharField(
        max_length=20, choices=ENROLLMENT_CHOICES, default='active',
        verbose_name='Hali ya Masomo',
        help_text='active = anasoma, graduated = alihitimu (bado anaweza kuwa na deni)',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = 'Mwanafunzi'
        verbose_name_plural = 'Wanafunzi'

    def __str__(self):
        return f"{self.full_name} ({self.registration_number})"

    def save(self, *args, **kwargs):
        # Keep the linked user in sync
        if self.user_id:
            self.user.first_name = self.full_name.split(' ')[0] if self.full_name else ''
            self.user.last_name = ' '.join(self.full_name.split(' ')[1:]) if self.full_name else ''
            self.user.email = self.email or self.user.email
            self.user.phone_number = self.phone_number
            self.user.save()
        super().save(*args, **kwargs)

    # ── Financial summary helpers (SR2-style) ──
    @property
    def bills(self):
        return self.bills.all()

    @property
    def total_billed(self):
        return sum(b.amount for b in self.bills.all())

    @property
    def total_paid(self):
        return sum(p.amount for p in self.payments.filter(status='confirmed'))

    @property
    def balance_due(self):
        return max(0, self.total_billed - self.total_paid)

    @property
    def has_balance(self):
        return self.balance_due > 0

    @property
    def is_first_year(self):
        return self.enrollment_status == 'active' and self.year_of_study == 1

    @property
    def is_continuing(self):
        return self.enrollment_status == 'active' and self.year_of_study > 1
