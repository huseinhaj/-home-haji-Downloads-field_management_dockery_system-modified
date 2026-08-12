from django.db import models


class FeeItem(models.Model):
    """Kipengee cha ada au mchango kinachotozwa na chuo (mf. Ada, Mchango wa Chuo)."""

    CATEGORY_CHOICES = [
        ('ada', 'Ada (Tuition)'),
        ('mchango', 'Mchango wa Chuo'),
        ('other', 'Nyingine'),
    ]

    college = models.ForeignKey(
        'colleges.College', on_delete=models.CASCADE, related_name='fee_items',
        verbose_name='Chuo',
    )
    name = models.CharField(max_length=200, verbose_name='Jina la Ada/Mchango')
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default='ada', verbose_name='Aina',
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name='Kiasi (TZS)',
    )
    academic_year = models.CharField(
        max_length=20, blank=True, verbose_name='Mwaka wa Masomo',
        help_text='Wacha tupu kwa ada za kila mwaka.',
    )
    year_of_study = models.IntegerField(
        null=True, blank=True, verbose_name='Mwaka wa Masomo unaohusika',
        help_text='1 au 2; wacha tupu ikiwa inahusu miaka yote.',
    )
    description = models.TextField(blank=True, verbose_name='Maelezo')
    due_date = models.DateField(null=True, blank=True, verbose_name='Tarehe ya Malipo')
    is_active = models.BooleanField(default=True, verbose_name='Inatumika')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'Ada / Mchango'
        verbose_name_plural = 'Ada na Michango'

    def __str__(self):
        return f"{self.name} — {self.college.short_name} (TZS {self.amount:,.0f})"


class FeeBill(models.Model):
    """Bili ya mwanafunzi kwa kipengee kimoja cha ada, pamoja na namba ya malipo.

    SR2 flow: bili inajitokeza moja kwa moja; namba ya malipo (control number)
    inazalishwa mwanafunzi anapobofya 'Generate'.
    """

    STATUS_CHOICES = [
        ('unpaid', 'Haijalipwa'),
        ('partially_paid', 'Imelipwa Sehemu'),
        ('paid', 'Imelipwa'),
    ]

    student = models.ForeignKey(
        'students.Student', on_delete=models.CASCADE, related_name='bills',
        verbose_name='Mwanafunzi',
    )
    fee_item = models.ForeignKey(
        FeeItem, on_delete=models.CASCADE, related_name='bills',
        verbose_name='Ada / Mchango',
    )
    academic_year = models.CharField(max_length=20, verbose_name='Mwaka wa Masomo')
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Kiasi (TZS)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid')

    control_number = models.CharField(
        max_length=30, unique=True, null=True, blank=True,
        verbose_name='Namba ya Malipo (Control Number)',
    )
    control_number_generated_at = models.DateTimeField(null=True, blank=True)
    control_number_expires = models.DateTimeField(null=True, blank=True)

    # GePG: BillId iliyowasilishwa kwenye GePG (inahitajika kwa bill
    # update/cancel/reuse na ku-correlate malipo) — inatolewa na GePG halisi.
    gepg_bill_id = models.CharField(
        max_length=64, blank=True, db_index=True, verbose_name='GePG Bill ID',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['fee_item__category', 'created_at']
        unique_together = ('student', 'fee_item', 'academic_year')
        verbose_name = 'Bili'
        verbose_name_plural = 'Bili'

    def __str__(self):
        return f"{self.student.full_name} — {self.fee_item.name} ({self.status})"

    @property
    def paid_amount(self):
        return sum(
            p.amount for p in self.payments.filter(status='confirmed')
        )

    @property
    def remaining_amount(self):
        return max(0, self.amount - self.paid_amount)

    @property
    def is_fully_paid(self):
        return self.status == 'paid'


class Payment(models.Model):
    """Malipo yaliyofanywa dhidi ya bili — yanathibitishwa na msimamizi wa chuo."""

    METHOD_CHOICES = [
        ('bank', 'Benki (NMB / CRDB / NBC)'),
        ('mobile', 'Simu ya Mkonomi (M-Pesa / Tigo Pesa / Airtel Money)'),
        ('cash', 'Fedha Taslimu (Cash)'),
        ('other', 'Nyingine'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Inasubiri Kuthibitishwa'),
        ('confirmed', 'Imethibitishwa'),
        ('rejected', 'Imekataliwa'),
    ]

    bill = models.ForeignKey(
        FeeBill, on_delete=models.CASCADE, related_name='payments',
        verbose_name='Bili',
    )
    student = models.ForeignKey(
        'students.Student', on_delete=models.CASCADE, related_name='payments',
        verbose_name='Mwanafunzi',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Kiasi (TZS)')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='mobile')
    reference = models.CharField(
        max_length=100, blank=True, verbose_name='Namba ya Kumbukumbu',
        help_text='mfano: kumbukumbu ya M-Pesa/Tigo, au namba ya benki',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.CharField(max_length=255, blank=True, verbose_name='Maelezo')
    confirmed_by = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='confirmed_payments', verbose_name='Aliyethibitisha',
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Malipo'
        verbose_name_plural = 'Malipo'

    def __str__(self):
        return f"{self.student.full_name} — TZS {self.amount:,.0f} ({self.get_status_display()})"
