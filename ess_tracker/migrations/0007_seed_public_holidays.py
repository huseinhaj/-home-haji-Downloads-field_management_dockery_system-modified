from datetime import date

from django.db import migrations

# Likizo za kitaifa za Tanzania (tarehe zisizobadilika) kwa miaka 2025-2030.
# Likizo zinazobadilika (Eid, Pasaka, Ijumaa Kuu) mwalimu anaweza kuongeza
# mwenyewe kama likizo ya shule.
PUBLIC_HOLIDAYS = [
    ('Mwaka Mpya', 1, 1),
    ('Mapinduzi ya Zanzibar', 1, 12),
    ('Siku ya Karume', 4, 7),
    ('Muungano wa Tanganyika na Zanzibar', 4, 26),
    ('Siku ya Wafanyakazi', 5, 1),
    ('Saba Saba', 7, 7),
    ('Nane Nane', 8, 8),
    ('Siku ya Mwalimu Nyerere', 10, 14),
    ('Siku ya Uhuru', 12, 9),
    ('Krismasi', 12, 25),
    ('Boxing Day', 12, 26),
]

YEARS = range(2025, 2031)


def seed(apps, schema_editor):
    Holiday = apps.get_model('ess_tracker', 'Holiday')
    objs = [
        Holiday(name=name, start_date=date(year, month, day),
                end_date=date(year, month, day), is_public=True, profile=None)
        for year in YEARS
        for name, month, day in PUBLIC_HOLIDAYS
    ]
    Holiday.objects.bulk_create(objs)


def unseed(apps, schema_editor):
    Holiday = apps.get_model('ess_tracker', 'Holiday')
    Holiday.objects.filter(is_public=True, profile__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ess_tracker', '0006_task_topics_taught_task_topics_total_and_more'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
