from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """User with role-based access — SR2-style: students, college admins, super admin."""

    ROLE_CHOICES = [
        ('super_admin', 'Super Admin (Msimamizi Mkuu)'),
        ('college_admin', 'College Admin (Msimamizi wa Chuo)'),
        ('student', 'Student Teacher (Mwanafunzi)'),
    ]

    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default='student',
        verbose_name='Wajibu (Role)',
    )
    phone_number = models.CharField(
        max_length=15, blank=True, verbose_name='Namba ya Simu',
    )

    class Meta:
        verbose_name = 'Mtumiaji'
        verbose_name_plural = 'Watumiaji'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_student(self):
        return self.role == 'student'

    @property
    def is_college_admin(self):
        return self.role == 'college_admin'

    @property
    def is_super_admin(self):
        return self.role == 'super_admin'


class LoginAttempt(models.Model):
    """Ulinzi dhidi ya brute-force: hufuatilia majaribio yaliyoshindikana ya
    kuingia kwa kila (username + IP) na hufunga akaunti kwa muda baada ya
    majaribio mengi — muhimu kwa mfumo unaoshughulikia malipo."""

    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.CharField(max_length=45, default='', blank=True)
    failed = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Jaribio la Kuingia'
        verbose_name_plural = 'Majaribio ya Kuingia'
        unique_together = [('username', 'ip_address')]

    def __str__(self):
        return f'{self.username} @ {self.ip_address} (failed={self.failed})'
