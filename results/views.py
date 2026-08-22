import os
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from django.core.exceptions import ValidationError

from .forms import ExamUploadForm, TeacherSelfSubjectsForm
from .models import Exam, ExamResult, FormStudent, PersonalUpload, PersonalUploadResult, ProcessedResult, School, SchoolSubject, Student, Subject, SubjectSubmission, TeacherFormAssignment
from .permissions import academic_required, results_login_required as login_required, teacher_required
from .services.excel_export_service import generate_professional_excel_response, generate_results_excel_response
from .services.pdf_export_service import generate_results_pdf_response
from .services.subject_pdf_service import (
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


def _get_exam_or_404(exam_id, user):
    """Safe exam lookup — tolerates NULL school FK and school mismatches.

    1. Find by ID.
    2. If user has a school and exam.school matches → OK.
    3. If exam.school is NULL or mismatched → check teacher owns subjects on this exam.
    4. Otherwise → 404.
    """
    exam = Exam.objects.filter(id=exam_id).first()
    if exam is None:
        raise Http404("Mtihani haujapatikana.")
    user_school = getattr(user, 'school', None)
    # Fast path: schools match
    if user_school and exam.school_id == user_school.id:
        return exam
    # exam.school may be NULL or wrong — check teacher access
    has_access = (
        exam.subject_submissions.filter(
            subject__in=user.subjects.all()
        ).exists()
        or exam.subject_submissions.filter(submitted_by_user=user).exists()
    )
    if has_access:
        return exam
    raise Http404("Mtihani haujapatikana kwenye shule yako.")


COMMON_SUBJECTS = [
    'Mathematics', 'English', 'Kiswahili', 'Biology', 'Chemistry',
    'Physics', 'History', 'Geography', 'Civics', 'Computer Studies',
    'Agriculture', 'Business Studies', 'CRE', 'IRE', 'Fine Art',
    'Music', 'Physical Education', 'Further Mathematics',
]


@login_required
def home(request):
    exams = Exam.objects.filter(school=request.user.school).order_by('-year', 'name')

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
    school = request.user.school
    no_exams = not Exam.objects.filter(school=school).exists()

    if request.method == 'POST':
        action = request.POST.get('action', 'upload')

        if action == 'create_exam':
            import json as _json
            name = request.POST.get('exam_name', '').strip()
            year = request.POST.get('exam_year', '2026')
            form_level = request.POST.get('exam_form', '4')
            stream = request.POST.get('exam_stream', '').strip()
            exam_type = request.POST.get('exam_type_new', 'TERMINAL')
            subjects_raw = request.POST.get('subjects', '[]')
            try:
                subject_names = [s.strip() for s in _json.loads(subjects_raw) if str(s).strip()]
            except Exception:
                subject_names = []

            if name:
                exam, _ = Exam.objects.get_or_create(
                    name=name, year=int(year), form=int(form_level), stream=stream,
                    exam_type=exam_type, school=school,
                    defaults={'school_name': school.name if school else ''},
                )

                # Create subjects + SubjectSubmission (PENDING) for each
                for sname in subject_names:
                    subject, _ = Subject.objects.get_or_create(name=sname)
                    SubjectSubmission.objects.get_or_create(exam=exam, subject=subject)

                # Redirect to exam overview — main hub for teachers
                return redirect(reverse('exam_overview', args=[exam.id]))

        form = ExamUploadForm(request.POST, request.FILES, school=school)
        if form.is_valid():
            exam = form.cleaned_data['exam']
            file = form.cleaned_data['file']
            try:
                process_uploaded_results(exam=exam, uploaded_file=file)
                messages.success(request, f"Matokeo yamepakiwa: {exam.name}")
                download_url = reverse('generate_results_pdf', args=[exam.id])
                return render(request, 'results/upload.html', {
                    'form': ExamUploadForm(school=school),
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
        'form': ExamUploadForm(school=school),
    })


@login_required
def filter_exams(request):
    exam_type = request.GET.get('exam_type')
    exams = Exam.objects.filter(school=request.user.school)
    if exam_type:
        exams = exams.filter(exam_type=exam_type)

    options_html = render_to_string('results/exam_options.html', {'exams': exams})
    return HttpResponse(options_html)


@academic_required
def generate_results_pdf(request, exam_id):
    exam = _get_exam_or_404(exam_id, request.user)
    return generate_results_pdf_response(exam)


@academic_required
def export_results_excel(request, exam_id):
    exam = _get_exam_or_404(exam_id, request.user)
    return generate_results_excel_response(exam)


# ── Public Results Portal — Search Page (NECTA-style, no login required) ───

def public_results_search(request):
    """Public search portal — no login required.
    Parents can search for their child's results by name.
    Like NECTA's online results portal."""
    query = request.GET.get('q', '').strip()
    selected_form = request.GET.get('form', '').strip()
    selected_year = request.GET.get('year', '').strip()

    results = []
    has_searched = bool(query)
    lang = 'sw'  # Default to Swahili for public page

    # Detect language from browser
    accept_lang = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    if 'en' in accept_lang and 'sw' not in accept_lang:
        lang = 'en'

    form_choices = range(1, 7)
    current_year = timezone.now().year
    year_choices = range(current_year, current_year - 5, -1)

    if has_searched:
        # Build query for ProcessedResult, filtering by student name
        from django.db.models import Q

        qs = ProcessedResult.objects.select_related(
            'student', 'exam', 'exam__school'
        ).all()

        # Filter by form
        if selected_form:
            try:
                qs = qs.filter(exam__form=int(selected_form))
            except ValueError:
                pass

        # Filter by year
        if selected_year:
            try:
                qs = qs.filter(exam__year=int(selected_year))
            except ValueError:
                pass

        # Search by name — split query into parts and match across name fields
        name_parts = query.split()
        name_filter = Q()
        for part in name_parts:
            name_filter &= (
                Q(student__first_name__icontains=part) |
                Q(student__middle_name__icontains=part) |
                Q(student__last_name__icontains=part)
            )
        qs = qs.filter(name_filter)

        # Order by exam year descending, then position
        qs = qs.order_by('-exam__year', 'position')

        # Limit to recent results (max 50 to avoid overload)
        qs = qs[:50]

        for r in qs:
            st = r.student
            name = ' '.join(p for p in [st.first_name, st.middle_name or '', st.last_name] if p)
            school_name = r.exam.school_name or (r.exam.school.name if r.exam.school else '')
            results.append({
                'student_name': name,
                'school_name': school_name,
                'exam_type': r.exam.get_exam_type_display(),
                'form': r.exam.form,
                'year': r.exam.year,
                'division': r.division,
                'position': r.position,
                'share_token': str(r.share_token),
            })

    return render(request, 'results/student_results_search.html', {
        'query': query,
        'selected_form': selected_form,
        'selected_year': selected_year,
        'results': results,
        'has_searched': has_searched,
        'form_choices': form_choices,
        'year_choices': year_choices,
        'lang': lang,
    })


# ── Public Results Lookup (NECTA-style, no login required) ───────────────────

def student_result_public(request, token):
    """Public view — no login required. Look up a student's result by share token.
    Returns a clean, professional results page like NECTA's online portal."""
    result = get_object_or_404(ProcessedResult, share_token=token)
    exam = result.exam
    student = result.student

    # Get all subjects and scores for this exam+student
    subjects = list(Subject.objects.filter(examresult__exam=exam).distinct().order_by('name'))
    scores = {
        er.subject_id: er.score
        for er in ExamResult.objects.filter(exam=exam, student=student)
    }

    # Prepare row data for each subject
    subject_rows = []
    for subj in subjects:
        score = scores.get(subj.id)
        if score is not None:
            subject_rows.append({
                'subject': subj.name,
                'score': score,
                'grade': get_grade_for_form(score, exam.form),
            })

    student_name = ' '.join(p for p in [student.first_name, student.middle_name or '', student.last_name] if p)
    location = ''
    if exam.school:
        parts = []
        if exam.school.district:
            parts.append(exam.school.district)
        if exam.school.region:
            parts.append(exam.school.region)
        location = ', '.join(parts)

    division_label = dict(ProcessedResult.DIVISION_CHOICES).get(result.division, result.division)

    from .services.subject_pdf_service import get_grade_keys_for_form
    grade_key = get_grade_keys_for_form(exam.form)

    return render(request, 'results/student_result_public.html', {
        'result': result,
        'exam': exam,
        'student': student,
        'student_name': student_name,
        'subject_rows': subject_rows,
        'division_label': division_label,
        'grade_key': grade_key,
        'location': location,
        'school_name': exam.school_name or (exam.school.name if exam.school else ''),
        'total_students': ProcessedResult.objects.filter(exam=exam).count(),
    })


# ── Shareable Links Management (academic only) ───────────────────────────────

@academic_required
def exam_share_links(request, exam_id):
    """Academic officer views all shareable links for an exam's students.
    Each link can be copied and shared with parents for online results lookup."""
    exam = _get_exam_or_404(exam_id, request.user)
    results = list(
        ProcessedResult.objects.filter(exam=exam)
        .select_related('student')
        .order_by('position')
    )

    # Build the base URL from request
    base_url = f"{request.scheme}://{request.get_host()}"

    students_links = []
    for r in results:
        st = r.student
        name = ' '.join(p for p in [st.first_name, st.middle_name or '', st.last_name] if p)
        full_url = f"{base_url}/shule/matokeo/{r.share_token}/"
        students_links.append({
            'position': r.position,
            'name': name,
            'division': r.division,
            'token': str(r.share_token),
            'full_url': full_url,
        })

    school_name = exam.school_name or (exam.school.name if exam.school else '')
    etype = exam.get_exam_type_display()

    return render(request, 'results/exam_share_links.html', {
        'exam': exam,
        'school_name': school_name,
        'etype': etype,
        'students_links': students_links,
        'total_students': len(students_links),
        'base_url': base_url,
    })


# ── Exam Overview Dashboard ───────────────────────────────────────────────────

@login_required
def exam_overview(request, exam_id):
    exam = _get_exam_or_404(exam_id, request.user)
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
        is_returned = submission and submission.status == SubjectSubmission.STATUS_RETURNED
        if is_submitted or is_approved:
            submitted_count += 1
        if is_approved:
            approved_count += 1
        subjects_ctx.append({
            'subject': subject,
            'submission': submission,
            'is_submitted': is_submitted,
            'is_approved': is_approved,
            'is_returned': is_returned,
            'marks_url': reverse('marks_entry') + f'?exam={exam.id}&subject={subject.id}',
            'upload_url': reverse('subject_upload', args=[exam.id, subject.id]),
            'pdf_url': reverse('subject_pdf', args=[exam.id, subject.id]) if (is_submitted or is_approved) else None,
            'approve_url': reverse('approve_subject', args=[exam.id, subject.id]) if (is_submitted and is_academic) else None,
            'return_url': reverse('return_submission', args=[exam.id, subject.id]) if (is_submitted and is_academic) else None,
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
    exam = _get_exam_or_404(exam_id, request.user)
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

            # ── PDF roster upload (names only — no scores) ──
            if file_name.endswith('.pdf'):
                from .views import _parse_pdf_roster, _save_student
                students_out = _parse_pdf_roster(uploaded_file)
                if not students_out:
                    raise UploadProcessingError(
                        "Hakuna wanafunzi waliopatikana kwenye PDF."
                    )
                # Return to marks_entry with these students pre-loaded
                # Store student IDs in session so marks_entry picks them up
                request.session['pending_roster_ids'] = [s['id'] for s in students_out]
                request.session['pending_roster_subject'] = subject.id
                request.session['pending_roster_exam'] = exam.id
                messages.success(
                    request,
                    f"Orodha ya wanafunzi {len(students_out)} imepakwa. Jaza alama na ubadilishe."
                )
                return redirect(
                    reverse('marks_entry') + f'?exam={exam.id}&subject={subject.id}'
                )

            # ── CSV / Excel upload (names + scores) ──
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

            parsed_rows = []
            for _, row in df.iterrows():
                first_name = str(row.get('First Name', row.get('first_name', ''))).strip()
                last_name = str(row.get('Last Name', row.get('last_name', ''))).strip()
                gender_raw = str(row.get('Gender', row.get('gender', 'M'))).strip()

                if not first_name or first_name in ('nan', 'None'):
                    continue

                score_val = parse_score(row.get(score_col))
                if score_val is None:
                    continue

                parsed_rows.append((first_name, last_name or 'Unknown', normalize_gender(gender_raw), score_val))

            saved_count = 0
            if parsed_rows:
                from django.db.models import Q

                name_pairs = {(fn, ln) for fn, ln, _, _ in parsed_rows}
                name_filter = Q()
                for fn, ln in name_pairs:
                    name_filter |= Q(first_name=fn, last_name=ln)

                student_map = {(s.first_name, s.last_name): s for s in Student.objects.filter(name_filter)}

                new_students = []
                seen = set()
                for fn, ln, gender, _ in parsed_rows:
                    key = (fn, ln)
                    if key not in student_map and key not in seen:
                        seen.add(key)
                        new_students.append(Student(first_name=fn, last_name=ln, gender=gender))
                if new_students:
                    Student.objects.bulk_create(new_students)
                    student_map = {(s.first_name, s.last_name): s for s in Student.objects.filter(name_filter)}

                exam_results = []
                for fn, ln, _, score_val in parsed_rows:
                    student = student_map.get((fn, ln))
                    if not student:
                        continue
                    exam_results.append(ExamResult(exam=exam, student=student, subject=subject, score=score_val))
                    saved_count += 1

                ExamResult.objects.bulk_create(
                    exam_results,
                    update_conflicts=True,
                    unique_fields=['exam', 'student', 'subject'],
                    update_fields=['score'],
                )

            if saved_count == 0:
                messages.error(
                    request,
                    "Hakuna mwanafunzi aliyesomwa kwenye faili — angalia kama safu za 'First Name', "
                    "'Last Name' na 'Score' zipo na zina data sahihi. Hakuna kilichopakiwa."
                )
                return redirect(request.path)

            # Mark SubjectSubmission as SUBMITTED (update_or_create to avoid IntegrityError)
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
                    'revision_number': SubjectSubmission.objects.filter(
                        exam=exam, subject=subject
                    ).values_list('revision_number', flat=True).first() or 1,
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
    exam = _get_exam_or_404(exam_id, request.user)
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
    exam = _get_exam_or_404(exam_id, request.user)
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
    from .services.subject_pdf_service import get_grade_keys_for_form
    grade_keys = get_grade_keys_for_form(exam.form)
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
    """Match a column using substring containment so that
    'Jina la Mwanafunzi' matches the key 'jina', and 'Student Name'
    matches 'name'.  We walk columns in order and return the first hit,
    which is usually what the user intends.
    """
    # 1) Exact match first (most reliable)
    for k in keys:
        if k in col_lower_map:
            val = str(row[col_lower_map[k]]).strip()
            return '' if val in ('nan', 'None', '') else val
    # 2) Substring match — key must appear as a word-boundary fragment
    #    in the column name (e.g. 'jina' matches 'Jina la Mwanafunzi',
    #    but NOT 'firstname').
    for k in keys:
        for col_lower, col_orig in col_lower_map.items():
            if k in col_lower and k not in ('no', 'id',):  # skip short ambiguous keys
                val = str(row[col_orig]).strip()
                return '' if val in ('nan', 'None', '') else val
    return ''


GENDER_TOKENS = {'m', 'me', 'male', 'kiume', 'f', 'fe', 'female', 'kike'}


def _split_concatenated_names(text):
    """Split concatenated CamelCase names — e.g. 'HalimaAllyMohamedF' → 'Halima Ally Mohamed F'.

    Handles the common case where pdfplumber extracts text without spaces.
    Last single-letter token is treated as gender if it matches M/F.
    """
    import re as _re
    # Insert space before each uppercase letter that follows a lowercase letter
    spaced = _re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Also split digits from letters (e.g. 'John2Smith' → 'John 2 Smith')
    spaced = _re.sub(r'([A-Za-z])(\d)', r'\1 \2', spaced)
    spaced = _re.sub(r'(\d)([A-Za-z])', r'\1 \2', spaced)
    return spaced


def _parse_roster_line(line):
    """Parse one text line: 'FirstName MiddleName LastName Gender' → (first, middle, last, gender)."""
    parts = line.split()
    if len(parts) < 2:
        # May be concatenated (no spaces) — try splitting CamelCase
        if len(line) > 3 and not line[0].isupper():
            return None
        if any(c.isupper() for c in line[1:]):
            line = _split_concatenated_names(line)
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


def _parse_pdf_roster(uploaded_file, on_student=_save_student):
    """Extract student rows from a PDF roster using pdfplumber.

    `on_student(first, middle, last, gender)` is called for each row found
    and its return value collected — defaults to _save_student (creates/
    gets a Student, for the per-teacher roster upload), but the Academic's
    form-wide roster upload passes a FormStudent-saving callback instead so
    both uploads share this exact same PDF/CSV parsing logic.
    """
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
                        # Skip header rows — note: 'no' removed (too aggressive;
                        # matches real names like Noel/Norah).
                        if any(h in ' '.join(cells).lower() for h in ('jina la', 'first name', 'last name', 'gender', 'jinsia', 'jinsia ya', '#')):
                            continue
                        # Try joining all cells as one line
                        line = ' '.join(cells)
                        parsed = _parse_roster_line(line)
                        if parsed:
                            first, middle, last, gender = parsed
                            if first and first.lower() not in ('nan', 'none', ''):
                                students_out.append(on_student(first, middle, last, gender))
            else:
                # Plain text extraction — each line is one student.
                # Some PDFs contain CSV text (comma-separated) rather than
                # plain text with spaces.  Detect this by checking whether
                # the first non-empty line contains commas.
                text = page.extract_text() or ''
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                if not lines:
                    continue

                # Detect CSV-style: first line has commas and looks like a header
                first_data_line = re.sub(r'^\d+[.)]\s*', '', lines[0]).strip()
                _is_csv = ',' in first_data_line and len(first_data_line.split(',')) >= 2

                # If CSV, detect which column is which from the header
                _col_map = {}  # role → column index
                if _is_csv:
                    header_cells = [c.strip().lower() for c in lines[0].split(',')]
                    for ci, hc in enumerate(header_cells):
                        if hc in ('firstname', 'first name', 'jina la kwanza'):
                            _col_map.setdefault('first', ci)
                        elif hc in ('middlename', 'middle name', 'jina la kati'):
                            _col_map.setdefault('middle', ci)
                        elif hc in ('lastname', 'last name', 'surname', 'jina la mwisho'):
                            _col_map.setdefault('last', ci)
                        elif hc in ('gender', 'jinsia', 'sex'):
                            _col_map.setdefault('gender', ci)
                        elif hc in ('name', 'full name', 'jina', 'student name', 'jina la mwanafunzi'):
                            _col_map.setdefault('full', ci)
                    # If no explicit columns, treat as: name,gender or name...
                    if not _col_map and len(header_cells) >= 2:
                        # Guess: first non-trivial column = name, last = gender
                        for ci, hc in enumerate(header_cells):
                            if hc and hc not in ('namba', 'no', 'no.', '#', 'id'):
                                _col_map.setdefault('full', ci)
                                break
                    _start_row = 1  # skip header
                else:
                    _start_row = 0

                for line in lines[_start_row:]:
                    # Remove leading numbering like "1." "1)" "01."
                    line = re.sub(r'^\d+[.)]\s*', '', line).strip()
                    if not line:
                        continue
                    # Skip obvious header lines (safety net for CSV-detected data too)
                    if any(h in line.lower() for h in ('jina la', 'first name', 'last name', 'gender', 'jinsia', 'student')):
                        continue

                    if _is_csv:
                        cells = [c.strip() for c in line.split(',')]
                        if len(cells) < 2:
                            continue
                        first = middle = last = ''
                        gender = 'M'
                        if 'first' in _col_map and _col_map['first'] < len(cells):
                            first = cells[_col_map['first']]
                        if 'middle' in _col_map and _col_map['middle'] < len(cells):
                            middle = cells[_col_map['middle']]
                        if 'last' in _col_map and _col_map['last'] < len(cells):
                            last = cells[_col_map['last']]
                        if 'gender' in _col_map and _col_map['gender'] < len(cells):
                            gender = cells[_col_map['gender']]
                        if 'full' in _col_map and _col_map['full'] < len(cells):
                            full_val = cells[_col_map['full']]
                            parts = full_val.split()
                            if not first and len(parts) >= 3:
                                first = parts[0]
                                middle = ' '.join(parts[1:-1])
                                last = parts[-1]
                            elif not first and len(parts) == 2:
                                first = parts[0]
                                last = parts[1]
                            elif not first and parts:
                                first = parts[0]
                        if not first and cells:
                            # Last resort: first non-empty cell
                            for c in cells:
                                if c and c.lower() not in ('nan', 'none', ''):
                                    parsed = _parse_roster_line(c)
                                    if parsed:
                                        first, middle, last, gender = parsed
                                        break
                    else:
                        parsed = _parse_roster_line(line)
                        if not parsed:
                            continue
                        first, middle, last, gender = parsed

                    if first and first.lower() not in ('nan', 'none', ''):
                        students_out.append(on_student(
                            first.strip(), (middle or '').strip(), last.strip() or 'Unknown',
                            normalize_gender(gender)
                        ))
    return students_out


def _parse_spreadsheet_roster(uploaded_file, on_student=_save_student):
    """Parse CSV or Excel roster with flexible column detection.

    See _parse_pdf_roster for what `on_student` is for.
    """
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
        full   = _pick_col(row, col_lower, [
            'name', 'full name', 'jina kamili', 'majina', 'jina',
            'student name', 'jina la mwanafunzi', 'jina kamili la mwanafunzi',
        ])

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

        # Last-resort fallback: walk columns left-to-right looking for
        # any non-numeric text value that contains at least 2 words.
        # This catches spreadsheets where the name column has a header
        # the detection above doesn't know about (e.g. 'Majina', 'Full',
        # 'Mwanafunzi').
        if not first:
            _SKIP_COLS = {'namba', 'no.', 'no', '#', 'id', 's/n', 'sirina', 'register', 'reg no'}
            for ci in range(len(df.columns)):
                cname = df.columns[ci].strip().lower()
                if cname in _SKIP_COLS:
                    continue
                val = str(row.iloc[ci]).strip()
                if val in ('nan', 'None', '', '0'):
                    continue
                parsed = _parse_roster_line(val)
                if parsed:
                    first, middle, last, _ = parsed
                    break

        if not first or first in ('nan', 'None', ''):
            continue

        gender_raw = _pick_col(row, col_lower, ['gender', 'jinsia', 'sex', 'jinsia ya mwanafunzi']) or 'M'
        students_out.append(on_student(
            first.strip().capitalize(),
            (middle or '').strip().capitalize(),
            (last or 'Unknown').strip().capitalize(),
            normalize_gender(gender_raw),
        ))
    return students_out


@login_required
@require_POST
def upload_roster(request):
    """Accept PDF, CSV, or Excel roster → create/get Student objects → return IDs.

    When exam_id + subject_id are passed, the roster is saved to StoredRoster
    so the teacher can reload it later from the dashboard.
    """
    from .models import StoredRoster
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
                'error': 'Hakuna wanafunzi waliopatikana. Muundo unaoeleweka: (a) PDF/CSV ya maneno kwa mstari: Halima Ally Mohamed F \n (b) CSV/Excel zenye column: First Name, Middle Name, Last Name, Gender \n (c) CSV/Excel yenye column moja ya jina kamili: Name, Gender'
            }, status=400)

        # Optionally persist roster for later access
        exam_id = request.POST.get('exam_id')
        subject_id = request.POST.get('subject_id')
        if exam_id and subject_id:
            try:
                exam = Exam.objects.filter(id=exam_id).first()
                subject = Subject.objects.filter(id=subject_id).first()
                if exam and subject:
                    StoredRoster.objects.update_or_create(
                        teacher=request.user,
                        exam=exam,
                        subject=subject,
                        defaults={
                            'students': students_out,
                            'student_count': len(students_out),
                            'source_file': uploaded_file.name,
                            'source_format': 'pdf' if fname.endswith('.pdf') else 'csv',
                        },
                    )
            except Exception:
                pass  # roster save is best-effort

        return JsonResponse({'students': students_out, 'count': len(students_out)})
    except Exception as exc:
        return JsonResponse({'error': f'Hitilafu ya faili: {exc}'}, status=400)


@login_required
def download_roster_template(request):
    """Download a ready-to-fill class list template (CSV or PDF)."""
    fmt = request.GET.get('fmt', 'csv').lower()

    # ── CSV template ──
    if fmt == 'csv':
        import csv, io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['First Name', 'Middle Name', 'Last Name', 'Gender'])
        w.writerow(['Halima', 'Ally', 'Mohamed', 'F'])
        w.writerow(['Juma', 'Said', 'Hassan', 'M'])
        w.writerow(['Aisha', '', 'Khamis', 'F'])
        w.writerow(['', '', '', ''])  # empty row for teacher to start
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="Orodha_Ya_Wanafunzi.csv"'
        return response

    # ── PDF template ──
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    import io as _io

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('T', parent=styles['Title'], fontSize=16, spaceAfter=6,
                                  textColor=colors.HexColor('#1F7A3D'))
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=10, spaceAfter=10,
                                textColor=colors.HexColor('#333333'))
    hint_style = ParagraphStyle('Hint', parent=styles['Normal'], fontSize=9, spaceAfter=4,
                                 textColor=colors.HexColor('#555555'))
    field_style = ParagraphStyle('Field', parent=styles['Normal'], fontSize=10, spaceAfter=8)

    GREEN = colors.HexColor('#1F7A3D')
    GOLD = colors.HexColor('#D9A441')
    GREY = colors.HexColor('#F2F4F7')

    elements = []
    elements.append(Paragraph('ORODHA YA WANAFUNZI — CLASS LIST', title_style))
    elements.append(Paragraph('Pakua, jaza kwa mkono au kompyuta, kisha piga picha / scan na upakie kwenye mfumo.', sub_style))
    elements.append(Spacer(1, 4*mm))

    # School / class / year fields
    _field = [
        ['Shule / School:', '____________________________', 'Mwaka / Year:', '________'],
        ['Darasa / Class:',  '____________________________', 'Somo / Subject:', '________'],
        ['Mwalimu / Teacher:', '__________________________', '', ''],
    ]
    ft = Table(_field, colWidths=[3.2*cm, 7*cm, 3.2*cm, 3.5*cm])
    ft.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(ft)
    elements.append(Spacer(1, 6*mm))

    # Instructions
    elements.append(Paragraph('<b>Maelekezo / Instructions:</b>', hint_style))
    elements.append(Paragraph("\u2022 Andika jina la kila mwanafunzi kwenye mstari wake / Write each student\u2019s name on their own row.", hint_style))
    elements.append(Paragraph('• Jinsia: F = Mwanamke (Female), M = Mwanaume (Male).', hint_style))
    elements.append(Paragraph('• Jina la Kati (Middle Name) — kama hakuna, acha tupu / leave blank.', hint_style))
    elements.append(Paragraph('• Fomu hii inatumika kwa PDF, Excel, au CSV / Use this form for PDF, Excel, or CSV uploads.', hint_style))
    elements.append(Spacer(1, 6*mm))

    # Student table
    hdr = ['#', 'Jina la Kwanza / First Name', 'Jina la Kati / Middle Name', 'Jina la Mwisho / Last Name', 'Jinsia / Gender']
    rows = [hdr]
    examples = [
        ['1', 'Halima', 'Ally', 'Mohamed', 'F'],
        ['2', 'Juma', 'Said', 'Hassan', 'M'],
        ['3', 'Aisha', '', 'Khamis', 'F'],
    ]
    for ex in examples:
        rows.append(ex)
    # 17 empty rows for teachers to fill
    for i in range(4, 21):
        rows.append([str(i), '', '', '', ''])

    t = Table(rows, colWidths=[1.2*cm, 3.8*cm, 3.8*cm, 3.8*cm, 2*cm])
    t.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), GREEN),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Body
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (-1, 1), (-1, -1), 'CENTER'),
        # Example rows — light green background
        ('BACKGROUND', (0, 1), (-1, 3), colors.HexColor('#E8F5E9')),
        # Alternating rows
        *[('BACKGROUND', (0, i), (-1, i), GREY) for i in range(4, 21, 2)],
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('BOX', (0, 0), (-1, -1), 1.2, GREEN),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)

    doc.build(elements)
    response = HttpResponse(buf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Orodha_Ya_Wanafunzi.pdf"'
    return response


# ── Finalize Exam ─────────────────────────────────────────────────────────────

@academic_required
@require_POST
def finalize_exam(request, exam_id):
    exam = _get_exam_or_404(exam_id, request.user)
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
    """Dashboard for academic officer: exams grouped by Form → Stream.

    Shows Form I A, B, C, … then Form II A, B, C, … etc.  Clicking on a
    form level in the sidebar shows all exams / submissions across streams.
    """
    exams = Exam.objects.filter(school=request.user.school).prefetch_related(
        'subject_submissions__subject'
    ).select_related('school').order_by('form', 'stream', '-year', 'name')

    # Nested: { form_num: { stream: [exam_ctx, …], … }, … }
    forms_map = {}       # form_num → { stream_str: [exam_ctx] }
    form_totals = {}     # form_num → { submitted, approved, total }

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

        pending_subs = [s for s in subs if s.status == SubjectSubmission.STATUS_PENDING]
        submitted_subs = [s for s in subs if s.status == SubjectSubmission.STATUS_SUBMITTED]
        approved_subs_list = [s for s in subs if s.status == SubjectSubmission.STATUS_APPROVED]
        returned_subs = [s for s in subs if s.status == SubjectSubmission.STATUS_RETURNED]
        pending_names = ', '.join(s.subject.name for s in pending_subs)

        form_key = exam.form
        stream_key = exam.stream or ''
        if form_key not in forms_map:
            forms_map[form_key] = {}
        if stream_key not in forms_map[form_key]:
            forms_map[form_key][stream_key] = []

        exam_ctx = {
            'exam': exam,
            'submissions': subs,
            'pending_subs': pending_subs,
            'submitted_subs': submitted_subs,
            'approved_subs_list': approved_subs_list,
            'returned_subs': returned_subs,
            'pending_names': pending_names,
            'total': total,
            'submitted': submitted,
            'approved': approved,
            'all_submitted': all_submitted,
            'all_approved': all_approved,
            'ready_for_approval': ready_for_approval,
            'progress_pct': round(submitted / total * 100) if total else 0,
            'approval_pct': round(approved / total * 100) if total else 0,
        }
        forms_map[form_key][stream_key].append(exam_ctx)

        # Accumulate form-level totals
        ft = form_totals.setdefault(form_key, {'submitted': 0, 'approved': 0, 'total': 0})
        ft['submitted'] += submitted
        ft['approved'] += approved
        ft['total'] += total

    # Build sorted structure for template: [(form_num, { stream: [exams] })]
    FORM_LABELS = Exam.FORM_LABELS
    forms_list = []
    for form_num in sorted(forms_map.keys()):
        streams = forms_map[form_num]
        form_label = FORM_LABELS.get(form_num, f'Form {form_num}')
        ft = form_totals.get(form_num, {'submitted': 0, 'approved': 0, 'total': 0})
        forms_list.append({
            'form_num': form_num,
            'form_label': form_label,
            'streams': streams,
            'total_submitted': ft['submitted'],
            'total_approved': ft['approved'],
            'total_all': ft['total'],
        })

    return render(request, 'results/academic_dashboard.html', {
        'forms_list': forms_list,
        'total_exams': exams.count(),
    })


# ── Approve Subject Submission ────────────────────────────────────────────────

@academic_required
@require_POST
def approve_subject(request, exam_id, subject_id):
    exam = _get_exam_or_404(exam_id, request.user)
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


# ── Return Submission to Teacher ─────────────────────────────────────────────

@academic_required
@require_POST
def return_submission(request, exam_id, subject_id):
    """Mtaaluma anarudisha submission kwa mwalimu kwa ukarabati.

    Mtaaluma anaandika comment (return_notes) inayoonekana na mwalimu.
    Submission hubadilisha status kuwa RETURNED — mwalimu atarekebisha
    na kuwasilisha upya, na submission ya zamani itatolewa.
    """
    exam = _get_exam_or_404(exam_id, request.user)
    subject = get_object_or_404(Subject, id=subject_id)
    sub = get_object_or_404(SubjectSubmission, exam=exam, subject=subject)

    if sub.status not in (SubjectSubmission.STATUS_SUBMITTED,):
        messages.error(request, f"{subject.name} haiwezi kurudishwa (hali: {sub.get_status_display()}).")
        return redirect(reverse('academic_dashboard'))

    notes = request.POST.get('return_notes', '').strip()
    if not notes:
        messages.error(request, "Andika sababu ya kurudisha submission hii.")
        return redirect(reverse('exam_overview', args=[exam.id]))

    sub.status = SubjectSubmission.STATUS_RETURNED
    sub.return_notes = notes
    sub.returned_at = timezone.now()
    sub.returned_by = request.user.full_name or request.user.email
    sub.returned_by_user = request.user
    sub.save(update_fields=[
        'status', 'return_notes', 'returned_at', 'returned_by', 'returned_by_user',
    ])

    messages.warning(
        request,
        f"Somo la {subject.name} limerudishwa kwa mwalimu ({sub.submitted_by}) kwa ukarabati."
    )
    return redirect(reverse('exam_overview', args=[exam.id]))


# ── Bulk Approve All Subjects for an Exam ────────────────────────────────────

@academic_required
@require_POST
def approve_exam_submissions(request, exam_id):
    exam = _get_exam_or_404(exam_id, request.user)
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
    exams = Exam.objects.filter(form=form_num, school=request.user.school).order_by('-year', 'name')

    exams_ctx = []
    for exam in exams:
        subs = exam.subject_submissions.select_related('subject')
        total_subs = subs.count()
        approved_subs = subs.filter(status=SubjectSubmission.STATUS_APPROVED).count()
        processed = exam.processedresult_set.select_related('student').order_by('position')

        # NECTA-style per-subject grades for this exam
        from .services.export_data import get_exam_export_payload
        payload = get_exam_export_payload(exam)
        exam_subjects = payload['subjects']
        score_lookup = payload['score_lookup']
        grade_lookup = {}
        for (sid, subj_id), score in score_lookup.items():
            grade_lookup.setdefault(sid, {})[subj_id] = get_grade_for_form(score, exam.form)
        from .services.subject_pdf_service import get_grade_keys_for_form
        grade_key = get_grade_keys_for_form(exam.form)

        exams_ctx.append({
            'exam': exam,
            'total_subs': total_subs,
            'approved_subs': approved_subs,
            'all_approved': total_subs > 0 and approved_subs == total_subs,
            'processed_results': list(processed),
            'subjects': exam_subjects,
            'grade_lookup': grade_lookup,
            'grade_key': grade_key,
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

    NAVY, GOLD, WHITE, GREY = "FF1F7A3D", "FFD9A441", "FFFFFFFF", "FFF2F4F7"

    def _fill(hex_c):
        return PatternFill(start_color=hex_c, end_color=hex_c, fill_type="solid")

    def _border():
        s = Side(style="thin", color="CCCCCC")
        return Border(left=s, right=s, top=s, bottom=s)

    def _score_color(score):
        if score is None:
            return None, None
        if score >= 75: return "FFC6F4D6", "FF145A32"   # A
        if score >= 65: return "FFD5F5E3", "FF1E8449"   # B+
        if score >= 55: return "FFD5F5E3", "FF2D7D46"   # B
        if score >= 45: return "FFFFF9C4", "FF7D6608"   # C+
        if score >= 35: return "FFFFF9C4", "FF8A6F00"   # C
        if score >= 25: return "FFFDEBD0", "FF784212"   # D
        return "FFFADBD8", "FF922B21"                   # F

    exams = Exam.objects.filter(form=form_num, school=request.user.school).order_by('-year', 'name')
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


# ── My School ─────────────────────────────────────────────────────────────────
# Schools themselves are registered by the site's system administrator via
# Django admin (each with its first Academic account). An academic officer
# only ever sees and manages their own school — they can no longer browse or
# create other schools from here.

@academic_required
def school_setup(request):
    """Read-only info about the academic officer's own school."""
    school = request.user.school
    if not school:
        messages.error(
            request,
            "Akaunti yako haijapangiwa shule. Wasiliana na msimamizi wa mfumo (system admin)."
        )
    return render(request, 'results/school_setup.html', {'school': school})


# ── School Subjects Management ────────────────────────────────────────────────

@academic_required
def school_subjects(request):
    """Add/remove subjects taught at the academic officer's own school."""
    school = request.user.school
    if not school:
        messages.error(request, "Akaunti yako haijapangiwa shule. Wasiliana na msimamizi wa mfumo.")
        return redirect(reverse('home'))

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

        return redirect(reverse('school_subjects'))

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
def create_exam_for_school(request):
    """Create an Exam for the academic officer's own school and auto-create
    PENDING SubjectSubmissions for every subject the school teaches."""
    school = request.user.school
    if not school:
        messages.error(request, "Akaunti yako haijapangiwa shule. Wasiliana na msimamizi wa mfumo.")
        return redirect(reverse('home'))

    if request.method == 'POST':
        name = request.POST.get('exam_name', '').strip()
        year = int(request.POST.get('exam_year', timezone.now().year))
        form_level = int(request.POST.get('exam_form', 4))
        stream = request.POST.get('exam_stream', '').strip()
        exam_type = request.POST.get('exam_type', 'TERMINAL')

        if not name:
            messages.error(request, "Tafadhali weka jina la mtihani.")
            return redirect(request.path)

        exam, created = Exam.objects.get_or_create(
            name=name,
            year=year,
            form=form_level,
            stream=stream,
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
    """Walimu wanaona masomo yao pekee ya kupakia (submission status kwa kila exam).
    Pia onyesha orodha zilizohifadhiwa (stored rosters) kwa urahisi wa kujaza alama."""
    from .models import StoredRoster
    teacher_subject_ids = set(request.user.subjects.values_list('id', flat=True))

    exams = Exam.objects.filter(school=request.user.school).prefetch_related(
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
        returned = [s for s in subs if s.status == SubjectSubmission.STATUS_RETURNED]
        for s in submitted + approved:
            s.pdf_url = reverse('subject_pdf', args=[exam.id, s.subject_id])
            s.summary_url = reverse('subject_summary', args=[exam.id, s.subject_id])
        for s in returned:
            s.marks_url = reverse('marks_entry') + f'?exam={exam.id}&subject={s.subject_id}'
        # Attach stored roster info for pending subjects
        for s in pending:
            roster = StoredRoster.objects.filter(
                teacher=request.user, exam=exam, subject=s.subject
            ).first()
            s.has_roster = roster is not None
            s.roster_count = roster.student_count if roster else 0
            s.marks_url = reverse('marks_entry') + f'?exam={exam.id}&subject={s.subject_id}'
        exams_ctx.append({
            'exam': exam,
            'pending': pending,
            'submitted': submitted,
            'approved': approved,
            'returned': returned,
            'total': len(subs),
        })

    # Stored rosters summary
    stored_rosters = StoredRoster.objects.filter(
        teacher=request.user
    ).select_related('exam', 'subject').order_by('-created_at')[:20]

    return render(request, 'results/teacher_dashboard.html', {
        'exams_ctx': exams_ctx,
        'has_subjects': bool(teacher_subject_ids),
        'stored_rosters': stored_rosters,
    })


# ── Self-Service Subject Selection — teacher picks their own subject(s) ──────

@login_required
def select_my_subjects(request):
    """Pick the subject(s) you teach yourself — no one else needs to assign
    them. Open to both roles: academic officers often teach a subject too,
    on top of their admin duties."""
    if request.method == 'POST':
        form = TeacherSelfSubjectsForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Masomo yako yamesasishwa.")
            return redirect('academic_dashboard' if request.user.is_academic else 'teacher_dashboard')
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
        # Jina la tathmini linachaguliwa kwenye dropdown (aina za mtihani)
        # badala ya kuandikwa — default ni 'OTHER' ikiwa hakuna kilichochaguliwa.
        title_choice = request.POST.get('title', '').strip()
        title_label = dict(Exam.EXAM_TYPE_CHOICES).get(title_choice, '')
        title = title_label or title_choice or 'Matokeo Binafsi'
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
        'exam_type_choices': Exam.EXAM_TYPE_CHOICES,
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


# ── Logo Upload ──────────────────────────────────────────────────────────────

@academic_required
def upload_logos(request):
    """Upload school and district logos for the PDF report header."""
    school = request.user.school
    if not school:
        messages.error(request, "Hakuna shule iliyowekwa. Weka shule kwanza.")
        return redirect('home')

    if request.method == 'POST':
        logo_type = request.POST.get('logo_type', '')
        uploaded_file = request.FILES.get('logo_file')

        if not uploaded_file:
            messages.error(request, "Hakuna faili lililochaguliwa.")
            return redirect('upload_logos')

        # Validate file type — SVG is deliberately NOT accepted: the PDF
        # renderer (ReportLab's ImageReader, backed by Pillow) cannot
        # decode SVG at all. It used to be listed as "supported" here but
        # every SVG upload silently failed to ever appear in the PDF, with
        # no error anywhere, because the drawing code swallows the
        # resulting exception. PNG/JPG only, so what's accepted here is
        # guaranteed to actually be drawable.
        allowed_types = ['image/png', 'image/jpeg', 'image/jpg']
        if uploaded_file.content_type not in allowed_types:
            messages.error(request, "Aina ya faili haitambuliki. Tumia PNG au JPG (SVG haiwezi kuonyeshwa kwenye PDF).")
            return redirect('upload_logos')

        # Validate file size (max 2MB)
        if uploaded_file.size > 2 * 1024 * 1024:
            messages.error(request, "Faili ni kubwa sana. Kiwango ni 2MB.")
            return redirect('upload_logos')

        # Verify the bytes are actually a decodable image — a spoofed or
        # corrupt content_type would otherwise pass the check above and
        # then silently fail to render in the PDF with no error at all.
        import io as _io
        from PIL import Image as _PILImage
        file_data = uploaded_file.read()
        try:
            _PILImage.open(_io.BytesIO(file_data)).verify()
        except Exception:
            messages.error(request, "Faili hii si picha inayosomeka. Jaribu picha nyingine ya PNG/JPG.")
            return redirect('upload_logos')

        # Save to School model — both ImageField AND base64 in DB
        # (base64 persists on Railway where filesystem is ephemeral)
        import base64 as _b64
        ext = Path(uploaded_file.name).suffix.lower()
        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif'}
        mime = mime_map.get(ext, 'image/png')
        b64_str = f'data:{mime};base64,{_b64.b64encode(file_data).decode("ascii")}'
        uploaded_file.seek(0)  # reset for ImageField save

        if logo_type == 'school':
            school.school_logo = uploaded_file
            school.school_logo_b64 = b64_str
            school.save(update_fields=['school_logo', 'school_logo_b64'])
            logo_name = "ya Shule"
        elif logo_type == 'district':
            school.district_logo = uploaded_file
            school.district_logo_b64 = b64_str
            school.save(update_fields=['district_logo', 'district_logo_b64'])
            logo_name = "ya Halmashauri"
        elif logo_type == 'coa':
            school.coat_of_arms = uploaded_file
            school.coat_of_arms_b64 = b64_str
            school.save(update_fields=['coat_of_arms', 'coat_of_arms_b64'])
            logo_name = "ya Coat of Arms"
        else:
            messages.error(request, "Aina ya logo haijulikani.")
            return redirect('upload_logos')

        messages.success(request, f"Logo {logo_name} imehifadhiwa! Itaonekana kwenye PDF ya matokeo.")
        return redirect('upload_logos')

    return render(request, 'results/upload_logos.html', {
        'school_logo_exists': bool(school.school_logo_b64 or school.school_logo) if school else False,
        'district_logo_exists': bool(school.district_logo_b64 or school.district_logo) if school else False,
        'coa_exists': bool(school.coat_of_arms_b64 or school.coat_of_arms) if school else False,
        'school_logo_url': school.school_logo.url if school and school.school_logo else '',
        'district_logo_url': school.district_logo.url if school and school.district_logo else '',
        'coa_url': school.coat_of_arms.url if school and school.coat_of_arms else '',
    })


# ══════════════════════════════════════════════════════════════════════════════
# FORM STUDENT LIST — Upload + Teacher Dashboard
# ══════════════════════════════════════════════════════════════════════════════

@academic_required
def upload_form_students(request):
    """Academic Officer uploads orodha ya wanafunzi kwa form fulani.

    Same file formats as the per-teacher roster upload (upload_roster):
    PDF (one full name + gender per line, e.g. "Halima Ally Mohamed F"),
    or CSV/Excel with columns First Name | Middle Name | Last Name |
    Gender — parsed by the exact same _parse_pdf_roster/
    _parse_spreadsheet_roster used there, just pointed at a FormStudent-
    saving callback instead of Student, so both uploads accept identically
    formatted files.
    """
    school = request.user.school
    if not school:
        messages.error(request, "Hakuna shule iliyowekwa.")
        return redirect('home')

    form_num = request.GET.get('form') or request.POST.get('form') or ''
    selected_form = int(form_num) if form_num.isdigit() and int(form_num) in (1,2,3,4,5,6) else None

    if request.method == 'POST' and selected_form:
        uploaded_file = request.FILES.get('student_file')
        if not uploaded_file:
            messages.error(request, "Chagua faili la orodha ya wanafunzi.")
            return redirect(f'{reverse("upload_form_students")}?form={selected_form}')

        import uuid
        ext = Path(uploaded_file.name).suffix.lower()

        # FormStudent has no free-text admission number in this bare
        # "Name Gender" format — synthesize a unique one so rows never
        # collide on the (school, form, admission_no) constraint, and
        # dedupe by name so re-uploading the same file doesn't create
        # duplicate students.
        def _save_form_student(first, middle, last, gender):
            existing = FormStudent.objects.filter(
                school=school, form=selected_form,
                first_name=first, middle_name=middle, last_name=last,
            ).first()
            if existing:
                if existing.gender != gender:
                    existing.gender = gender
                    existing.save(update_fields=['gender'])
                return {'created': False}
            FormStudent.objects.create(
                school=school, form=selected_form,
                admission_no=f'NA-{uuid.uuid4().hex[:10]}',
                first_name=first, middle_name=middle, last_name=last, gender=gender,
            )
            return {'created': True}

        try:
            if ext == '.pdf':
                saved = _parse_pdf_roster(uploaded_file, on_student=_save_form_student)
            elif ext in ('.csv', '.xlsx', '.xls'):
                saved = _parse_spreadsheet_roster(uploaded_file, on_student=_save_form_student)
            else:
                messages.error(request, f"Aina ya faili '{ext}' haijulikani. Tumia PDF, CSV au Excel.")
                return redirect(f'{reverse("upload_form_students")}?form={selected_form}')

            count = len(saved)
            if count:
                messages.success(request, f"Wanafunzi {count} wa Form {selected_form} wamehifadhiwa!")
            else:
                messages.warning(request, "Hakuna wanafunzi waliohifadhiwa. Angalia muundo wa faili.")
        except Exception as e:
            messages.error(request, f"Hitilafu ya kusoma faili: {e}")

        return redirect(f'{reverse("upload_form_students")}?form={selected_form}')

    # GET — show form. Ordered by insertion order (id), not alphabetically —
    # the Academic uploaded a specific roster order (e.g. matching the
    # school register) and expects to see it back exactly as uploaded.
    students = FormStudent.objects.filter(school=school, form=selected_form).order_by('id') if selected_form else FormStudent.objects.none()
    counts = {}
    for f in range(1, 7):
        counts[f] = FormStudent.objects.filter(school=school, form=f).count()

    return render(request, 'results/upload_form_students.html', {
        'selected_form': selected_form,
        'students': students,
        'form_counts': counts,
    })


@academic_required
@require_POST
def delete_form_student(request, student_id):
    """Delete a single form student."""
    school = request.user.school
    student = get_object_or_404(FormStudent, id=student_id, school=school)
    form_num = student.form
    student.delete()
    messages.success(request, "Mwanafunzi ameondolewa.")
    return redirect(f'{reverse("upload_form_students")}?form={form_num}')


@academic_required
def assign_teacher_form(request):
    """Academic Officer assigns teacher to form + subject."""
    school = request.user.school
    if not school:
        messages.error(request, "Hakuna shule iliyowekwa.")
        return redirect('home')

    if request.method == 'POST':
        teacher_id = request.POST.get('teacher_id')
        form_num = request.POST.get('form')
        subject_id = request.POST.get('subject_id')
        if teacher_id and form_num and subject_id:
            from .models import TeacherAccount
            teacher = TeacherAccount.objects.filter(id=teacher_id, school=school).first()
            subject = Subject.objects.filter(id=subject_id).first()
            if teacher and subject and int(form_num) in (1,2,3,4,5,6):
                TeacherFormAssignment.objects.get_or_create(
                    teacher=teacher, form=int(form_num), subject=subject, school=school,
                )
                messages.success(request, f"{teacher.full_name} ameassignwa Form {form_num} — {subject.name}")
            else:
                messages.error(request, "Taarifa hazijakamilika.")
        return redirect('assign_teacher_form')

    from .models import TeacherAccount
    teachers = TeacherAccount.objects.filter(school=school, role='TEACHER').order_by('full_name')
    subjects = Subject.objects.all().order_by('name')
    assignments = TeacherFormAssignment.objects.filter(school=school).select_related('teacher', 'subject').order_by('form', 'subject__name')

    return render(request, 'results/assign_teacher_form.html', {
        'teachers': teachers,
        'subjects': subjects,
        'assignments': assignments,
    })


def _generate_recommendations_for_teacher(teacher, form, school):
    """Generate automatic recommendations for a teacher based on subject performance."""
    from .models import ExamResult, Exam, ExamResult as ER
    from django.db.models import Avg, Count, Q

    recs = []
    assignment = TeacherFormAssignment.objects.filter(
        teacher=teacher, form=form, school=school
    ).first()
    if not assignment:
        return recs

    subject = assignment.subject

    # Find exams for this form at this school
    exams = Exam.objects.filter(school=school, form=form).order_by('-year', '-date')[:5]
    if not exams:
        recs.append({
            'type': 'info',
            'title': 'Hakuna mitihani bado',
            'detail': f'Hakuna mitihani ya Form {form} iliyopo. Tumia mitihani kuona matokeo ya somo la {subject.name}.',
        })
        return recs

    for exam in exams[:3]:
        results = ExamResult.objects.filter(exam=exam, subject=subject)
        if not results.exists():
            continue

        avg = results.aggregate(avg=Avg('score'))['avg'] or 0
        total = results.count()
        passed = results.filter(score__gte=40).count()
        pass_rate = (passed / total * 100) if total else 0
        failed = total - passed

        if pass_rate < 50:
            recs.append({
                'type': 'warning',
                'title': f'{exam.name} — Kiwango cha kufaulu ni chini ( {pass_rate:.0f}%)',
                'detail': f'Wanafunzi {failed} kati ya {total} wamefail {subject.name}. Fikiria: ongeza muda wa masomo, tumia mitihani ya ziada, au rekebisha mbinu za ufundishaji.',
            })
        elif avg < 45:
            recs.append({
                'type': 'info',
                'title': f'{exam.name} — Wastani ni {avg:.1f} (chini ya 45)',
                'detail': f'Wastani wa alama za {subject.name} ni {avg:.1f}. Wanafunzi wanahitaji msaada zaidi — ongeza mazoezi na ushauri wa karibu.',
            })
        elif pass_rate >= 80:
            recs.append({
                'type': 'success',
                'title': f'{exam.name} — Matokeo mazuri ({pass_rate:.0f}% wamefaulu)',
                'detail': f'Wanafunzi {passed} kati ya {total} wamefaulu {subject.name} kwa wastani wa {avg:.1f}. Endelea na mbinu ulizo nazo!',
            })
        else:
            recs.append({
                'type': 'info',
                'title': f'{exam.name} — Wastani {avg:.1f}, Kufaulu {pass_rate:.0f}%',
                'detail': f'Matokeo ni ya wastani. Fikiria kuongeza muda wa mazoezi na kuwasaidia wanafunzi walio chini ya 40.',
            })

    if not recs:
        recs.append({
            'type': 'info',
            'title': 'Hakuna data ya kutosha',
            'detail': f'Hakuna matokeo ya {subject.name} kwa Form {form} kwa ripoti ya mapendekezo.',
        })

    return recs


@academic_required
def teacher_performance_report(request, form_num):
    """Generate PDF report ya walimu wote wa form fulani — performance + recommendations."""
    school = request.user.school
    if not school:
        messages.error(request, "Hakuna shule iliyowekwa.")
        return redirect('home')

    if form_num not in (1,2,3,4,5,6):
        raise Http404("Form haijulikani")

    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.units import cm
    from reportlab.lib import colors

    assignments = TeacherFormAssignment.objects.filter(
        school=school, form=form_num
    ).select_related('teacher', 'subject').order_by('teacher__full_name', 'subject__name')

    form_labels = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI'}
    form_label = form_labels.get(form_num, str(form_num))

    student_count = FormStudent.objects.filter(school=school, form=form_num).count()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
    content_w = A4[0] - 4*cm
    story = []

    ss = getSampleStyleSheet()
    title_s = ParagraphStyle('rpt_title', parent=ss['Title'], fontSize=16, alignment=TA_CENTER, textColor=colors.HexColor('#1A3C6E'), spaceAfter=6)
    subtitle_s = ParagraphStyle('rpt_sub', parent=ss['Normal'], fontSize=11, alignment=TA_CENTER, textColor=colors.HexColor('#555555'), spaceAfter=12)
    section_s = ParagraphStyle('rpt_sec', parent=ss['Heading2'], fontSize=12, textColor=colors.HexColor('#1A3C6E'), spaceBefore=16, spaceAfter=8)
    body_s = ParagraphStyle('rpt_body', parent=ss['Normal'], fontSize=10, leading=14, spaceAfter=4)
    rec_s = ParagraphStyle('rpt_rec', parent=ss['Normal'], fontSize=9, leading=13, leftIndent=12, spaceAfter=6)

    # Title
    story.append(Paragraph(f"{school.name}", title_s))
    story.append(Paragraph(f"Ripoti ya Ufaulu — Form {form_label}", subtitle_s))
    story.append(Paragraph(f"Wanafunzi: {student_count} | Walimu: {assignments.values('teacher').distinct().count()} | Masomo: {assignments.values('subject').distinct().count()}", subtitle_s))
    story.append(Spacer(1, 12))

    # Per-teacher sections
    teachers_seen = []
    for ta in assignments:
        teacher = ta.teacher
        if teacher.id in [t.id for t in teachers_seen]:
            continue
        teachers_seen.append(teacher)

        teacher_assignments = [a for a in assignments if a.teacher.id == teacher.id]
        teacher_subjects = ', '.join(a.subject.name for a in teacher_assignments)

        story.append(Paragraph(f"<b>{teacher.full_name or teacher.email}</b>", section_s))
        story.append(Paragraph(f"Masomo: {teacher_subjects}", body_s))

        # Performance per subject
        for ta2 in teacher_assignments:
            subject = ta2.subject
            from django.db.models import Avg
            exams = Exam.objects.filter(school=school, form=form_num).order_by('-year')[:5]
            perf_data = [['Mtihani', 'Wastani', 'Kufaulu%', 'Idadi']]
            for ex in exams:
                results = ExamResult.objects.filter(exam=ex, subject=subject)
                if results.exists():
                    avg = results.aggregate(a=Avg('score'))['a'] or 0
                    passed = results.filter(score__gte=40).count()
                    total = results.count()
                    pr = round(passed/total*100, 1) if total else 0
                    perf_data.append([ex.name, f'{avg:.1f}', f'{pr}%', str(total)])

            if len(perf_data) > 1:
                story.append(Paragraph(f"<b>{subject.name}</b>", body_s))
                t = Table(perf_data, colWidths=[content_w*0.35, content_w*0.2, content_w*0.2, content_w*0.15])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A3C6E')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
                    ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(t)
                story.append(Spacer(1, 6))

        # Recommendations
        recs = _generate_recommendations_for_teacher(teacher, form_num, school)
        if recs:
            story.append(Paragraph("<b>Mapendekezo ya Kuimprove:</b>", body_s))
            for rec in recs:
                icon = {'warning': '⚠️', 'success': '✅', 'info': 'ℹ️'}.get(rec['type'], '•')
                story.append(Paragraph(f"{icon} <b>{rec['title']}</b>", rec_s))
                story.append(Paragraph(rec['detail'], rec_s))

        story.append(Spacer(1, 8))

    if not teachers_seen:
        story.append(Paragraph("Hakuna walimu walioassignwa kwa Form hii bado.", body_s))
        story.append(Paragraph("Tafadhali assign walimu kwanza (Assign Teacher → Form).", body_s))

    doc.build(story)
    buf.seek(0)
    resp = HttpResponse(buf, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="Form_{form_label}_Teacher_Report.pdf"'
    return resp
