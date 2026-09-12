# Backfill: rosti zote zilizopo kabla ya year-rollover feature zipewe
# mwaka halisi waliosajiliwa, na shule zipate current_academic_year.
#
# Mwaka wa rosti unakadiriwa kutoka kwa mitihani ya shule iliyoandikisha
# matokeo — rosti haikuwa ina mwaka kabla ya feature hii. Mwanafunzi wa
# Form 1 aliyepatikana kwenye mtihani wa 2026 ni wa intake ya 2026.
#
# Constraint ya unique (school, academic_year, form, admission_no) ina
# hatari moja: admission_no za placeholder ('NA-xxxx') zinaweza kurudiwa
# kwenye miteto miwili tofauti ya shule moja. Kabla ya kuweka constraint,
# duplicates hizi zinagawanyiwa miaka mbalimbali (zisizo na migongano);
# ndani ya mwaka mmoja, mpya zinatakiwa ziwe na placeholder tofauti.
from django.db import migrations
from django.db.models import Max


def backfill(apps, schema_editor):
    FormStudent = apps.get_model('results', 'FormStudent')
    School = apps.get_model('results', 'School')
    Exam = apps.get_model('results', 'Exam')

    # 1. Shule: current_academic_year = mwaka mpya zaidi wa mtihani wake
    for school in School.objects.all():
        latest = Exam.objects.filter(school=school).aggregate(m=Max('year'))['m']
        if latest:
            school.current_academic_year = latest
            school.save(update_fields=['current_academic_year'])

    # 2. Rosti: academic_year = mwaka wa mtihani wa mwisho wa shule hiyo
    #    kwa form ileile (fallback: mwaka mpya zaidi wa shule).
    school_years = {
        s.id: (s.current_academic_year or 0)
        for s in School.objects.all()
    }
    form_years = {}
    for exam in Exam.objects.exclude(school=None).values('school_id', 'form').annotate(m=Max('year')):
        form_years[(exam['school_id'], exam['form'])] = exam['m']

    batch = []
    for fs in FormStudent.objects.all():
        year = form_years.get((fs.school_id, fs.form)) or school_years.get(fs.school_id) or 2026
        fs.academic_year = year
        batch.append(fs)
        if len(batch) >= 500:
            FormStudent.objects.bulk_update(batch, ['academic_year'])
            batch = []
    if batch:
        FormStudent.objects.bulk_update(batch, ['academic_year'])


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0040_alter_formstudent_unique_together_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
