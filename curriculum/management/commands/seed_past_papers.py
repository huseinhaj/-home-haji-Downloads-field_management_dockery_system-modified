"""Seed NECTA past-paper links (TETEA Maktaba) into the PastPaper table.

Links ni halisi kutoka https://maktaba.tetea.org/past-papers/ (direct PDFs) na
maktaba ya TETEA kwa kila somo. Subject id inalinganishwa kwa jina.
Run:  python manage.py seed_past_papers
"""
from django.core.management.base import BaseCommand

from field_app.models import Subject
from curriculum.models import PastPaper


# ── Direct PDF links (TETEA Maktaba) kwa subjects za kawaida ──
TETEA_BASE = 'https://maktaba.tetea.org/past-papers/'

# (exam_code, level, class_name, subject_name, year, relative_url)
PAST_PAPERS = [
    # ── CSEE (Form 4) ──
    ('CSEE', 'ordinary', 'Form 4', 'Basic Mathematics', 2009, 'csee/basic_math/Basic%20Math%20-%20F4%20-%202009.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Basic Mathematics', 2010, 'csee/basic_math/Basic%20Math%20-%20F4%20-%202010.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Basic Mathematics', 2011, 'csee/basic_math/Basic%20Math%20-%20F4%20-%202011.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Biology', 2014, 'csee/biology/Biology%20-%20F4%20-%202014.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Biology', 2015, 'csee/biology/Biology%20-%20F4%20-%202015.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Chemistry', 2016, 'csee/chemistry/Chemistry%201%20-%20F4%20-%202016.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Chemistry', 2017, 'csee/chemistry/Chemistry%201%20-%20F4%20-%202017.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Physics', 2016, 'csee/physics/Physics%201%20-%20F4%20-%202016.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Physics', 2015, 'csee/physics/Physics%201%20-%20F4%20-%202015.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'English', 2021, 'csee/english/English-F4-2021.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Kiswahili', 2004, 'csee/kiswahili/Kiswahili-F4-2004.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Geography', 2014, 'csee/geography/Geography%20-%20F4%20-%202014.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'History', 2013, 'csee/history/History%20-%20F4%20-%202013.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Civics', 2012, 'csee/civics/Civics%20-%20F4%20-%202012.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Book Keeping', 2015, 'csee/book_keeping/Book%20Keeping%20-%20F4%20-%202015.pdf'),
    ('CSEE', 'ordinary', 'Form 4', 'Commerce', 2014, 'csee/commerce/Commerce%20-%20F4%20-%202014.pdf'),

    # ── FTNA (Form 2) ──
    ('FTNA', 'ordinary', 'Form 2', 'Physics', 2022, 'form_ii/physics/Physics-F2-2022.pdf'),
    ('FTNA', 'ordinary', 'Form 2', 'English', 2022, 'form_ii/english/English-F2-2022.pdf'),
    ('FTNA', 'ordinary', 'Form 2', 'Kiswahili', 2005, 'form_ii/kiswahili/Kiswahili-F2-2005.pdf'),
    ('FTNA', 'ordinary', 'Form 2', 'Basic Mathematics', 2019, 'form_ii/basic_math/Basic%20Math%20-%20F2%20-%202019.pdf'),
    ('FTNA', 'ordinary', 'Form 2', 'Biology', 2021, 'form_ii/biology/Biology-F2-2021.pdf'),
    ('FTNA', 'ordinary', 'Form 2', 'Chemistry', 2018, 'form_ii/chemistry/Chemistry-F2-2018.pdf'),
    ('FTNA', 'ordinary', 'Form 2', 'Geography', 2020, 'form_ii/geography/Geography-F2-2020.pdf'),
    ('FTNA', 'ordinary', 'Form 2', 'History', 2017, 'form_ii/history/History-F2-2017.pdf'),
    ('FTNA', 'ordinary', 'Form 2', 'Civics', 2019, 'form_ii/civics/Civics-F2-2019.pdf'),

    # ── PSLE (Standard 7) ──
    ('PSLE', 'primary', 'Standard 7', 'Mathematics', 2012, 'psle/math/Mathematics%20-%20PSLE%20-%202012.pdf'),
    ('PSLE', 'primary', 'Standard 7', 'Mathematics', 2015, 'psle/math/Mathematics%20-%20PSLE%20-%202015.pdf'),
    ('PSLE', 'primary', 'Standard 7', 'Science', 2013, 'psle/science/Science%20-%20PSLE%20-%202013.pdf'),
    ('PSLE', 'primary', 'Standard 7', 'Science', 2016, 'psle/science/Science%20-%20PSLE%20-%202016.pdf'),
    ('PSLE', 'primary', 'Standard 7', 'Kiswahili', 2014, 'psle/kiswahili/Kiswahili%20-%20PSLE%20-%202014.pdf'),
    ('PSLE', 'primary', 'Standard 7', 'English', 2018, 'psle/english/English%20-%20PSLE%20-%202018.pdf'),
    ('PSLE', 'primary', 'Standard 7', 'Social Studies', 2015, 'psle/social_studies/Social%20Studies%20-%20PSLE%20-%202015.pdf'),

    # ── ACSEE (Form 6) ──
    ('ACSEE', 'advanced', 'Form 6', 'Advanced Mathematics', 2014, 'acsee/adv_math/Advanced%20Math%201%20-%20F6%20-%202014.pdf'),
    ('ACSEE', 'advanced', 'Form 6', 'Advanced Mathematics', 2015, 'acsee/adv_math/Advanced%20Math%201%20-%20F6%20-%202015.pdf'),
    ('ACSEE', 'advanced', 'Form 6', 'Physics', 2016, 'acsee/physics/Physics%202%20-%20F6%20-%202016.pdf'),
    ('ACSEE', 'advanced', 'Form 6', 'Physics', 2014, 'acsee/physics/Physics%201%20-%20F6%20-%202014.pdf'),
    ('ACSEE', 'advanced', 'Form 6', 'Chemistry', 2015, 'acsee/chemistry/Chemistry%201%20-%20F6%20-%202015.pdf'),
    ('ACSEE', 'advanced', 'Form 6', 'Biology', 2016, 'acsee/biology/Biology%202%20-%20F6%20-%202016.pdf'),
    ('ACSEE', 'advanced', 'Form 6', 'Economics', 2015, 'acsee/economics/Economics%201%20-%20F6%20-%202015.pdf'),
    ('ACSEE', 'advanced', 'Form 6', 'Geography', 2016, 'acsee/geography/Geography%201%20-%20F6%20-%202016.pdf'),
    ('ACSEE', 'advanced', 'Form 6', 'History', 2014, 'acsee/history/History%201%20-%20F6%20-%202014.pdf'),
    ('ACSEE', 'advanced', 'Form 6', 'English', 2018, 'acsee/english/English%201%20-%20F6%20-%202018.pdf'),
]

# Generic maktaba URL kwa kila somo (fallback kwa mwaka wowote)
SUBJECT_LIBRARY = {
    'Basic Mathematics': 'csee/basic_math/',
    'Mathematics': 'psle/math/',
    'Advanced Mathematics': 'acsee/adv_math/',
    'Biology': 'csee/biology/',
    'Chemistry': 'csee/chemistry/',
    'Physics': 'csee/physics/',
    'English': 'csee/english/',
    'Kiswahili': 'csee/kiswahili/',
    'Geography': 'csee/geography/',
    'History': 'csee/history/',
    'Civics': 'csee/civics/',
    'Book Keeping': 'csee/book_keeping/',
    'Commerce': 'csee/commerce/',
    'Science': 'psle/science/',
    'Social Studies': 'psle/social_studies/',
    'Economics': 'acsee/economics/',
}


class Command(BaseCommand):
    help = 'Seed NECTA past-paper links (TETEA Maktaba) into PastPaper table.'

    def handle(self, *args, **options):
        created = 0
        skipped = 0
        for exam_code, level, class_name, subject_name, year, rel_url in PAST_PAPERS:
            subject = Subject.objects.filter(name__iexact=subject_name).first()
            title = f"{exam_code} — {subject_name} ({year})"
            if PastPaper.objects.filter(title=title, exam_code=exam_code, year=year).exists():
                skipped += 1
                continue
            PastPaper.objects.create(
                education_level=level,
                class_name=class_name,
                subject=subject,
                subject_name=subject_name,
                exam_code=exam_code,
                year=year,
                title=title,
                url=TETEA_BASE + rel_url,
                source='tetea',
            )
            created += 1

        # Subject-library fallback pages (kila somo — mwaka wowote)
        lib_created = 0
        for subject_name, path in SUBJECT_LIBRARY.items():
            title = f"Maktaba TETEA — {subject_name}"
            if PastPaper.objects.filter(title=title, source='tetea_library').exists():
                continue
            PastPaper.objects.create(
                education_level='ordinary',
                class_name='Form 1-4',
                subject=Subject.objects.filter(name__iexact=subject_name).first(),
                subject_name=subject_name,
                exam_code='',
                year=None,
                title=title,
                url=TETEA_BASE + path,
                source='tetea_library',
            )
            lib_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Past papers seeded: {created} created, {lib_created} library pages, {skipped} skipped.'
        ))
