from django.db import transaction
from django.db.models import Prefetch

from ..models import ExamResult, ProcessedResult, Student, Subject
from ..utils import (
    extract_subject_columns,
    load_results_dataframe,
    normalize_gender,
    normalize_subject_name,
    parse_score,
)


class UploadProcessingError(Exception):
    pass


@transaction.atomic
def process_uploaded_results(exam, uploaded_file):
    if not uploaded_file:
        raise UploadProcessingError("No file uploaded.")

    uploaded_file.seek(0)
    data_frame = load_results_dataframe(uploaded_file)

    subject_columns = extract_subject_columns(data_frame)
    if not subject_columns:
        raise UploadProcessingError("No subject columns found. Please check your file.")

    subjects_by_column = {}
    for column_name in subject_columns:
        normalized_name = normalize_subject_name(column_name)
        subject, _ = Subject.objects.get_or_create(name=normalized_name)
        subjects_by_column[column_name] = subject

    for _, row in data_frame.iterrows():
        first_name = str(row.get('First Name', '')).strip() or 'Unknown'
        middle_name = str(row.get('Middle Name', '')).strip() if 'Middle Name' in data_frame.columns else ''
        last_name = str(row.get('Last Name', '')).strip() or 'Unknown'

        if not (first_name or middle_name or last_name):
            continue

        student, _ = Student.objects.get_or_create(
            first_name=first_name,
            last_name=last_name,
            defaults={
                'middle_name': middle_name,
                'gender': normalize_gender(row.get('Gender', '')),
            },
        )

        for column_name, subject in subjects_by_column.items():
            score = parse_score(row.get(column_name))
            if score is None:
                continue

            ExamResult.objects.update_or_create(
                exam=exam,
                student=student,
                subject=subject,
                defaults={'score': score},
            )

    recompute_processed_results_for_exam(exam)


def _calculate_division(average):
    if average >= 75.0:
        return 'I'
    if 65.0 <= average < 75.0:
        return 'II'
    if 45.0 <= average < 65.0:
        return 'III'
    if 30.0 <= average < 45.0:
        return 'IV'
    return '0'


def _subject_point(score):
    if score >= 75:
        return 1
    if score >= 65:
        return 2
    if score >= 50:
        return 3
    if score >= 40:
        return 4
    return 5


def recompute_processed_results_for_exam(exam):
    students = Student.objects.filter(examresult__exam=exam).distinct().prefetch_related(
        Prefetch('examresult_set', queryset=ExamResult.objects.filter(exam=exam))
    )

    student_data = []

    for student in students:
        results = list(student.examresult_set.all())
        if not results:
            continue

        total = sum(result.score for result in results)
        count = len(results)
        average = (total / count) if count else 0.0
        points = sum(_subject_point(result.score) for result in results)
        division = _calculate_division(average)

        student_data.append(
            {
                'student': student,
                'total': total,
                'average': average,
                'points': points,
                'division': division,
            }
        )

    student_data.sort(key=lambda item: item['total'], reverse=True)

    for position, data in enumerate(student_data, start=1):
        ProcessedResult.objects.update_or_create(
            exam=exam,
            student=data['student'],
            defaults={
                'total_score': data['total'],
                'average_score': round(data['average'], 2),
                'points': data['points'],
                'division': data['division'],
                'position': position,
            },
        )