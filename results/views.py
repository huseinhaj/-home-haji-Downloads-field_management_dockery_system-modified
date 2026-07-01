from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

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
    approved_count = 0
    for subject in all_subjects:
        submission = submission_map.get(subject.id)
        is_submitted = submission and submission.status == SubjectSubmission.STATUS_SUBMITTED
        is_approved = submission and submission.status == SubjectSubmission.STATUS_APPROVED
        if is_submitted or is_approved:
            submitted_count += 1
        if is_approved:
            approved_count += 1
        subjects_ctx.append({
            'subject': subject,
            'submission': submission,
            'is_submitted': is_submitted,
            'is_approved': is_approved,
            'speech_url': reverse('speech_entry_page') + f'?exam={exam.id}&subject={subject.id}',
            'upload_url': reverse('subject_upload', args=[exam.id, subject.id]),
            'pdf_url': reverse('subject_pdf', args=[exam.id, subject.id]) if (is_submitted or is_approved) else None,
            'approve_url': reverse('approve_subject', args=[exam.id, subject.id]) if is_submitted else None,
        })

    total_subjects = len(all_subjects)
    all_submitted = submitted_count == total_subjects and total_subjects > 0
    all_approved = approved_count == total_subjects and total_subjects > 0
    enough_to_finalize = submitted_count >= 2 or all_submitted

    progress_pct = round(submitted_count / total_subjects * 100) if total_subjects else 0
    approval_pct = round(approved_count / total_subjects * 100) if total_subjects else 0

    return render(request, 'results/exam_overview.html', {
        'exam': exam,
        'subjects_ctx': subjects_ctx,
        'submitted_count': submitted_count,
        'approved_count': approved_count,
        'total_subjects': total_subjects,
        'all_submitted': all_submitted,
        'all_approved': all_approved,
        'enough_to_finalize': enough_to_finalize,
        'progress_pct': progress_pct,
        'approval_pct': approval_pct,
        'finalize_url': reverse('finalize_exam', args=[exam.id]),
        'approve_all_url': reverse('approve_exam_submissions', args=[exam.id]),
        'excel_url': reverse('export_results_excel', args=[exam.id]),
        'form_results_url': reverse('form_results', args=[exam.form]),
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


# ── Roster Upload ─────────────────────────────────────────────────────────────

def _pick_col(row, col_lower_map, keys):
    for k in keys:
        if k in col_lower_map:
            val = str(row[col_lower_map[k]]).strip()
            return '' if val in ('nan', 'None', '') else val
    return ''


GENDER_TOKENS = {'m', 'me', 'male', 'kiume', 'f', 'fe', 'female', 'kike'}


def _parse_roster_line(line):
    """Parse one text line: 'FirstName MiddleName LastName Gender' → (first, middle, last, gender)."""
    parts = line.split()
    if len(parts) < 2:
        return None

    # Last token is gender if it's a known gender word
    gender = 'M'
    if parts[-1].lower() in GENDER_TOKENS:
        gender = normalize_gender(parts[-1])
        parts = parts[:-1]

    if len(parts) == 1:
        return parts[0].capitalize(), '', 'Unknown', gender
    if len(parts) == 2:
        return parts[0].capitalize(), '', parts[1].capitalize(), gender
    # 3+ parts: first, middle(s), last
    return parts[0].capitalize(), ' '.join(p.capitalize() for p in parts[1:-1]), parts[-1].capitalize(), gender


def _save_student(first, middle, last, gender):
    student, _ = Student.objects.get_or_create(
        first_name=first,
        last_name=last or 'Unknown',
        defaults={'middle_name': middle, 'gender': gender},
    )
    if middle and not student.middle_name:
        student.middle_name = middle
        student.save(update_fields=['middle_name'])
    name_parts = [p for p in [student.first_name, student.middle_name, student.last_name] if p]
    return {'id': student.id, 'name': ' '.join(name_parts)}


def _parse_pdf_roster(uploaded_file):
    """Extract student rows from a PDF roster using pdfplumber."""
    import pdfplumber, re
    students_out = []
    uploaded_file.seek(0)
    raw_bytes = uploaded_file.read()
    import io
    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        for page in pdf.pages:
            # Try table extraction first (structured PDFs)
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        cells = [str(c).strip() for c in row if c and str(c).strip()]
                        if len(cells) < 2:
                            continue
                        # Skip header rows
                        if any(h in ' '.join(cells).lower() for h in ('jina', 'name', 'first', 'gender', 'jinsia', '#', 'no')):
                            continue
                        # Try joining all cells as one line
                        line = ' '.join(cells)
                        parsed = _parse_roster_line(line)
                        if parsed:
                            first, middle, last, gender = parsed
                            if first and first.lower() not in ('nan', 'none', ''):
                                students_out.append(_save_student(first, middle, last, gender))
            else:
                # Plain text extraction — each line is one student
                text = page.extract_text() or ''
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    # Remove leading numbering like "1." "1)" "01."
                    line = re.sub(r'^\d+[.)]\s*', '', line).strip()
                    if not line:
                        continue
                    # Skip obvious header lines
                    if any(h in line.lower() for h in ('jina la', 'first name', 'last name', 'gender', 'jinsia', 'student')):
                        continue
                    parsed = _parse_roster_line(line)
                    if parsed:
                        first, middle, last, gender = parsed
                        if first and first.lower() not in ('nan', 'none', ''):
                            students_out.append(_save_student(first, middle, last, gender))
    return students_out


def _parse_spreadsheet_roster(uploaded_file):
    """Parse CSV or Excel roster with flexible column detection."""
    import pandas as pd
    uploaded_file.seek(0)
    fname = uploaded_file.name.lower()
    df = pd.read_csv(uploaded_file) if fname.endswith('.csv') else pd.read_excel(uploaded_file)
    df.columns = [str(c).strip() for c in df.columns]
    col_lower = {c.lower(): c for c in df.columns}

    students_out = []
    for _, row in df.iterrows():
        first  = _pick_col(row, col_lower, ['first name', 'firstname', 'jina la kwanza'])
        middle = _pick_col(row, col_lower, ['middle name', 'middlename', 'jina la kati', 'jina la pili'])
        last   = _pick_col(row, col_lower, ['last name', 'lastname', 'surname', 'jina la mwisho', 'ukoo'])
        full   = _pick_col(row, col_lower, ['name', 'full name', 'jina kamili', 'majina', 'jina'])

        if not first and full:
            parts = full.split()
            if len(parts) >= 3:
                first  = parts[0].capitalize()
                middle = ' '.join(p.capitalize() for p in parts[1:-1])
                last   = parts[-1].capitalize()
            elif len(parts) == 2:
                first = parts[0].capitalize()
                last  = parts[1].capitalize()
            elif parts:
                first = parts[0].capitalize()

        if not first:
            val = str(row.iloc[0]).strip()
            if val and val not in ('nan', 'None', ''):
                parsed = _parse_roster_line(val)
                if parsed:
                    first, middle, last, _ = parsed

        if not first or first in ('nan', 'None', ''):
            continue

        gender_raw = _pick_col(row, col_lower, ['gender', 'jinsia', 'sex']) or 'M'
        students_out.append(_save_student(
            first.strip().capitalize(),
            (middle or '').strip().capitalize(),
            (last or 'Unknown').strip().capitalize(),
            normalize_gender(gender_raw),
        ))
    return students_out


@require_POST
def upload_roster(request):
    """Accept PDF, CSV, or Excel roster → create/get Student objects → return IDs."""
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({'error': 'Hakuna faili lililotumwa.'}, status=400)
    try:
        fname = uploaded_file.name.lower()
        if fname.endswith('.pdf'):
            students_out = _parse_pdf_roster(uploaded_file)
        else:
            students_out = _parse_spreadsheet_roster(uploaded_file)

        if not students_out:
            return JsonResponse({
                'error': 'Hakuna wanafunzi waliopatikana. Angalia muundo wa faili — kila mstari: Jina la Kwanza Jina la Kati Jina la Mwisho Jinsia'
            }, status=400)

        return JsonResponse({'students': students_out, 'count': len(students_out)})
    except Exception as exc:
        return JsonResponse({'error': f'Hitilafu ya faili: {exc}'}, status=400)


# ── Finalize Exam ─────────────────────────────────────────────────────────────

@require_POST
def finalize_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    recompute_processed_results_for_exam(exam)
    return generate_professional_excel_response(exam)


# ── Academic Dashboard ────────────────────────────────────────────────────────

def academic_dashboard(request):
    """Dashboard for academic officer: see all exams grouped by form, approve submissions."""
    exams = Exam.objects.prefetch_related('subject_submissions__subject').order_by('form', '-year', 'name')

    forms_map = {}
    for exam in exams:
        subs = list(exam.subject_submissions.all())
        total = len(subs)
        submitted = sum(1 for s in subs if s.status in (SubjectSubmission.STATUS_SUBMITTED, SubjectSubmission.STATUS_APPROVED))
        approved = sum(1 for s in subs if s.status == SubjectSubmission.STATUS_APPROVED)
        all_submitted = total > 0 and submitted == total
        all_approved = total > 0 and approved == total
        ready_for_approval = all_submitted and not all_approved
        form_key = exam.form
        if form_key not in forms_map:
            forms_map[form_key] = []
        forms_map[form_key].append({
            'exam': exam,
            'submissions': subs,
            'total': total,
            'submitted': submitted,
            'approved': approved,
            'all_submitted': all_submitted,
            'all_approved': all_approved,
            'ready_for_approval': ready_for_approval,
            'progress_pct': round(submitted / total * 100) if total else 0,
            'approval_pct': round(approved / total * 100) if total else 0,
        })

    forms_list = sorted(forms_map.items())
    return render(request, 'results/academic_dashboard.html', {
        'forms_list': forms_list,
        'total_exams': exams.count(),
    })


# ── Approve Subject Submission ────────────────────────────────────────────────

@require_POST
def approve_subject(request, exam_id, subject_id):
    exam = get_object_or_404(Exam, id=exam_id)
    subject = get_object_or_404(Subject, id=subject_id)
    sub = get_object_or_404(SubjectSubmission, exam=exam, subject=subject)

    if sub.status != SubjectSubmission.STATUS_SUBMITTED:
        messages.error(request, f"{subject.name} haijawa na hali ya Submitted.")
        return redirect(reverse('academic_dashboard'))

    approved_by = request.POST.get('approved_by', '').strip() or 'Academic Officer'
    notes = request.POST.get('notes', '').strip()

    sub.status = SubjectSubmission.STATUS_APPROVED
    sub.approved_by = approved_by
    sub.approved_at = timezone.now()
    sub.approval_notes = notes
    sub.save(update_fields=['status', 'approved_by', 'approved_at', 'approval_notes'])

    messages.success(request, f"Somo la {subject.name} limeidhinishwa.")
    return redirect(reverse('exam_overview', args=[exam.id]))


# ── Bulk Approve All Subjects for an Exam ────────────────────────────────────

@require_POST
def approve_exam_submissions(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    approved_by = request.POST.get('approved_by', '').strip() or 'Academic Officer'
    notes = request.POST.get('notes', '').strip()
    now = timezone.now()

    updated = SubjectSubmission.objects.filter(
        exam=exam, status=SubjectSubmission.STATUS_SUBMITTED
    ).update(
        status=SubjectSubmission.STATUS_APPROVED,
        approved_by=approved_by,
        approved_at=now,
        approval_notes=notes,
    )

    if updated == 0:
        messages.warning(request, "Hakuna masomo yaliyokuwa tayari kwa idhini.")
    else:
        recompute_processed_results_for_exam(exam)
        messages.success(request, f"Masomo {updated} yameidhinishwa. Matokeo yamehesabiwa upya.")

    return redirect(reverse('exam_overview', args=[exam.id]))


# ── Form-Level Results View ───────────────────────────────────────────────────

def form_results(request, form_num):
    """Results for all approved exams of a given form level."""
    exams = Exam.objects.filter(form=form_num).order_by('-year', 'name')

    exams_ctx = []
    for exam in exams:
        subs = exam.subject_submissions.select_related('subject')
        total_subs = subs.count()
        approved_subs = subs.filter(status=SubjectSubmission.STATUS_APPROVED).count()
        processed = exam.processedresult_set.select_related('student').order_by('position')
        exams_ctx.append({
            'exam': exam,
            'total_subs': total_subs,
            'approved_subs': approved_subs,
            'all_approved': total_subs > 0 and approved_subs == total_subs,
            'processed_results': list(processed),
            'excel_url': reverse('export_results_excel', args=[exam.id]),
            'pdf_url': reverse('generate_results_pdf', args=[exam.id]),
            'overview_url': reverse('exam_overview', args=[exam.id]),
        })

    return render(request, 'results/form_results.html', {
        'form_num': form_num,
        'exams_ctx': exams_ctx,
        'form_label': f'Form {form_num}' if form_num <= 4 else f'Form {form_num} (Advanced)',
    })
