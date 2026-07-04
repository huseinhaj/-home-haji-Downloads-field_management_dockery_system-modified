from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from django.core.exceptions import ValidationError

from .forms import ExamUploadForm, TeacherSelfSubjectsForm
from .models import Exam, ExamResult, PersonalUpload, PersonalUploadResult, School, SchoolSubject, Student, Subject, SubjectSubmission
from .permissions import academic_required, results_login_required as login_required, teacher_required
from .services.excel_export_service import generate_professional_excel_response, generate_results_excel_response
from .services.pdf_export_service import generate_results_pdf_response
from .services.subject_pdf_service import (
    GRADE_KEYS_ALEVEL,
    GRADE_KEYS_OLEVEL,
    generate_personal_pdf_response,
    generate_subject_pdf_response,
)
from .services.results_analytics import compute_subject_stats, generate_recommendations
from .services.upload_processing_service import (
    UploadProcessingError,
    process_uploaded_results,
    recompute_processed_results_for_exam,
)
from .utils import get_grade, get_grade_for_form, normalize_gender, parse_name_score_sheet, parse_score

_EXAM_TYPE_CHOICES = Exam.EXAM_TYPE_CHOICES

COMMON_SUBJECTS = [
    'Mathematics', 'English', 'Kiswahili', 'Biology', 'Chemistry',
    'Physics', 'History', 'Geography', 'Civics', 'Computer Studies',
    'Agriculture', 'Business Studies', 'CRE', 'IRE', 'Fine Art',
    'Music', 'Physical Education', 'Further Mathematics',
]


@login_required
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


@academic_required
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


@login_required
def filter_exams(request):
    exam_type = request.GET.get('exam_type')
    exams = Exam.objects.all()
    if exam_type:
        exams = exams.filter(exam_type=exam_type)

    options_html = render_to_string('results/exam_options.html', {'exams': exams})
    return HttpResponse(options_html)


@academic_required
def generate_results_pdf(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    return generate_results_pdf_response(exam)


@academic_required
def export_results_excel(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    return generate_results_excel_response(exam)


# ── Exam Overview Dashboard ───────────────────────────────────────────────────

@login_required
def exam_overview(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    is_academic = getattr(request.user, 'is_academic', False)

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
            'approve_url': reverse('approve_subject', args=[exam.id, subject.id]) if (is_submitted and is_academic) else None,
        })

    total_subjects = len(all_subjects)
    all_submitted = submitted_count == total_subjects and total_subjects > 0
    all_approved = approved_count == total_subjects and total_subjects > 0
    # General school results are only ready once every subject for this exam
    # has been submitted by its teacher — partial results would misrepresent
    # each student's overall division/position.
    enough_to_finalize = all_submitted

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
        'is_academic': is_academic,
        'finalize_url': reverse('finalize_exam', args=[exam.id]) if is_academic else None,
        'approve_all_url': reverse('approve_exam_submissions', args=[exam.id]) if is_academic else None,
        'excel_url': reverse('export_results_excel', args=[exam.id]) if is_academic else None,
        'form_results_url': reverse('form_results', args=[exam.form]),
    })


# ── Subject Upload (CSV/Excel for one subject) ────────────────────────────────

@teacher_required
def subject_upload(request, exam_id, subject_id):
    exam = get_object_or_404(Exam, id=exam_id)
    subject = get_object_or_404(Subject, id=subject_id)
    if not request.user.subjects.filter(pk=subject.pk).exists():
        raise PermissionDenied("You are not assigned to teach this subject.")

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

            if saved_count == 0:
                messages.error(
                    request,
                    "Hakuna mwanafunzi aliyesomwa kwenye faili — angalia kama safu za 'First Name', "
                    "'Last Name' na 'Score' zipo na zina data sahihi. Hakuna kilichopakiwa."
                )
                return redirect(request.path)

            # Mark SubjectSubmission as SUBMITTED
            SubjectSubmission.objects.update_or_create(
                exam=exam,
                subject=subject,
                defaults={
                    'status': SubjectSubmission.STATUS_SUBMITTED,
                    'method': 'UPLOAD',
                    'submitted_by': request.user.full_name or request.user.email,
                    'submitted_by_user': request.user,
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

@login_required
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

    lang = request.session.get('ui_lang', 'en')
    return generate_subject_pdf_response(exam, subject, teacher_name=teacher_name, lang=lang)


# ── Subject Results Summary (in-app view: stats + recommendations) ───────────

@login_required
def subject_summary(request, exam_id, subject_id):
    """Same analysis as the PDF (distribution, gender, recommendations) but
    viewable directly in the app — teachers don't have to download anything
    to see how their subject did and what to do next."""
    exam = get_object_or_404(Exam, id=exam_id)
    subject = get_object_or_404(Subject, id=subject_id)

    teacher_name = ''
    try:
        submission = SubjectSubmission.objects.get(exam=exam, subject=subject)
        teacher_name = submission.submitted_by or ''
    except SubjectSubmission.DoesNotExist:
        pass

    results = list(
        ExamResult.objects.filter(exam=exam, subject=subject).select_related('student')
    )
    results.sort(key=lambda r: r.score, reverse=True)

    is_alevel = exam.form in (5, 6)
    rows_data = []
    for pos, result in enumerate(results, 1):
        student = result.student
        full_name = ' '.join(part for part in [student.first_name, student.middle_name, student.last_name] if part)
        rows_data.append({
            'position': pos,
            'name': full_name,
            'score': result.score,
            'grade': get_grade_for_form(result.score, exam.form),
            'gender': student.gender,
        })

    lang = request.session.get('ui_lang', 'en')
    stats = compute_subject_stats(rows_data)
    recommendations = generate_recommendations(stats, subject_name=subject.name, lang=lang)
    grade_keys = GRADE_KEYS_ALEVEL if is_alevel else GRADE_KEYS_OLEVEL
    distribution = _build_distribution(stats, grade_keys)
    teacher_label = 'Mwalimu' if lang == 'sw' else 'Teacher'

    return render(request, 'results/results_summary.html', {
        'heading': subject.name,
        'meta_parts': [p for p in [exam.school_name, str(exam), f"{teacher_label}: {teacher_name}" if teacher_name else ''] if p],
        'rows_data': rows_data,
        'stats': stats,
        'recommendations': recommendations,
        'distribution': distribution,
        'pdf_url': reverse('subject_pdf', args=[exam.id, subject.id]),
        'back_url': reverse('exam_overview', args=[exam.id]),
    })


def _build_distribution(stats, grade_keys):
    total = stats['total'] or 1
    return [
        {
            'grade': g,
            'range': rng,
            'count': stats['grade_counts'].get(g, 0),
            'pct': round(stats['grade_counts'].get(g, 0) / total * 100),
        }
        for g, rng in grade_keys
    ]


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

@academic_required
@require_POST
def finalize_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    subs = exam.subject_submissions.all()
    total = subs.count()
    submitted = subs.filter(
        status__in=[SubjectSubmission.STATUS_SUBMITTED, SubjectSubmission.STATUS_APPROVED]
    ).count()
    if total == 0 or submitted < total:
        messages.error(
            request,
            f"Bado hayajakamilika: masomo {submitted}/{total} yamewasilishwa. "
            "Matokeo ya jumla yanaweza kuzalishwa tu masomo yote yakishawasilishwa."
        )
        return redirect(reverse('exam_overview', args=[exam.id]))
    recompute_processed_results_for_exam(exam)
    return generate_professional_excel_response(exam)


# ── Academic Dashboard ────────────────────────────────────────────────────────

@academic_required
def academic_dashboard(request):
    """Dashboard for academic officer: see all exams grouped by form, approve submissions."""
    exams = Exam.objects.prefetch_related(
        'subject_submissions__subject'
    ).select_related('school').order_by('form', '-year', 'name')

    forms_map = {}
    for exam in exams:
        subs = list(exam.subject_submissions.all())
        total = len(subs)
        submitted = sum(
            1 for s in subs
            if s.status in (SubjectSubmission.STATUS_SUBMITTED, SubjectSubmission.STATUS_APPROVED)
        )
        approved = sum(1 for s in subs if s.status == SubjectSubmission.STATUS_APPROVED)
        all_submitted = total > 0 and submitted == total
        all_approved = total > 0 and approved == total
        ready_for_approval = all_submitted and not all_approved

        # Split subjects by status for clear pending display
        pending_subs = [s for s in subs if s.status == SubjectSubmission.STATUS_PENDING]
        submitted_subs = [s for s in subs if s.status == SubjectSubmission.STATUS_SUBMITTED]
        approved_subs_list = [s for s in subs if s.status == SubjectSubmission.STATUS_APPROVED]
        pending_names = ', '.join(s.subject.name for s in pending_subs)

        form_key = exam.form
        if form_key not in forms_map:
            forms_map[form_key] = []
        forms_map[form_key].append({
            'exam': exam,
            'submissions': subs,
            'pending_subs': pending_subs,
            'submitted_subs': submitted_subs,
            'approved_subs_list': approved_subs_list,
            'pending_names': pending_names,
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

@academic_required
@require_POST
def approve_subject(request, exam_id, subject_id):
    exam = get_object_or_404(Exam, id=exam_id)
    subject = get_object_or_404(Subject, id=subject_id)
    sub = get_object_or_404(SubjectSubmission, exam=exam, subject=subject)

    if sub.status != SubjectSubmission.STATUS_SUBMITTED:
        messages.error(request, f"{subject.name} haijawa na hali ya Submitted.")
        return redirect(reverse('academic_dashboard'))

    approved_by = request.user.full_name or request.user.email
    notes = request.POST.get('notes', '').strip()

    sub.status = SubjectSubmission.STATUS_APPROVED
    sub.approved_by = approved_by
    sub.approved_by_user = request.user
    sub.approved_at = timezone.now()
    sub.approval_notes = notes
    sub.save(update_fields=['status', 'approved_by', 'approved_by_user', 'approved_at', 'approval_notes'])
    recompute_processed_results_for_exam(exam)

    messages.success(request, f"Somo la {subject.name} limeidhinishwa.")
    return redirect(reverse('exam_overview', args=[exam.id]))


# ── Bulk Approve All Subjects for an Exam ────────────────────────────────────

@academic_required
@require_POST
def approve_exam_submissions(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    approved_by = request.user.full_name or request.user.email
    notes = request.POST.get('notes', '').strip()
    now = timezone.now()

    updated = SubjectSubmission.objects.filter(
        exam=exam, status=SubjectSubmission.STATUS_SUBMITTED
    ).update(
        status=SubjectSubmission.STATUS_APPROVED,
        approved_by=approved_by,
        approved_by_user=request.user,
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

@login_required
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
        'excel_url': reverse('form_results_excel', args=[form_num]),
        'is_academic': getattr(request.user, 'is_academic', False),
    })


# ── Form-Level Excel Export ───────────────────────────────────────────────────

@academic_required
def form_results_excel(request, form_num):
    """Single Excel workbook with one sheet per exam for the given form."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    NAVY, GOLD, WHITE, GREY = "1B3A6B", "C9A84C", "FFFFFF", "F2F4F7"

    def _fill(hex_c):
        return PatternFill(start_color=hex_c, end_color=hex_c, fill_type="solid")

    def _border():
        s = Side(style="thin", color="CCCCCC")
        return Border(left=s, right=s, top=s, bottom=s)

    def _score_color(score):
        if score is None:
            return None, None
        if score >= 75: return "C6F4D6", "145A32"
        if score >= 65: return "D5F5E3", "1E8449"
        if score >= 50: return "FFF9C4", "7D6608"
        if score >= 40: return "FDEBD0", "784212"
        return "FADBD8", "922B21"

    exams = Exam.objects.filter(form=form_num).order_by('-year', 'name')
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default empty sheet

    for exam in exams:
        from .services.export_data import get_exam_export_payload
        payload = get_exam_export_payload(exam)
        subjects = payload['subjects']
        results = payload['processed_results']
        score_lookup = payload['score_lookup']

        sheet_title = f"{exam.name[:25]} {exam.year}"[:31]
        ws = wb.create_sheet(title=sheet_title)

        total_cols = 3 + len(subjects) + 4  # POS JINA JINSIA + subjects + JUMLA WASTANI DARAJA POINTI

        # Title
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
        c = ws.cell(row=1, column=1)
        school = exam.school_name or 'SHULE'
        c.value = f"{school.upper()} — {exam.get_exam_type_display().upper()} {exam.year} — FORM {exam.form}"
        c.font = Font(bold=True, size=13, color=WHITE, name='Calibri')
        c.fill = _fill(NAVY)
        c.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 26

        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_cols)
        c2 = ws.cell(row=2, column=1)
        c2.value = exam.name
        c2.font = Font(bold=False, size=10, color=GOLD, name='Calibri')
        c2.fill = _fill(NAVY)
        c2.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[2].height = 16

        # Header row
        headers = ['POS', 'JINA', 'JINSIA'] + [s.name.upper() for s in subjects] + ['JUMLA', 'WASTANI', 'DARAJA', 'POINTI']
        for ci, h in enumerate(headers, 1):
            cell = ws.cell(row=3, column=ci, value=h)
            cell.font = Font(color=WHITE, bold=True, name='Calibri', size=9)
            cell.fill = _fill(NAVY)
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = _border()
        ws.row_dimensions[3].height = 20
        ws.freeze_panes = ws.cell(row=4, column=1)

        # Data rows
        for ri, result in enumerate(results):
            row = 4 + ri
            st = result.student
            name = ' '.join(p for p in [st.first_name, st.middle_name or '', st.last_name] if p)
            row_fill = _fill(GREY) if ri % 2 == 0 else None

            ws.cell(row=row, column=1, value=result.position)
            ws.cell(row=row, column=2, value=name)
            ws.cell(row=row, column=3, value=st.gender)

            for si, subj in enumerate(subjects):
                score = score_lookup.get((st.id, subj.id))
                col = 4 + si
                cell = ws.cell(row=row, column=col)
                if score is not None:
                    cell.value = score
                    bg, fg = _score_color(score)
                    if bg: cell.fill = _fill(bg)
                    if fg: cell.font = Font(bold=True, name='Calibri', size=9, color=fg)
                else:
                    cell.value = '—'

            base = 4 + len(subjects)
            ws.cell(row=row, column=base).value = result.total_score
            ws.cell(row=row, column=base).font = Font(bold=True, name='Calibri', size=9, color=NAVY)
            avg_cell = ws.cell(row=row, column=base + 1, value=float(result.average_score))
            avg_cell.number_format = '0.00'
            ws.cell(row=row, column=base + 2, value=result.division)
            ws.cell(row=row, column=base + 3, value=result.points)

            for ci in range(1, total_cols + 1):
                cell = ws.cell(row=row, column=ci)
                cell.border = _border()
                cell.alignment = Alignment(horizontal='center', vertical='center')
                if row_fill and not cell.fill.fgColor.rgb not in ('00000000', '000000'):
                    if not cell.fill or cell.fill.fill_type == 'none':
                        cell.fill = row_fill
            ws.cell(row=row, column=2).alignment = Alignment(horizontal='left', vertical='center')

        # Summary row
        if results:
            last = 4 + len(results)
            ws.merge_cells(start_row=last, start_column=1, end_row=last, end_column=3)
            sc = ws.cell(row=last, column=1, value=f"Jumla ya Wanafunzi: {len(results)}")
            sc.font = Font(bold=True, name='Calibri', size=9, color=WHITE)
            sc.fill = _fill(NAVY)
            sc.alignment = Alignment(horizontal='left', vertical='center')

        # Auto column widths
        for col in ws.columns:
            max_len = 8
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = min(max_len + 2, 30)
        ws.column_dimensions['B'].width = 28

    if not wb.sheetnames:
        ws = wb.create_sheet("Hakuna Data")
        ws.cell(row=1, column=1, value=f"Hakuna mitihani ya Form {form_num} bado.")

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    label = f'Form_{form_num}'
    response['Content-Disposition'] = f'attachment; filename="Matokeo_{label}.xlsx"'
    wb.save(response)
    return response


# ── School Setup ──────────────────────────────────────────────────────────────

@academic_required
def school_setup(request):
    """GET: list registered schools. POST: register a new school."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        region = request.POST.get('region', '').strip()
        district = request.POST.get('district', '').strip()
        if name and region and district:
            school, created = School.objects.get_or_create(
                name=name,
                defaults={'region': region, 'district': district},
            )
            if created:
                messages.success(request, f"Shule '{school.name}' imesajiliwa.")
            else:
                messages.info(request, f"Shule '{school.name}' tayari ipo.")
            return redirect(reverse('school_subjects', args=[school.id]))
        else:
            messages.error(request, "Tafadhali jaza sehemu zote.")

    schools = School.objects.all().order_by('name')
    return render(request, 'results/school_setup.html', {
        'schools': schools,
        # Pre-fill defaults for Isingiro
        'default_name': 'Isingiro Secondary School',
        'default_region': 'Kagera',
        'default_district': 'Kyerwa',
    })


# ── School Subjects Management ────────────────────────────────────────────────

@academic_required
def school_subjects(request, school_id):
    """Add/remove subjects taught at a school."""
    school = get_object_or_404(School, id=school_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            subject_name = request.POST.get('subject_name', '').strip()
            form_levels = request.POST.get('form_levels', '1,2,3,4').strip()
            if subject_name:
                subject, _ = Subject.objects.get_or_create(name=subject_name)
                ss, created = SchoolSubject.objects.get_or_create(
                    school=school,
                    subject=subject,
                    defaults={'form_levels': form_levels},
                )
                if created:
                    messages.success(request, f"Somo '{subject.name}' limeongezwa.")
                else:
                    messages.info(request, f"Somo '{subject.name}' tayari lipo.")
            else:
                messages.error(request, "Andika jina la somo.")

        elif action == 'remove':
            ss_id = request.POST.get('school_subject_id')
            if ss_id:
                SchoolSubject.objects.filter(id=ss_id, school=school).delete()
                messages.success(request, "Somo limeondolewa.")

        return redirect(reverse('school_subjects', args=[school.id]))

    school_subjects_qs = school.school_subjects.select_related('subject').order_by('subject__name')
    existing_ids = school_subjects_qs.values_list('subject_id', flat=True)
    available_subjects = Subject.objects.exclude(id__in=existing_ids).order_by('name')

    return render(request, 'results/school_subjects.html', {
        'school': school,
        'school_subjects': school_subjects_qs,
        'available_subjects': available_subjects,
        'common_subjects': COMMON_SUBJECTS,
    })


# ── Create Exam for School ────────────────────────────────────────────────────

@academic_required
def create_exam_for_school(request, school_id):
    """Create an Exam linked to a school and auto-create PENDING SubjectSubmissions."""
    school = get_object_or_404(School, id=school_id)

    if request.method == 'POST':
        name = request.POST.get('exam_name', '').strip()
        year = int(request.POST.get('exam_year', timezone.now().year))
        form_level = int(request.POST.get('exam_form', 4))
        exam_type = request.POST.get('exam_type', 'TERMINAL')

        if not name:
            messages.error(request, "Tafadhali weka jina la mtihani.")
            return redirect(request.path)

        exam, created = Exam.objects.get_or_create(
            name=name,
            year=year,
            form=form_level,
            exam_type=exam_type,
            school=school,
            defaults={'school_name': school.name},
        )
        if not created:
            messages.info(request, f"Mtihani '{exam.name}' tayari upo.")
        else:
            # Auto-create PENDING SubjectSubmissions for each school subject
            school_subjs = school.school_subjects.select_related('subject').all()
            for ss in school_subjs:
                SubjectSubmission.objects.get_or_create(
                    exam=exam,
                    subject=ss.subject,
                    defaults={'status': SubjectSubmission.STATUS_PENDING},
                )
            messages.success(
                request,
                f"Mtihani '{exam.name}' umeundwa. Masomo {school_subjs.count()} yanangojea kupakiwa."
            )

        return redirect(reverse('exam_overview', args=[exam.id]))

    school_subjects_qs = school.school_subjects.select_related('subject').order_by('subject__name')
    current_year = timezone.now().year

    return render(request, 'results/create_exam.html', {
        'school': school,
        'school_subjects': school_subjects_qs,
        'exam_type_choices': _EXAM_TYPE_CHOICES,
        'current_year': current_year,
        'year_range': range(current_year - 2, current_year + 3),
    })


# ── Teacher Dashboard ─────────────────────────────────────────────────────────

@teacher_required
def teacher_dashboard(request):
    """Walimu wanaona masomo yao pekee ya kupakia (submission status kwa kila exam)."""
    teacher_subject_ids = set(request.user.subjects.values_list('id', flat=True))

    exams = Exam.objects.prefetch_related(
        'subject_submissions__subject'
    ).order_by('-year', 'form', 'name')

    exams_ctx = []
    for exam in exams:
        subs = [s for s in exam.subject_submissions.all() if s.subject_id in teacher_subject_ids]
        if not subs:
            continue
        pending = [s for s in subs if s.status == SubjectSubmission.STATUS_PENDING]
        submitted = [s for s in subs if s.status == SubjectSubmission.STATUS_SUBMITTED]
        approved = [s for s in subs if s.status == SubjectSubmission.STATUS_APPROVED]
        for s in submitted + approved:
            s.pdf_url = reverse('subject_pdf', args=[exam.id, s.subject_id])
            s.summary_url = reverse('subject_summary', args=[exam.id, s.subject_id])
        exams_ctx.append({
            'exam': exam,
            'pending': pending,
            'submitted': submitted,
            'approved': approved,
            'total': len(subs),
        })

    return render(request, 'results/teacher_dashboard.html', {
        'exams_ctx': exams_ctx,
        'has_subjects': bool(teacher_subject_ids),
    })


# ── Self-Service Subject Selection — teacher picks their own subject(s) ──────

@teacher_required
def select_my_subjects(request):
    """Teacher picks the subject(s) they teach themselves — no academic officer needed."""
    if request.method == 'POST':
        form = TeacherSelfSubjectsForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Masomo yako yamesasishwa.")
            return redirect('teacher_dashboard')
    else:
        form = TeacherSelfSubjectsForm(instance=request.user)

    return render(request, 'results/select_subjects.html', {'form': form})


# ── Personal (Binafsi) Upload — private scratch tool, not part of the official exam ──

@teacher_required
def personal_upload(request):
    """Mwalimu anapakia alama za somo lake mwenyewe na kupata PDF papo hapo.

    Hii haihitaji Mtihani (Exam) uliotengenezwa na Afisa Taaluma, na
    haiathiri matokeo ya jumla ya shule kwa vyovyote vile.
    """
    teacher_subjects = request.user.subjects.all().order_by('name')
    recent_uploads = PersonalUpload.objects.filter(teacher=request.user).select_related('subject')[:10]

    if request.method == 'POST':
        subject_id = request.POST.get('subject_id')
        title = request.POST.get('title', '').strip() or 'Matokeo Binafsi'
        uploaded_file = request.FILES.get('file')

        subject = teacher_subjects.filter(pk=subject_id).first()
        if not subject:
            messages.error(request, "Chagua somo unalofundisha.")
            return redirect('personal_upload')
        if not uploaded_file:
            messages.error(request, "Hakuna faili lililochaguliwa.")
            return redirect('personal_upload')

        try:
            rows = parse_name_score_sheet(uploaded_file)
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('personal_upload')
        except Exception as e:
            messages.error(request, f"Hitilafu ya faili: {e}")
            return redirect('personal_upload')

        if not rows:
            messages.error(request, "Hakuna wanafunzi waliopatikana kwenye faili.")
            return redirect('personal_upload')

        upload = PersonalUpload.objects.create(teacher=request.user, subject=subject, title=title)
        PersonalUploadResult.objects.bulk_create([
            PersonalUploadResult(upload=upload, student_name=name, score=score) for name, score in rows
        ])
        messages.success(request, f"Alama {len(rows)} zimepakiwa. Pakua PDF ya matokeo hapa chini.")
        return redirect('personal_upload')

    return render(request, 'results/personal_upload.html', {
        'teacher_subjects': teacher_subjects,
        'recent_uploads': recent_uploads,
    })


@teacher_required
def personal_upload_pdf(request, upload_id):
    upload = get_object_or_404(PersonalUpload, id=upload_id, teacher=request.user)
    lang = request.session.get('ui_lang', 'en')
    return generate_personal_pdf_response(upload, lang=lang)


@teacher_required
def personal_upload_summary(request, upload_id):
    upload = get_object_or_404(PersonalUpload, id=upload_id, teacher=request.user)
    results = list(upload.results.order_by('-score', 'student_name'))
    rows_data = []
    for pos, result in enumerate(results, 1):
        rows_data.append({
            'position': pos,
            'name': result.student_name,
            'score': result.score,
            'grade': get_grade(result.score),
            'gender': None,
        })

    lang = request.session.get('ui_lang', 'en')
    stats = compute_subject_stats(rows_data)
    recommendations = generate_recommendations(stats, subject_name=upload.subject.name, lang=lang)
    uploader_name = upload.teacher.full_name or upload.teacher.email
    subject_word, teacher_word = ('Somo', 'Mwalimu') if lang == 'sw' else ('Subject', 'Teacher')
    distribution = _build_distribution(stats, GRADE_KEYS_OLEVEL)

    return render(request, 'results/results_summary.html', {
        'heading': upload.title,
        'meta_parts': [f"{subject_word}: {upload.subject.name}", f"{teacher_word}: {uploader_name}", upload.created_at.strftime('%d %b %Y')],
        'rows_data': rows_data,
        'stats': stats,
        'recommendations': recommendations,
        'distribution': distribution,
        'pdf_url': reverse('personal_upload_pdf', args=[upload.id]),
        'back_url': reverse('personal_upload'),
    })
