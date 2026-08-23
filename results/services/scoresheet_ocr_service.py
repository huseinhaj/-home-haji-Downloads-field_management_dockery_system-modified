"""Scoresheet Upload — mwalimu anapakia picha (au PDF iliyochanganuliwa/
scanned) ya scoresheet aliyoijaza kwa mkono, mfumo unatumia AI (vision
model) kusoma majina na alama kwenye kila ukurasa.

Chain: OpenRouter (google/gemini-2.5-flash, vision) -> Gemini direct HTTP
(FREE fallback) -- inafanana na chain ya curriculum/ai_utils.py lakini hii
inatuma picha (multimodal), si maandishi tu.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

VISION_MODEL_OPENROUTER = "google/gemini-2.5-flash"
GEMINI_MODEL = "gemini-2.5-flash"

MAX_DIMENSION = 1600
JPEG_QUALITY = 85
PDF_RENDER_SCALE = 2.0  # ~144 DPI — clear enough for handwriting without huge files
MAX_PDF_PAGES = 5  # a single subject's scoresheet is never a 20-page document

PROMPT = (
    "Hii ni picha ya scoresheet — jedwali la wanafunzi na alama zao "
    "walizoandika mwalimu kwa mkono au kuchapa. Soma kila mstari na "
    "utoe JINA na ALAMA (0-100) ya kila mwanafunzi.\n\n"
    "Rudisha JSON array TU, bila maelezo mengine, kwa muundo huu hasa:\n"
    '[{"name": "Jina Kamili", "score": 78}, {"name": "Jina Lingine", "score": 55}]\n\n'
    "Kanuni:\n"
    "- Puuza vichwa vya habari, sahihi, tarehe, na mistari isiyo na jina+alama.\n"
    "- Alama lazima iwe nambari kati ya 0 na 100.\n"
    "- Kama huwezi kusoma alama ya mstari fulani kwa uhakika, ruka mstari huo.\n"
    "- Usibuni majina au alama — andika kile kilichoandikwa tu."
)


class ScoreSheetOCRError(Exception):
    pass


def _is_pdf(uploaded_file) -> bool:
    name = (getattr(uploaded_file, "name", "") or "").lower()
    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if name.endswith(".pdf") or content_type == "application/pdf":
        return True
    uploaded_file.seek(0)
    header = uploaded_file.read(5)
    uploaded_file.seek(0)
    return header == b"%PDF-"


def _load_page_images(uploaded_file) -> list:
    """Returns a list of PIL Images — one per page for a PDF, or a single
    entry for a photo. Handles BOTH a plain photo and a scanned PDF the
    same way from here on: everything downstream just sees page images."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - pillow is a hard requirement
        raise ScoreSheetOCRError("Pillow haijasanidiwa kwenye seva.") from exc

    if _is_pdf(uploaded_file):
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:  # pragma: no cover - pypdfium2 is a hard requirement
            raise ScoreSheetOCRError("Usomaji wa PDF haujasanidiwa kwenye seva.") from exc

        uploaded_file.seek(0)
        try:
            pdf = pdfium.PdfDocument(uploaded_file.read())
        except Exception as exc:
            raise ScoreSheetOCRError("PDF haikusomeka. Jaribu faili nyingine.") from exc

        page_count = min(len(pdf), MAX_PDF_PAGES)
        if page_count == 0:
            raise ScoreSheetOCRError("PDF haina ukurasa wowote.")
        images = []
        for i in range(page_count):
            bitmap = pdf[i].render(scale=PDF_RENDER_SCALE)
            images.append(bitmap.to_pil().convert("RGB"))
        pdf.close()
        return images

    uploaded_file.seek(0)
    try:
        img = Image.open(uploaded_file)
        img = img.convert("RGB")
    except Exception as exc:
        raise ScoreSheetOCRError("Picha haikusomeka. Jaribu picha nyingine.") from exc
    return [img]


def _encode_jpeg(img) -> bytes:
    """Resize to a max dimension and re-encode as JPEG — keeps the request
    small/fast regardless of how large the original photo/PDF page is."""
    width, height = img.size
    if max(width, height) > MAX_DIMENSION:
        scale = MAX_DIMENSION / max(width, height)
        img = img.resize((max(1, int(width * scale)), max(1, int(height * scale))))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def _extract_json_array(text: str) -> list:
    if not text:
        raise ScoreSheetOCRError("AI haikurudisha jibu.")
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()
    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if not match:
        raise ScoreSheetOCRError("AI haikurudisha muundo sahihi wa JSON.")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ScoreSheetOCRError("AI haikurudisha JSON sahihi.") from exc
    if not isinstance(data, list):
        raise ScoreSheetOCRError("AI haikurudisha orodha (list).")
    return data


def _clean_rows(raw_rows: list) -> list[dict]:
    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        score = item.get("score")
        try:
            score = int(score)
        except (TypeError, ValueError):
            continue
        if not name or score < 0 or score > 100:
            continue
        rows.append({"raw_name": name, "score": score})
    return rows


def _call_openrouter_vision(image_bytes: bytes, mime_type: str, api_key: str) -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tlm-tanzania.railway.app",
        "X-Title": "TLM Tanzania - Field Management Results",
    }
    payload = {
        "model": VISION_MODEL_OPENROUTER,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter vision error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("OpenRouter vision: empty response")
    return content


def _call_gemini_vision(image_bytes: bytes, mime_type: str, api_key: str) -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": PROMPT},
                    {"inlineData": {"mimeType": mime_type, "data": b64}},
                ]
            }
        ],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
    }
    resp = requests.post(url, json=payload, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini vision error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini vision: no candidates")
    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    if not text:
        raise RuntimeError("Gemini vision: empty response")
    return text


def _read_page_with_ai(img) -> str:
    """OpenRouter first, Gemini fallback — one rendered page/photo in, raw
    model text out. Raises RuntimeError if both providers fail."""
    image_bytes = _encode_jpeg(img)
    mime_type = "image/jpeg"

    or_error = None
    if OPENROUTER_API_KEY:
        try:
            logger.info("[ScoreSheetOCR] Trying OpenRouter (%s)", VISION_MODEL_OPENROUTER)
            text = _call_openrouter_vision(image_bytes, mime_type, OPENROUTER_API_KEY)
            logger.info("[ScoreSheetOCR] OpenRouter success")
            return text
        except Exception as exc:
            or_error = exc
            logger.warning("[ScoreSheetOCR] OpenRouter failed: %s", exc)

    if GOOGLE_API_KEY:
        try:
            logger.info("[ScoreSheetOCR] Trying Gemini (fallback)")
            text = _call_gemini_vision(image_bytes, mime_type, GOOGLE_API_KEY)
            logger.info("[ScoreSheetOCR] Gemini success")
            return text
        except Exception as exc:
            logger.warning("[ScoreSheetOCR] Gemini failed: %s", exc)
            raise RuntimeError(str(exc)) from (or_error or exc)

    raise RuntimeError(str(or_error) if or_error else "No AI provider configured")


def extract_scores_from_document(uploaded_file) -> list[dict]:
    """Returns [{"raw_name": str, "score": int}, ...] read from the upload —
    a single photo, or every page of a scanned PDF (each page's rows are
    concatenated, since a multi-page scoresheet just continues the list)."""
    if not (OPENROUTER_API_KEY or GOOGLE_API_KEY):
        raise ScoreSheetOCRError(
            "Hakuna AI provider iliyosanidiwa. Weka OPENROUTER_API_KEY au GOOGLE_API_KEY kwenye .env"
        )

    pages = _load_page_images(uploaded_file)

    all_rows: list[dict] = []
    last_error = None
    any_page_succeeded = False
    for page_img in pages:
        try:
            text = _read_page_with_ai(page_img)
        except Exception as exc:
            last_error = exc
            continue
        any_page_succeeded = True
        raw_rows = _extract_json_array(text)
        all_rows.extend(_clean_rows(raw_rows))

    if not any_page_succeeded:
        raise ScoreSheetOCRError(
            "Imeshindwa kusoma faili — jaribu tena au jaza alama mwenyewe."
        ) from last_error

    if not all_rows:
        raise ScoreSheetOCRError(
            "Hakuna jina/alama iliyotambulika kwenye faili. Hakikisha picha/PDF iko wazi na jaribu tena."
        )
    return all_rows
