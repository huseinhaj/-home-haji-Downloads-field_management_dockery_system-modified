"""
Run: python bulk_load_subjects.py
Requires DATABASE_URL to be set.
"""
import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'field_management.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from field_app.models import School, Subject, SchoolSubjectCapacity

PRIMARY_IDS   = list(range(1, 11))   # pk 1-10
SECONDARY_IDS = list(range(11, 28))  # pk 11-27

# New schools only (pk 21466+)
schools = School.objects.filter(pk__gte=21466).values('pk', 'level')
print(f"Schools to process: {schools.count()}")

# Fetch existing pairs to avoid duplicates
existing = set(
    SchoolSubjectCapacity.objects.filter(school_id__gte=21466)
    .values_list('school_id', 'subject_id')
)
print(f"Already existing: {len(existing)}")

subj_ids = {s['pk']: (PRIMARY_IDS if s['level'] == 'Primary' else SECONDARY_IDS)
            for s in schools}

to_create = []
for school_pk, sids in subj_ids.items():
    for sid in sids:
        if (school_pk, sid) not in existing:
            to_create.append(SchoolSubjectCapacity(
                school_id=school_pk,
                subject_id=sid,
                max_students=2,
                current_students=0,
            ))

print(f"Records to insert: {len(to_create)}")
if to_create:
    SchoolSubjectCapacity.objects.bulk_create(to_create, batch_size=500,
                                               ignore_conflicts=True)
    print("Done!")
else:
    print("Nothing to insert.")
