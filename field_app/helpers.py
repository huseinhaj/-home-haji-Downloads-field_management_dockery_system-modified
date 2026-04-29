from .models import Subject, SchoolSubjectCapacity

PRIMARY_SUBJECTS = [
    ("Hisabati", "MATH"),
    ("Kiswahili", "SWA"),
    ("Sayansi", "SCI"),
    ("Maarifa ya Jamii", "MAJ"),
    ("English", "ENG"),
    ("Stadi za Kazi", "SK"),
    ("Michezo", "PE")
]

SECONDARY_SUBJECTS = [
    ("Mathematics", "MATH"),
    ("English", "ENG"),
    ("Biology", "BIO"),
    ("Physics", "PHY"),
    ("Chemistry", "CHE"),
    ("Kiswahili", "SWA"),
    ("Geography", "GEO"),
    ("History", "HIST"),
    ("Civics", "CIV"),
    ("Bookkeeping", "BK"),
    ("Commerce", "COM")
]


def create_subjects_for_school(school):
    subjects = PRIMARY_SUBJECTS if school.level == 'Primary' else SECONDARY_SUBJECTS

    for name, code in subjects:
        subject, _ = Subject.objects.get_or_create(name=name, code=code)
        SchoolSubjectCapacity.objects.get_or_create(
            school=school,
            subject=subject,
            defaults={'max_students': 2, 'current_students': 0}
        )

