from __future__ import annotations

import logging
import os
from functools import lru_cache
from tempfile import NamedTemporaryFile
from typing import Optional

from django.core.exceptions import ValidationError


DEFAULT_MODEL_SIZE = os.getenv("SPEECH_RECOGNITION_MODEL_SIZE", "medium")
DEFAULT_SWAHILI_MODEL_SIZE = os.getenv("SPEECH_RECOGNITION_SWAHILI_MODEL_SIZE", "large-v3")
DEFAULT_DEVICE = os.getenv("SPEECH_RECOGNITION_DEVICE", "cpu")
DEFAULT_COMPUTE_TYPE = os.getenv("SPEECH_RECOGNITION_COMPUTE_TYPE", "int8")
DEFAULT_VAD_ENABLED = os.getenv("SPEECH_RECOGNITION_VAD_ENABLED", "true").lower() in {"1", "true", "yes"}
DEFAULT_EN_BEAM_SIZE = int(os.getenv("SPEECH_RECOGNITION_EN_BEAM_SIZE", "5"))
DEFAULT_SW_BEAM_SIZE = int(os.getenv("SPEECH_RECOGNITION_SW_BEAM_SIZE", "8"))
DEFAULT_EN_BEST_OF = int(os.getenv("SPEECH_RECOGNITION_EN_BEST_OF", "5"))
DEFAULT_SW_BEST_OF = int(os.getenv("SPEECH_RECOGNITION_SW_BEST_OF", "8"))
DEFAULT_HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("SPEECH_RECOGNITION_HF_TOKEN")
DEFAULT_LOCAL_FILES_ONLY = os.getenv("SPEECH_RECOGNITION_LOCAL_FILES_ONLY", "false").lower() in {"1", "true", "yes"}


logger = logging.getLogger(__name__)


class SpeechTranscriptionError(Exception):
    pass


@lru_cache(maxsize=4)
def _load_model(model_size: str = DEFAULT_MODEL_SIZE, device: str = DEFAULT_DEVICE, compute_type: str = DEFAULT_COMPUTE_TYPE):
    logger.info(
        "speech_asr: loading model model_size=%s device=%s compute_type=%s",
        model_size,
        device,
        compute_type,
    )
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - dependency error path
        raise SpeechTranscriptionError(
            "faster-whisper is not installed. Add it to requirements and install dependencies."
        ) from exc

    if DEFAULT_HF_TOKEN and not os.getenv("HF_TOKEN"):
        os.environ["HF_TOKEN"] = DEFAULT_HF_TOKEN

    try:
        return WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            local_files_only=DEFAULT_LOCAL_FILES_ONLY,
        )
    except Exception as exc:
        if DEFAULT_LOCAL_FILES_ONLY:
            raise SpeechTranscriptionError(
                "Model is not available in local cache while SPEECH_RECOGNITION_LOCAL_FILES_ONLY=true. "
                "Disable local-only mode once to download the model, then enable it again."
            ) from exc
        raise


SUPPORTED_LANGUAGES = {"en", "sw", "english", "swahili"}


def _normalize_language(language: Optional[str]) -> Optional[str]:
    if not language:
        raise SpeechTranscriptionError(
            "Language is required. Specify 'en' (English) or 'sw' (Swahili)."
        )
    language_lower = language.lower().strip()
    if language_lower in {"en", "english"}:
        return "en"
    if language_lower in {"sw", "swahili"}:
        return "sw"
    raise SpeechTranscriptionError(
        f"Unsupported language: {language}. Only English (en) or Swahili (sw) are supported."
    )


def _resolve_model_size(language: Optional[str]) -> str:
    if language == "sw":
        return DEFAULT_SWAHILI_MODEL_SIZE
    return DEFAULT_MODEL_SIZE


def _decode_profile(language: Optional[str]) -> dict:
    if language == "sw":
        return {
            "beam_size": DEFAULT_SW_BEAM_SIZE,
            "best_of": DEFAULT_SW_BEST_OF,
            "temperature": 0,
            "condition_on_previous_text": False,
        }
    return {
        "beam_size": DEFAULT_EN_BEAM_SIZE,
        "best_of": DEFAULT_EN_BEST_OF,
        "temperature": 0,
        "condition_on_previous_text": False,
    }


def _run_transcription(model, temp_path: str, *, normalized_language: Optional[str], initial_prompt: Optional[str], vad_enabled: bool, decode_profile: dict):
    return model.transcribe(
        temp_path,
        language=normalized_language,
        vad_filter=vad_enabled,
        initial_prompt=initial_prompt,
        beam_size=decode_profile["beam_size"],
        best_of=decode_profile["best_of"],
        temperature=decode_profile["temperature"],
        condition_on_previous_text=decode_profile["condition_on_previous_text"],
    )


_HALLUCINATION_PHRASES = [
    "muktadha wa shule",
    "taja jina la mwanafunzi kisha alama",
    "mfano wa jina la mwanafunzi",
    "mfano juma ali",
    "school context say the student name",
    "say the student name followed by mark",
    "example juma ali",
    "maneno ya alama sifuri",
    "jina la kwanza jina la kati",
]

_HALLUCINATION_EXACT = {
    "jina na alama",
    "name and score",
    "jina na alama.",
    "name and score.",
}

def _is_hallucination(transcript: str) -> bool:
    t = transcript.lower().strip().rstrip('.')
    # Exact match of our short prompts
    if t in _HALLUCINATION_EXACT:
        return True
    # Contains long known-bad phrases
    return any(phrase in t for phrase in _HALLUCINATION_PHRASES)


def transcribe_uploaded_audio(uploaded_file, language: Optional[str] = None) -> str:
    if not uploaded_file:
        raise ValidationError("No audio file provided.")

    suffix = os.path.splitext(getattr(uploaded_file, "name", "speech.webm"))[1] or ".webm"
    temp_path = None

    normalized_language = None
    if language:
        try:
            normalized_language = _normalize_language(language)
        except SpeechTranscriptionError:
            raise

    logger.info(
        "speech_asr: received upload name=%r size=%s content_type=%r language=%r normalized=%r",
        getattr(uploaded_file, "name", None),
        getattr(uploaded_file, "size", None),
        getattr(uploaded_file, "content_type", None),
        language,
        normalized_language,
    )

    # Keep prompts very short — long prompts cause Whisper to hallucinate them back
    initial_prompt = None
    if normalized_language == "sw":
        initial_prompt = "Jina na alama:"
    elif normalized_language == "en":
        initial_prompt = "Name and score:"

    try:
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)

        logger.debug("speech_asr: wrote temporary file path=%s suffix=%s", temp_path, suffix)

        decode_profile = _decode_profile(normalized_language)
        model_size = _resolve_model_size(normalized_language)
        try:
            model = _load_model(model_size=model_size)
        except Exception as exc:
            if normalized_language == "sw" and model_size != DEFAULT_MODEL_SIZE:
                logger.warning(
                    "speech_asr: failed loading preferred Swahili model=%s, falling back to model=%s. error=%s",
                    model_size,
                    DEFAULT_MODEL_SIZE,
                    exc,
                )
                model = _load_model(model_size=DEFAULT_MODEL_SIZE)
            else:
                raise
        
        vad_enabled = DEFAULT_VAD_ENABLED
        segments, _info = _run_transcription(
            model,
            temp_path,
            normalized_language=normalized_language,
            initial_prompt=initial_prompt,
            vad_enabled=vad_enabled,
            decode_profile=decode_profile,
        )

        transcript_parts = []
        segment_count = 0
        for segment in segments:
            segment_count += 1
            segment_text = (segment.text or "").strip()
            if segment_text:
                logger.debug(
                    "speech_asr: segment index=%s start=%s end=%s text=%r",
                    segment_count,
                    getattr(segment, "start", None),
                    getattr(segment, "end", None),
                    segment_text,
                )
                transcript_parts.append(segment_text)

        transcript = " ".join(transcript_parts).strip()
        
        if not transcript and vad_enabled and segment_count == 0:
            logger.warning(
                "speech_asr: vad_filter produced 0 segments, retrying without vad file=%r language=%r file_size=%s",
                getattr(uploaded_file, "name", None),
                language,
                getattr(uploaded_file, "size", None),
            )
            segments, _info = _run_transcription(
                model,
                temp_path,
                normalized_language=normalized_language,
                initial_prompt=initial_prompt,
                vad_enabled=False,
                decode_profile=decode_profile,
            )
            transcript_parts = []
            segment_count = 0
            for segment in segments:
                segment_count += 1
                segment_text = (segment.text or "").strip()
                if segment_text:
                    logger.debug(
                        "speech_asr: retry segment index=%s start=%s end=%s text=%r",
                        segment_count,
                        getattr(segment, "start", None),
                        getattr(segment, "end", None),
                        segment_text,
                    )
                    transcript_parts.append(segment_text)
            transcript = " ".join(transcript_parts).strip()
            logger.info("speech_asr: retry without vad produced segments=%s", segment_count)
        
        if not transcript:
            logger.warning(
                "speech_asr: no transcript produced file=%r language=%r segments=%s file_size=%s vad_enabled=%s",
                getattr(uploaded_file, "name", None),
                language,
                segment_count,
                getattr(uploaded_file, "size", None),
                vad_enabled,
            )
            raise SpeechTranscriptionError(
                "Sauti haikutambuliwa. Sema kwa sauti ya wazi karibu na maikrofoni."
            )

        if _is_hallucination(transcript):
            logger.warning(
                "speech_asr: hallucination detected — transcript matches initial_prompt file=%r transcript=%r",
                getattr(uploaded_file, "name", None),
                transcript,
            )
            raise SpeechTranscriptionError(
                "Sauti haikutambuliwa wazi. Sema tena: jina la mwanafunzi kisha alama."
            )

        logger.info(
            "speech_asr: transcribed file=%r language=%r segments=%s transcript=%r",
            getattr(uploaded_file, "name", None),
            language,
            segment_count,
            transcript,
        )
        return transcript
    except SpeechTranscriptionError:
        raise
    except Exception as exc:
        logger.exception("speech_asr: failed to transcribe file=%r language=%r", getattr(uploaded_file, "name", None), language)
        raise SpeechTranscriptionError(f"Failed to transcribe audio: {exc}") from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.debug("speech_asr: removed temporary file path=%s", temp_path)
            except OSError:
                pass
