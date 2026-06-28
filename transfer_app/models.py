from django.db import models

CREDIT_PACKAGES = {
    'single':     {'credits': 1,    'price': 1000, 'label': 'Namba 1 — TZS 1,000'},
    'pack5':      {'credits': 5,    'price': 3500, 'label': 'Namba 5 — TZS 3,500'},
    'unlimited3': {'credits': 999,  'price': 8000, 'label': 'Unlimited (Miezi 3) — TZS 8,000'},
}


class TeacherTransfer(models.Model):
    LEVEL_CHOICES = [
        ('primary', 'Shule ya Msingi'),
        ('secondary', 'Shule ya Sekondari'),
    ]
    LOCATION_CHOICES = [
        ('village', 'Kijijini'),
        ('middle', 'Mji Mdogo'),
        ('urban', 'Mjini'),
    ]

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    current_school = models.CharField(max_length=300)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    subjects = models.CharField(max_length=500, blank=True)
    region_name = models.CharField(max_length=100)
    district_name = models.CharField(max_length=100)
    location_type = models.CharField(max_length=20, choices=LOCATION_CHOICES)
    willing_to_go = models.CharField(max_length=20, choices=LOCATION_CHOICES, blank=True)
    session_key = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = 'transfer_app'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} — {self.current_school} ({self.district_name})"


class CreditBalance(models.Model):
    session_key = models.CharField(max_length=64, unique=True)
    credits = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'transfer_app'
        verbose_name = 'Credit Balance'
        verbose_name_plural = 'Credit Balances'

    def __str__(self):
        return f"{self.session_key[:12]}... — credits: {self.credits}"


class UnlockedContact(models.Model):
    session_key = models.CharField(max_length=64, db_index=True)
    unlocked_teacher_id = models.IntegerField()
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'transfer_app'
        unique_together = [['session_key', 'unlocked_teacher_id']]
        verbose_name = 'Unlocked Contact'

    def __str__(self):
        return f"{self.session_key[:12]}... → teacher#{self.unlocked_teacher_id}"


class PaymentRequest(models.Model):
    STATUS_CHOICES = [
        ('pending',  'Inasubiri'),
        ('approved', 'Imeidhinishwa'),
        ('rejected', 'Imekataliwa'),
    ]
    PACKAGE_CHOICES = [(k, v['label']) for k, v in CREDIT_PACKAGES.items()]

    session_key   = models.CharField(max_length=64)
    teacher_name  = models.CharField(max_length=200, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    package       = models.CharField(max_length=20, choices=PACKAGE_CHOICES)
    mpesa_ref     = models.CharField(max_length=100, verbose_name='Kumb. ya Malipo (Mpesa/Tigo/Airtel)')
    amount        = models.PositiveIntegerField()
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    credits_awarded = models.PositiveIntegerField(default=0)
    created_at    = models.DateTimeField(auto_now_add=True)
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    notes         = models.TextField(blank=True)

    class Meta:
        app_label = 'transfer_app'
        ordering = ['-created_at']
        verbose_name = 'Ombi la Malipo'
        verbose_name_plural = 'Maombi ya Malipo'

    def __str__(self):
        return f"{self.teacher_name} — {self.get_package_display()} [{self.get_status_display()}]"
