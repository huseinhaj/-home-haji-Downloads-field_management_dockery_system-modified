from django.db import models
from django.conf import settings


class College(models.Model):
    """Chuo cha ualimu (Teacher Training College) kinachotoa Diploma in Education."""

    name = models.CharField(max_length=200, verbose_name='Jina Kamili la Chuo')
    short_name = models.CharField(
        max_length=60, verbose_name='Jina Fupi (mf. Kasulu TC)',
        help_text='Jina linalotumika kwenye namba ya usajili, mfano "KAS".',
    )
    code = models.CharField(
        max_length=20, unique=True, verbose_name='Msimbo wa Chuo',
        help_text='Msimbo mfupi wa kipekee, mfano KAS (Kasulu), BUT (Butimba).',
    )
    region = models.CharField(max_length=100, verbose_name='Mkoa')
    district = models.CharField(max_length=100, blank=True, verbose_name='Wilaya')
    established = models.IntegerField(null=True, blank=True, verbose_name='Mwaka wa Kuanzishwa')
    email = models.EmailField(blank=True, verbose_name='Barua Pepe')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Namba ya Simu')
    address = models.CharField(max_length=255, blank=True, verbose_name='Anwani (P.O.Box)')
    website = models.URLField(blank=True, verbose_name='Tovuti')
    description = models.TextField(blank=True, verbose_name='Maelezo')
    logo = models.ImageField(
        upload_to='college_logos/', blank=True, null=True, verbose_name='Nembo (Logo)',
    )
    is_active = models.BooleanField(default=True, verbose_name='Inatumika')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Chuo'
        verbose_name_plural = 'Vyuo'

    def __str__(self):
        return self.name

    @property
    def student_count(self):
        return self.students.count()

    @property
    def program_count(self):
        return self.programs.count()

    @property
    def fee_item_count(self):
        return self.fee_items.filter(is_active=True).count()


class Program(models.Model):
    """Programu ya Diploma inayotolewa na chuo."""

    college = models.ForeignKey(
        College, on_delete=models.CASCADE, related_name='programs', verbose_name='Chuo',
    )
    name = models.CharField(max_length=200, verbose_name='Jina la Programu')
    code = models.CharField(max_length=30, blank=True, verbose_name='Msimbo wa Programu')
    duration_years = models.IntegerField(default=2, verbose_name='Muda (Miaka)')

    class Meta:
        ordering = ['name']
        verbose_name = 'Programu'
        verbose_name_plural = 'Programu'

    def __str__(self):
        return f"{self.name} — {self.college.short_name}"

    @property
    def student_count(self):
        return self.students.count()


class CollegeAdmin(models.Model):
    """Msimamizi wa chuo mmoja — anasimamia wanafunzi, ada na malipo."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='college_admin_profile',
        verbose_name='Mtumiaji',
    )
    college = models.ForeignKey(
        College, on_delete=models.CASCADE, related_name='admins', verbose_name='Chuo',
    )
    full_name = models.CharField(max_length=200, verbose_name='Jina Kamili')
    phone_number = models.CharField(max_length=20, blank=True, verbose_name='Namba ya Simu')
    title = models.CharField(
        max_length=100, blank=True, verbose_name='Cheo',
        help_text='mfano: Mtumishi wa Mahesabu, Mkuu wa Chuo',
    )

    class Meta:
        verbose_name = 'Msimamizi wa Chuo'
        verbose_name_plural = 'Wasimamizi wa Vyuo'

    def __str__(self):
        return f"{self.full_name} — {self.college.short_name}"
