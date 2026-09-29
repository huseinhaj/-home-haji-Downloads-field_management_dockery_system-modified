"""Scoresheet Upload — mwalimu anapakia picha (au PDF iliyochanganuliwa/
scanned) ya scoresheet aliyoijaza kwa mkono, mfumo unatumia AI (vision
model) kusoma majina na alama kwenye kila ukurasa.

Chain: Gemini direct HTTP (FREE) -> OpenRouter (google/gemini-2.5-flash,
vision, ya malipo) -- inafanana na chain ya curriculum/ai_utils.py lakini
hii inatuma picha (multimodal), si maandishi tu.

Gemini ya kwanza kwa sababu OpenRouter ni *mawakala wa malipo* wa Gemini
hiyo-hiyo: kulipia OpenRouter kununua Gemini kupitia njia ndefu. Weka
OCR_PROVIDER_ORDER=openrouter,gemini kurejesha mpangilio wa awali bila
kugusa msimbo.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def _read_key(name: str) -> str:
    """Soma ufunguo wa API na kuukawaha. Dashboard za Railway, .env na
    copy-paste za mwanagenzi hupeleka viwilio au alama za semi huwa pamoja
    naye, na ufunguo ulioambishwa na kimoja hufanya Google 401 (UNAUTHENTICATED)
— hapo ndipo mfumo unadai 'ufunguo si sahihi' wakati kwa kweli ni sahihi.
"""
    raw = os.getenv(name) or ""
    return raw.strip().strip('"').strip("'").strip()


OPENROUTER_API_KEY = _read_key("OPENROUTER_API_KEY")
GOOGLE_API_KEY = _read_key("GOOGLE_API_KEY")

# Ufunguo wa Gemini direct API (generativelanguage.googleapis.com)
# hauhusuwi na mtindo wake. Msimu wa awali ulikuwa unakataa chochote
# isiyokuwa na 'AIza' kichwa, na hivyo likarukia Gemini KILA wito. Kwa
# mpangilio wa 'gemini,openrouter' maana yake: salio la OpenRouter
# ndio lililokuwa likitumika kwa kila ukurasa, na mnyororo wa backup
# ulikuwa tupu — OpenRouter ikikosea (402) hakuna kilichobaki kulijibu.
# Ufunguo halisi wa mpangilio huu ('AQ.Ab8...') umeuthibitishwa kwa
# kweli kwenye endpoint ya Gemini: 200, wakati ufunguo wa kubuni
# unajibu 400. Sasa tunaamini Google, si mtindo wa ufunguo.
GEMINI_PROBE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_PROBE_TTL_S = 600  # dakika 10 — ukaguzi wa ukweli, si kila ukurasa
_gemini_probe = {"at": None, "problem": ""}


def _gemini_key_problem() -> str:
    """"" kama GOOGLE_API_KEY haiwezi kutumika na Gemini direct, au
    '' kama inaweza. Tunarudisha sentensi ya Kiswahili ili
    check_ocr_health / log ionyeshe sababu halisi."""
    if not GOOGLE_API_KEY:
        return "GOOGLE_API_KEY haijasetwa"
    now = time.monotonic()
    if _gemini_probe["at"] is not None and now - _gemini_probe["at"] < GEMINI_PROBE_TTL_S:
        return _gemini_probe["problem"]
    try:
        # Bure kabisa: endpoint hii inaorodhesha modeli tu — hakuna
        # kizalishaji, hakuna token zinazolipwa. Ufunguo wa kweli
        # unajibu 200; ufunguo wa kubuni au wa OAuth token unajibu
        # 400/401. Tunakaa matokeo kwa dakika 10 ili tusiombe
        # ukaguzi wa ziada kwa kila ukurasa wa kila pakia.
        resp = requests.get(
            GEMINI_PROBE_URL,
            headers={"x-goog-api-key": GOOGLE_API_KEY},
            timeout=15,
        )
        if resp.status_code == 200:
            problem = ""
        else:
            # Namba na maneno ya Google yenyewe — si mkadiria yetu.
            # _google_status() haisemiishi JSON tupu (imeandikwa kwa
            # majibu tayali ya mfano 'Gemini vision error 403: {...}'),
            # kwa hiyo hapa tunachimba msimbo na ujumbe moja kwa moja.
            label = re.search(r'"status"\s*:\s*"([A-Z_]+)"', resp.text or "")
            status = "%s %s" % (resp.status_code, label.group(1)) if label else "HTTP %s" % resp.status_code
            detail = re.search(r'"message"\s*:\s*"([^"]{3,120})"', resp.text or "")
            problem = (
                "GOOGLE_API_KEY haukubaliwa na Gemini (%s%s) — pata ufunguo mpya wa "
                "Gemini API kwenye Google AI Studio" % (
                    status, ": " + detail.group(1) if detail else "",
                )
            )
    except Exception as exc:
        # Mfuko wa mtandao si uthibitisho wa kwamba ufunguo ni mbaya —
        # tunasema hivyo, na tunakubali Gemini jaribuwe iwezekanavyo
        # (mtu wa backup si lazima aonekane kama amekosewa kwa sababu
        # ya mtandao wa mpangizio).
        problem = "Gemini haijafikika kwa ukaguzi (%s)" % (str(exc)[:60] or "timeout",)
    _gemini_probe["at"] = now
    _gemini_probe["problem"] = problem
    return problem

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

# Ceiling ya OpenRouter. Iliokuwa 4096: ukurasa wa scoresheet ya darasa
# (60-100 wanafunzi) unahitaji 4000-8000 token, hivyo modeli ilikatika
# na mistari ya mwisho ilipotea bila sababu inayoonekana. Gemini tayari
# ina 16384, tunaiwanya hapa ili nyuma ziwe sawa.
MAX_TOKENS_OPENROUTER = 16384

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
    "6. Scores must be between 0 and 100. They MAY contain DECIMALS — "
    "write them exactly as written: '10.6' stays 10.6, do NOT round it to "
    "11, and '7.5' stays 7.5. Only 'X' for absent or 'BLANK' for empty "
    "are non-numeric.\n"
    "7. NEVER invent names or scores — write ONLY what you see.\n"
    "8. Read each name COMPLETELY — do NOT cut off or abbreviate names.\n"
    "9. A score of '0' (zero) is a valid score — include it.\n"
    "10. For handwritten scores: look very carefully at each digit. "
    "A '1' can look like '7', a '6' can look like '8', a '3' can look like '8'. "
    "Double-check each digit against its neighbors.\n"
    "11. COMMON CONFUSIONS to watch for:\n"
    "    - '0' vs 'O' (letter O) — if it's in the score column, it's 0\n"
    "    - '1' vs 'l' (lowercase L) vs 'I' (uppercase i) — in scores it's 1\n"
    "    - 'X' vs 'x' vs '✕' vs '✗' vs a cross/tick mark — all mean ABSENT\n"
    "12. UNCLEAR MARKS — THIS MATTERS. If a mark is smudged, overwritten, "
    "crossed out, torn, or you are simply NOT SURE which digit it is, do "
    "NOT silently pick your best guess. Return that row like this:\n"
    '    {"row": 9, "name": "Full Name", "score": 10.6, "uncertain": true, '
    '"raw_score": "1O.6"}\n'
    "    - \"uncertain\": true means a HUMAN MUST check this mark before it "
    "is trusted.\n"
    "    - \"raw_score\": the characters you actually see, copied as-is, so "
    "the teacher can compare against the photo.\n"
    "    - ONLY use uncertain:true when you genuinely cannot tell. Clear, "
    "legible marks are plain numbers with no extra keys — do NOT add "
    "uncertain:true to every row, or the teacher loses the signal.\n"
    "    - NEVER resolve an unclear mark by choosing the most likely number. "
    "Flagging it is correct; guessing is not."
)


class ScoreSheetOCRError(Exception):
    pass


def _provider_order() -> list:
    """Mlipangilio wa watoa huduma: 'gemini' kwanja (bure), 'openrouter'
    cha pili (ya malipo). Env variable ya OCR_PROVIDER_ORDER inaweza
    kuibadilisha kwa mfano 'openrouter,gemini'."""
    raw = os.getenv("OCR_PROVIDER_ORDER", "gemini,openrouter")
    order = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return [p for p in order if p in ("gemini", "openrouter")] or ["gemini", "openrouter"]


# 402 = salio la OpenRouter limeisha. Hali hiyo haijibadilika kwenye muda
# wa mfumo uliofunguliwa, so kuijaribu tena kwa kila ukurasa wa kila
# pakia huzalisha tu sekunde za bure. Tunakumbuka na tunakwenda kwenye
# Gemini mara moja, kisha tunarudi kujaribu baada ya muda mfupi — ili
# salio likishatiwa vizuri mfumo unashuka kwenye OpenRouter bila kufanya
# deploy.
_OR_DISABLED_UNTIL = 0.0
_OR_COOLDOWN_S = 900  # dakika 15


def _openrouter_usable() -> bool:
    return bool(OPENROUTER_API_KEY) and time.monotonic() > _OR_DISABLED_UNTIL


def _disable_openrouter(seconds: int = _OR_COOLDOWN_S) -> None:
    global _OR_DISABLED_UNTIL
    _OR_DISABLED_UNTIL = time.monotonic() + seconds
    logger.warning(
        "[ScoreSheetOCR] OpenRouter imeuzimwa kwa sekunda %s (salio limeisha) — "
        "Gemini ndiyo inatumika kwa sasa", seconds,
    )


def _reset_provider_health() -> None:
    """[Tumia kwenye tests] Safisha kumbukumbu ya iko ya OpenRouter na
    ukaguzi wa Gemini, ili kila jaribio lianze kwenye hali safi."""
    global _OR_DISABLED_UNTIL
    _OR_DISABLED_UNTIL = 0.0
    _gemini_probe["at"] = None
    _gemini_probe["problem"] = ""


def _key_fingerprint(name: str) -> dict:
    """Maelezo ya ufunguo bila kuuacha (si sehemu, si urefu kamili) — vya
    kutosha kulinganisha na thamani kwenye .env wakati unatafuta 401, bila
    kuvitisha siri kwenye ukurasa wa JSON."""
    raw = os.getenv(name) or ""
    clean = raw.strip().strip('"').strip("'").strip()
    return {
        'len': len(clean),
        'prefix': clean[:6],
        # True = the pasted value carried quotes or a stray space, which
        # authenticates as nobody and reads as "wrong key" on the dashboard.
        'had_paste_junk': raw != clean,
        'missing': not clean,
    }


def _is_out_of_credits(exc) -> bool:
    msg = str(exc).lower()
    return " 402" in msg or "insufficient credits" in msg


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


def _strip_fences(text: str) -> str:
    """Ondoa markdown code fences na maelezo yoyote yaliyo nje ya JSON.

    Vision models hawaifu kila wakati: mmoja anasema "Hapa kuna matokeo:"
    kabla ya JSON, mwingine analalamika baadaye ("Nimeona mistari 20"), au
    anazunguka jibu lake kwa ```json ... ```. Tatu hizo hazihujumuishi
    ukweli wa data, kwa hiyo tunakata yote na kujaribu kuparekana kwa
    JSON halisi tu."""
    cleaned = (text or "").strip()
    # Fence inayofungua na inayofunga (zenye maeno kama ```json au ```JSON)
    cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _repair_json(text: str) -> str:
    """Safi za kawaida za JSON zinazotokea kwenye majibu ya AI.

    Vision model mara nyingi huandika JSON ambayo ni 'karibu' sahihi:
    koma mwisho (,) kabla ya } au ], newlines za ziada ndani ya muundo,
    au majibu yaliyokatwa kwa idadi. Hapa tunalingana na ile ambayo
    Python inaweza kusoma; kama bado haiwezekani, tunarudi kwenye
    njia zingine za kukomaa chini (mfano mistari).
    """
    fixed = re.sub(r",\s*([}\]])", r"\1", text)      # koma mwisho
    fixed = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", fixed)  # udhibiti wa mistari
    # Single quotes zilizo ndani ya string halisi zinaweza kuangusha
    # json.loads; badala ya kuzingatia hapa tunabeba tu kama
    # jibu lote linatumia single quotes (halali ya kutosha kwa AI).
    if '"' not in fixed and "'" in fixed:
        fixed = fixed.replace("'", '"')
    return fixed


def _longest_valid_json_array(text: str):
    """Chukua array ya JSON yenye urefu MKUBWA inayoweza kusomwa.

    Jibu linalokatwa (max_tokens) huacha mwisho bila ']' — hapo
    json.loads inashindwa kwa 'Unterminated string'. Badala ya kufa
    kabisa (mtumiaji hupoteza wanafunzi WOTE wa ukurasa huo), tunajaribu
    kila mwisho unawezekana: hapa tunapunguza array hadi mwisho wa
    object inayofuata iliyokamilika, na kuangalia kama hiyo basi inasomwa.
    """
    start = text.find("[")
    if start == -1:
        return None
    # Kila mfuatano wa '}' au ']' ndani ya array huwa mwisho unawezekana
    for end in sorted({m.end() for m in re.finditer(r"[\]\}]", text[start:])}, reverse=True):
        chunk = text[start:end]
        if chunk.rstrip().endswith(","):
            chunk = chunk.rstrip().rstrip(",")
        try:
            data = json.loads(_repair_json(chunk))
            if isinstance(data, list) and data:
                return _normalise_rows(data)
        except json.JSONDecodeError:
            continue
    return None


def _rows_from_objects(objects: list) -> list:
    """Chukua mistari kutoka kwa dict zilizomo jina na alama, safi au
    zenye majina ya tofauti ya maelezo (vision models hutofautisha sana
    kwenye uandishi wa ulezi).

    Majina mengine ya AI (k.v. 'gender' kwenye orodha) hubaki pale
    mistari imejaaliwa hapa — kama tungezi tu row/name/score, basi
    kila mwanafunzi wa kike katika orodha angehifadhiwa kama kiume.
    Kwa hivyo tunabeba nyongezo zote za asili na kuiweka tu zile
    tatu kuu kwa majina safi.
    """
    name_keys = ("name", "student", "student_name", "full_name", "fullname", "jina", "studentname")
    score_keys = ("score", "mark", "marks", "alama", "points", "grade", "value")
    row_keys = ("row", "na", "no", "number", "namba", "index")
    rows = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        lowered = {str(k).strip().lower(): v for k, v in obj.items()}
        name = next((str(lowered[k]).strip() for k in name_keys if k in lowered and lowered[k]), "")
        if not name:
            continue
        raw_score = next((lowered[k] for k in score_keys if k in lowered), None)
        row_no = next((lowered.get(k) for k in row_keys if lowered.get(k) is not None), None)
        # Nyongezo zote isizokuwa majina ya kawaida (gender, class, n.k.)
        aliases = set(name_keys) | set(score_keys) | set(row_keys)
        extra = {
            k: v for k, v in obj.items()
            if str(k).strip().lower() not in aliases
        }
        rows.append({"row": row_no, "name": name, "score": raw_score, **extra})
    return rows


def _normalise_rows(data: list) -> list:
	"""Ikiwa array ni ya muundo ulioombwa (kila row ina 'name' na 'score'),
	haigushwi — majaribio na wanafunzi wanaoona matokeo yanategemea
	hiyo hasa. Ikiwa ni majina sani ('student_name'/'marks'), tunavitengua
	kuwa muundo wetu ili _clean_rows isielewe, na tunafuta ufunguo
	wa None (k.v. 'row': None) ili usichukue nafasi.
	"""
	if not data:
		return data
	all_dicts = all(isinstance(item, dict) for item in data)
	if all_dicts and all("name" in item and "score" in item for item in data):
		return data
	rows = _rows_from_objects(data)
	if not rows:
		return data
	return [
		{k: v for k, v in row.items() if v is not None or k == 'row'}
		for row in rows
	]


def _wrong_document_message(text: str):
    """AI ikirudi maneno badala ya JSON, mara nyingi hiyo ni sababu
    mtu alipakia karatasi isiyo scoresheet — kwa kawaida marking
    scheme. Bezwe hapo awali kosa lilikuwa "AI haikurudisha muundo
    sahihi wa JSON" + nusu ya maneno ya AI kwa Kiingereza, ambayo
    haikuwa na maana kwa mwalimu.

    Tunarudisha ujumbe wa Kiswahili wenye maelekezo, au None kama
    jibu si "karatasi isiyo sahihi" bali tatizo lingine.
    """
    if not text:
        return None
    low = text.lower()

    # Alama za kipekee za aina ya karatasi iliyo onekana, ili
    # tumbuze mtu kile alichopakia hasa.
    found = ""
    if "marking scheme" in low or "marking guide" in low or "answer key" in low:
        found = "iliyoonekana ni **marking scheme** (mpango wa kuangalia majibu)"
    elif any(p in low for p in (
        "not a scoresheet", "not the scoresheet", "does not appear to be a scoresheet",
        "does not contain a scoresheet", "is not a score sheet",
    )):
        found = "haionekani kuwa scoresheet"
    elif any(p in low for p in (
        "does not contain student names", "no student names",
        "not contain a list of students", "does not appear to be a list of students",
    )):
        found = "haionekani kuwa ina majina ya wanafunzi"
    elif any(p in low for p in (
        "cannot extract", "can't extract", "unable to extract", "cannot determine",
        "i'm sorry", "i am sorry", "as an ai",
    )):
        found = "AI haikuweza kutoa jina na alama za wanafunzi kutoka"

    if not found:
        return None

    return (
        f"Siyo scoresheet — {found}.\n\n"
        "Pakia **karatasi ya alama**: kila mwanafunzi awe na jina lake kando ya "
        "alama yake, mfano:\n"
        "  1. JOHN DOE ............ 85\n"
        "  2. MARY JONES ......... 72\n\n"
        "Marking scheme (mpango wa kuangalia majibu), maswali, au ukurasa wa "
        "maelekezo hayatoshiweza kusomwa hapa — AI inahitaji jina + alama."
    )


def _extract_json_array(text: str) -> list:
    if not text:
        raise ScoreSheetOCRError("AI haikurudisha jibu.")
    cleaned = _strip_fences(text)

    # ── 1. JSON safi kama ilivyotoka ────────────────────────────────────
    for candidate in (cleaned, _repair_json(cleaned)):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return _normalise_rows(data)
        if isinstance(data, dict):
            # Mfumo mwingine wa AI hufanya {"rows": [...]} au
            # {"students": [...]}: kuchukua array iliyo ndani yake.
            for value in data.values():
                if isinstance(value, list):
                    rows = _rows_from_objects(value)
                    if rows:
                        return rows
            single = _rows_from_objects([data])
            if single:
                return single

    # ── 2. Array iliyo ndani ya mazungumzo (neno kabla/baada) ──────────
    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(_repair_json(match.group(0)))
            if isinstance(data, list) and data:
                return data
        except json.JSONDecodeError:
            # Jibu lililokatwa — chukua array ya mistari iliyoizidi
            # kwenye ukurasa, si kufa na kupoteza wote.
            partial = _longest_valid_json_array(_repair_json(match.group(0)))
            if partial:
                logger.warning(
                    "[ScoreSheetOCR] AI response was truncated — salvaged %d rows "
                    "from the incomplete JSON", len(partial),
                )
                return partial

    # ── 3. Object kwa object (zikiwa na braces zilizo ndani) ────────────
    decoder = json.JSONDecoder()
    objects = []
    idx = 0
    while True:
        brace = cleaned.find("{", idx)
        if brace == -1:
            break
        try:
            obj, end = decoder.raw_decode(_repair_json(cleaned[brace:]))
            objects.append(obj)
            idx = brace + end
        except json.JSONDecodeError:
            idx = brace + 1
    rows = _rows_from_objects(objects)
    if rows:
        return rows

    # ── 4. Mistari ya maandishi: "Jina 85" / "Jina: 85" ────────────────
    fallback_rows = []
    for line in cleaned.split("\n"):
        line = re.sub(r"^\s*[-*\d.)\]]+\s*", "", line).strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z][A-Za-z\s\.'\-]{2,}?)\s*[:\-–]?\s*(\d{1,3})\s*$", line)
        if m:
            name = m.group(1).strip()
            score = int(m.group(2))
            # Jina la mwanafunzi lina maneno >= 2. bila hili sentensi za
            # AI kama "I counted 20 rows" zingeonekana kama mwanafunzi.
            if 0 <= score <= 100 and len(name.split()) >= 2:
                fallback_rows.append({"name": name, "score": score})
    if fallback_rows:
        return fallback_rows

    wrong_doc = _wrong_document_message(text)
    if wrong_doc:
        raise ScoreSheetOCRError(wrong_doc)

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


def _parse_mark(raw_str):
    """Soma alama ya mwanafunzi na irudishe kama Decimal, au None kama
    haisomeki.

    Hapa ndipo alama za desimali zilizopotea. Msimu wa zamani ulitumia
    int(), na pale inapofaa ilikata non-digit: "7.5" → "75". Mwanafunzi
    aliyepata alama 7.5 alipewa 75 — na kila mstari uliotoweka husababisha
    wanafunzi wa baadaye kusogeza nafasi hadi mwisho wa listi.

    Mantiku halisi iko kwenye results.utils.parse_mark ili ukurasa
    wote usome alama kwa njia moja.
    """
    from results.utils import parse_mark
    return parse_mark(raw_str)


# Herufi ambazo AI mara nyingi huwa na ambazo hazina maana katika
# safu ya alama — kama zipo hapo, alama imeandikwa au kusomwa vibaye
# (mfano "1O.6" badala ya "10.6", "S5" badala ya "55", "B0" badala
# ya "80"). AI inadai kuwa "score" ni namba, lakini mara nyingi
# inarudisha kitu kilichokuwa herufi na namba.
_SUSPECT_MARK_CHARS = set("SOolIBGZTD")


def _special_case_reason(item, raw_str, score, is_absent) -> str:
    """Cha alama hii kama "special case" inayohitaji kuangaliwa na mwalimu.

    Inarudi '' kama alama ni safi (ikiwa ni namba tu, 0-100, na AI
    haikuwa amesema ana washa).

    Kanuni zinazotumika:
      1. AI mwenyewe akisema ana washa (`uncertain: true`) — ndiyo
         maelekezo yake yenyewe.
      2. Alama ina herufi zinazohusishwa na kukoseka kwa macho
         ("1O.6", "S5", "B0") — alama imeandikwa vibaya kwenye
         karatasi, na AI imeikusaha kuachilia.
      3. AI imeripa `raw_score` tofauti na alama yake yenyewe
         ("1O.6" → 10.6): AI ina uhakika zaidi kuliko mtaa aliyoiandika,
         ndiyo maana mwalimu anapaswa kuiona.

    Tunakwagua kwa HATUA tatu hivi tu. Alama safi hazipati alama
    ya sumaku hata kidogo: mwanafunzi aliyepata 0, 100, au 7.5 kwa
    uakiki ni mwanafunzi wa kawaida, si tatizo la kusoma. Ukaguzi
    mkubwa ungewafanya mwalimu wengi wasiweze kuona alama zinazohitaji
    ukaguzi halisi, na hapo ndipo alama za mashaka zingeyakosewa.
    """
    if is_absent:
        return ''

    # (1) AI mwenyewe akisema ana washa — maelekezo yake yenyewe.
    flag = item.get("uncertain", item.get("needs_review", False))
    if isinstance(flag, str):
        if flag.strip().lower() in ("true", "yes", "1", "uncertain"):
            flag = True
        else:
            flag = False
    if flag:
        return 'AI haikuwa na uhakika wa alama hii'

    # (2) Herufi za kushaka zilizo ndani ya alama.
    text = str(raw_str)
    suspect = sorted({c for c in text if c in _SUSPECT_MARK_CHARS})
    if suspect:
        return 'Alama ina herufi za kushaka: ' + ' '.join(suspect)

    # (3) raw_score tofauti na alama AI iliyotoa.
    raw_reported = item.get("raw_score")
    if raw_reported is not None:
        raw_reported_str = str(raw_reported).strip()
        if raw_reported_str and raw_reported_str != text:
            parsed_raw = _parse_mark(raw_reported_str)
            if parsed_raw is None or parsed_raw != score:
                return (
                    f'AI ilisoma "{text}" lakini ilaonyesha "{raw_reported_str}"'
                )

    return ''



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
            # ── Alama namba (inaweza kuwa desimali) ───────────────────
            # Kabla ya hapa kila alama ilipitiwa kwa int(), na kama
            # isingefaa, mstari mzima ulikatika. Matokeo: "10.6"
            # ilikatika, "7.5" ilibadilika kuwa 75 (namba zilizounganishwa),
            # na kwa kuwa mistari iliyobaki inasogea nafasi, mwanafunzi
            # wa mwisho alipata alama ya mwanafunzi aliyetangulia.
            # Sasa: desimali zinasomwa, na kisichosomeka hushikwa na
            # kuacha alama tupu badala ya kukatika.
            parsed = _parse_mark(raw_str)
            if parsed is None:
                # Hatuna uhakika kama hii ni namba. Mstari unabaki
                # ili mwalimu aone, lakini bila alama — si kujaza
                # kwa kubahatisha.
                rows.append({
                    "raw_name": name, "score": None, "is_absent": False,
                    "row": row_no, "blank": True, "unreadable": True,
                    "raw_mark": raw_str[:40],
                })
                continue
            score = parsed

        if score < 0 or score > 100:
            # Namba iko nje ya 0-100 (mfano "106" iliyotokana na
            # alama ya desimali iliyosomewa vibaya). Tunashika mstari
            # ili mstari uzingiwe — lakini bila alama, na AI ataona
            # mstari huu kama wa kushindwa kusoma.
            rows.append({
                "raw_name": name, "score": None, "is_absent": False,
                "row": row_no, "blank": True, "unreadable": True,
                "raw_mark": str(raw_str)[:40],
            })
            continue

        # ── Special case: AI haikuwa na uhakika wa alama hii ───────────
        # Alama iliyoandikwa vibaya (doti, imefutwa, digit ya mashaka)
        # haipaswi kuingizwa kwa kuonekana kama nyingine. Tunaiweka
        # kama "special case" na mwalimu lazima aikague mwenyewe
        # kabla ya kuikubali — kisha anaendelea kama kawaida.
        special_reason = _special_case_reason(item, raw_str, score, is_absent)
        if special_reason:
            # raw_mark: alama ILIYOANDIKWA kwenye karatasi. Mwalimu
            # anahitaji kuiona ili auangalie dhidi ya picha — bila
            # hii, anaona tu "1.60" na hataweza kujua kwamba
            # karatasi ilikuwa "1O.6".
            rows.append({
                "raw_name": name, "score": score, "is_absent": is_absent,
                "row": row_no, "blank": False,
                "is_special_case": True, "special_reason": special_reason,
                "raw_mark": str(raw_str)[:40],
            })
            continue

        rows.append({"raw_name": name, "score": score, "is_absent": is_absent, "row": row_no, "blank": False})
    return rows


def _call_openrouter_vision(image_bytes: bytes, mime_type: str, api_key: str, max_tokens: int = MAX_TOKENS_OPENROUTER, prompt: str = PROMPT) -> str:
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
    """Gemini first (free), OpenRouter second (paid) — one rendered page/photo
    in, raw model text out. Raises RuntimeError if every provider fails.
    `prompt` lets other vision tasks (roster scan) reuse this provider
    chain with their own instructions."""
    image_bytes = _encode_jpeg(img)
    mime_type = "image/jpeg"

    errors = []

    for provider in _provider_order():
        if provider == 'gemini':
            # Ufunguo wa mtindo mbaya (mfano OAuth token) hawezi
            # kuthibitisha kamwe — tukiruka kabla ya kutuma wito
            # ambalo lingekuwa 401, ili OpenRouter ipate nafasi yake
            # bila kupoteza sekunda na bila kuchanganya mpangilio kwa
            # mwanagenzi.
            gemini_problem = _gemini_key_problem()
            if gemini_problem:
                logger.info("[ScoreSheetOCR] Gemini kurukiwa: %s", gemini_problem)
                continue
            try:
                logger.info("[ScoreSheetOCR] Trying Gemini (%s)", GEMINI_MODEL)
                text = _call_gemini_vision(image_bytes, mime_type, GOOGLE_API_KEY, prompt=prompt)
                logger.info("[ScoreSheetOCR] Gemini success")
                return text
            except Exception as exc:
                # Alama ya ufunguo (si siri yenyewe) kwenye log: mpangilio
                # anaona kwa neno kama thamani iliyo kwenye Railway ni ile
                # ile ya .env bila kuingiza siri kwenye ukurasa wa mwalimu.
                logger.warning("[ScoreSheetOCR] Gemini failed: %s | ufunguo: %s", exc, _key_fingerprint("GOOGLE_API_KEY"))
                errors.append(("Gemini", exc))
                continue

        # OpenRouter — a paid hop, so it only runs while it is actually usable.
        if not _openrouter_usable():
            if OPENROUTER_API_KEY:
                logger.info("[ScoreSheetOCR] OpenRouter imebaki iko — kurukia")
            continue
        try:
            logger.info("[ScoreSheetOCR] Trying OpenRouter (%s)", VISION_MODEL_OPENROUTER)
            text = _call_openrouter_vision(image_bytes, mime_type, OPENROUTER_API_KEY, prompt=prompt)
            logger.info("[ScoreSheetOCR] OpenRouter success")
            return text
        except Exception as exc:
            logger.warning("[ScoreSheetOCR] OpenRouter failed: %s", exc)
            if 'OR_TRUNCATED' in str(exc):
                # Ukurasa wa wanafunzi wengi (100+) unahitaji token
                # nyingi: kila mstari ~40-60 token. 4096 iliyokuwa
                # mwanzo ilikatika kwa kurasa 60+ — na retry ya kwanza
                # ilikuwa ikitumia ceiling ile ile, kwa hivyo haikusaidii
                # chochote. Sasa tunajaribu kwa ceiling kubwa mara moja.
                big = MAX_TOKENS_OPENROUTER * 2
                try:
                    logger.info("[ScoreSheetOCR] Truncated — retrying OpenRouter with max_tokens=%s", big)
                    text = _call_openrouter_vision(
                        image_bytes, mime_type, OPENROUTER_API_KEY,
                        max_tokens=big, prompt=prompt,
                    )
                    logger.info("[ScoreSheetOCR] OpenRouter retry (bigger ceiling) success")
                    return text
                except Exception as retry_exc:
                    exc = retry_exc
                    logger.warning("[ScoreSheetOCR] OpenRouter bigger-ceiling retry failed: %s", retry_exc)
            if _is_out_of_credits(exc):
                # Salio haliishukawi ndani ya muda wa mfumo — sitaki kulipa
                # safari ya bure kwa kila ukurasa wa kila pakia.
                _disable_openrouter()
            else:
                # Salio dogo (si kabisa limeisha): OpenRouter hifadhi bajeti
                # ya max_tokens nzima awali, si matumizi halisi — kwa hiyo
                # salio dogo bado linaweza kulipa jibu dogo la JSON. Jaribu
                # mara moja kwa kile OpenRouter anachosema kinachoweza.
                afford_match = re.search(r"can only afford (\d+)", str(exc))
                if afford_match:
                    affordable = int(afford_match.group(1))
                    # Even 18 tokens is enough for a tiny JSON response. The
                    # vision request is the expensive part (input); output tiny.
                    if affordable >= 10:
                        try:
                            logger.info("[ScoreSheetOCR] Retrying OpenRouter with max_tokens=%s", affordable)
                            text = _call_openrouter_vision(image_bytes, mime_type, OPENROUTER_API_KEY, max_tokens=affordable, prompt=prompt)
                            logger.info("[ScoreSheetOCR] OpenRouter retry success")
                            return text
                        except Exception as retry_exc:
                            exc = retry_exc
                            logger.warning("[ScoreSheetOCR] OpenRouter retry failed: %s", retry_exc)
            errors.append(("OpenRouter", exc))

    if not errors:
        raise RuntimeError("No AI provider configured")
    # Watumiaji waliona JSON ghafi ya Gemini tu ("401 … OAuth 2 access
    # token …") wakati chanzo halisi kilikuwa pia salio la OpenRouter
    # kuisha. Eleza kila mtoa huduma kwa lugha rahisi + nini cha kufanya.
    reasons = ["%s: %s" % (name, _explain_ai_error(exc)) for name, exc in errors]
    raise RuntimeError(" | ".join(reasons)) from errors[-1][1]


def _google_status(msg: str) -> str:
    """Namba halisi na neno halisi lililotoka kwa Google (mfano '403
    PERMISSION_DENIED'). Nini kimeandikwa hapa awali — 'weka ufunguo
    sahihi (401)' — ni maneno yetu, si jibu la Google, kwa hiyo mwalimu
    alikuwa anakomesha ujumbe ambayo Google haikuambiri hata kamwe."""
    low = msg.lower()
    for code in ("400", "401", "403", "404", "429", "500", "503"):
        if f"error {code}" in low or f" {code}:" in low:
            label = re.search(r'"status"\s*:\s*"([A-Z_]+)"', msg)
            return f"{code} {label.group(1)}" if label else code
    return ""


def _explain_ai_error(exc) -> str:
    """Kosa la mtoa huduma wa AI → sentensi fupi ya Kiswahili yenye suluhisho,
    ikiwa na namba halisi ya mtoa huduma ili mpangilio usiwe anaonyesha
    dalili zake za kudhani. 'OR_TRUNCATED' inabaki kwenye maandishi ili
    retry iendelee kuitambua."""
    msg = str(exc)
    low = msg.lower()

    if msg == "OR_TRUNCATED":
        return "jibu lilikatika katikati (OR_TRUNCATED)"
    if " 402" in msg or "insufficient credits" in low or "can only afford" in low:
        return "salio limeisha (402) — ongeza credits: openrouter.ai/settings/credits"
    if " 401" in msg or "unauthenticated" in low or "api key not valid" in low or "api_key_invalid" in low:
        return ("ufunguo wa Gemini si sahihi (%s) — thamani ya GOOGLE_API_KEY kwenye "
                "Railway → Variables inapaswa kuwa ile kwenye .env yako" % (_google_status(msg) or "401"))
    if " 403" in msg or "permission_denied" in low:
        return ("Google imekataa ufunguo (%s) — API haijaWashwa au ufunguo umefunguliwa "
                "kwa programu ya Android/iOS pekee: Google Cloud Console → APIs & Services → "
                "Generative Language API → ENABLE, kisha ondoa vikwazo vya ufunguo" % (_google_status(msg) or "403"))
    if " 404" in msg or "not_found" in low:
        return "mfumo wa Gemini haupo (%s) — GEMINI_MODEL inahitaji kubadilishwa" % (_google_status(msg) or "404")
    if " 429" in msg or "quota" in low or "rate limit" in low or "resource_exhausted" in low:
        return "kikomo cha matumizi kimefikiwa (%s) — subiri dakika chache ujaribu tena" % (_google_status(msg) or "429")
    if "timed out" in low or "timeout" in low:
        return "imechelewa kujibu (mtandao) — jaribu tena"
    # 5xx = kosa upande wa mtoa huduma, si mpangilio wetu. Muisi 'isichojulikana'
    # iliwafanya waangalimu kutaratibu ufunguo ambao hauhusiani na tatizo.
    five_xx = re.search(r"error (5\d\d)", low)
    if five_xx:
        return ("seva ya %s imeshindwa (%s) — si kosa la mpangilio, jaribu tena "
                "baada ya dakika chache" % ("Gemini", _google_status(msg) or five_xx.group(1)))
    # Kosa lisichojulikana: onyesha sehemu ya jibu halisi (bila JSON nzito)
    # ili mpangilio anaweza kuona namba halisi badala ya maneno yetu tu.
    return "hitilafu isiyotambulika: " + re.sub(r"\s+", " ", msg)[:180]


def check_ocr_health() -> dict:
    """Quick check: are API keys set, do they work, and (OpenRouter) is there
    any money left? A key that authenticates fine still returns 402 on every
    call once the account balance runs out, so the balance is the part worth
    reporting — it is what silently turned scans into 'imeshindwa kusoma
    faili' when the account had spent $10.20 of its $10."""
    status = {
        'provider_order': _provider_order(),
        'openrouter': bool(OPENROUTER_API_KEY),
        'gemini': bool(GOOGLE_API_KEY),
        'gemini_key': _key_fingerprint("GOOGLE_API_KEY"),
        'openrouter_key': _key_fingerprint("OPENROUTER_API_KEY"),
    }
    # Sababu ya hasa ya kukosa Gemini. Nyumbani, GOOGLE_API_KEY iliyokuwa
    # ikishweka OAuth token ilikuwa ikifanya kila ukurasa 401 na
    # mpangilio akidhani OpenRouter ndiyo iliyokosea. Sasa tunaeleza
    # wazi kabla ya kujaribu hata wito moja.
    gemini_problem = _gemini_key_problem()
    status['gemini_usable'] = not gemini_problem
    if gemini_problem:
        status['gemini_problem'] = gemini_problem
    # Mwanagenzi alimlipa OpenRouter mara tu: mfumo wa gunicorn uliokuwa
    # umesahaulisha salio lililokuwa limeisha na hujiruhusu OpenRouter
    # kwa dakika 15 — alionekana kama ameendelea kulipwa bila kutendeka.
    status['openrouter_cooldown_s'] = round(max(0.0, _OR_DISABLED_UNTIL - time.monotonic()))
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
        try:
            creds = requests.get(
                'https://openrouter.ai/api/v1/credits',
                headers={'Authorization': f'Bearer {OPENROUTER_API_KEY}'},
                timeout=10,
            )
            if creds.status_code == 200:
                data = creds.json().get('data', {})
                total, used = data.get('total_credits'), data.get('total_usage')
                if total is not None and used is not None:
                    balance = round(float(total) - float(used), 4)
                    status['openrouter_balance'] = balance
                    status['openrouter_has_credits'] = balance > 0
        except Exception:
            pass  # balance is a nicety — never fail the health check over it
    return status


def extract_scores_from_document(uploaded_file, on_progress=None) -> list[dict]:
    """Returns [{"raw_name": str, "score": int}, ...] read from the upload —
    a single photo, or every page of a scanned PDF (each page's rows are
    concatenated, since a multi-page scoresheet just continues the list).

    Pages are sent to the vision API concurrently — each is an independent,
    slow (up to 180s) HTTP call, so a 3-5 page scoresheet reading pages one
    at a time could take minutes; reading them in parallel bounds the wait
    to roughly the slowest single page instead of the sum of all of them.

    on_progress: optional callable, called as on_progress(stage, done, total)
    after every page finishes so the caller can show real progress instead
    of an open-ended spinner. Default None keeps every other caller (and the
    existing tests) on the previous behaviour — no callback, no overhead."""
    if not (OPENROUTER_API_KEY or GOOGLE_API_KEY):
        raise ScoreSheetOCRError(
            "Hakuna AI provider iliyosanidiwa. Weka OPENROUTER_API_KEY au GOOGLE_API_KEY kwenye .env"
        )

    pages = _load_page_images(uploaded_file)
    total_pages = len(pages)
    if on_progress:
        on_progress('reading', 0, total_pages)

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
    pages_done = 0
    with ThreadPoolExecutor(max_workers=min(len(pages), MAX_OCR_WORKERS)) as pool:
        future_to_index = {pool.submit(_read_page_with_retry, img, i + 1): i for i, img in enumerate(pages)}
        for future in as_completed(future_to_index):
            i = future_to_index[future]
            try:
                page_results[i] = (future.result(), None)
            except Exception as exc:
                page_results[i] = (None, exc)
            # Report after every page — finished OR failed — so the count
            # only ever moves forward. A page that dies still gets counted;
            # a progress bar that stalls looks like a hang.
            pages_done += 1
            if on_progress:
                on_progress('reading', pages_done, total_pages)

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
