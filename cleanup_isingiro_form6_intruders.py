"""Futa wanafunzi 4 wa Form 5 walioingia kimakosa kwenye matokeo ya Form 6
(Isingiro, exam #37 'Midterm 2026' Form 6) — idhini ya user 2026-09-23.

Rosti yao (FormStudent) iko Form 5 tayari; matokeo yao ya Form 5 (exam #36)
HAYAGUSWI. Tunafuta ExamResult + ProcessedResult zao za exam #37 tu, kisha
tunapanga upya nafasi za Form 6. Student #2603 'KENEDY KAKURU ROBERT' ni
nakala yatima (data yake yote ni exam #37 tu; Form 5 yake ni #2606 KENNEDY)
— anafutwa kabisa.

Run: python3 manage.py shell < cleanup_isingiro_form6_intruders.py
"""
import json
from datetime import datetime

from django.core import serializers
from django.db import transaction

from results.models import Exam, ExamResult, ProcessedResult, Student
from results.services.upload_processing_service import recompute_processed_results_for_exam

EXAM_ID = 37
INTRUDERS = {
    2602: 'OMARY ALLY SHABAN',
    2603: 'KENEDY KAKURU ROBERT',
    2604: 'EVANCE ERADIUS CHRISTIAN',
    2605: 'DERICK NGALINDA DISMAS',
}
ORPHAN_STUDENT = 2603

exam = Exam.objects.get(pk=EXAM_ID)
assert exam.form == 6 and exam.school_id == 1, exam
for sid, name in INTRUDERS.items():
    s = Student.objects.get(pk=sid)
    assert f"{s.first_name} {s.middle_name} {s.last_name}".upper() == name, (sid, s)
# orphan lazima asiwe na data nje ya exam #37
assert not ExamResult.objects.filter(student_id=ORPHAN_STUDENT).exclude(exam_id=EXAM_ID).exists()
assert not ProcessedResult.objects.filter(student_id=ORPHAN_STUDENT).exclude(exam_id=EXAM_ID).exists()

ids = list(INTRUDERS)
er = ExamResult.objects.filter(exam_id=EXAM_ID, student_id__in=ids)
pr_all = ProcessedResult.objects.filter(exam_id=EXAM_ID)  # nafasi zote kabla (kwa rollback ya mkono)
fname = f"backup_isingiro_form6_intruders_{datetime.now():%Y%m%d_%H%M%S}.json"
with open(fname, 'w') as f:
    json.dump({
        'exam_results': json.loads(serializers.serialize('json', er)),
        'processed_results_exam37_all': json.loads(serializers.serialize('json', pr_all)),
        'student_orphan': json.loads(serializers.serialize('json', Student.objects.filter(pk=ORPHAN_STUDENT))),
    }, f, indent=1)
print('BACKUP:', fname)

with transaction.atomic(using='results'):
    n_er = er.delete()[0]
    n_pr = ProcessedResult.objects.filter(exam_id=EXAM_ID, student_id__in=ids).delete()[0]
    Student.objects.filter(pk=ORPHAN_STUDENT).delete()
    recompute_processed_results_for_exam(exam)
    left = ProcessedResult.objects.filter(exam_id=EXAM_ID, student_id__in=ids).count()
    assert left == 0, left
print(f'DELETED: ExamResult={n_er}, ProcessedResult={n_pr}, Student #{ORPHAN_STUDENT}')

print('Form 6 top 5 sasa:')
for p in ProcessedResult.objects.filter(exam_id=EXAM_ID, position__isnull=False).order_by('position')[:5]:
    print(f'  {p.position}. {p.student.first_name} {p.student.middle_name} {p.student.last_name} — Div {p.division}')
print('Form 5 (exam 36) bado ina:', ProcessedResult.objects.filter(exam_id=36, student_id__in=[2602, 2604, 2605, 2606]).count(), 'kati ya 4')
