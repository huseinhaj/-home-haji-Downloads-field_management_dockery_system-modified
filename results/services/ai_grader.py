"""
AI Grader ya Sahishi — karatasi HALISI za wanafunzi.

Tofauti na OMR (bubbles tu), hii inasoma karatasi za kweli zenye:
  - jina + namba ya mwanafunzi yaliyoandikwa kwa mkono
  - maswali ya aina zote: matching, select, list, fupi, essay, calculations

Chain ile ile ya scoresheet_ocr_service: Gemini direct (FREE) → OpenRouter
(google/gemini-2.5-flash, vision) fallback. Inapeleka:
  picha za MARKING SCHEME (mwalimu alizopakia) + picha ya KARATASI
  → JSON yenye alama kwa kila swali + jina/reg ya mwanafunzi.

Inarudi:
{
  "student_name": "Amina Juma",
  "reg_number": "S0451",
  "questions": [
     {"q": 1, "score": 5, "max": 5, "correct": true,
      "note": "sahihi", "bbox": [12.5, 30.0]},   # % ya ukurasa (x, y)
     ...
  ],
  "total": 23, "max_total": 30
}
"""
from __future__ import annotations

import base64
import difflib
import io
import json
import logging
import os
import re
import time

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _read_key(name: str) -> str:
    """Soma ufunguo wa API na kuusafisha. Dashboard za Railway na copy-paste
    hupeleka nafasi au alama za semi pamoja na ufunguo, na hiyo hufanya
    Google/OpenRouter ikatae kama ufunguo si sahihi."""
    raw = os.getenv(name) or ""
    return raw.strip().strip('"').strip("'").strip()


OPENROUTER_API_KEY = _read_key("OPENROUTER_API_KEY")
GOOGLE_API_KEY = _read_key("GOOGLE_API_KEY")

# OpenRouter 401 "User not found" = ufunguo/akaunti imefutwa au imezimwa.
# Hali hii haibadiliki kwa karatasi inayofuata, kwa hiyo tunaikwepa kwa
# muda mfupi badala ya kuipigia kila picha (na kupoteza sekunde kila mara).
_OR_DISABLED_UNTIL = 0.0
_OR_COOLDOWN_S = 900  # dakika 15


def _openrouter_usable() -> bool:
    return bool(OPENROUTER_API_KEY) and time.monotonic() > _OR_DISABLED_UNTIL


def _disable_openrouter(seconds: int = _OR_COOLDOWN_S) -> None:
    global _OR_DISABLED_UNTIL
    _OR_DISABLED_UNTIL = time.monotonic() + seconds


def _is_openrouter_dead(exc) -> bool:
    msg = str(exc).lower()
    return any(t in msg for t in (
        " 401", "user not found", " 403", "account deactivated",
        "no auth credentials",
    ))


VISION_MODEL_OPENROUTER = "google/gemini-2.5-flash"

# Google hufunga modeli za zamani na huweka modeli moja kwenye "high demand"
# (503) wakati nyingine zinajibu. Kwa hiyo tunajaribu mnyororo huu hadi moja
# ifanye kazi; GEMINI_MODEL env inabadilisha ya kwanza.
GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "").strip().strip('"').strip("'").strip() or "gemini-3.5-flash"
GEMINI_FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
]


def _gemini_models() -> list:
    seen = []
    for name in [GEMINI_MODEL] + GEMINI_FALLBACK_MODELS:
        name = (name or "").strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def _gemini_model_retryable(exc) -> bool:
    """503/429/404 = modeli imejaa/haipo, jaribu inayofuata. 400/401/403 =
    ufunguo au ombi linakataliwa, kubadilisha modeli hakutasaidia."""
    msg = str(exc).lower()
    # Mtandao/DNS/timeout: kubadilisha modeli hakutatui na kungerudia
    # modeli 8 × sekunde 60 kunavuka kikomo cha gunicorn. Achana mara moja.
    if any(t in msg for t in (
        "timed out", "timeout", "connection", "connect", "dns",
        "resolve", "name resolution", "eof", "reset", "refused",
        "unreachable",
    )):
        return False
    if any(t in msg for t in (
        " 400", " 401", " 403", "unauthenticated", "permission_denied",
        "api key not valid", "api_key_invalid",
    )):
        return False
    return True

VISION_TIMEOUT_S = 90
MAX_TOKENS = 4000
MAX_DIMENSION = 1800
JPEG_QUALITY = 88

PROMPT = """You are an exam grading assistant (red pen). You will receive:
1. One or more images of the MARKING SCHEME (model answers with marks allocation).
2. ONE image of a STUDENT'S ANSWER SHEET (answers handwritten or typed).

The student wrote their NAME and ADMISSION/REG NUMBER at the top of the sheet.

Grade EVERY question you can see on the STUDENT SHEET against the marking scheme:
- Multiple choice / matching / true-false: exact match only.
- Short answers / lists: accept equivalent wording, spelling tolerant; award
  partial marks exactly as the scheme allocates.
- Calculations: follow the scheme's mark breakdown (method marks even if the
  final answer is wrong).
- Essays: award marks per the scheme's points; be fair and consistent.
- Unanswered question: score 0.

Return ONLY a JSON object — no markdown fences, no explanations — exactly:
{
  "student_name": "<name as written on the sheet>",
  "reg_number": "<reg number as written, empty if not visible>",
  "questions": [
    {"q": 1, "score": 5, "max": 5, "correct": true, "note": "<very short reason>",
     "bbox": [X, Y]},
    {"q": 2, "score": 2, "max": 3, "correct": false, "note": "<why marks lost>",
     "bbox": [X, Y]}
  ],
  "total": 23,
  "max_total": 30
}

RULES:
1. "q" = the question number as printed on the student sheet.
2. "bbox" = position of the START of the student's answer for that question on
   the STUDENT SHEET image, as PERCENTAGES of page width/height (X: 0-100 left
   to right, Y: 0-100 top to bottom). Always include it.
3. "correct" = true only if full marks.
4. Never invent answers — grade only what is actually written.
5. "total" = sum of scores; "max_total" = sum of max.
6. If the sheet has no visible answers, return empty "questions" list.
"""


class AIGradeError(Exception):
    pass


def _jpeg_bytes(image_bytes: bytes) -> bytes:
    """Decode scan (jpg/png/tiff...) → normalized JPEG (ndogo, nzito vizuri)."""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")
    w, h = img.size
    scale = MAX_DIMENSION / max(w, h)
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def _call_openrouter_multi(image_jpegs: list[bytes], prompt: str) -> str:
    b64s = [
        {"type": "image_url",
         "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(b).decode('ascii')}"}}
        for b in image_jpegs
    ]
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tlm-tanzania.railway.app",
        "X-Title": "TLM Tanzania - Sahishi AI Grader",
    }
    payload = {
        "model": VISION_MODEL_OPENROUTER,
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": prompt}] + b64s,
        }],
        "temperature": 0.1,
        "max_tokens": MAX_TOKENS,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=VISION_TIMEOUT_S)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter vision error {resp.status_code}: {resp.text[:300]}")
    content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("OpenRouter vision: empty response")
    return content


def _call_gemini_multi(image_jpegs: list[bytes], prompt: str, model: str = "") -> str:
    if not GOOGLE_API_KEY:
        raise RuntimeError("Gemini: no key")
    model = (model or GEMINI_MODEL).strip()
    parts = [{"text": prompt}]
    for b in image_jpegs:
        parts.append({
            "inlineData": {
                "mimeType": "image/jpeg",
                "data": base64.b64encode(b).decode("ascii"),
            }
        })
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={GOOGLE_API_KEY}"
    )
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 16384},
    }
    resp = requests.post(url, json=payload, timeout=VISION_TIMEOUT_S)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini vision error {resp.status_code}: {resp.text[:300]}")
    candidates = resp.json().get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini vision: no candidates")
    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    if not text:
        raise RuntimeError("Gemini vision: empty response")
    return text


def _extract_json_object(text: str) -> dict:
    """Toa JSON object kutoka majibu ya model (inaweza kuwa na maelezo/fences)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise AIGradeError("Hakuna JSON kwenye majibu ya AI")
        text = text[start:end + 1]
    return json.loads(text)


def grade_sheet(sheet_image_bytes: bytes, scheme_image_bytes_list: list[bytes]) -> dict:
    """Sahihisha karatasi MOJA ya mwanafunzi kwa kutumia marking scheme.

    Inarudi dict (ona docstring ya module). Inatoa AIGradeError kama AI
    imeshindikana au majibu si JSON sahihi.
    """
    if not scheme_image_bytes_list:
        raise AIGradeError("Marking scheme haina kurasa")
    sheet_jpeg = _jpeg_bytes(sheet_image_bytes)
    scheme_jpegs = [_jpeg_bytes(b) for b in scheme_image_bytes_list[:5]]  # max kurasa 5
    images = scheme_jpegs + [sheet_jpeg]

    errors = []
    # Gemini direct kwanza (bure). OpenRouter sasa ni fallback tu — ufunguo
    # wake unaweza kuwa umefutwa, na kuitanguliza kunapoteza sekunde kwa
    # kila karatasi bila sababu.
    if GOOGLE_API_KEY:
        for model in _gemini_models():
            try:
                text = _call_gemini_multi(images, PROMPT, model=model)
            except Exception as exc:
                errors.append(f"gemini {model}: {exc}")
                logger.warning("[AIGrader] Gemini %s failed: %s", model, exc)
                if not _gemini_model_retryable(exc):
                    break
                continue
            try:
                return _extract_json_object(text)
            except Exception as exc:
                errors.append(f"gemini {model} (JSON): {exc}")
                logger.warning("[AIGrader] Gemini %s returned invalid JSON: %s", model, exc)
                continue
    if _openrouter_usable():
        try:
            return _extract_json_object(_call_openrouter_multi(images, PROMPT))
        except Exception as exc:
            errors.append(f"openrouter: {exc}")
            logger.warning("[AIGrader] OpenRouter failed: %s", exc)
            if _is_openrouter_dead(exc):
                _disable_openrouter(3600)
    raise AIGradeError("; ".join(errors) or "Hakuna AI provider imewekwa")


# ---------------- Matching ya mwanafunzi ----------------

def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def match_student(school, name: str, reg_number: str, roster: list):
    """Match mwanafunzi kutoka majibu ya AI → FormStudent.

    1. Reg number (iexact)
    2. Jina kamili (fuzzy ≥ 0.82 au tokeni zote zilipo)
    Inarudi FormStudent au None.
    """
    if not roster:
        return None
    reg = (reg_number or "").strip()
    if reg:
        for fs in roster:
            if (fs.admission_no or "").strip().lower() == reg.lower():
                return fs
    nname = _norm_name(name)
    if not nname:
        return None
    best, best_score = None, 0.0
    for fs in roster:
        full = _norm_name(fs.full_name)
        if not full:
            continue
        if full == nname:
            return fs
        # tokeni zote za jina la AI zipo kwenye jina kamili (mpya/ya zamani)
        toks = nname.split()
        if toks and all(t in full for t in toks if len(t) > 1):
            ratio = 0.9
        else:
            ratio = difflib.SequenceMatcher(None, nname, full).ratio()
        if ratio > best_score:
            best, best_score = fs, ratio
    return best if best_score >= 0.82 else None
