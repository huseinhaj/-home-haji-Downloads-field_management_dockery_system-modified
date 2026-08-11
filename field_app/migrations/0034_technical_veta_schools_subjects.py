"""
Data migration: Vyuo vya VETA na Shule za Technical nchini Tanzania.
- Ongeza 'Technical' kwenye School.level na 'technical' kwenye Subject.level.
- Tengeneza EducationLevel "Technical / VETA" + ClassLevels (Grade I-III, NTA 4-6).
- Ingiza vyuo vyote vya VETA (RVTSC/DVTC/VTC) na shule za technical.
- Ingiza masomo yote ya ufundi (technical/vocational subjects).
Inatekelezwa kiotomatiki wakati wa 'manage.py migrate'.
"""
from django.db import migrations, models


# ── Masomo ya Ufundi (Technical/Vocational) — NACTVET/VETA trades ──
TECHNICAL_SUBJECTS = [
    # (name, code)
    ('Electrical Installation',            'T01'),
    ('Electrical Engineering',             'T02'),
    ('Electronics and Communication',      'T03'),
    ('Plumbing and Pipe Fitting',          'T04'),
    ('Masonry and Brick Laying',           'T05'),
    ('Carpentry and Joinery',              'T06'),
    ('Welding and Metal Fabrication',      'T07'),
    ('Motor Vehicle Mechanics',            'T08'),
    ('Motorcycle and Engine Mechanics',    'T09'),
    ('Agriculture and Crop Production',    'T10'),
    ('Animal Husbandry',                   'T11'),
    ('Tailoring and Garment Making',       'T12'),
    ('Fashion Design and Beauty Therapy',  'T13'),
    ('Catering and Food Production',       'T14'),
    ('Hotel and Tourism Management',       'T15'),
    ('Information and Communication Technology', 'T16'),
    ('Computer Applications',              'T17'),
    ('Secretarial and Office Management',  'T18'),
    ('Accounting and Bookkeeping',         'T19'),
    ('Entrepreneurship and Business Studies', 'T20'),
    ('Building and Civil Engineering',     'T21'),
    ('Mechanical Engineering',             'T22'),
    ('Renewable Energy and Solar Installation', 'T23'),
    ('Refrigeration and Air Conditioning', 'T24'),
    ('Graphic Design and Printing',        'T25'),
    ('Leather and Shoe Making',            'T26'),
    ('Painting and Decorating',            'T27'),
    ('Woodwork and Furniture Making',      'T28'),
    ('Food Processing and Preservation',   'T29'),
    ('Occupational Safety and Health',     'T30'),
    ('Communication Skills',               'T31'),
    ('Applied Mathematics for Trades',     'T32'),
    ('Basic Health and Caregiving',        'T33'),
    ('Automotive Electrical Systems',      'T34'),
    ('Water Supply and Sanitation',        'T35'),
    ('Baking and Confectionery',           'T36'),
]


# ── Vyuo vya VETA — (jina, wilaya, mkoa) ──
VETA_COLLEGES = [
    # Arusha
    ('VETA Arusha (RVTSC)',            'Arusha Cc',    'Arusha'),
    ('VETA Karatu (DVTC)',             'Karatu Dc',    'Arusha'),
    ('VETA Monduli (DVTC)',            'Monduli Dc',   'Arusha'),
    ('VETA Longido (DVTC)',            'Longido Dc',   'Arusha'),
    ('VETA Ngorongoro (DVTC)',         'Ngorongoro Dc','Arusha'),
    # Coast (Pwani)
    ('VETA Kibaha (RVTSC)',            'Kibaha Tc',    'Coast'),
    ('VETA Rufiji (DVTC)',             'Rufiji Dc',    'Coast'),
    ('VETA Mafia (DVTC)',              'Mafia Dc',     'Coast'),
    ('VETA Kisarawe (DVTC)',           'Kisarawe Dc',  'Coast'),
    ('VETA Mkuranga (DVTC)',           'Mkuranga Dc',  'Coast'),
    ('VETA Bagamoyo (DVTC)',           'Bagamoyo Dc',  'Coast'),
    ('VETA Chalinze (DVTC)',           'Chalinze Dc',  'Coast'),
    # Dar es Salaam
    ('VETA Dar es Salaam (RVTSC)',     'Temeke Mc',    'Dar Es Salaam'),
    ('VETA Kipawa ICT Centre',         'Ilala Mc',     'Dar Es Salaam'),
    ('VETA Makongo (VTC)',             'Kinondoni Mc', 'Dar Es Salaam'),
    ('VETA Mikocheni (VTC)',           'Kinondoni Mc', 'Dar Es Salaam'),
    ('VETA Yombo (VTC)',               'Temeke Mc',    'Dar Es Salaam'),
    # Dodoma
    ('VETA Dodoma (RVTSC)',            'Dodoma Cc',    'Dodoma'),
    ('VETA Bahi (DVTC)',               'Bahi Dc',      'Dodoma'),
    ('VETA Chemba (DVTC)',             'Chemba Dc',    'Dodoma'),
    ('VETA Kongwa (DVTC)',             'Kongwa Dc',    'Dodoma'),
    ('VETA Ihumwa (VTC)',              'Dodoma Dc',    'Dodoma'),
    ('VETA Mpwapwa (DVTC)',            'Mpwapwa Dc',   'Dodoma'),
    ('VETA Chamwino (DVTC)',           'Chamwino Dc',  'Dodoma'),
    ('VETA Kondoa (DVTC)',             'Kondoa Dc',    'Dodoma'),
    # Geita
    ('VETA Geita (VTC)',               'Geita Tc',     'Geita'),
    ('VETA Chato (VTC)',               'Chato Dc',     'Geita'),
    ('VETA Bukombe (DVTC)',            'Bukombe Dc',   'Geita'),
    # Iringa
    ('VETA Iringa (RVTSC)',            'Iringa Mc',    'Iringa'),
    ('VETA Ulete (VTC)',               'Kilolo Dc',    'Iringa'),
    ('VETA Minani (VTC)',              'Mufindi Dc',   'Iringa'),
    ('VETA Mafinga (VTC)',             'Mafinga Tc',   'Iringa'),
    # Kagera
    ('VETA Kagera (RVTSC)',            'Bukoba Mc',    'Kagera'),
    ('VETA Karagwe (DVTC)',            'Karagwe Dc',   'Kagera'),
    ('VETA Ndolage (VTC)',             'Muleba Dc',    'Kagera'),
    ('VETA Ngara (DVTC)',              'Ngara Dc',     'Kagera'),
    ('VETA Biharamulo (DVTC)',         'Biharamulo Dc','Kagera'),
    ('VETA Muleba (VTC)',              'Muleba Dc',    'Kagera'),
    # Katavi
    ('VETA Mpanda (VTC)',              'Mpanda Mc',    'Katavi'),
    ('VETA Mlele (DVTC)',              'Mlele Dc',     'Katavi'),
    # Kigoma
    ('VETA Kigoma (RVTSC)',            'Kigoma Mc',    'Kigoma'),
    ('VETA Kasulu (DVTC)',             'Kasulu Dc',    'Kigoma'),
    ('VETA Buhigwe (DVTC)',            'Buhigwe Dc',   'Kigoma'),
    ('VETA Uvinza (DVTC)',             'Uvinza Dc',    'Kigoma'),
    ('VETA Kibondo (DVTC)',            'Kibondo Dc',   'Kigoma'),
    ('VETA Kakonko (DVTC)',            'Kakonko Dc',   'Kigoma'),
    # Kilimanjaro
    ('VETA Moshi (RVTSC)',             'Moshi Mc',     'Kilimanjaro'),
    ('VETA Mawella (VTC)',             'Moshi Dc',     'Kilimanjaro'),
    ('VETA Same (DVTC)',               'Same Dc',      'Kilimanjaro'),
    ('VETA Rombo (DVTC)',              'Rombo Dc',     'Kilimanjaro'),
    ('VETA Hai (DVTC)',                'Hai Dc',       'Kilimanjaro'),
    ('VETA Mwanga (DVTC)',             'Mwanga Dc',    'Kilimanjaro'),
    ('VETA Siha (DVTC)',               'Siha Dc',      'Kilimanjaro'),
    # Lindi
    ('VETA Lindi (RVTSC)',             'Lindi Mc',     'Lindi'),
    ('VETA Ruangwa (DVTC)',            'Ruangwa Dc',   'Lindi'),
    ('VETA Nachingwea (VTC)',          'Nachingwea Dc','Lindi'),
    ('VETA Kilwa (DVTC)',              'Kilwa Dc',     'Lindi'),
    ('VETA Liwale (DVTC)',             'Liwale Dc',    'Lindi'),
    # Manyara
    ('VETA Babati (RVTSC)',            'Babati Tc',    'Manyara'),
    ('VETA Gorowa (VTC)',              'Babati Dc',    'Manyara'),
    ('VETA Simanjiro (DVTC)',          'Simanjiro Dc', 'Manyara'),
    ('VETA Mbulu (DVTC)',              'Mbulu Dc',     'Manyara'),
    ('VETA Hanang (DVTC)',             'Hanang Dc',    'Manyara'),
    ('VETA Kiteto (DVTC)',             'Kiteto Dc',    'Manyara'),
    # Mara
    ('VETA Mara (VTC)',                'Musoma Mc',    'Mara'),
    ('VETA Butiama (DVTC)',            'Butiama Dc',   'Mara'),
    ('VETA Tarime (DVTC)',             'Tarime Dc',    'Mara'),
    ('VETA Bunda (DVTC)',              'Bunda Dc',     'Mara'),
    ('VETA Rorya (DVTC)',              'Rorya Dc',     'Mara'),
    ('VETA Serengeti (DVTC)',          'Serengeti Dc', 'Mara'),
    # Mbeya
    ('VETA Mbeya (RVTSC)',             'Mbeya Cc',     'Mbeya'),
    ('VETA Chunya (DVTC)',             'Chunya Dc',    'Mbeya'),
    ('VETA Mbarali (DVTC)',            'Mbarali Dc',   'Mbeya'),
    ('VETA Busokelo (DVTC)',           'Busokelo Dc',  'Mbeya'),
    ('VETA Kyela (DVTC)',              'Kyela Dc',     'Mbeya'),
    ('VETA Rungwe (VTC)',              'Rungwe Dc',    'Mbeya'),
    ('Mbeya Trade School',             'Mbeya Cc',     'Mbeya'),
    # Morogoro
    ('VETA Kihonda (RVTSC)',           'Morogoro Mc',  'Morogoro'),
    ('VETA Dakawa (VTC)',              'Mvomero Dc',   'Morogoro'),
    ('VETA Mikumi (VTC)',              'Kilosa Dc',    'Morogoro'),
    ('VETA Ulanga (DVTC)',             'Ulanga Dc',    'Morogoro'),
    ('VETA Kilombero (DVTC)',          'Kilombero Dc', 'Morogoro'),
    ('VETA Gairo (DVTC)',              'Gairo Dc',     'Morogoro'),
    # Mtwara
    ('VETA Mtwara (RVTSC)',            'Mtwara Mc',    'Mtwara'),
    ('VETA Kitangari (DVTC)',          'Newala Dc',    'Mtwara'),
    ('VETA Masasi (DVTC)',             'Masasi Tc',    'Mtwara'),
    ('VETA Tandahimba (DVTC)',         'Tandahimba Dc','Mtwara'),
    ('VETA Newala (VTC)',              'Newala Dc',    'Mtwara'),
    # Mwanza
    ('VETA Mwanza (RVTSC)',            'Mwanza Cc',    'Mwanza'),
    ('VETA Kwimba (DVTC)',             'Kwimba Dc',    'Mwanza'),
    ('VETA Ukerewe (DVTC)',            'Ukerewe Dc',   'Mwanza'),
    ('VETA Magu (VTC)',                'Magu Dc',      'Mwanza'),
    ('VETA Sengerema (VTC)',           'Sengerema Dc', 'Mwanza'),
    ('VETA Misungwi (VTC)',            'Misungwi Dc',  'Mwanza'),
    # Njombe
    ('VETA Njombe (RVTSC)',            'Njombe Tc',    'Njombe'),
    ('VETA Makete (DVTC)',             'Makete Dc',    'Njombe'),
    ("VETA Wanging'ombe (DVTC)",       'Wangingombe Dc','Njombe'),
    ('VETA Ludewa (DVTC)',             'Ludewa Dc',    'Njombe'),
    ('VETA Makambako (VTC)',           'Makambako Tc', 'Njombe'),
    # Rukwa
    ('VETA Rukwa (RVTSC)',             'Sumbawanga Mc','Rukwa'),
    ('VETA Nkasi (DVTC)',              'Nkasi Dc',     'Rukwa'),
    ('VETA Kalambo (DVTC)',            'Kalambo Dc',   'Rukwa'),
    # Ruvuma
    ('VETA Songea (VTC)',              'Songea Mc',    'Ruvuma'),
    ('VETA Namtumbo (DVTC)',           'Namtumbo Dc',  'Ruvuma'),
    ('VETA Nyasa (DVTC)',              'Nyasa Dc',     'Ruvuma'),
    ('VETA Tunduru (DVTC)',            'Tunduru Dc',   'Ruvuma'),
    ('VETA Mbinga (DVTC)',             'Mbinga Dc',    'Ruvuma'),
    # Shinyanga
    ('VETA Shinyanga (VTC)',           'Shinyanga Mc', 'Shinyanga'),
    ('VETA Kishapu (DVTC)',            'Kishapu Dc',   'Shinyanga'),
    ('VETA Kanadi (VTC)',              'Shinyanga Dc', 'Shinyanga'),
    ('VETA Kahama (VTC)',              'Kahama Tc',    'Shinyanga'),
    # Simiyu
    ('VETA Simiyu (RVTSC)',            'Bariadi Tc',   'Simiyu'),
    ('VETA Binza (VTC)',               'Maswa Dc',     'Simiyu'),
    ('VETA Itilima (DVTC)',            'Itilima Dc',   'Simiyu'),
    ('VETA Meatu (DVTC)',              'Meatu Dc',     'Simiyu'),
    ('VETA Busega (DVTC)',             'Busega Dc',    'Simiyu'),
    # Singida
    ('VETA Singida (VTC)',             'Singida Mc',   'Singida'),
    ('VETA Ikungi (DVTC)',             'Ikungi Dc',    'Singida'),
    ('VETA Nyamidaho (VTC)',           'Iramba Dc',    'Singida'),
    ('VETA Manyoni (DVTC)',            'Manyoni Dc',   'Singida'),
    ('VETA Mkalama (DVTC)',            'Mkalama Dc',   'Singida'),
    # Songwe
    ('VETA Ileje (DVTC)',              'Ileje Dc',     'Songwe'),
    ('VETA Mbozi (VTC)',               'Mbozi Dc',     'Songwe'),
    ('VETA Tunduma (VTC)',             'Tunduma Tc',   'Songwe'),
    # Tabora
    ('VETA Tabora (RVTSC)',            'Tabora Mc',    'Tabora'),
    ('VETA Igunga (DVTC)',             'Igunga Dc',    'Tabora'),
    ('VETA Urambo (DVTC)',             'Urambo Dc',    'Tabora'),
    ('VETA Ulyankulu (VTC)',           'Kaliua Dc',    'Tabora'),
    ('VETA Nzega (DVTC)',              'Nzega Dc',     'Tabora'),
    ('VETA Sikonge (DVTC)',            'Sikonge Dc',   'Tabora'),
    # Tanga
    ('VETA Tanga (RVTSC)',             'Tanga Cc',     'Tanga'),
    ('VETA Korogwe (DVTC)',            'Korogwe Tc',   'Tanga'),
    ('VETA Lushoto (DVTC)',            'Lushoto Dc',   'Tanga'),
    ('VETA Pangani (DVTC)',            'Pangani Dc',   'Tanga'),
    ('VETA Mkinga (DVTC)',             'Mkinga Dc',    'Tanga'),
    ('VETA Kilindi (DVTC)',            'Kilindi Dc',   'Tanga'),
    ('VETA Muheza (VTC)',              'Muheza Dc',    'Tanga'),
    ('VETA Handeni (VTC)',             'Handeni Dc',   'Tanga'),
]

# ── Shule za Technical (Secondary) zilizokosekana — (jina, wilaya, mkoa, code) ──
TECHNICAL_SCHOOLS = [
    ('Moshi Technical Secondary School',            'Moshi Mc',     'Kilimanjaro', 'S.0135'),
    ('Mtwara Technical Secondary School',           'Mtwara Mc',    'Mtwara',      'S.0139'),
    ('Iyunga Technical Secondary School',           'Mbeya Cc',     'Mbeya',       'S.0112'),
    ('Mwadui Technical Secondary School',           'Kishapu Dc',   'Shinyanga',   'S.0863'),
    ('Bwiru Boys Technical School',                 'Ilemela Mc',   'Mwanza',      ''),
    ('Musoma Technical Secondary School',           'Musoma Mc',    'Mara',        ''),
    ('Mwalimu Stephen Moshi Technical Secondary School', 'Rombo Dc', 'Kilimanjaro', ''),
    ('Chato Technical Secondary School',            'Chato Dc',     'Geita',       ''),
    ('Kengeja Technical Secondary School',          'Nachingwea Dc','Lindi',       ''),
]


def upgrade(apps, schema_editor):
    School = apps.get_model('field_app', 'School')
    Subject = apps.get_model('field_app', 'Subject')
    District = apps.get_model('field_app', 'District')
    Region = apps.get_model('field_app', 'Region')
    EducationLevel = apps.get_model('field_app', 'EducationLevel')
    ClassLevel = apps.get_model('field_app', 'ClassLevel')
    db = schema_editor.connection.alias

    # 1. EducationLevel: Technical / VETA + ClassLevels
    edu_level, _ = EducationLevel.objects.using(db).get_or_create(
        code='technical',
        defaults={'name': 'Technical / VETA', 'order': 4},
    )
    classes = [
        ('Grade III', 'GRADE3', 1),
        ('Grade II', 'GRADE2', 2),
        ('Grade I', 'GRADE1', 3),
        ('NTA 4 (Basic Certificate)', 'NTA4', 4),
        ('NTA 5 (Certificate)', 'NTA5', 5),
        ('NTA 6 (Diploma)', 'NTA6', 6),
    ]
    for name, code, order in classes:
        ClassLevel.objects.using(db).get_or_create(
            education_level=edu_level, name=name,
            defaults={'code': code, 'order': order},
        )

    # 2. Masomo ya ufundi (technical subjects)
    created_subjects = 0
    for name, code in TECHNICAL_SUBJECTS:
        subj = Subject.objects.using(db).filter(name=name).first()
        if subj:
            subj.level = 'technical'
            subj.save(using=db)
        else:
            Subject.objects.using(db).create(
                name=name, code=code, level='technical'
            )
            created_subjects += 1

    # 3. Vyuo vya VETA (level='Technical')
    created_veta = 0
    for name, district_name, region_name in VETA_COLLEGES:
        if School.objects.using(db).filter(
            name__iexact=name, district__name__iexact=district_name
        ).exists():
            continue
        district = District.objects.using(db).filter(
            name__iexact=district_name,
            region__name__iexact=region_name,
        ).first()
        if not district:
            continue
        School.objects.using(db).create(
            name=name, district=district, level='Technical',
            ownership='government', capacity=10, current_students=0,
        )
        created_veta += 1

    # 4. Shule za technical (Secondary)
    created_tech_schools = 0
    for name, district_name, region_name, code in TECHNICAL_SCHOOLS:
        if School.objects.using(db).filter(
            name__iexact=name, district__name__iexact=district_name
        ).exists():
            continue
        district = District.objects.using(db).filter(
            name__iexact=district_name,
            region__name__iexact=region_name,
        ).first()
        if not district:
            continue
        School.objects.using(db).create(
            name=name, district=district, level='Secondary',
            ownership='government', capacity=10, current_students=0,
            school_code=code,
        )
        created_tech_schools += 1

    # 5. Rekebisha jina la Ifunda (lililoharibika)
    #    Secondary-level → Ifunda Technical Secondary School
    #    Primary-level (school ya kituo cha ufundi) → Ifunda Technical Centre
    School.objects.using(db).filter(
        name__icontains='Ifunda', level='Secondary'
    ).exclude(name__iexact='Ifunda Technical Secondary School').update(
        name='Ifunda Technical Secondary School'
    )
    School.objects.using(db).filter(
        name__icontains='Ifunda', level='Primary'
    ).exclude(name__icontains='Technical Centre').update(
        name='Ifunda Technical Centre'
    )

    print(f"[VETA/Technical] EducationLevel+classes OK | subjects created={created_subjects} | "
          f"VETA colleges created={created_veta} | technical schools created={created_tech_schools}")


def downgrade(apps, schema_editor):
    # Reverse: haifutwi kwa uhalisi — tuondoe vitu vipya tu
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('field_app', '0033_rename_computer_studies'),
    ]

    operations = [
        migrations.AlterField(
            model_name='school',
            name='level',
            field=models.CharField(
                max_length=10,
                choices=[
                    ('Primary', 'Primary School'),
                    ('Secondary', 'Secondary School'),
                    ('Technical', 'Technical School / VETA College'),
                ],
            ),
        ),
        migrations.AlterField(
            model_name='subject',
            name='level',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('primary', 'Primary'),
                    ('secondary', 'Secondary'),
                    ('advanced', 'Advanced'),
                    ('technical', 'Technical / Vocational'),
                ],
                default='secondary',
            ),
        ),
        migrations.RunPython(upgrade, downgrade),
    ]
