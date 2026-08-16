"""Seed TIE textbooks + maktaba links into the Textbook table.

Vitabu halisi vya TIE Online Library (links zilizothibitishwa) kwa masomo na
madarasa makuu + links za maktaba rasmi (TIE Online Library, Maktaba TETEA)
kwa kila darasa — ili kila darasa liwe na vitabu vingi vya kufungua.

Run:  python manage.py seed_tie_books
"""
from django.core.management.base import BaseCommand

from field_app.models import ClassLevel, Subject, Textbook


# ── Links halisi za TIE Online Library (zilizothibitishwa) ──
# (class_name, subject_name_in_db, title, url, publisher)
TIE_BOOKS = [
    # ═══ PRIMARY — Standard 4 (links zilizothibitishwa) ═══
    ('Standard 4', 'Kusoma', 'English Standard 4 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/primary/Eng/Std4/English/English_Std_4.html', 'TIE'),
    ('Standard 4', 'Hesabu', 'Mathematics Standard 4 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/primary/Eng/Std4/Mathematics/Mathematics_Std_4.html', 'TIE'),
    ('Standard 4', 'Sayansi', 'Science and Technology Standard 4 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/primary/Eng/Std4/Science/Science_Std_4.html', 'TIE'),
    ('Standard 4', 'Kusoma', 'Kiswahili Standard 4 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/primary/Eng/Std4/Kiswahili/Kiswahili_Std_4.html', 'TIE'),
    ('Standard 4', 'Maarifa ya Jamii', 'Geography and Environment Standard 4 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/primary/Eng/Std4/Geography/Geography_n_Environ_Std_4.html', 'TIE'),
    ('Standard 4', 'Michezo', 'Culture, Arts and Sports Standard 4 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/primary/Eng/Std4/Art_n_Sports/Art_n_Sports_Std_4.html', 'TIE'),

    # ═══ SECONDARY — Form 1 (links zilizothibitishwa) ═══
    ('Form 1', 'English Language', 'English for Secondary Schools Form 1 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books//secondary/Form_One/English_Form_One/English.html', 'TIE'),
    ('Form 1', 'Mathematics', 'Mathematics for Secondary Schools Form 1 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books//secondary/Form_One/Mathematics_Form_One/Mathematics.html', 'TIE'),
    ('Form 1', 'History', 'History for Secondary Schools Form 1 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books//secondary/Form_One/History/History_Form_One.html', 'TIE'),
    ('Form 1', 'Physics', 'Physics for Secondary Schools Form 1 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books//secondary/Form_One/Physics_Form_One/Physics.html', 'TIE'),
    ('Form 1', 'Chemistry', 'Chemistry for Secondary Schools Form 1 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books//secondary/Form_One/Chemistry_Form_One/Chemistry_Form_One.html', 'TIE'),
    ('Form 1', 'Biology', 'Biology for Secondary Schools Form 1 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books//secondary/Form_One/Biology_Form_One/Biology_Form_One.html', 'TIE'),
    ('Form 1', 'Kiswahili', 'Kiswahili Kidato cha Kwanza (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books//secondary/Form_One/Kiswahili_Kidato_cha_Kwanza/Kiswahili.html', 'TIE'),
    ('Form 1', 'Geography', 'Geography for Secondary Schools Form 1 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books//secondary/Form_One/Geography_Form_One/Geography%20for%20Secondary%20Schools%20Student%E2%80%99s%20Book%20Form%20One.html', 'TIE'),

    # ═══ SECONDARY — Form 2 ═══
    ('Form 2', 'English Language', 'English for Secondary Schools Form 2 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books//secondary/Form_Two/English_Form_Two/English.html', 'TIE'),
    ('Form 2', 'Mathematics', 'Mathematics for Secondary Schools Form 2 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books//secondary/Form_Two/Mathematics_Form_Two/Mathematics_Form_Two.html', 'TIE'),
    ('Form 2', 'Physics', 'Physics for Secondary Schools Form 2 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/secondary/Form_Two/Physics_Form_Two/Physics_Form_2.html', 'TIE'),
    ('Form 2', 'Chemistry', 'Chemistry for Secondary Schools Form 2 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/secondary/Form_Two/Chemistry/Chemistry_Form_2.html', 'TIE'),

    # ═══ SECONDARY — Form 3 ═══
    ('Form 3', 'Mathematics', 'Mathematics for Secondary Schools Form 3 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/secondary/Form_Three/Mathematics/Mathematics_Form_3.html', 'TIE'),

    # ═══ SECONDARY — Form 4 (CSEE) ═══
    ('Form 4', 'English Language', 'English for Secondary Schools Form 4 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/secondary/Form_Four/English/English_Form_4.html', 'TIE'),
    ('Form 4', 'Kiswahili', 'Kiswahili Kidato cha Nne (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/secondary/Form_Four/Kiswahili/Kiswahili_Form_4.html', 'TIE'),
    ('Form 4', 'Chemistry', 'Chemistry for Secondary Schools Form 4 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/secondary/Form_Four/Chemistry/Chemistry_Form_4.html', 'TIE'),

    # ═══ ADVANCED — Form 5 ═══
    ('Form 5', 'Biology', 'Biology for Advanced Secondary Schools Form 5 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books//adv_secondary/frmv/Stud_Book/Biology/Biology_F5.html', 'TIE'),
    ('Form 5', 'English Language', 'English for Advanced Secondary Schools Form 5 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/adv_secondary/frmv/Stud_Book/English/English_F5.html', 'TIE'),
    ('Form 5', 'Accountancy', 'Accountancy for Advanced Secondary Schools Form 5 (TIE)',
     'https://ol.tie.go.tz/uploaded_files/books/adv_secondary/frmv/Stud_Book/Accountancy/Accountancy_F5.html', 'TIE'),
]


# ── Maktaba rasmi kwa kila darasa (fallback — zinafanya kazi kila wakati) ──
# (level_key, class_name, title, url)
LIBRARY_LINKS = [
    # Primary — kila Standard 1-7
    ('primary', 'Standard 1', 'TIE Online Library — Standard 1', 'https://ol.tie.go.tz/'),
    ('primary', 'Standard 1', 'Maktaba TETEA — Standards 1-4', 'https://maktaba.tetea.org/resources/'),
    ('primary', 'Standard 2', 'TIE Online Library — Standard 2', 'https://ol.tie.go.tz/'),
    ('primary', 'Standard 2', 'Maktaba TETEA — Standards 1-4', 'https://maktaba.tetea.org/resources/'),
    ('primary', 'Standard 3', 'TIE Online Library — Standard 3', 'https://ol.tie.go.tz/'),
    ('primary', 'Standard 3', 'Maktaba TETEA — Standards 1-4', 'https://maktaba.tetea.org/resources/'),
    ('primary', 'Standard 4', 'TIE Online Library — Standard 4', 'https://ol.tie.go.tz/'),
    ('primary', 'Standard 4', 'Maktaba TETEA — Standards 1-4', 'https://maktaba.tetea.org/resources/'),
    ('primary', 'Standard 5', 'TIE Online Library — Standard 5', 'https://ol.tie.go.tz/'),
    ('primary', 'Standard 5', 'Maktaba TETEA — Standards 5-7', 'https://maktaba.tetea.org/resources/'),
    ('primary', 'Standard 6', 'TIE Online Library — Standard 6', 'https://ol.tie.go.tz/'),
    ('primary', 'Standard 6', 'Maktaba TETEA — Standards 5-7', 'https://maktaba.tetea.org/resources/'),
    ('primary', 'Standard 7', 'TIE Online Library — Standard 7', 'https://ol.tie.go.tz/'),
    ('primary', 'Standard 7', 'Maktaba TETEA — Standards 5-7', 'https://maktaba.tetea.org/resources/'),
    # Ordinary — kila Form 1-4
    ('ordinary', 'Form 1', 'TIE Online Library — Form 1', 'https://ol.tie.go.tz/'),
    ('ordinary', 'Form 1', 'Maktaba TETEA — Forms 1-2', 'https://maktaba.tetea.org/resources/'),
    ('ordinary', 'Form 2', 'TIE Online Library — Form 2', 'https://ol.tie.go.tz/'),
    ('ordinary', 'Form 2', 'Maktaba TETEA — Forms 1-2', 'https://maktaba.tetea.org/resources/'),
    ('ordinary', 'Form 3', 'TIE Online Library — Form 3', 'https://ol.tie.go.tz/'),
    ('ordinary', 'Form 3', 'Maktaba TETEA — Forms 3-4', 'https://maktaba.tetea.org/resources/'),
    ('ordinary', 'Form 4', 'TIE Online Library — Form 4', 'https://ol.tie.go.tz/'),
    ('ordinary', 'Form 4', 'Maktaba TETEA — Forms 3-4', 'https://maktaba.tetea.org/resources/'),
    ('ordinary', 'Form 4', 'NECTA — CSEE Past Papers (TETEA)', 'https://maktaba.tetea.org/past-papers/'),
    # Advanced — Form 5-6
    ('advanced', 'Form 5', 'TIE Online Library — Form 5', 'https://ol.tie.go.tz/'),
    ('advanced', 'Form 5', 'Maktaba TETEA — Forms 5-6', 'https://maktaba.tetea.org/resources/'),
    ('advanced', 'Form 6', 'TIE Online Library — Form 6', 'https://ol.tie.go.tz/'),
    ('advanced', 'Form 6', 'Maktaba TETEA — Forms 5-6', 'https://maktaba.tetea.org/resources/'),
    ('advanced', 'Form 6', 'NECTA — ACSEE Past Papers (TETEA)', 'https://maktaba.tetea.org/past-papers/'),
    # Technical — kila Grade/NTA
    ('technical', 'Grade III', 'TIE Online Library — Technical Books', 'https://ol.tie.go.tz/'),
    ('technical', 'Grade III', 'NACTE — Mihtasari na Mitaala', 'https://nacte.go.tz/'),
    ('technical', 'Grade II', 'TIE Online Library — Technical Books', 'https://ol.tie.go.tz/'),
    ('technical', 'Grade II', 'NACTE — Mihtasari na Mitaala', 'https://nacte.go.tz/'),
    ('technical', 'Grade I', 'TIE Online Library — Technical Books', 'https://ol.tie.go.tz/'),
    ('technical', 'Grade I', 'NACTE — Mihtasari na Mitaala', 'https://nacte.go.tz/'),
    ('technical', 'NTA 4 (Basic Certificate)', 'TIE Online Library — Technical Books', 'https://ol.tie.go.tz/'),
    ('technical', 'NTA 4 (Basic Certificate)', 'NACTE — Mihtasari na Mitaala', 'https://nacte.go.tz/'),
    ('technical', 'NTA 5 (Certificate)', 'TIE Online Library — Technical Books', 'https://ol.tie.go.tz/'),
    ('technical', 'NTA 5 (Certificate)', 'NACTE — Mihtasari na Mitaala', 'https://nacte.go.tz/'),
    ('technical', 'NTA 6 (Diploma)', 'TIE Online Library — Technical Books', 'https://ol.tie.go.tz/'),
    ('technical', 'NTA 6 (Diploma)', 'NACTE — Mihtasari na Mitaala', 'https://nacte.go.tz/'),
]


class Command(BaseCommand):
    help = 'Seed TIE textbooks + maktaba links into the Textbook table (idempotent).'

    def handle(self, *args, **options):
        created = 0
        skipped = 0

        # ── 1. Vitabu maalum vya TIE ──
        for class_name, subject_name, title, url, publisher in TIE_BOOKS:
            cl = ClassLevel.objects.filter(name__iexact=class_name).first()
            if not cl:
                self.stdout.write(self.style.WARNING(f"⚠️  Class '{class_name}' haipo — imerukwa"))
                continue
            subject = Subject.objects.filter(name__iexact=subject_name).first()
            if Textbook.objects.filter(title=title, url=url).exists():
                skipped += 1
                continue
            level_key = 'primary'
            el_name = getattr(cl.education_level, 'name', '')
            if 'ordinary' in el_name.lower() or 'secondary' in el_name.lower():
                level_key = 'ordinary'
            elif 'advanced' in el_name.lower():
                level_key = 'advanced'
            elif 'technical' in el_name.lower() or 'veta' in el_name.lower():
                level_key = 'technical'
            Textbook.objects.create(
                title=title,
                subject=subject,
                education_level=level_key,
                class_level=cl,
                publisher=publisher,
                url=url,
                description=f'Kitabu cha TIE — {class_name}',
            )
            created += 1

        # ── 2. Maktaba rasmi kwa kila darasa ──
        lib_created = 0
        for level_key, class_name, title, url in LIBRARY_LINKS:
            cl = ClassLevel.objects.filter(name__iexact=class_name).first() if class_name else None
            if Textbook.objects.filter(title=title, url=url, education_level=level_key,
                                       class_level=cl).exists():
                skipped += 1
                continue
            Textbook.objects.create(
                title=title,
                education_level=level_key,
                class_level=cl,
                publisher='Rasmi',
                url=url,
                description='Maktaba rasmi ya vitabu (TIE / TETEA / NACTE / VETA)',
            )
            lib_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Vitabu seeded: {created} TIE books, {lib_created} maktaba links, {skipped} skipped.'
        ))
