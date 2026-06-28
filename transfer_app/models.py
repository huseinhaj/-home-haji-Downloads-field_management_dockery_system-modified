from django.db import models


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
    subjects = models.CharField(max_length=500, blank=True, help_text='Masomo yanayofundishwa, e.g. Hisabati, Fizikia')
    region_name = models.CharField(max_length=100)
    district_name = models.CharField(max_length=100)
    location_type = models.CharField(max_length=20, choices=LOCATION_CHOICES)
    willing_to_go = models.CharField(max_length=20, choices=LOCATION_CHOICES, blank=True, help_text='Aina ya eneo anayotaka kwenda')
    session_key = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = 'transfer_app'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} — {self.current_school} ({self.district_name})"

    def get_location_display_sw(self):
        return dict(self.LOCATION_CHOICES).get(self.location_type, self.location_type)

    def get_level_display_sw(self):
        return dict(self.LEVEL_CHOICES).get(self.level, self.level)
