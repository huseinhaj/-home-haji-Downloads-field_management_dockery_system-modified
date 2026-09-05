"""Merge duplicate 'Historia ya Tanzania na Maadili' Subject rows and
backfill Subject.code for History / Historia ya Tanzania na Maadili.

Why: normalize_subject_name() lowercases before matching SUBJECT_NAME_MAP,
so it's case-insensitive going forward -- but some Subject rows already in
the database were created by an older path that bypassed it entirely, so
case/typo variants of the same real-world subject ended up as separate
Subject rows ("Historia ya Tanzania na Maadili", "Historia ya tanzania na
Maadili", "HISTORIA YA TANZANIA NA MAADILI", "Historian ya Tanzania na
maadili"). Each also had a blank `code`, so both History and Historia
fell back to the same 4-letter name truncation ("HIST") on the results
PDF/Excel, making them indistinguishable.
"""
from django.db import migrations


HISTORIA_CANONICAL = 'Historia ya Tanzania na Maadili'
HISTORIA_VARIANTS = [
    'Historia ya tanzania na Maadili',
    'HISTORIA YA TANZANIA NA MAADILI',
    'Historian ya Tanzania na maadili',
    'Historia ya Tanzania na maadili',
]

SUBJECT_CODES = {
    'History': 'HIST',
    HISTORIA_CANONICAL: 'HIST/M',
}

# (model_name, fk_field_name, other_unique_together_fields_or_None)
# other_unique_together_fields lists the REST of that model's unique
# constraint involving `subject` -- checked before re-pointing so we never
# create a duplicate-key row; a genuine conflict means the canonical
# subject already has an equivalent row, so the variant's row is dropped
# instead of moved.
SINGLE_FK_MODELS = [
    ('SchoolSubject', 'subject', ('school',)),
    ('TeacherFormAssignment', 'subject', ('teacher', 'form')),
    ('ExamResult', 'subject', ('exam', 'student')),
    ('SubjectSubmission', 'subject', ('exam',)),
    ('StoredRoster', 'subject', ('teacher', 'exam')),
    ('SpeechSubmissionSession', 'subject', ('exam',)),
    ('TeachingAssignment', 'subject', ('school', 'form', 'stream')),
    ('PersonalUpload', 'subject', None),
    ('ClassTimetableEntry', 'subject', None),
]

M2M_MODELS = [
    ('FormStudent', 'subjects'),
    ('TeacherAccount', 'subjects'),
]


def _merge_subject(apps, old, new):
    for model_name, fk_field, unique_fields in SINGLE_FK_MODELS:
        Model = apps.get_model('results', model_name)
        for obj in list(Model.objects.filter(**{fk_field: old})):
            if unique_fields:
                conflict_kwargs = {fk_field: new}
                for f in unique_fields:
                    conflict_kwargs[f] = getattr(obj, f)
                if Model.objects.filter(**conflict_kwargs).exists():
                    print(f"  [merge_subject] dropping conflicting {model_name}#{obj.pk} "
                          f"(canonical already has an equivalent row)")
                    obj.delete()
                    continue
            setattr(obj, fk_field, new)
            obj.save(update_fields=[fk_field])

    for model_name, m2m_field in M2M_MODELS:
        Model = apps.get_model('results', model_name)
        for obj in Model.objects.filter(**{m2m_field: old}):
            getattr(obj, m2m_field).remove(old)
            getattr(obj, m2m_field).add(new)


def merge_and_backfill(apps, schema_editor):
    Subject = apps.get_model('results', 'Subject')

    # Only ever act on rows that already exist -- never create a
    # "Historia ya Tanzania na Maadili" Subject for a school that doesn't
    # teach it. Pick whichever existing row is already spelled exactly
    # right as canonical; if none is, promote the oldest row instead of
    # leaving an orphaned, wrongly-cased row behind.
    family_names = [HISTORIA_CANONICAL] + HISTORIA_VARIANTS
    rows = list(Subject.objects.filter(name__in=family_names).order_by('id'))
    if rows:
        canonical = next((r for r in rows if r.name == HISTORIA_CANONICAL), rows[0])
        if canonical.name != HISTORIA_CANONICAL:
            canonical.name = HISTORIA_CANONICAL
            canonical.save(update_fields=['name'])
        for row in rows:
            if row.id == canonical.id:
                continue
            print(f"[0035] merging Subject '{row.name}' (#{row.id}) into "
                  f"'{HISTORIA_CANONICAL}' (#{canonical.id})")
            _merge_subject(apps, row, canonical)
            row.delete()

    for name, code in SUBJECT_CODES.items():
        updated = Subject.objects.filter(name=name).exclude(code=code).update(code=code)
        if updated:
            print(f"[0035] backfilled code={code!r} on {updated} '{name}' row(s)")


def reverse_noop(apps, schema_editor):
    pass  # merging duplicates and backfilling a code isn't meaningfully reversible


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0034_add_subjects_to_form_student'),
    ]

    operations = [
        migrations.RunPython(merge_and_backfill, reverse_noop),
    ]
