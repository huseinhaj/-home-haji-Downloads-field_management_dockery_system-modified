from field_app.models import School, Subject, SchoolSubjectCapacity

# Masomo ya shule ya msingi (kwa Kiswahili)
PRIMARY_SUBJECTS = [
    ("Kiswahili", "PR001"),
    ("Kiingereza", "PR002"),
    ("Hisabati", "PR003"),
    ("Sayansi", "PR004"),
    ("Uraia na Maadili", "PR005"),
    ("Maarifa ya Jamii", "PR006"),
    ("Stadi za Kazi", "PR007"),
    ("TEHAMA", "PR008")
]

# Masomo ya shule ya sekondari
SECONDARY_SUBJECTS = [
    ("English", "SE001"),
    ("Kiswahili", "SE002"),
    ("Mathematics", "SE003"),
    ("Physics", "SE004"),
    ("Chemistry", "SE005"),
    ("Biology", "SE006"),
    ("Geography", "SE007"),
    ("History", "SE008"),
    ("Civics", "SE009"),
    ("Bookkeeping", "SE010"),
    ("Commerce", "SE011"),
    ("ICT", "SE012")
]

def populate_subjects():
    for school in School.objects.all():
        if school.level == 'Primary':
            subject_list = PRIMARY_SUBJECTS
        elif school.level == 'Secondary':
            subject_list = SECONDARY_SUBJECTS
        else:
            continue  # Skip unknown level

        for name, code in subject_list:
            subject, _ = Subject.objects.get_or_create(name=name, code=code)

            SchoolSubjectCapacity.objects.get_or_create(
                school=school,
                subject=subject,
                defaults={'max_students': 10, 'current_students': 0}
            )

populate_subjects()
print("✅ Masomo yameongezwa kwa mafanikio!")

