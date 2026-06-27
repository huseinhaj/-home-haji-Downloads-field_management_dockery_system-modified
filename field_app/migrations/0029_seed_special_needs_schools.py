"""
Data migration: weka alama shule za elimu maalumu na ongeza shule mpya za CSV.
Inatekelezwa kiotomatiki wakati wa 'manage.py migrate' — kabla app haijawasha.
"""
from django.db import migrations


SPECIAL_NEEDS_KEYWORDS = [
    'viziwi', 'wasioona', 'walemavu', 'viwete', 'wasiosikia',
    'maalum', 'albino', 'ulemavu',
    'blind', 'deaf', 'disabled', 'disability',
    'special need', 'special education', 'sped',
    'hearing impair', 'visual impair',
]

# (jina_icontains, district_name_icontains)
KNOWN_BY_DISTRICT = [
    ('Irente',    'Lushoto'),
    ('Mitindo',   'Misungwi'),
    ('Buhangija', 'Shinyanga'),
    ('Buigiri',   'Chamwino'),
]

# Shule mpya za CSV — (jina, district_icontains, level, ownership)
CSV_NEW_SCHOOLS = [
    ('Step by Step Learning Center',               'Arusha Cc',  'Primary',   'private'),
    ('Al Muntazir Special Education Needs School', 'Ilala',      'Primary',   'private'),
    ('Crown Secondary School',                     'Kinondoni',  'Secondary', 'private'),
    ('Kids Manual Skills Development Center',      'Ilala',      'Primary',   'private'),
    ('Josephian Schools Mbezi Beach',              'Kinondoni',  'Primary',   'private'),
    ('Faraja Home Special Needs School',           'Moshi Mc',   'Primary',   'private'),
    ('Visualization Pedagogy Global Learning',     'Tabora Mc',  'Primary',   'private'),
]


def seed_special_needs(apps, schema_editor):
    School = apps.get_model('field_app', 'School')
    District = apps.get_model('field_app', 'District')
    db = schema_editor.connection.alias

    # 1. Shule zote → is_inclusive = True
    School.objects.using(db).filter(is_inclusive=False).update(is_inclusive=True)

    # 2. Keyword matching
    from django.db.models import Q
    kw_q = Q()
    for kw in SPECIAL_NEEDS_KEYWORDS:
        kw_q |= Q(name__icontains=kw)
    School.objects.using(db).filter(kw_q).update(special_needs_education=True, is_inclusive=True)

    # 3. District-aware matching
    for sname, dname in KNOWN_BY_DISTRICT:
        School.objects.using(db).filter(
            name__icontains=sname,
            district__name__icontains=dname
        ).update(special_needs_education=True, is_inclusive=True)

    # 4. Ongeza shule mpya za CSV (kama hazijapo)
    for school_name, district_kw, level, ownership in CSV_NEW_SCHOOLS:
        if School.objects.using(db).filter(name__iexact=school_name).exists():
            # Weka alama tu
            School.objects.using(db).filter(name__iexact=school_name).update(
                special_needs_education=True, is_inclusive=True
            )
            continue

        district = District.objects.using(db).filter(
            name__icontains=district_kw
        ).first()
        if not district:
            continue

        School.objects.using(db).create(
            name=school_name,
            district=district,
            level=level,
            ownership=ownership,
            capacity=10,
            current_students=0,
            special_needs_education=True,
            is_inclusive=True,
        )


def reverse_seed(apps, schema_editor):
    # Haiwezekani kureverse kwa uhalisi — tuacha tu
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('field_app', '0028_school_special_needs_inclusive'),
    ]

    operations = [
        migrations.RunPython(seed_special_needs, reverse_code=reverse_seed),
    ]
