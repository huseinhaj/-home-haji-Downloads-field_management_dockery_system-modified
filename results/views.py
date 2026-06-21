from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ExamUploadForm
from .models import Exam, ExamResult, Student, Subject, SubjectSubmission
from .services.excel_export_service import generate_professional_excel_response, generate_results_excel_response
from .services.pdf_export_service import generate_results_pdf_response
from .services.subject_pdf_service import generate_subject_pdf_response
from .services.upload_processing_service import (
    UploadProcessingError,
    process_uploaded_results,
    recompute_processed_results_for_exam,
)
from .utils import normalize_gender, parse_score

_EXAM_TYPE_CHOICES = Exam.EXAM_TYPE_CHOICES

COMMON_SUBJECTS = [
    'Mathematics', 'English', 'Kiswahili', 'Biology', 'Chemistry',
    'Physics', 'History', 'Geography', 'Civics', 'Computer Studies',
    'Agriculture', 'Business Studies', 'CRE', 'IRE', 'Fine Art',
    'Music', 'Physical Education', 'Further Mathematics',
]


def home(request):
    exams = Exam.objects.all().order_by('-year', 'name')

    # Annotate each exam with submission progress
    exams_list = list(exams)
    for exam in exams_list:
        submitted = exam.subject_submissions.filter(status=SubjectSubmission.STATUS_SUBMITTED).count()
        total = exam.subject_submissions.count()
        exam.submitted_count = submitted
        exam.total_submissions = total

    return render(
        request,
        'results/home.html',
        {
            'exams': exams_list,
            'exam_count': len(exams_list),
            'latest_exam': exams_list[0] if exams_list else None,
        },
    )


def upload_results(request):
    exam_created = None
    no_exams = not Exam.objects.exists()

    if request.method == 'POST':
        action = request.POST.get('action', 'upload')

        if action == 'create_exam':
            import json as _json
            name = request.POST.get('exam_name', '').strip()
            year = request.POST.get('exam_year', '2026')
            form_level = request.POST.get('exam_form', '4')
            exam_type = request.POST.get('exam_type_new', 'TERMINAL')
            school_name = request.POST.get('school_name', '').strip()
            subjects_raw = request.POST.get('subjects', '[]')
            try:
                subject_names = [s.strip() for s in _json.loads(subjects_raw) if str(s).strip()]
            except Exception:
                subject_names = []

            if name:
                exam, _ = Exam.objects.get_or_create(
                    name=name, year=int(year), form=int(form_level), exam_type=exam_type,
                    defaults={'school_name': school_name},
                )
                if school_name:
                    exam.school_name = school_name
                    exam.save(update_fields=['school_name'])

                # Create subjects + SubjectSubmission (PENDING) for each
                for sname in subject_names:
                    subject, _ = Subject.objects.get_or_create(name=sname)
                    SubjectSubmission.objects.get_or_create(exam=exam, subject=subject)

                # Redirect to exam overview — main hub for teachers
                return redirect(reverse('exam_overview', args=[exam.id]))

        form = ExamUploadForm(request.POST, request.FILES)
        if form.is_valid():
            exam = form.cleaned_data['exam']
            file = form.cleaned_data['file']
            try:
                process_uploaded_results(exam=exam, uploaded_file=file)
                messages.success(request, f"Matokeo yamepakiwa: {exam.name}")
                download_url = reverse('generate_results_pdf', args=[exam.id])
                return render(request, 'results/upload.html', {
                    'form': ExamUploadForm(),
                    'download_url': download_url,
                    'no_exams': False,
                    'exam_type_choices': _EXAM_TYPE_CHOICES,
                })
            except UploadProcessingError as error:
                messages.error(request, str(error))
                return redirect(request.path)
            except Exception as e:
                messages.error(request, f"Hitilafu: {str(e)}")
                return redirect(request.path)
    else:
        pass

    return render(request, 'results/upload.html', {
        'exam_type_choices': _EXAM_TYPE_CHOICES,
        'common_subjects': COMMON_SUBJECTS,
    })


def filter_exams(request):
    exam_type = request.GET.get('exam_type')
    exams = Exam.objects.all()
    if exam_type:
        exams = exams.filter(exam_type=exam_type)

    options_html = render_to_string('results/exam_options.html', {'exams': exams})
    return HttpResponse(options_html)


def generate_results_pdf(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    return generate_results_pdf_response(exam)


def export_results_excel(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    return generate_results_excel_response(exam)


# ── Exam Overview Dashboard ───────────────────────────────────────────────────

def exam_overview(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)

    # Get all subjects that have results for this exam + known subjects from submissions
    subjects_with_results = list(
        Subject.objects.filter(examresult__exam=exam).distinct().order_by('name')
    )
    # Also include subjects from existing submissions
    submitted_subject_ids = set(
        exam.subject_submissions.values_list('subject_id', flat=True)
    )
    extra_subjects = Subject.objects.filter(id__in=submitted_subject_ids).exclude(
        id__in=[s.id for s in subjects_with_results]
    )
    all_subjects = list(subjects_with_results) + list(extra_subjects)
    all_subjects.sort(key=lambda s: s.name)

    # Build submission map
    submission_map = {
        sub.subject_id: sub
        for sub in exam.subject_submissions.select_related('subject').all()
    }

    # Build per-subject context
    subjects_ctx = []
    submitted_count = 0
    for subject in all_subjects:
        submission = submission_map.get(subject.id)
        is_submitted = submission and submission.status == SubjectSubmission.STATUS_SUBMITTED
        if is_submitted:
            submitted_count += 1
        subjects_ctx.append({
            'subject': subject,
            'submission': submission,
            'is_submitted': is_submitted,
            'speech_url': reverse('speech_entry_page') + f'?exam={exam.id}&subject={subject.id}',
            'upload_url': reverse('subject_upload', args=[exam.id, subject.id]),
            'pdf_url': reverse('subject_pdf', args=[exam.id, subject.id]) if is_submitted else None,
        })

    total_subjects = len(all_subjects)
    all_submitted = submitted_count == total_subjects and total_subjects > 0
    enough_to_finalize = submitted_count >= 2 or all_submitted

    progress_pct = round(submitted_count / total_subjects * 100) if total_subjects else 0

    return render(request, 'results/exam_overview.html', {
        'exam': exam,
        'subjects_ctx': subjects_ctx,
        'submitted_count': submitted_count,
        'total_subjects': total_subjects,
        'all_submitted': all_submitted,
        'enough_to_finalize': enough_to_finalize,
        'progress_pct': progress_pct,
        'finalize_url': reverse('finalize_exam', args=[exam.id]),
        'excel_url': reverse('export_results_excel', args=[exam.id]),
    })


# ── Subject Upload (CSV/Excel for one subject) ────────────────────────────────

def subject_upload(request, exam_id, subject_id):
    exam = get_object_or_404(Exam, id=exam_id)
    subject = get_object_or_404(Subject, id=subject_id)

    if request.method == 'POST':
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            messages.error(request, "Hakuna faili lililochaguliwa.")
            return redirect(request.path)

        try:
            import io
            import pandas as pd

            uploaded_file.seek(0)
            file_name = uploaded_file.name.lower()

            if file_name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)

            # Normalize column names
            df.columns = [str(c).strip() for c in df.columns]

            # Expected columns: First Name, Last Name, Gender, Score
            # Try to find score column flexibly
            score_col = None
            for col in df.columns:
                if col.lower() in ('score', 'alama', 'marks', 'mark', 'result'):
                    score_col = col
                    break
            if score_col is None:
                # Try the last numeric column
                numeric_cols = [c for c in df.columns if pd.to_numeric(df[c], errors='coerce').notna().any()]
                if numeric_cols:
                    score_col = numeric_cols[-1]

            if score_col is None:
                raise UploadProcessingError("Hakuna safu ya alama iliyopatikana. Tumia jina kama 'Score' au 'Alama'.")

            saved_count = 0
            for _, row in df.iterrows():
                first_name = str(row.get('First Name', row.get('first_name', ''))).strip()
                last_name = str(row.get('Last Name', row.get('last_name', ''))).strip()
                gender_raw = str(row.get('Gender', row.get('gender', 'M'))).strip()

                if not first_name or first_name in ('nan', 'None'):
                    continue

                score_val = parse_score(row.get(score_col))
                if score_val is None:
                    continue

                gender = normalize_gender(gender_raw)

                student, _ = Student.objects.get_or_create(
                    first_name=first_name,
                    last_name=last_name or 'Unknown',
                    defaults={'gender': gender},
                )

                ExamResult.objects.update_or_create(
                    exam=exam,
                    student=student,
                    subject=subject,
                    defaults={'score': score_val},
                )
                saved_count += 1

            # Mark SubjectSubmission as SUBMITTED
            SubjectSubmission.objects.update_or_create(
                exam=exam,
                subject=subject,
                defaults={
                    'status': SubjectSubmission.STATUS_SUBMITTED,
                    'method': 'UPLOAD',
                    'submitted_by': request.POST.get('teacher_name', '').strip(),
                    'submitted_at': timezone.now(),
                    'student_count': saved_count,
                },
            )

            # Recompute processed results
            recompute_processed_results_for_exam(exam)

            messages.success(
                request,
                f"Alama za {subject.name} zimepakiwa: wanafunzi {saved_count} wamesajiliwa."
            )
            return redirect(reverse('exam_overview', args=[exam.id]))

        except UploadProcessingError as e:
            messages.error(request, str(e))
            return redirect(request.path)
        except Exception as e:
            messages.error(request, f"Hitilafu ya faili: {e}")
            return redirect(request.path)

    return render(request, 'results/subject_upload.html', {
        'exam': exam,
        'subject': subject,
        'overview_url': reverse('exam_overview', args=[exam.id]),
    })


# ── Subject PDF Download ──────────────────────────────────────────────────────

def subject_pdf(request, exam_id, subject_id):
    exam = get_object_or_404(Exam, id=exam_id)
    subject = get_object_or_404(Subject, id=subject_id)

    # Get teacher name from SubjectSubmission if available
    teacher_name = ''
    try:
        submission = SubjectSubmission.objects.get(exam=exam, subject=subject)
        teacher_name = submission.submitted_by or ''
    except SubjectSubmission.DoesNotExist:
        pass

    return generate_subject_pdf_response(exam, subject, teacher_name=teacher_name)


# ── Finalize Exam ─────────────────────────────────────────────────────────────

@require_POST
def finalize_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)

    # Recompute processed results
    recompute_processed_results_for_exam(exam)

    # Return professional multi-sheet Excel
    return generate_professional_excel_response(exam)
