"""Futa Student #1824 'Omary Ally Shabani' — nakala ya #2602 'OMARY ALLY SHABAN'
(data yake pekee: History=60 exam #36, sawa kabisa na ya #2602). Idhini ya user 2026-09-23.
Run: python3 manage.py shell < cleanup_isingiro_omary_dup.py
"""
import json
from datetime import datetime
from django.core import serializers
from django.db import transaction
from results.models import Exam, ExamResult, ProcessedResult, Student
from results.services.upload_processing_service import recompute_processed_results_for_exam

DUP, KEEP, EXAM_ID = 1824, 2602, 36
dup_er = list(ExamResult.objects.filter(student_id=DUP))
assert [(e.exam_id, e.subject.name, e.score) for e in dup_er] == [(36, 'History', 60)], dup_er
assert ExamResult.objects.filter(student_id=KEEP, exam_id=36, subject__name='History', score=60).exists()

fname = f"backup_isingiro_omary_dup_{datetime.now():%Y%m%d_%H%M%S}.json"
with open(fname, 'w') as f:
    json.dump({k: json.loads(serializers.serialize('json', v)) for k, v in {
        'student': Student.objects.filter(pk=DUP),
        'exam_results': ExamResult.objects.filter(student_id=DUP),
        'processed_results_exam36_all': ProcessedResult.objects.filter(exam_id=EXAM_ID),
    }.items()}, f, indent=1)
print('BACKUP:', fname)

with transaction.atomic(using='results'):
    Student.objects.filter(pk=DUP).delete()  # CASCADE: ExamResult + ProcessedResult
    recompute_processed_results_for_exam(Exam.objects.get(pk=EXAM_ID))
print('DELETED Student', DUP, '| exists:', Student.objects.filter(pk=DUP).exists())
p = ProcessedResult.objects.get(exam_id=EXAM_ID, student_id=KEEP)
print(f'OMARY #{KEEP} Form 5: position {p.position}, Div {p.division}')
