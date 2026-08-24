"""Translate Swahili timetable labels to English in existing TimeSlot records."""
from django.db import migrations


MAPPING = {
    'Usafi na Gwaride': 'Cleanliness & Parade',
    'Mapumziko': 'Break',
    'Chakula cha Mchana': 'Lunch',
    'Dini': 'Religion',
    'DINI': 'Religion',
}


def translate_labels(apps, schema_editor):
    TimeSlot = apps.get_model('results', 'TimeSlot')
    for swahili, english in MAPPING.items():
        TimeSlot.objects.filter(label__iexact=swahili).update(label=english)


def reverse_translate(apps, schema_editor):
    TimeSlot = apps.get_model('results', 'TimeSlot')
    for swahili, english in MAPPING.items():
        TimeSlot.objects.filter(label=english).update(label=swahili)


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0029_timetableprintsubmission'),
    ]

    operations = [
        migrations.RunPython(translate_labels, reverse_translate),
    ]
