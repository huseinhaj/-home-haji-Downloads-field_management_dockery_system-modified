import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.shortcuts import render

from .models import Exam, ExamResult, ProcessedResult, SpeechSubmissionSession, Student, Subject, SubjectSubmission
from .utils import group_exams_by_type
from .permissions import results_login_required as login_required
from .services.speech_asr_service import transcribe_uploaded_audio, SpeechTranscriptionError
from .services.speech_submission_service import (
    SpeechMatchReviewRequired,
    SpeechSubmissionError,
    create_or_get_session_with_roster,
    get_session_status,
    maybe_finalize_exam,
    submit_speech_entries_batch,
    submit_speech_entry,
)
from .services.upload_processing_service import recompute_processed_results_for_exam


logger = logging.getLogger(__name__)


@login_required
@require_GET
def speech_entry_page(request):
    exams = Exam.objects.filter(school=request.user.school).order_by('-year', 'name')
    exam_groups = group_exams_by_type(exams, dict(Exam.EXAM_TYPE_CHOICES))
    subjects = Subject.objects.all().order_by('name')
    students = Student.objects.all().order_by('first_name', 'last_name')

    # Pre-select exam/subject from URL params
    preselect_exam_id = request.GET.get('exam')
    preselect_subject_id = request.GET.get('subject')

    return render(
        request,
        'results/speech_entry.html',
        {
            'exam_groups': exam_groups,
            'subjects': subjects,
            'students': students,
            'debug_mode': settings.DEBUG,
            'preselect_exam_id': preselect_exam_id or '',
            'preselect_subject_id': preselect_subject_id or '',
        },
    )


def _parse_payload(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            raise SpeechSubmissionError("Invalid JSON payload.")
    return request.POST.dict()


def _session_with_access_key(session_id, access_key):
    return get_object_or_404(SpeechSubmissionSession, id=session_id, access_key=access_key)


@login_required
@require_POST
def create_speech_session(request):
    try:
        payload = _parse_payload(request)
        logger.info(
            "create_speech_session: payload exam_id=%s subject_id=%s teacher_name=%r roster_student_ids=%s",
            payload.get("exam_id"),
            payload.get("subject_id"),
            payload.get("teacher_name"),
            payload.get("roster_student_ids"),
        )
        exam = get_object_or_404(Exam, id=payload.get("exam_id"), school=request.user.school)
        subject = get_object_or_404(Subject, id=payload.get("subject_id"))
        teacher_name = (payload.get("teacher_name") or "").strip()
        if not teacher_name:
            return JsonResponse({"error": "teacher_name is required."}, status=400)

        expected_student_count = payload.get("expected_student_count")
        roster_student_ids = payload.get("roster_student_ids") or []
        if not isinstance(roster_student_ids, list):
            return JsonResponse({"error": "roster_student_ids must be a list."}, status=400)
        roster_student_ids = [int(student_id) for student_id in roster_student_ids if str(student_id).strip()]
        # roster_student_ids inaweza kuwa tupu — mfumo utafanya kazi kwa open mode
        # wanafunzi wataundwa moja kwa moja kutoka kwa maneno ya mwalimu

        session = create_or_get_session_with_roster(
            exam=exam,
            subject=subject,
            teacher_name=teacher_name,
            roster_student_ids=roster_student_ids,
            expected_student_count=len(roster_student_ids) if roster_student_ids else None,
        )
        logger.info(
            "create_speech_session: created session_id=%s exam_id=%s subject_id=%s roster_size=%s",
            session.id,
            session.exam_id,
            session.subject_id,
            len(session.roster_student_ids),
        )
        return JsonResponse({
            "session_id": session.id,
            "access_key": str(session.access_key),
            "status": session.status,
            "expected_student_count": session.effective_expected_count,
            "roster_size": len(session.roster_student_ids),
        })
    except SpeechSubmissionError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_GET
def speech_session_status(request, session_id):
    access_key = request.GET.get("access_key")
    if not access_key:
        return JsonResponse({"error": "access_key is required."}, status=400)

    session = _session_with_access_key(session_id, access_key)
    return JsonResponse(get_session_status(session, include_existing_marks=settings.DEBUG))


@require_POST
def ingest_speech_entry(request, session_id):
    transcript = ""
    try:
        payload = _parse_payload(request)
        session = _session_with_access_key(session_id, payload.get("access_key"))
        transcript = payload.get("transcript") or payload.get("text") or ""
        teacher_name = (payload.get("teacher_name") or session.teacher_name or "").strip()
        audio_file = request.FILES.get("audio")
        if audio_file:
            language = payload.get("language") or "en"
            logger.info(
                "ingest_speech_entry: transcribing audio session_id=%s file_name=%r content_type=%r language=%r",
                session.id,
                getattr(audio_file, "name", None),
                getattr(audio_file, "content_type", None),
                language,
            )
            transcript = transcribe_uploaded_audio(audio_file, language=language)

        logger.info(
            "ingest_speech_entry: session_id=%s access_key_present=%s transcript_length=%s explicit_update=%s confirm_student_id=%s confidence_threshold=%s language=%r",
            session.id,
            bool(payload.get("access_key")),
            len(transcript),
            payload.get("explicit_update"),
            payload.get("confirm_student_id"),
            payload.get("confidence_threshold"),
            payload.get("language"),
        )
        if not transcript or not transcript.strip():
            logger.warning("ingest_speech_entry: empty transcript session_id=%s", session.id)
            return JsonResponse({
                "error": "Sauti haikutambuliwa. Sema kwa sauti ya wazi karibu na maikrofoni.",
                "transcript": "",
            }, status=400)

        confidence_threshold = float(payload.get("confidence_threshold", 0.85))

        # Audio blob from VAD = one student at a time → use single-entry path.
        # Manual text submission may contain multiple students → use batch path.
        if audio_file:
            result = _ingest_single(session, transcript, confidence_threshold, teacher_name)
        else:
            result = _ingest_batch(session, transcript, confidence_threshold, teacher_name)

        if result.get("finalize_detected") or result.get("session_finalized"):
            session.refresh_from_db()
            if session.status != SpeechSubmissionSession.STATUS_FINALIZED:
                session.mark_finalized()
            student_count = session.entries.count()
            SubjectSubmission.objects.update_or_create(
                exam=session.exam,
                subject=session.subject,
                defaults={
                    'status': SubjectSubmission.STATUS_SUBMITTED,
                    'method': 'SPEECH',
                    'submitted_by': teacher_name or session.teacher_name,
                    'submitted_at': timezone.now(),
                    'student_count': student_count,
                },
            )
            recompute_processed_results_for_exam(session.exam)
            result['subject_pdf_url'] = reverse('subject_pdf', args=[session.exam_id, session.subject_id])
            result['session_finalized'] = True

        logger.info(
            "ingest_speech_entry: success session_id=%s transcript=%r saved_count=%s",
            session.id, transcript, result.get("saved_count", 1),
        )
        return JsonResponse(result)

    except SpeechTranscriptionError as exc:
        logger.warning("ingest_speech_entry: transcription error session_id=%s error=%s", session_id, exc)
        return JsonResponse({"error": str(exc), "transcript": transcript}, status=400)
    except SpeechMatchReviewRequired as exc:
        logger.info("ingest_speech_entry: review required session_id=%s transcript=%r", session_id, transcript)
        return JsonResponse({"error": str(exc), "candidates": exc.candidates, "transcript": transcript}, status=409)
    except SpeechSubmissionError as exc:
        logger.warning("ingest_speech_entry: submission error session_id=%s transcript=%r error=%s", session_id, transcript, exc)
        return JsonResponse({"error": str(exc), "transcript": transcript}, status=400)
    except Exception as exc:
        logger.exception("ingest_speech_entry: unexpected error session_id=%s transcript=%r", session_id, transcript)
        return JsonResponse({"error": str(exc), "transcript": transcript}, status=400)


def _ingest_single(session, transcript, confidence_threshold, teacher_name):
    """Single-student path — used when audio blob comes from VAD recording."""
    from .services.speech_submission_service import (
        contains_finalize_signal, is_finalize_only,
    )
    if is_finalize_only(transcript):
        return {
            "status": "saved", "saved_count": 0, "skipped_count": 0,
            "saved_entries": [], "skipped_entries": [],
            "session_finalized": False, "exam_finalized": False,
            "finalize_detected": True,
        }

    result = submit_speech_entry(
        session=session,
        transcript=transcript,
        explicit_update=True,
        confidence_threshold=confidence_threshold,
        teacher_name=teacher_name,
    )
    finalize_detected = contains_finalize_signal(transcript)
    # Build a flat entry summary — do NOT nest result inside itself
    entry_summary = {
        "student":    result.get("student"),
        "score":      result.get("score"),
        "confidence": result.get("confidence"),
        "transcript": transcript,
    }
    return {
        "status":           "saved",
        "transcript":       transcript,
        "student":          result.get("student"),
        "score":            result.get("score"),
        "confidence":       result.get("confidence"),
        "candidates":       result.get("candidates", []),
        "saved_count":      1,
        "saved_entries":    [entry_summary],
        "skipped_count":    0,
        "skipped_entries":  [],
        "session_finalized": result.get("session_finalized", False),
        "exam_finalized":   result.get("exam_finalized", False),
        "finalize_detected": finalize_detected,
    }


def _ingest_batch(session, transcript, confidence_threshold, teacher_name):
    """Multi-student path — used when teacher types multiple entries manually."""
    result = submit_speech_entries_batch(
        session=session,
        transcript=transcript,
        confidence_threshold=confidence_threshold,
        teacher_name=teacher_name,
    )
    result["transcript"] = transcript
    return result


@require_POST
def confirm_speech_candidate(request, session_id):
    transcript = ""
    try:
        payload = _parse_payload(request)
        session = _session_with_access_key(session_id, payload.get("access_key"))
        transcript = payload.get("transcript") or payload.get("text") or ""
        teacher_name = (payload.get("teacher_name") or session.teacher_name or "").strip()
        logger.info(
            "confirm_speech_candidate: session_id=%s confirm_student_id=%s transcript=%r explicit_update=%s",
            session.id,
            payload.get("confirm_student_id"),
            transcript,
            payload.get("explicit_update"),
        )
        result = submit_speech_entry(
            session=session,
            transcript=transcript,
            explicit_update=str(payload.get("explicit_update", "false")).lower() in {"1", "true", "yes"},
            confirm_student_id=int(payload.get("confirm_student_id")),
            confidence_threshold=float(payload.get("confidence_threshold", 0.9)),
            teacher_name=teacher_name,
        )
        logger.info(
            "confirm_speech_candidate: success session_id=%s student_id=%s score=%s confidence=%s",
            session.id,
            result.get("student", {}).get("id"),
            result.get("score"),
            result.get("confidence"),
        )
        return JsonResponse(result)
    except SpeechMatchReviewRequired as exc:
        logger.info(
            "confirm_speech_candidate: review required session_id=%s transcript=%r candidates=%s",
            session_id,
            transcript,
            exc.candidates,
        )
        return JsonResponse({"error": str(exc), "candidates": exc.candidates, "transcript": payload.get("transcript") or payload.get("text") or ""}, status=409)
    except SpeechSubmissionError as exc:
        logger.warning(
            "confirm_speech_candidate: validation error session_id=%s transcript=%r error=%s",
            session_id,
            transcript,
            exc,
        )
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception(
            "confirm_speech_candidate: unexpected error session_id=%s transcript=%r",
            session_id,
            transcript,
        )
        return JsonResponse({"error": str(exc)}, status=400)


@require_POST
def finalize_speech_session(request, session_id):
    try:
        payload = _parse_payload(request)
        session = _session_with_access_key(session_id, payload.get("access_key"))
        teacher_name = (payload.get("teacher_name") or session.teacher_name or "").strip()
        logger.info(
            "finalize_speech_session: session_id=%s submitted_count=%s expected_count=%s status=%s",
            session.id,
            session.submitted_count,
            session.effective_expected_count,
            session.status,
        )
        # Open mode (no roster/expected count) always allows finalization
        is_open_mode = session.effective_expected_count is None
        if not is_open_mode and not session.is_complete:
            logger.warning(
                "finalize_speech_session: blocked incomplete session_id=%s submitted_count=%s expected_count=%s",
                session.id,
                session.submitted_count,
                session.effective_expected_count,
            )
            return JsonResponse(
                {
                    "error": "Session is not complete yet.",
                    "submitted_count": session.submitted_count,
                    "expected_student_count": session.effective_expected_count,
                },
                status=400,
            )

        session.mark_finalized()

        # Update SubjectSubmission
        student_count = session.entries.count()
        SubjectSubmission.objects.update_or_create(
            exam=session.exam,
            subject=session.subject,
            defaults={
                'status': SubjectSubmission.STATUS_SUBMITTED,
                'method': 'SPEECH',
                'submitted_by': teacher_name or session.teacher_name,
                'submitted_at': timezone.now(),
                'student_count': student_count,
            },
        )

        exam_finalized = maybe_finalize_exam(session.exam)
        subject_pdf_url = reverse('subject_pdf', args=[session.exam_id, session.subject_id])

        logger.info(
            "finalize_speech_session: finalized session_id=%s exam_finalized=%s",
            session.id,
            exam_finalized,
        )
        return JsonResponse({
            "session_id": session.id,
            "status": session.status,
            "finalized_at": session.finalized_at,
            "exam_finalized": exam_finalized,
            "subject_pdf_url": subject_pdf_url,
        })
    except SpeechSubmissionError as exc:
        logger.warning("finalize_speech_session: validation error session_id=%s error=%s", session_id, exc)
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("finalize_speech_session: unexpected error session_id=%s", session_id)
        return JsonResponse({"error": str(exc)}, status=400)


# ═══════════════════════════════════════════════════════════════════════════════
# GUIDED VOICE ENTRY — mwalimu anasikia jina la mwanafunzi, anasema alama,
# mfumo unajaza na kuendelea kwenye mwanafunzi wa pili automatically.
# ═══════════════════════════════════════════════════════════════════════════════

from .services.upload_processing_service import recompute_processed_results_for_exam


@login_required
def guided_voice_entry(request):
    """Guided voice entry page — upload roster, then speak scores student by student."""
    teacher = request.user
    school_exams = Exam.objects.filter(school=teacher.school).order_by('-year', 'name')
    if teacher.school and school_exams.exists():
        exams = school_exams
    else:
        exams = Exam.objects.order_by('-year', 'name')
    exam_groups = group_exams_by_type(exams, dict(Exam.EXAM_TYPE_CHOICES))

    return render(request, 'results/guided_voice_entry.html', {
        'exam_groups': exam_groups,
        'teacher_subjects': teacher.subjects.all().order_by('name'),
    })


@require_POST
@login_required
def voice_entry_transcribe(request):
    """Transcribe a short audio clip (student name + score) and return the score."""
    audio = request.FILES.get('audio')
    language = request.POST.get('language', 'sw')
    if not audio:
        return JsonResponse({'error': 'Hakuna sauti iliyotumwa.'}, status=400)
    try:
        transcript = transcribe_uploaded_audio(audio, language=language)
        # Extract numeric score from transcript
        import re
        numbers = re.findall(r'\b(\d{1,3})\b', transcript)
        score = None
        if numbers:
            # Take the last number (usually the score comes after the name)
            score = int(numbers[-1])
            if score > 100:
                score = None
        return JsonResponse({
            'transcript': transcript,
            'score': score,
        })
    except SpeechTranscriptionError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except Exception as exc:
        logger.exception('voice_entry_transcribe: unexpected error')
        return JsonResponse({'error': str(exc)}, status=400)


@require_POST
@login_required
def voice_entry_save_score(request):
    """Save a single score for one student in an exam+subject."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Data ya JSON si sahihi.'}, status=400)

    exam_id = data.get('exam_id')
    subject_id = data.get('subject_id')
    student_id = data.get('student_id')
    score = data.get('score')

    if not all([exam_id, subject_id, student_id, score is not None]):
        return JsonResponse({'error': 'Taarifa zote zinahitajika: exam_id, subject_id, student_id, score.'}, status=400)

    try:
        score = int(score)
    except (TypeError, ValueError):
        return JsonResponse({'error': f'Alama "{score}" si nambari sahihi.'}, status=400)

    if score < 0 or score > 100:
        return JsonResponse({'error': f'Alama {score} ni nje ya kipimo 0-100.'}, status=400)

    exam = get_object_or_404(Exam, id=exam_id)
    subject = get_object_or_404(Subject, id=subject_id)
    student = get_object_or_404(Student, id=student_id)

    ExamResult.objects.update_or_create(
        exam=exam, student=student, subject=subject,
        defaults={'score': score},
    )

    return JsonResponse({'success': True, 'student_id': student_id, 'score': score})


@require_POST
@login_required
def voice_entry_bulk_finalize(request):
    """Recompute processed results for the exam after all scores are entered."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Data ya JSON si sahihi.'}, status=400)

    exam_id = data.get('exam_id')
    subject_id = data.get('subject_id')

    if not exam_id or not subject_id:
        return JsonResponse({'error': 'exam_id na subject_id zinahitajika.'}, status=400)

    exam = get_object_or_404(Exam, id=exam_id)
    subject = get_object_or_404(Subject, id=subject_id)

    # Mark SubjectSubmission as SUBMITTED
    student_count = ExamResult.objects.filter(exam=exam, subject=subject).count()
    SubjectSubmission.objects.update_or_create(
        exam=exam, subject=subject,
        defaults={
            'status': SubjectSubmission.STATUS_SUBMITTED,
            'method': 'SPEECH',
            'submitted_by': request.user.full_name or request.user.email,
            'submitted_by_user': request.user,
            'submitted_at': timezone.now(),
            'student_count': student_count,
        },
    )

    try:
        recompute_processed_results_for_exam(exam)
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'student_count': student_count,
        'overview_url': reverse('exam_overview', args=[exam.id]),
    })
