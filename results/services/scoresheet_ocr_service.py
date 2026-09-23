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
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

VISION_MODEL_OPENROUTER = "google/gemini-2.5-flash"
GEMINI_MODEL = "gemini-3.6-flash"

MAX_DIMENSION = 1800
JPEG_QUALITY = 90
PDF_RENDER_SCALE = 2.5  # ~180 DPI — good balance of clarity and speed
# One subject's scoresheet for a big class runs 8-10 A4 pages (~25-30
# names/page). Capping at 5 silently dropped every page past the 5th, so
# a 230-student sheet only ever reached the AI for its first ~140 names —
# the rest came back flagged "no mark found". Keep a ceiling (a runaway
# upload shouldn't fan out to hundreds of vision calls) but a realistic one.
MAX_PDF_PAGES = 25
MAX_OCR_WORKERS = 8  # concurrent vision calls — bound API load / rate limits
# Without a Celery worker deployed (no REDIS_URL on Railway), every upload
# runs THIS call synchronously inside the web request, bounded by gunicorn's
# --timeout 300. At the old 180s-per-provider, one page failing on BOTH
# OpenRouter and Gemini alone burned 360s — past the gunicorn limit, killing
# the request with no error shown to the teacher (looked like an endless
# "Uploading..."). 60s comfortably covers a real vision response (usually
# a few seconds to ~20s) while keeping the worst single-page case (both
# providers failing) at 120s, safely inside the request timeout.
VISION_TIMEOUT_S = 60

PROMPT = (
    "This is a PHOTO of a scoresheet — a table with a row number column "
    "('Na.'), student names, and their marks written by a teacher "
    "(handwritten or typed). Read EVERY row carefully and extract the ROW "
    "NUMBER, NAME and SCORE for each student.\n\n"
    "Return ONLY a JSON array — no explanations — in this exact format:\n"
    '[{"row": 1, "name": "Full Name", "score": 78}, '
    '{"row": 2, "name": "Another Name", "score": 8}, '
    '{"row": 3, "name": "Absent Student", "score": "X"}, '
    '{"row": 4, "name": "Zero Score", "score": 0}, '
    '{"row": 5, "name": "Does Not Sit Subject", "score": "BLANK"}]\n\n'
    "CRITICAL RULES — follow exactly:\n"
    "1. ROW NUMBER: Copy the printed number from the 'Na.' column exactly. "
    "EVERY printed row must appear exactly once in your output, in order, "
    "even if its score cell is empty — see rule 3.\n"
    "2. SCORES: Read the exact number. '00' = 0, '08' = 8, '05' = 5, '10' = 10. "
    "NEVER change the number — write EXACTLY what is written.\n"
    "3. ABSENT MARKS: If you see 'X', 'XX', 'x', 'xx', a cross mark (✕), "
    "a checkmark, or any non-numeric symbol in the SCORE cell, "
    "set score to 'X' (meaning absent — student did not take the exam). "
    "This applies EVERYWHERE you see it: score column, next to the name, "
    "or anywhere on the row that indicates absence.\n"
    "4. If the score cell is EMPTY, BLANK, or has a dash '-', set score to "
    "'BLANK' — do NOT skip or omit the row. Every printed row must be "
    "reported, blank ones included, so the row count always matches the "
    "printed sheet.\n"
    "4a. AN EMPTY CELL IS NOT A MARK. If the score cell is empty, you MUST "
    "report 'BLANK' — NEVER write a number for an empty cell, never copy a "
    "neighbouring row's mark, and never guess from handwriting elsewhere "
    "on the page. A row with no visible mark must come back as 'BLANK'.\n"
    "5. IGNORE headers, dates, signatures, and ID numbers — but never a row "
    "that has a printed row number and a name, even with a blank score.\n"
    "6. Scores must be integers between 0 and 100, 'X' for absent, or "
    "'BLANK' for empty.\n"
    "7. NEVER invent names or scores — write ONLY what you see.\n"
    "8. Read each name COMPLETELY — do NOT cut off or abbreviate names.\n"
    "9. A score of '0' (zero) is a valid score — include it.\n"
    "10. For handwritten scores: look very carefully at each digit. "
    "A '1' can look like '7', a '6' can look like '8', a '3' can look like '8'. "
    "Double-check each digit against its neighbors.\n"
    "11. COMMON CONFUSIONS to watch for:\n"
    "    - '0' vs 'O' (letter O) — if it's in the score column, it's 0\n"
    "    - '1' vs 'l' (lowercase L) vs 'I' (uppercase i) — in scores it's 1\n"
    "    - 'X' vs 'x' vs '✕' vs '✗' vs a cross/tick mark — all mean ABSENT"
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
        # iPhones and newer Androids save camera photos as HEIC/HEIF, which
        # PIL cannot open on its own — pillow-heif registers the format
        # when available. Without this, a teacher photographing a
        # scoresheet on such a phone gets "Picha haikusomeka" every time.
        heif_img = _open_with_pillow_heif(uploaded_file)
        if heif_img is not None:
            return [heif_img]
        raise ScoreSheetOCRError("Picha haikusomeka. Jaribu picha nyingine.") from exc
    return [img]


def _open_with_pillow_heif(uploaded_file):
    """Best-effort HEIC/HEIF decode via pillow-heif. Returns the RGB image
    or None when the library is missing or the file isn't HEIF at all."""
    try:
        from pillow_heif import register_heif_opener
    except ImportError:
        return None
    try:
        register_heif_opener()
        uploaded_file.seek(0)
        img = Image.open(uploaded_file)
        return img.convert("RGB")
    except Exception:
        return None


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
    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()
    # Try to find a JSON array [...]
    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass  # Try other strategies below

    # Fallback: try to find individual {"name":..., "score":...} objects
    objects = re.findall(r'\{[^{}]*"name"[^{}]*"score"[^{}]*\}', cleaned, re.DOTALL)
    if objects:
        parsed = []
        for obj_str in objects:
            try:
                obj = json.loads(obj_str)
                if isinstance(obj, dict) and "name" in obj and "score" in obj:
                    parsed.append(obj)
            except json.JSONDecodeError:
                continue
        if parsed:
            return parsed

    # Last resort: AI returned conversational text — try to extract any numbers
    # near names (e.g., "John Doe 85" or "John Doe: 85")
    lines = text.split('\n')
    fallback_rows = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Match patterns like: "Name Score" or "Name: Score" or "Name - Score"
        m = re.match(r'^([A-Za-z\s\.]+?)\s*[:\-]?\s*(\d{1,3})\s*$', line)
        if m:
            name = m.group(1).strip()
            score = int(m.group(2))
            if 0 <= score <= 100 and len(name) >= 3:
                fallback_rows.append({"name": name, "score": score})
    if fallback_rows:
        return fallback_rows

    raise ScoreSheetOCRError(
        f"AI haikurudisha muundo sahihi wa JSON.\n"
        f"Jibu la AI: {text[:500]}"
    )


def _clean_row_number(raw_row) -> "int | None":
    try:
        n = int(str(raw_row).strip())
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _clean_rows(raw_rows: list) -> list[dict]:
    """Normalise raw OCR rows into [{raw_name, score, is_absent, row, blank}, ...].

    Handles:
    - Numeric scores (including leading zeros like '00' → 0, '08' → 8)
    - 'X' / 'XX' → is_absent=True, score=0
    - Blank / dash / empty → blank=True, score=None (student doesn't study
      this subject) — kept, NOT dropped, so callers can tell "this printed
      row was genuinely empty" apart from "the AI never reported this row
      at all" (the latter usually means a mark was missed, not that the
      student doesn't take the subject).
    - 'row': the printed "Na." serial number, when the AI reported one —
      lets callers anchor a row back to the exact roster position the
      scoresheet PDF was generated from, instead of relying only on a
      re-typed name matching back to the roster.
    """
    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue

        row_no = _clean_row_number(item.get("row"))
        raw_score = item.get("score")
        is_absent = False

        # ── Blank / dash / empty → keep as an explicit blank row ───────
        if raw_score is None:
            rows.append({"raw_name": name, "score": None, "is_absent": False, "row": row_no, "blank": True})
            continue
        raw_str = str(raw_score).strip()
        if raw_str in ('', '-', '--', 'null', 'None') or raw_str.upper() == 'BLANK':
            rows.append({"raw_name": name, "score": None, "is_absent": False, "row": row_no, "blank": True})
            continue

        # ── X / XX / cross marks → absent ──────────────────────────
        # Handle all variations: X, x, XX, xx, ✕, ✗, ✓, ✓✓, tick, cross
        absent_patterns = ('x', 'xx', 'xxx', '✕', '✗', '✗✗', '✓', '✓✓',
                           'tick', 'cross', 'absent', 'abs')
        if raw_str.lower() in absent_patterns or raw_str in ('✕', '✗', '✓'):
            is_absent = True
            score = 0
        else:
            # ── Numeric score (may have leading zeros) ────────────────
            try:
                # int('00') → 0, int('08') → 8, int('10') → 10
                score = int(raw_str)
            except (TypeError, ValueError):
                # Last resort: strip non-numeric chars (e.g. '78.' → '78')
                cleaned = re.sub(r'[^\d]', '', raw_str)
                if not cleaned:
                    continue
                try:
                    score = int(cleaned)
                except ValueError:
                    continue

        if score < 0 or score > 100:
            continue

        rows.append({"raw_name": name, "score": score, "is_absent": is_absent, "row": row_no, "blank": False})
    return rows


def _call_openrouter_vision(image_bytes: bytes, mime_type: str, api_key: str, max_tokens: int = 4096, prompt: str = PROMPT) -> str:
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
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=VISION_TIMEOUT_S)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter vision error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    choice = data.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("OpenRouter vision: empty response")
    # Truncation detection: output ikifika max_tokens kabla model haijaisha,
    # mistari ya mwisho ya ukurasa inatupwa kimya-kimya — walimu wanaona
    # wanafunzi wa mwisho "hana alama" wakati karatasi ina. finish_reason
    # 'length' inatuambia waziwazi tukatika, retry na ceiling kubwa.
    if choice.get("finish_reason") == "length":
        raise RuntimeError("OR_TRUNCATED")
    return content


def _call_gemini_vision(image_bytes: bytes, mime_type: str, api_key: str, prompt: str = PROMPT) -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": mime_type, "data": b64}},
                ]
            }
        ],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 16384},
    }
    resp = requests.post(url, json=payload, timeout=VISION_TIMEOUT_S)
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


def _read_page_with_ai(img, prompt: str = PROMPT) -> str:
    """OpenRouter first, Gemini fallback — one rendered page/photo in, raw
    model text out. Raises RuntimeError if both providers fail.
    `prompt` lets other vision tasks (roster scan) reuse this provider
    chain with their own instructions."""
    image_bytes = _encode_jpeg(img)
    mime_type = "image/jpeg"

    or_error = None
    if OPENROUTER_API_KEY:
        try:
            logger.info("[ScoreSheetOCR] Trying OpenRouter (%s)", VISION_MODEL_OPENROUTER)
            text = _call_openrouter_vision(image_bytes, mime_type, OPENROUTER_API_KEY, prompt=prompt)
            logger.info("[ScoreSheetOCR] OpenRouter success")
            return text
        except Exception as exc:
            or_error = exc
            logger.warning("[ScoreSheetOCR] OpenRouter failed: %s", exc)
            # Low account balance: OpenRouter reserves budget for the full
            # max_tokens ceiling up front, not actual usage — a low-balance
            # account can still afford this task's genuinely small JSON
            # output if we ask for a lower ceiling. Retry once with
            # whatever it says it can afford.
            afford_match = re.search(r"can only afford (\d+)", str(exc))
            if afford_match:
                affordable = int(afford_match.group(1))
                # Retry with whatever OpenRouter says it can afford — even 18
                # tokens is enough for a tiny JSON response.  The vision
                # request is the expensive part (input); the output is tiny.
                if affordable >= 10:
                    try:
                        logger.info("[ScoreSheetOCR] Retrying OpenRouter with max_tokens=%s", affordable)
                        text = _call_openrouter_vision(image_bytes, mime_type, OPENROUTER_API_KEY, max_tokens=affordable, prompt=prompt)
                        logger.info("[ScoreSheetOCR] OpenRouter retry success")
                        return text
                    except Exception as retry_exc:
                        or_error = retry_exc
                        logger.warning("[ScoreSheetOCR] OpenRouter retry failed: %s", retry_exc)

    gemini_error = None
    if GOOGLE_API_KEY:
        try:
            logger.info("[ScoreSheetOCR] Trying Gemini (fallback)")
            text = _call_gemini_vision(image_bytes, mime_type, GOOGLE_API_KEY, prompt=prompt)
            logger.info("[ScoreSheetOCR] Gemini success")
            return text
        except Exception as exc:
            gemini_error = exc
            logger.warning("[ScoreSheetOCR] Gemini failed: %s", exc)

    if not (or_error or gemini_error):
        raise RuntimeError("No AI provider configured")
    # Watumiaji waliona JSON ghafi ya Gemini tu ("401 … OAuth 2 access
    # token …") wakati chanzo halisi kilikuwa pia salio la OpenRouter
    # kuisha. Eleza kila mtoa huduma kwa lugha rahisi + nini cha kufanya.
    reasons = []
    if or_error:
        reasons.append("OpenRouter: " + _explain_ai_error(or_error))
    if gemini_error:
        reasons.append("Gemini: " + _explain_ai_error(gemini_error))
    raise RuntimeError(" | ".join(reasons)) from (gemini_error or or_error)


def _explain_ai_error(exc) -> str:
    """Kosa la mtoa huduma wa AI → sentensi fupi ya Kiswahili yenye suluhisho.
    'OR_TRUNCATED' inabaki kwenye maandishi ili retry iendelee kuitambua."""
    msg = str(exc)
    low = msg.lower()
    if msg == "OR_TRUNCATED":
        return "jibu lilikatika katikati (OR_TRUNCATED)"
    if " 402" in msg or "insufficient credits" in low or "can only afford" in low:
        return "salio limeisha (402) — ongeza credits: openrouter.ai/settings/credits"
    if " 401" in msg or " 403" in msg or "api key not valid" in low or "unauthenticated" in low:
        return ("ufunguo wa API kwenye server si sahihi (401) — weka ufunguo sahihi "
                "kwenye Railway → Variables")
    if " 429" in msg or "quota" in low or "rate limit" in low:
        return "kikomo cha matumizi kimefikiwa (429) — subiri dakika chache ujaribu tena"
    if "timed out" in low or "timeout" in low:
        return "imechelewa kujibu (mtandao) — jaribu tena"
    return msg[:160]


def check_ocr_health() -> dict:
    """Quick check: are API keys set and do they work?"""
    status = {
        'openrouter': bool(OPENROUTER_API_KEY),
        'gemini': bool(GOOGLE_API_KEY),
    }
    # Quick OpenRouter ping
    if OPENROUTER_API_KEY:
        try:
            resp = requests.get(
                'https://openrouter.ai/api/v1/models',
                headers={'Authorization': f'Bearer {OPENROUTER_API_KEY}'},
                timeout=10,
            )
            status['openrouter_ok'] = resp.status_code == 200
            if resp.status_code != 200:
                status['openrouter_error'] = f'HTTP {resp.status_code}'
        except Exception as e:
            status['openrouter_ok'] = False
            status['openrouter_error'] = str(e)
    return status


def extract_scores_from_document(uploaded_file) -> list[dict]:
    """Returns [{"raw_name": str, "score": int}, ...] read from the upload —
    a single photo, or every page of a scanned PDF (each page's rows are
    concatenated, since a multi-page scoresheet just continues the list).

    Pages are sent to the vision API concurrently — each is an independent,
    slow (up to 180s) HTTP call, so a 3-5 page scoresheet reading pages one
    at a time could take minutes; reading them in parallel bounds the wait
    to roughly the slowest single page instead of the sum of all of them."""
    if not (OPENROUTER_API_KEY or GOOGLE_API_KEY):
        raise ScoreSheetOCRError(
            "Hakuna AI provider iliyosanidiwa. Weka OPENROUTER_API_KEY au GOOGLE_API_KEY kwenye .env"
        )

    pages = _load_page_images(uploaded_file)

    def _read_page_with_retry(img, page_num):
        """Soma ukurasa mmoja; ukikataika (truncation au network blip) jaribu
        tena mara 1. Truncation ndiyo ilikuwa inamwaga wanafunzi wa mwisho
        wa kila ukurasa — max_tokens ya chini + retry bila kubadilisha
        ceiling haikusaidii chochote, hivyo retry ya pili ina ceiling kubwa."""
        last_exc = None
        for attempt in range(2):
            try:
                return _read_page_with_ai(img) if attempt == 0 else _read_page_with_ai(
                    img, prompt=PROMPT,
                )
            except RuntimeError as exc:
                last_exc = exc
                is_truncation = 'OR_TRUNCATED' in str(exc)
                if not is_truncation and attempt == 0:
                    # Network/timeout blip — jaribu tena mara moja
                    continue
                if is_truncation and attempt == 0:
                    # Truncated — retry ina handled kwenye _read_page_with_ai
                    # kupitia OpenRouter affordability retry; kama bado
                    # inakatika, tunairudisha kama failure ya ukurasa.
                    continue
                raise
        raise last_exc

    page_results: list[tuple[str | None, Exception | None]] = [(None, None)] * len(pages)
    with ThreadPoolExecutor(max_workers=min(len(pages), MAX_OCR_WORKERS)) as pool:
        future_to_index = {pool.submit(_read_page_with_retry, img, i + 1): i for i, img in enumerate(pages)}
        for future in as_completed(future_to_index):
            i = future_to_index[future]
            try:
                page_results[i] = (future.result(), None)
            except Exception as exc:
                page_results[i] = (None, exc)

    all_rows: list[dict] = []
    last_error = None
    failed_pages: list[int] = []
    for page_num, (text, exc) in enumerate(page_results, 1):
        if exc is not None:
            last_error = exc
            failed_pages.append(page_num)
            logger.warning("[ScoreSheetOCR] Page %d failed: %s", page_num, exc)
            continue
        logger.info("[ScoreSheetOCR] Page %d AI response (first 500 chars): %s", page_num, text[:500])
        raw_rows = _extract_json_array(text)
        logger.info("[ScoreSheetOCR] Page %d extracted %d raw rows", page_num, len(raw_rows))
        cleaned = _clean_rows(raw_rows)
        logger.info("[ScoreSheetOCR] Page %d cleaned rows: %s", page_num, cleaned)
        all_rows.extend(cleaned)

    if failed_pages and all_rows:
        # Ukurasa mmoja au zaidi zimefaili lakini wengine wamesoma —
        # makusudi hatutoi error: rows zilizopatikana ni za kweli, na
        # mwalimu ataona wanafunzi wasiojazwa kwenye UI (missing rows).
        # Error kamili hapa ingemfanya apakie upya kila kitu bila sababu.
        logger.warning(
            "[ScoreSheetOCR] Pages %s failed but %d rows were read from other pages — "
            "returning partial results; teacher will see unfilled rows in the UI",
            failed_pages, len(all_rows),
        )

    if not all_rows:
        if last_error:
            logger.error(
                "[ScoreSheetOCR] ALL pages failed. Last error: %s | API keys: OPENROUTER=%s, GEMINI=%s",
                last_error,
                'set' if OPENROUTER_API_KEY else 'MISSING',
                'set' if GOOGLE_API_KEY else 'MISSING',
            )
            raise ScoreSheetOCRError(
                f"Imeshindwa kusoma faili — jaribu tena au jaza alama mwenyewe.\n"
                f"Sababu: {last_error}"
            ) from last_error
        raise ScoreSheetOCRError(
            "Hakuna jina/alama iliyotambulika kwenye faili. Hakikisha picha/PDF iko wazi na jaribu tena."
        )
    logger.info("[ScoreSheetOCR] FINAL: %d rows total", len(all_rows))
    for i, r in enumerate(all_rows[:10], 1):  # Log first 10 rows
        logger.info("[ScoreSheetOCR] Row %d: name=%r score=%s absent=%s", i, r['raw_name'], r['score'], r.get('is_absent'))
    return all_rows
