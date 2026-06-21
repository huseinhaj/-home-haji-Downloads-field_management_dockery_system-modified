import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.shortcuts import render

from .models import Exam, SpeechSubmissionSession, Student, Subject, SubjectSubmission
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


@require_GET
def speech_entry_page(request):
    exams = Exam.objects.all().order_by('-year', 'name')
    subjects = Subject.objects.all().order_by('name')
    students = Student.objects.all().order_by('first_name', 'last_name')

    # Pre-select exam/subject from URL params
    preselect_exam_id = request.GET.get('exam')
    preselect_subject_id = request.GET.get('subject')

    return render(
        request,
        'results/speech_entry.html',
        {
            'exams': exams,
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
        exam = get_object_or_404(Exam, id=payload.get("exam_id"))
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
            logger.warning(
                "ingest_speech_entry: empty transcript provided session_id=%s",
                session.id,
            )
            raise SpeechSubmissionError(
                "Transcript is empty. Please record a clear voice entry with both student name and mark."
            )

        result = submit_speech_entries_batch(
            session=session,
            transcript=transcript,
            confidence_threshold=float(payload.get("confidence_threshold", 0.9)),
            teacher_name=teacher_name,
        )

        # Handle "nimemaliza" finalize signal
        if result.get("finalize_detected"):
            session.refresh_from_db()
            if session.status != SpeechSubmissionSession.STATUS_FINALIZED:
                session.mark_finalized()

            # Update or create SubjectSubmission record
            student_count = session.entries.count()
            submission, _ = SubjectSubmission.objects.update_or_create(
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

            # Recompute processed results
            recompute_processed_results_for_exam(session.exam)

            # Build PDF URL for this subject
            subject_pdf_url = reverse('subject_pdf', args=[session.exam_id, session.subject_id])
            result['subject_pdf_url'] = subject_pdf_url
            result['session_finalized'] = True

        logger.info(
            "ingest_speech_entry: success session_id=%s saved_count=%s skipped_count=%s session_finalized=%s exam_finalized=%s finalize_detected=%s",
            session.id,
            result.get("saved_count"),
            result.get("skipped_count"),
            result.get("session_finalized"),
            result.get("exam_finalized"),
            result.get("finalize_detected"),
        )
        return JsonResponse(result)
    except SpeechTranscriptionError as exc:
        logger.warning(
            "ingest_speech_entry: transcription error session_id=%s error=%s",
            session_id,
            exc,
        )
        return JsonResponse({"error": str(exc)}, status=400)
    except SpeechMatchReviewRequired as exc:
        logger.info(
            "ingest_speech_entry: review required session_id=%s transcript=%r candidates=%s",
            session_id,
            transcript,
            exc.candidates,
        )
        return JsonResponse({"error": str(exc), "candidates": exc.candidates, "transcript": transcript}, status=409)
    except SpeechSubmissionError as exc:
        logger.warning(
            "ingest_speech_entry: validation error session_id=%s transcript=%r error=%s",
            session_id,
            transcript,
            exc,
        )
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception(
            "ingest_speech_entry: unexpected error session_id=%s transcript=%r",
            session_id,
            transcript,
        )
        return JsonResponse({"error": str(exc)}, status=400)


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
