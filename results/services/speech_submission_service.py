from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from ..models import Exam, ExamResult, ProcessedResult, SpeechSubmissionEntry, SpeechSubmissionSession, Student, SubjectSubmission
from .upload_processing_service import recompute_processed_results_for_exam

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover - optional dependency fallback
    fuzz = None
    process = None


logger = logging.getLogger(__name__)


class SpeechSubmissionError(Exception):
    pass


class SpeechMatchReviewRequired(SpeechSubmissionError):
    def __init__(self, message: str, candidates: list[dict]):
        super().__init__(message)
        self.candidates = candidates


def normalize_text(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


SCORE_FILLER_WORDS = {
    "mark",
    "marks",
    "score",
    "scores",
    "is",
    "equals",
    "equal",
    "got",
    "was",
    "of",
    "out",
    "to",
    "the",
}


FINALIZE_KEYWORDS = frozenset({
    'nimemaliza',
    'nimekwisha',
    'namaliza',
    'imekamilika',
    'finished',
    'done',
    'complete',
    'completed',
})


def contains_finalize_signal(transcript: str) -> bool:
    normalized = normalize_text(transcript)
    words = set(normalized.split())
    return bool(FINALIZE_KEYWORDS & words)


def is_finalize_only(transcript: str) -> bool:
    """True if transcript is ONLY a finalize signal with no student entry."""
    normalized = normalize_text(transcript)
    words = set(normalized.split())
    remaining = words - FINALIZE_KEYWORDS - {'na', 'ya', 'hiyo', 'hizo'}
    return bool(FINALIZE_KEYWORDS & words) and len(remaining) <= 1


ENGLISH_NUMBER_WORDS = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
}

ENGLISH_ONES_WORDS = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
}

SWAHILI_NUMBER_WORDS = {
    "sifuri": 0,
    "moja": 1,
    "mbili": 2,
    "tatu": 3,
    "nne": 4,
    "tano": 5,
    "sita": 6,
    "saba": 7,
    "nane": 8,
    "tisa": 9,
    "kumi": 10,
    "ishirini": 20,
    "thelathini": 30,
    "arobaini": 40,
    "hamsini": 50,
    "sitini": 60,
    "sabini": 70,
    "themanini": 80,
    "tisini": 90,
    "mia": 100,
}

SWAHILI_NUMBER_VARIANTS = {
    "sistini": "sitini",
    "thelathini": "thelathini",
    "themanini": "themanini",
    "kumia": "kumi",
    "kumi": "kumi",
    "tisinani": "tisini",
    "nishini": "ishirini",
    "nishinambili": "ishirinambili",
}

SWAHILI_COMPOUND_NUMBER_WORDS = {
    "ishirinambili": 22,
    "ishirinatatu": 23,
    "ishirinanane": 28,
    "thelathininne": 34,
    "arobaininatano": 45,
    "hamsininambili": 52,
    "sitininambili": 62,
    "sabininambili": 72,
    "themanininambili": 82,
    "tisininatano": 95,
}


def parse_spoken_score(text: str) -> Optional[int]:
    normalized = normalize_text(text)
    if not normalized:
        logger.warning(
            "parse_spoken_score: transcript normalized to empty. raw_text=%r. Only English and Swahili are supported.",
            text,
        )
        return None

    tokens = normalized.split()
    logger.debug("parse_spoken_score: transcript=%r tokens=%s", normalized, tokens)

    spaced_digit_score = _parse_trailing_spaced_digits(tokens)
    if spaced_digit_score is not None:
        logger.debug("parse_spoken_score: matched spaced digits -> %s", spaced_digit_score)
        return spaced_digit_score

    digits_match = re.search(r"(\d{1,3})(?!.*\d)", normalized)
    if digits_match:
        score = int(digits_match.group(1))
        logger.debug("parse_spoken_score: matched numeric score -> %s", score)
        return score if 0 <= score <= 100 else None

    score_window = _find_score_window(tokens)
    if score_window is not None:
        score, start_index, end_index = score_window
        logger.debug(
            "parse_spoken_score: matched word score -> %s from tokens[%s:%s]=%s",
            score,
            start_index,
            end_index,
            tokens[start_index:end_index],
        )
        return score

    logger.debug("parse_spoken_score: no score matched for transcript=%r", normalized)
    return None


def extract_name_and_score(transcript: str) -> tuple[str, int]:
    normalized = normalize_text(transcript)
    if not normalized:
        logger.warning(
            "extract_name_and_score: transcript normalized to empty. raw_transcript=%r. Only English and Swahili are supported.",
            transcript,
        )
        raise SpeechSubmissionError(
            "Transcript is empty or in an unsupported language. Only English and Swahili are supported."
        )

    tokens = normalized.split()
    logger.debug("extract_name_and_score: transcript=%r tokens=%s", normalized, tokens)

    trailing_digit_score = _parse_trailing_spaced_digits(tokens)
    if trailing_digit_score is not None:
        name_tokens = _trim_score_tokens(tokens)
        name_part = _normalize_name_tokens(name_tokens)
        if not name_part:
            logger.debug(
                "extract_name_and_score: spaced digits matched but name missing transcript=%r tokens=%s",
                normalized,
                tokens,
            )
            raise SpeechSubmissionError("Could not extract student name from transcript.")
        logger.debug(
            "extract_name_and_score: matched spaced digits name=%r score=%s",
            name_part,
            trailing_digit_score,
        )
        return name_part, trailing_digit_score

    digit_match = re.search(r"(\d{1,3})(?!.*\d)", normalized)
    if digit_match:
        score = int(digit_match.group(1))
        if not 0 <= score <= 100:
            raise SpeechSubmissionError("Score must be between 0 and 100.")
        name_part = normalized[: digit_match.start()].strip(" ,:-")
        name_part = re.sub(r"\b(mark|score|is|equals)\b$", "", name_part).strip()
        if not name_part:
            logger.debug(
                "extract_name_and_score: numeric score matched but name missing transcript=%r score=%s",
                normalized,
                score,
            )
            raise SpeechSubmissionError("Could not extract student name from transcript.")
        logger.debug("extract_name_and_score: matched numeric score name=%r score=%s", name_part, score)
        return name_part, score

    score_window = _find_score_window(tokens)
    if score_window is not None:
        score, start_index, end_index = score_window
        name_tokens = tokens[:start_index] + tokens[end_index:]
        name_part = _normalize_name_tokens(name_tokens)
        if not name_part:
            logger.debug(
                "extract_name_and_score: word score matched but name missing transcript=%r score=%s window=%s",
                normalized,
                score,
                tokens[start_index:end_index],
            )
            raise SpeechSubmissionError("Could not extract student name from transcript.")
        if not 0 <= score <= 100:
            logger.debug(
                "extract_name_and_score: score out of range transcript=%r score=%s window=%s",
                normalized,
                score,
                tokens[start_index:end_index],
            )
            raise SpeechSubmissionError("Score must be between 0 and 100.")
        logger.debug(
            "extract_name_and_score: matched word score name=%r score=%s window=%s",
            name_part,
            score,
            tokens[start_index:end_index],
        )
        return name_part, score

    logger.warning("extract_name_and_score: no valid score parsed transcript=%r tokens=%s", normalized, tokens)
    raise SpeechSubmissionError("Could not extract a valid score from the transcript.")


def normalize_student_name(student: Student) -> str:
    parts = [student.first_name, student.middle_name, student.last_name]
    return normalize_text(" ".join(part for part in parts if part))


def _compare_names(target: str, candidate: str) -> float:
    if fuzz is not None:
        try:
            return float(fuzz.WRatio(target, candidate)) / 100.0
        except Exception:
            pass

    target_tokens = target.split()
    candidate_tokens = candidate.split()
    token_sort_target = " ".join(sorted(target_tokens))
    token_sort_candidate = " ".join(sorted(candidate_tokens))
    token_ratio = SequenceMatcher(None, token_sort_target, token_sort_candidate).ratio()
    full_ratio = SequenceMatcher(None, target, candidate).ratio()
    return max(full_ratio, token_ratio)


def fuzzy_match_student_name(raw_name: str, roster_students: Iterable[Student], threshold: float = 0.9) -> tuple[Optional[Student], float, list[dict]]:
    normalized_name = normalize_text(raw_name)
    roster_students = list(roster_students)
    candidate_rows: list[dict] = []

    for student in roster_students:
        student_name = normalize_student_name(student)
        confidence = _compare_names(normalized_name, student_name)
        candidate_rows.append(
            {
                "student_id": student.id,
                "name": student_name,
                "confidence": round(confidence, 4),
            }
        )

    candidate_rows.sort(key=lambda row: row["confidence"], reverse=True)
    top_candidates = candidate_rows[:3]

    if not top_candidates:
        return None, 0.0, top_candidates

    best_candidate = top_candidates[0]
    if best_candidate["confidence"] < threshold:
        return None, best_candidate["confidence"], top_candidates

    matched_student = next((student for student in roster_students if student.id == best_candidate["student_id"]), None)
    return matched_student, best_candidate["confidence"], top_candidates


def match_rows_to_roster_exclusive(
    rows: List[dict],
    roster_students: Iterable[Student],
    threshold: float = 0.80,
) -> Tuple[dict, list]:
    """Match a BATCH of scoresheet rows (name -> score) against a roster,
    exclusively — each roster student is claimed by at most ONE row, and
    each row is matched to at most ONE student.

    Matching each row independently against the whole roster (the old
    approach) lets two rows for similarly-named students — e.g. same
    surname, or a name the OCR misread as another student's — both pick
    the SAME "best" student, silently giving one student the wrong score
    and leaving the other with none. This picks the globally best-scoring
    (row, student) pairs first, so a near-exact name match always wins its
    student before a weaker, merely-similar match can steal them.

    Returns (assignments, unmatched_row_indices) where assignments maps
    row_index -> (student, confidence) for every confidently, exclusively
    matched row; unmatched_row_indices lists the row indices left over
    (below threshold, or whose best candidates were already claimed by a
    stronger match) for the caller's existing "create new student" or
    "leave unmatched" fallback.
    """
    roster_students = list(roster_students)
    student_names = {student.id: normalize_student_name(student) for student in roster_students}

    pairs = []  # (confidence, row_index, student)
    for row_index, row in enumerate(rows):
        normalized_name = normalize_text(row.get('raw_name') or '')
        for student in roster_students:
            confidence = _compare_names(normalized_name, student_names[student.id])
            if confidence >= threshold:
                pairs.append((confidence, row_index, student))

    # Highest confidence first; stable tie-break keeps results deterministic.
    pairs.sort(key=lambda p: (-p[0], p[1], p[2].id))

    assignments: dict = {}
    claimed_students: set = set()
    for confidence, row_index, student in pairs:
        if row_index in assignments or student.id in claimed_students:
            continue
        assignments[row_index] = (student, confidence)
        claimed_students.add(student.id)

    unmatched_row_indices = [i for i in range(len(rows)) if i not in assignments]
    return assignments, unmatched_row_indices


@transaction.atomic
def create_or_get_session(
    *,
    exam: Exam,
    subject,
    teacher_name: str,
    expected_student_count: Optional[int] = None,
    roster_student_ids: Optional[list[int]] = None,
) -> SpeechSubmissionSession:
    session, _ = SpeechSubmissionSession.objects.update_or_create(
        exam=exam,
        subject=subject,
        defaults={
            "teacher_name": teacher_name,
            "roster_student_ids": roster_student_ids or [],
        },
    )
    if expected_student_count and session.expected_student_count != expected_student_count:
        session.expected_student_count = expected_student_count
        session.save(update_fields=["expected_student_count"])
    return session


def create_or_get_session_with_roster(*, exam: Exam, subject, teacher_name: str, roster_student_ids: list[int], expected_student_count: Optional[int] = None) -> SpeechSubmissionSession:
    session = create_or_get_session(
        exam=exam,
        subject=subject,
        teacher_name=teacher_name,
        expected_student_count=expected_student_count,
        roster_student_ids=[int(sid) for sid in roster_student_ids] if roster_student_ids else [],
    )
    # Kama hakuna roster — open mode, expected_count si lazima
    if roster_student_ids and session.expected_student_count != len(session.roster_student_ids):
        session.expected_student_count = len(session.roster_student_ids)
        session.save(update_fields=["expected_student_count"])
    return session


def submit_speech_entry(
    *,
    session: SpeechSubmissionSession,
    transcript: str,
    explicit_update: bool = False,
    confirm_student_id: Optional[int] = None,
    confidence_threshold: float = 0.9,
    teacher_name: str = '',
    roster_students: Optional[List[Student]] = None,
) -> dict:
    if session.status == SpeechSubmissionSession.STATUS_FINALIZED:
        raise SpeechSubmissionError("This speech submission session is already finalized.")

    logger.info(
        "submit_speech_entry: session_id=%s exam_id=%s subject_id=%s transcript=%r explicit_update=%s confirm_student_id=%s confidence_threshold=%s roster_size=%s",
        session.id,
        session.exam_id,
        session.subject_id,
        transcript,
        explicit_update,
        confirm_student_id,
        confidence_threshold,
        len(session.roster_student_ids or []),
    )

    student_name, score = extract_name_and_score(transcript)
    roster_ids = session.roster_student_ids or []
    if roster_students is None:
        # roster_student_ids is fixed for the life of the session, so a
        # caller processing many chunks of the same session (see
        # submit_speech_entries_batch) can fetch this once and pass it in
        # instead of re-running the same query per chunk.
        if roster_ids:
            roster_students = list(Student.objects.filter(id__in=roster_ids).order_by("first_name", "last_name"))
        else:
            roster_students = list(Student.objects.all().order_by("first_name", "last_name"))

    logger.debug(
        "submit_speech_entry: parsed student_name=%r score=%s roster_student_ids=%s",
        student_name,
        score,
        roster_ids,
    )

    matched_student = None
    confidence = 0.0
    candidates: list[dict] = []

    if confirm_student_id is not None:
        matched_student = next((s for s in roster_students if s.id == confirm_student_id), None)
        if matched_student is None:
            logger.warning(
                "submit_speech_entry: confirmed student missing session_id=%s confirm_student_id=%s roster_ids=%s",
                session.id,
                confirm_student_id,
                roster_ids,
            )
            raise SpeechSubmissionError("Confirmed student does not exist in the roster.")
        confidence = 1.0
        candidates = [
            {
                "student_id": matched_student.id,
                "name": normalize_student_name(matched_student),
                "confidence": 1.0,
            }
        ]
    else:
        matched_student, confidence, candidates = fuzzy_match_student_name(
            student_name,
            roster_students,
            threshold=confidence_threshold,
        )
        if matched_student is None:
            recovered_name = recover_name_from_transcript(transcript, roster_students)
            if recovered_name:
                logger.info(
                    "submit_speech_entry: retrying fuzzy match with recovered_name=%r parsed_name=%r",
                    recovered_name,
                    student_name,
                )
                matched_student, confidence, candidates = fuzzy_match_student_name(
                    recovered_name,
                    roster_students,
                    threshold=confidence_threshold,
                )
                if matched_student is not None:
                    student_name = recovered_name

        logger.debug(
            "submit_speech_entry: fuzzy match result student_id=%s confidence=%s candidates=%s",
            getattr(matched_student, "id", None),
            confidence,
            candidates,
        )

        # Auto-create student when truly no match exists (confidence < 0.45)
        if matched_student is None and confidence < 0.45:
            parts = student_name.strip().split()
            first = parts[0].capitalize() if parts else 'Unknown'
            last = ' '.join(parts[1:]).capitalize() if len(parts) > 1 else 'Unknown'
            matched_student = Student.objects.create(first_name=first, last_name=last, gender='M')
            confidence = 1.0
            candidates = [{'student_id': matched_student.id, 'name': student_name, 'confidence': 1.0}]
            logger.info(
                "submit_speech_entry: auto-created student id=%s name=%r from transcript=%r",
                matched_student.id,
                student_name,
                transcript,
            )

        if matched_student is None:
            logger.info(
                "submit_speech_entry: low confidence match session_id=%s transcript=%r parsed_name=%r confidence=%s candidates=%s",
                session.id,
                transcript,
                student_name,
                confidence,
                candidates,
            )
            raise SpeechMatchReviewRequired(
                "Low confidence match. Please confirm one of the top candidates.",
                candidates,
            )

    if not 0 <= score <= 100:
        logger.warning(
            "submit_speech_entry: score out of range session_id=%s transcript=%r parsed_name=%r score=%s",
            session.id,
            transcript,
            student_name,
            score,
        )
        raise SpeechSubmissionError("Score must be between 0 and 100.")

    try:
        entry = SpeechSubmissionEntry.objects.get(
            session=session,
            student=matched_student,
        )
        entry.raw_name_transcript = transcript
        entry.parsed_name = student_name
        entry.score = score
        entry.match_confidence = confidence
        entry.match_candidates = candidates
        entry.explicit_update = explicit_update
        entry.save(update_fields=["raw_name_transcript", "parsed_name", "score", "match_confidence", "match_candidates", "explicit_update", "updated_at"])
    except SpeechSubmissionEntry.DoesNotExist:
        entry = SpeechSubmissionEntry.objects.create(
            session=session,
            student=matched_student,
            raw_name_transcript=transcript,
            parsed_name=student_name,
            score=score,
            match_confidence=confidence,
            match_candidates=candidates,
            explicit_update=explicit_update,
        )

    try:
        exam_result = ExamResult.objects.get(
            exam=session.exam,
            student=matched_student,
            subject=session.subject,
        )
        exam_result.score = score
        exam_result.save(update_fields=["score"])
    except ExamResult.DoesNotExist:
        ExamResult.objects.create(
            exam=session.exam,
            student=matched_student,
            subject=session.subject,
            score=score,
        )

    session_finalized = False
    exam_finalized = False

    if session.is_complete:
        with transaction.atomic():
            session.refresh_from_db()
            if session.is_complete:
                session.mark_finalized()
                session_finalized = True
                _update_subject_submission(session, teacher_name=teacher_name or session.teacher_name)
                exam_finalized = maybe_finalize_exam(session.exam)

    logger.info(
        "submit_speech_entry: saved entry_id=%s session_id=%s student_id=%s score=%s confidence=%s session_finalized=%s exam_finalized=%s",
        entry.id,
        session.id,
        matched_student.id,
        score,
        confidence,
        session_finalized,
        exam_finalized,
    )

    return {
        "status": "saved",
        "entry_id": entry.id,
        "session_finalized": session_finalized,
        "exam_finalized": exam_finalized,
        "student": {
            "id": matched_student.id,
            "name": normalize_student_name(matched_student),
        },
        "score": score,
        "confidence": confidence,
        "candidates": candidates,
    }


def split_transcript_entries(transcript: str) -> list[str]:
    """Split one long teacher transcript into per-student utterances."""
    raw_text = str(transcript or "").strip()
    if not raw_text:
        return []

    chunks = [
        chunk.strip(" ,.;")
        for chunk in re.split(r"(?:\s*[.;]\s+|[\r\n]+)", raw_text)
        if chunk and chunk.strip(" ,.;")
    ]
    return chunks or [raw_text]


def submit_speech_entries_batch(
    *,
    session: SpeechSubmissionSession,
    transcript: str,
    confidence_threshold: float = 0.9,
    teacher_name: str = '',
) -> dict:
    # Check for finalize signal in the overall transcript
    finalize_detected = contains_finalize_signal(transcript)

    # If the ENTIRE transcript is only "nimemaliza" with no student data, skip processing
    if is_finalize_only(transcript):
        logger.info(
            "submit_speech_entries_batch: finalize-only transcript detected session_id=%s transcript=%r",
            session.id,
            transcript,
        )
        return {
            "status": "saved",
            "mode": "batch",
            "saved_count": 0,
            "skipped_count": 0,
            "saved_entries": [],
            "skipped_entries": [],
            "session_finalized": False,
            "exam_finalized": False,
            "finalize_detected": True,
        }

    chunks = split_transcript_entries(transcript)
    if not chunks:
        raise SpeechSubmissionError(
            "Transcript is empty. Please record a clear voice entry with student names and marks."
        )

    # Filter out finalize-only chunks from the data chunks
    data_chunks = [chunk for chunk in chunks if not is_finalize_only(chunk)]
    if not data_chunks and chunks:
        # All chunks were finalize signals
        return {
            "status": "saved",
            "mode": "batch",
            "saved_count": 0,
            "skipped_count": 0,
            "saved_entries": [],
            "skipped_entries": [],
            "session_finalized": False,
            "exam_finalized": False,
            "finalize_detected": True,
        }

    saved_entries: list[dict] = []
    skipped_entries: list[dict] = []
    session_finalized = False
    exam_finalized = False

    # Only prefetch once for a fixed roster. In "open mode" (no roster —
    # students are auto-created from the teacher's speech as it's heard)
    # a later chunk must still see students an earlier chunk in this same
    # batch just created, so that path keeps querying fresh per chunk.
    roster_ids = session.roster_student_ids or []
    roster_students = (
        list(Student.objects.filter(id__in=roster_ids).order_by("first_name", "last_name"))
        if roster_ids else None
    )

    for chunk in data_chunks:
        try:
            result = submit_speech_entry(
                session=session,
                transcript=chunk,
                explicit_update=True,
                confidence_threshold=confidence_threshold,
                teacher_name=teacher_name,
                roster_students=roster_students,
            )
            saved_entries.append(result)
            if result.get("session_finalized"):
                session_finalized = True
            if result.get("exam_finalized"):
                exam_finalized = True
        except SpeechMatchReviewRequired as exc:
            skipped_entries.append(
                {
                    "transcript": chunk,
                    "error": str(exc),
                    "candidates": exc.candidates,
                }
            )
        except SpeechSubmissionError as exc:
            skipped_entries.append(
                {
                    "transcript": chunk,
                    "error": str(exc),
                    "candidates": [],
                }
            )

    if not saved_entries:
        raise SpeechSubmissionError(
            "Could not save any entries from this transcript. Please speak more clearly and separate students with pauses or full stops."
        )

    logger.info(
        "submit_speech_entries_batch: session_id=%s total_chunks=%s saved=%s skipped=%s session_finalized=%s exam_finalized=%s finalize_detected=%s",
        session.id,
        len(data_chunks),
        len(saved_entries),
        len(skipped_entries),
        session_finalized,
        exam_finalized,
        finalize_detected,
    )

    return {
        "status": "saved",
        "mode": "batch",
        "saved_count": len(saved_entries),
        "skipped_count": len(skipped_entries),
        "saved_entries": saved_entries,
        "skipped_entries": skipped_entries,
        "session_finalized": session_finalized,
        "exam_finalized": exam_finalized,
        "finalize_detected": finalize_detected,
    }


def _update_subject_submission(session: SpeechSubmissionSession, teacher_name: str = '') -> SubjectSubmission:
    """Create or update SubjectSubmission when a session is finalized via speech."""
    student_count = session.entries.count()
    existing = SubjectSubmission.objects.filter(
        exam=session.exam, subject=session.subject,
    ).first()
    new_rev = 1
    if existing and existing.status == SubjectSubmission.STATUS_RETURNED:
        new_rev = existing.revision_number + 1
        existing.delete()
    submission = SubjectSubmission.objects.create(
        exam=session.exam,
        subject=session.subject,
        status=SubjectSubmission.STATUS_SUBMITTED,
        method='SPEECH',
        submitted_by=teacher_name or session.teacher_name,
        submitted_at=timezone.now(),
        student_count=student_count,
        revision_number=new_rev,
    )
    return submission


@transaction.atomic
def maybe_finalize_exam(exam: Exam) -> bool:
    sessions = SpeechSubmissionSession.objects.filter(exam=exam)
    if not sessions.exists():
        return False

    if sessions.filter(status=SpeechSubmissionSession.STATUS_OPEN).exists():
        return False

    recompute_processed_results_for_exam(exam)
    return True


@transaction.atomic
def get_session_status(session: SpeechSubmissionSession, include_existing_marks: bool = False) -> dict:
    status_payload = {
        "session_id": session.id,
        "exam_id": session.exam_id,
        "subject_id": session.subject_id,
        "status": session.status,
        "submitted_count": session.submitted_count,
        "expected_student_count": session.effective_expected_count,
        "finalized_at": session.finalized_at,
        "teacher_name": session.teacher_name,
    }

    if include_existing_marks:
        entries = list(
            session.entries.select_related("student").order_by("-updated_at", "-id")
        )
        entry_student_ids = {entry.student_id for entry in entries}

        results_query = ExamResult.objects.filter(
            exam=session.exam,
            subject=session.subject,
        ).select_related("student").order_by("student__first_name", "student__last_name", "student__id")

        if session.roster_student_ids:
            results_query = results_query.filter(student_id__in=session.roster_student_ids)

        status_payload["existing_subject_marks"] = [
            {
                "student_id": result.student_id,
                "student_name": " ".join(
                    part for part in [result.student.first_name, result.student.middle_name, result.student.last_name] if part
                ),
                "score": result.score,
                "source": "speech_session" if result.student_id in entry_student_ids else "existing_result",
            }
            for result in results_query
        ]
        status_payload["saved_entries"] = [
            {
                "entry_id": entry.id,
                "student_id": entry.student_id,
                "student_name": " ".join(
                    part for part in [entry.student.first_name, entry.student.middle_name, entry.student.last_name] if part
                ),
                "score": entry.score,
                "updated_at": entry.updated_at,
            }
            for entry in entries
        ]

    return status_payload


def _parse_english_score_tokens(tokens: List[str]) -> Optional[int]:
    if not tokens:
        return None

    if len(tokens) == 1:
        return ENGLISH_NUMBER_WORDS.get(tokens[0])

    if len(tokens) == 2:
        first, second = tokens
        if first == "one" and second == "hundred":
            return 100
        if first in ENGLISH_NUMBER_WORDS and second in ENGLISH_ONES_WORDS:
            first_value = ENGLISH_NUMBER_WORDS[first]
            second_value = ENGLISH_ONES_WORDS[second]
            if first_value >= 20:
                return first_value + second_value
            if first_value < 20:
                return first_value + second_value
        if first in ENGLISH_ONES_WORDS and second in ENGLISH_ONES_WORDS:
            return ENGLISH_ONES_WORDS[first] * 10 + ENGLISH_ONES_WORDS[second]

    if len(tokens) == 3 and tokens[0] == "one" and tokens[1] == "hundred" and tokens[2] in ENGLISH_ONES_WORDS:
        return 100 + ENGLISH_ONES_WORDS[tokens[2]]

    if len(tokens) == 3 and tokens[1] == "hundred" and tokens[0] in ENGLISH_ONES_WORDS and tokens[2] in ENGLISH_ONES_WORDS:
        hundreds = ENGLISH_ONES_WORDS[tokens[0]] * 100
        return hundreds + ENGLISH_ONES_WORDS[tokens[2]]
    return None


def _fuzzy_match_swahili_number(token: str) -> Optional[int]:
    if token in SWAHILI_NUMBER_WORDS:
        return SWAHILI_NUMBER_WORDS[token]
    if token in SWAHILI_COMPOUND_NUMBER_WORDS:
        return SWAHILI_COMPOUND_NUMBER_WORDS[token]
    if token in SWAHILI_NUMBER_VARIANTS:
        canonical = SWAHILI_NUMBER_VARIANTS[token]
        if canonical in SWAHILI_NUMBER_WORDS:
            return SWAHILI_NUMBER_WORDS.get(canonical)
        return SWAHILI_COMPOUND_NUMBER_WORDS.get(canonical)

    similar_word, similarity = _best_swahili_number_similarity(token)
    if similar_word and similarity >= 0.82:
        logger.debug(
            "_fuzzy_match_swahili_number: fuzzy matched token=%r to word=%r similarity=%.3f",
            token,
            similar_word,
            similarity,
        )
        return _swahili_score_for_word(similar_word)
    return None


def _parse_swahili_score_tokens(tokens: List[str]) -> Optional[int]:
    if not tokens:
        return None

    if len(tokens) == 1:
        score = _fuzzy_match_swahili_number(tokens[0])
        if score is not None:
            logger.debug("_parse_swahili_score_tokens: single token %r -> %s", tokens[0], score)
        return score

    if len(tokens) == 2:
        first_score = _fuzzy_match_swahili_number(tokens[0])
        second_score = _fuzzy_match_swahili_number(tokens[1])
        if first_score is not None and second_score is not None:
            if first_score < 10 and second_score < 10:
                result = first_score * 10 + second_score
                logger.debug("_parse_swahili_score_tokens: two tokens %r -> %s", tokens, result)
                return result
        if tokens[0] == "mia" and second_score is not None:
            result = 100 + second_score
            logger.debug("_parse_swahili_score_tokens: mia tokens %r -> %s", tokens, result)
            return result

    if len(tokens) == 3 and tokens[1] == "na":
        tens_score = _fuzzy_match_swahili_number(tokens[0])
        unit_score = _fuzzy_match_swahili_number(tokens[2])
        if tens_score is not None and unit_score is not None:
            result = tens_score + unit_score
            logger.debug("_parse_swahili_score_tokens: 'na' tokens %r -> %s", tokens, result)
            return result

    return None


def _find_score_window(tokens: List[str]) -> Optional[tuple[int, int, int]]:
    if not tokens:
        return None

    best_match: Optional[tuple[int, int, int, int, int]] = None
    # tuple: (score, start_index, end_index, distance_from_end, window_size)
    token_count = len(tokens)

    max_window = min(5, token_count)
    for window_size in range(1, max_window + 1):
        for start_index in range(0, token_count - window_size + 1):
            end_index = start_index + window_size
            candidate = tokens[start_index:end_index]
            filtered_candidate = _strip_score_fillers(candidate)
            score = _parse_english_score_tokens(filtered_candidate)
            if score is None:
                score = _parse_swahili_score_tokens(filtered_candidate)
            if score is None or not 0 <= score <= 100:
                continue

            distance_from_end = token_count - end_index
            candidate_match = (score, start_index, end_index, distance_from_end, window_size)
            if best_match is None:
                best_match = candidate_match
                continue

            _, _, _, best_distance, best_window_size = best_match
            if distance_from_end < best_distance:
                best_match = candidate_match
                continue
            if distance_from_end == best_distance and window_size > best_window_size:
                best_match = candidate_match

    if best_match is None:
        return None

    score, start_index, end_index, _, _ = best_match
    return score, start_index, end_index


def _swahili_score_for_word(word: str) -> Optional[int]:
    if word in SWAHILI_NUMBER_WORDS:
        return SWAHILI_NUMBER_WORDS[word]
    if word in SWAHILI_COMPOUND_NUMBER_WORDS:
        return SWAHILI_COMPOUND_NUMBER_WORDS[word]
    return None


def _best_swahili_number_similarity(token: str) -> tuple[Optional[str], float]:
    candidates = list(SWAHILI_NUMBER_WORDS.keys()) + list(SWAHILI_COMPOUND_NUMBER_WORDS.keys())

    best_word: Optional[str] = None
    best_similarity = 0.0
    for candidate in candidates:
        similarity = SequenceMatcher(None, token, candidate).ratio()
        if similarity > best_similarity:
            best_word = candidate
            best_similarity = similarity

    return best_word, best_similarity


def recover_name_from_transcript(transcript: str, roster_students: Iterable[Student]) -> Optional[str]:
    normalized = normalize_text(transcript)
    if not normalized:
        return None

    tokens = [token for token in normalized.split() if token not in SCORE_FILLER_WORDS]
    if not tokens:
        return None

    ngram_candidates: list[str] = []
    token_count = len(tokens)
    for ngram_size in range(2, min(5, token_count + 1)):
        for start_index in range(0, token_count - ngram_size + 1):
            candidate = " ".join(tokens[start_index : start_index + ngram_size])
            ngram_candidates.append(candidate)

    # Also include the full transcript to catch cases where score removal was imperfect.
    ngram_candidates.append(" ".join(tokens))

    best_candidate_name: Optional[str] = None
    best_similarity = 0.0
    for candidate in ngram_candidates:
        for student in roster_students:
            student_name = normalize_student_name(student)
            similarity = _compare_names(candidate, student_name)
            if similarity > best_similarity:
                best_similarity = similarity
                best_candidate_name = student_name

    if best_candidate_name and best_similarity >= 0.72:
        logger.debug(
            "recover_name_from_transcript: matched candidate_name=%r similarity=%.3f transcript=%r",
            best_candidate_name,
            best_similarity,
            normalized,
        )
        return best_candidate_name

    logger.debug(
        "recover_name_from_transcript: no recovery transcript=%r best_similarity=%.3f",
        normalized,
        best_similarity,
    )
    return None


def _strip_score_fillers(tokens: List[str]) -> List[str]:
    filtered = [token for token in tokens if token not in SCORE_FILLER_WORDS]
    return filtered or tokens


def _parse_trailing_spaced_digits(tokens: List[str]) -> Optional[int]:
    if not tokens:
        return None

    digit_tokens: list[str] = []
    for token in reversed(tokens):
        if token.isdigit() and len(token) == 1:
            digit_tokens.append(token)
            continue
        break

    if not digit_tokens:
        return None

    score = int("".join(reversed(digit_tokens)))
    return score if 0 <= score <= 100 else None


def _trim_score_tokens(tokens: List[str]) -> List[str]:
    trimmed = list(tokens)
    while trimmed and trimmed[-1] in {"mark", "score", "is", "equals"}:
        trimmed.pop()

    if trimmed and trimmed[-1].isdigit() and len(trimmed[-1]) == 1:
        while trimmed and trimmed[-1].isdigit() and len(trimmed[-1]) == 1:
            trimmed.pop()
        return trimmed

    if trimmed and trimmed[-1].isdigit() and len(trimmed[-1]) > 1:
        trimmed.pop()
        return trimmed

    for window_size in range(min(4, len(trimmed)), 0, -1):
        candidate = trimmed[-window_size:]
        if _parse_english_score_tokens(candidate) is not None or _parse_swahili_score_tokens(candidate) is not None:
            return trimmed[:-window_size]

    return trimmed


def _normalize_name_tokens(tokens: List[str]) -> str:
    name_tokens = [token for token in tokens if token not in {"mark", "score", "is", "equals"}]
    return " ".join(name_tokens).strip()
