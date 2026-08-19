"""
AI utilities for the Curriculum app.
All providers use direct HTTP calls (no SDK library issues).
Chain: OpenRouter ($5 credits, direct HTTP) → Groq (SDK) → Gemini (direct HTTP, FREE).
"""
import os
import json
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

PRIMARY_MODEL = "google/gemini-2.5-flash"  # Fast & cheap via OpenRouter

FALLBACK_MODELS_OPENROUTER = [
    "deepseek/deepseek-chat",
    "google/gemini-2.5-flash",
    "google/gemini-2.5-flash-lite",
    "meta-llama/llama-3.3-70b-instruct",
]

FALLBACK_MODELS_GROQ = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]

logger = logging.getLogger(__name__)


class GenerateContentConfig:
    def __init__(self, system_instruction=None, temperature=0.7, max_output_tokens=16384, **kwargs):
        self.system_instruction = system_instruction
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens


class _Response:
    def __init__(self, text):
        self.text = text


class _Chunk:
    def __init__(self, text):
        self.text = text


# -- Direct HTTP helpers -------------------------------------------------------

def _call_openrouter(messages, model, api_key, temperature=0.7, max_tokens=16384):
    """Call OpenRouter API via direct HTTP. Returns response text."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tlm-tanzania.railway.app",
        "X-Title": "TLM Tanzania - Teaching & Learning Materials",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=300)
    if resp.status_code != 200:
        err_msg = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
        raise RuntimeError(f"OpenRouter {model} error {resp.status_code}: {err_msg}")
    data = resp.json()
    choice = data.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content", "")
    if not content:
        raise RuntimeError(f"OpenRouter {model}: empty response")
    return content


def _call_openrouter_stream(messages, model, api_key, temperature=0.7, max_tokens=16384):
    """Call OpenRouter API streaming via direct HTTP. Yields text chunks."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tlm-tanzania.railway.app",
        "X-Title": "TLM Tanzania - Teaching & Learning Materials",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    with requests.post(url, json=payload, headers=headers, stream=True, timeout=300) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter stream {model} error {resp.status_code}: {resp.text[:200]}")
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                chunk_data = line[6:]
                if chunk_data == "[DONE]":
                    break
                try:
                    chunk_json = json.loads(chunk_data)
                    delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue


def _call_gemini(prompt_text, api_key):
    """Call Gemini API via direct HTTP. Returns response text."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 16384},
    }
    resp = requests.post(url, json=payload, timeout=300)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini: no candidates")
    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    if not text:
        raise RuntimeError(f"Gemini: empty response")
    return text


def _call_gemini_stream(prompt_text, api_key):
    """Call Gemini API streaming via direct HTTP. Yields text chunks."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?alt=sse&key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 16384},
    }
    with requests.post(url, json=payload, stream=True, timeout=300) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini stream error {resp.status_code}: {resp.text[:200]}")
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                chunk_data = line[6:]
                if chunk_data == "[DONE]":
                    break
                try:
                    chunk_json = json.loads(chunk_data)
                    candidates = chunk_json.get("candidates", [])
                    if candidates:
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text:
                            yield text
                except json.JSONDecodeError:
                    continue


def _call_groq(messages, model, api_key, temperature=0.7, max_tokens=8192):
    """Call Groq API via direct HTTP. Returns response text."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=300)
    if resp.status_code != 200:
        raise RuntimeError(f"Groq {model} error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError(f"Groq {model}: empty response")
    return content


def _call_groq_stream(messages, model, api_key, temperature=0.7, max_tokens=8192):
    """Call Groq API streaming via direct HTTP. Yields text chunks."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    with requests.post(url, json=payload, headers=headers, stream=True, timeout=300) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"Groq stream {model} error {resp.status_code}: {resp.text[:200]}")
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                chunk_data = line[6:]
                if chunk_data == "[DONE]":
                    break
                try:
                    chunk_json = json.loads(chunk_data)
                    delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue


def _to_openai_messages(contents, system_instruction=None):
    """Convert contents to OpenAI-style messages list."""
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": str(system_instruction)})
    if isinstance(contents, str):
        messages.append({"role": "user", "content": contents})
    elif isinstance(contents, list):
        for item in contents:
            if isinstance(item, dict):
                role = item.get("role", "user")
                if role == "model":
                    role = "assistant"
                parts = item.get("parts", [])
                text = parts[0].get("text", "") if parts and isinstance(parts[0], dict) else (str(parts[0]) if parts else item.get("content", ""))
                messages.append({"role": role, "content": text})
            else:
                messages.append({"role": "user", "content": str(item)})
    else:
        messages.append({"role": "user", "content": str(contents)})
    return messages


def _prompt_text(contents):
    """Extract plain text from contents."""
    if isinstance(contents, str):
        return contents
    if isinstance(contents, list):
        texts = []
        for item in contents:
            if isinstance(item, dict):
                parts = item.get("parts", [])
                if parts:
                    t = parts[0].get("text", "") if isinstance(parts[0], dict) else str(parts[0])
                    texts.append(t)
            else:
                texts.append(str(item))
        return "\n".join(texts)
    return str(contents)


# =============================================================================
# UNIFIED AI CLIENT — ALL providers use direct HTTP (no SDK!)
# Chain: OpenRouter ($5 credits) → Groq → Gemini (FREE)
# =============================================================================

class _UnifiedModels:
    """Mimics models.generate_content() with all providers using direct HTTP."""

    def __init__(self, or_key=None, groq_key=None, gemini_key=None):
        self._or_key = or_key
        self._groq_key = groq_key
        self._gemini_key = gemini_key

    def generate_content(self, model, contents, config=None):
        system_instruction = None
        temperature = 0.7
        max_tokens = 16384
        if config:
            system_instruction = getattr(config, "system_instruction", None)
            temperature = getattr(config, "temperature", 0.7)
            max_tokens = getattr(config, "max_output_tokens", 16384)

        messages = _to_openai_messages(contents, system_instruction)

        # ── 1st TRY OPENROUTER ($5 credits, direct HTTP) ──
        _or_error = None
        if self._or_key:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_OPENROUTER if m != model]
            for attempt_model in models_to_try:
                try:
                    logger.info(f"[AI] OpenRouter (direct HTTP): {attempt_model}")
                    text = _call_openrouter(messages, attempt_model, self._or_key, temperature, max_tokens)
                    logger.info(f"[AI] OpenRouter success: {attempt_model}")
                    return _Response(text)
                except Exception as e:
                    _or_error = e
                    err_str = str(e).lower()
                    logger.warning(f"[AI] OpenRouter {attempt_model}: {type(e).__name__}: {str(e)[:150]}")
                    if any(k in err_str for k in ('auth', '401', '403', 'api_key', 'unauthorized', 'forbidden', 'missing authentication')):
                        logger.error(f"[AI] OpenRouter auth — skipping all models: {str(e)[:200]}")
                        break
                    if '413' in err_str or 'request too large' in err_str:
                        break
                    if any(k in err_str for k in (
                        'rate', '429', 'quota', 'limit', 'model', 'unavailable',
                        'overloaded', 'capacity', 'insufficient_quota', 'credits',
                        'connection', 'connect', 'timeout', 'dns', 'resolve',
                        'eof', 'reset', 'abort', 'refused', 'unreachable',
                        'network', 'server error', '500', '502', '503',
                    )):
                        continue
                    break

        # ── 2nd TRY GROQ ──
        _groq_error = None
        if self._groq_key:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_GROQ if m != model]
            for attempt_model in models_to_try:
                try:
                    logger.info(f"[AI] Groq (direct HTTP): {attempt_model}")
                    text = _call_groq(messages, attempt_model, self._groq_key, temperature, 8192)
                    logger.info(f"[AI] Groq success: {attempt_model}")
                    return _Response(text)
                except Exception as e:
                    _groq_error = e
                    err_str = str(e).lower()
                    logger.warning(f"[AI] Groq {attempt_model}: {type(e).__name__}: {str(e)[:150]}")
                    if '413' in err_str or 'request too large' in err_str:
                        break
                    if any(k in err_str for k in (
                        'rate', '429', 'quota', 'limit', 'model', 'unavailable',
                        'overloaded', 'capacity',
                        'connection', 'connect', 'timeout', 'dns', 'resolve',
                        'eof', 'reset', 'abort', 'refused', 'unreachable',
                        'network', 'server error', '500', '502', '503',
                    )):
                        continue
                    break

        # ── 3rd TRY GEMINI ──
        if self._gemini_key:
            try:
                logger.info("[AI] Gemini (direct HTTP, FREE fallback)")
                text = _call_gemini(_prompt_text(contents), self._gemini_key)
                logger.info("[AI] Gemini success!")
                return _Response(text)
            except Exception as e:
                logger.warning(f"[AI] Gemini failed: {type(e).__name__}: {str(e)[:200]}")

        # All failed
        if _groq_error:
            raise _groq_error
        if _or_error:
            raise _or_error
        raise RuntimeError("Hakuna AI provider iliyofanya kazi. Angalia OPENROUTER_API_KEY.")

    def generate_content_stream(self, model, contents, config=None):
        system_instruction = None
        temperature = 0.7
        max_tokens = 16384
        if config:
            system_instruction = getattr(config, "system_instruction", None)
            temperature = getattr(config, "temperature", 0.7)
            max_tokens = getattr(config, "max_output_tokens", 16384)

        messages = _to_openai_messages(contents, system_instruction)

        # ── 1st OPENROUTER ──
        if self._or_key:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_OPENROUTER if m != model]
            for attempt_model in models_to_try:
                try:
                    logger.info(f"[AI] OpenRouter stream (direct HTTP): {attempt_model}")
                    for chunk_text in _call_openrouter_stream(messages, attempt_model, self._or_key, temperature, max_tokens):
                        yield _Chunk(chunk_text)
                    return
                except Exception as e:
                    err_str = str(e).lower()
                    logger.warning(f"[AI] OpenRouter stream {attempt_model}: {type(e).__name__}: {str(e)[:150]}")
                    if any(k in err_str for k in ('auth', '401', '403', 'api_key', 'unauthorized', 'forbidden', 'missing authentication')):
                        break
                    if '413' in err_str or 'request too large' in err_str:
                        break
                    if any(k in err_str for k in (
                        'rate', '429', 'quota', 'limit', 'model', 'unavailable',
                        'overloaded', 'capacity', 'insufficient_quota', 'credits',
                    )):
                        continue
                    break

        # ── 2nd GROQ ──
        if self._groq_key:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_GROQ if m != model]
            for attempt_model in models_to_try:
                try:
                    logger.info(f"[AI] Groq stream (direct HTTP): {attempt_model}")
                    for chunk_text in _call_groq_stream(messages, attempt_model, self._groq_key, temperature, 8192):
                        yield _Chunk(chunk_text)
                    return
                except Exception as e:
                    err_str = str(e).lower()
                    logger.warning(f"[AI] Groq stream {attempt_model}: {type(e).__name__}: {str(e)[:150]}")
                    if '413' in err_str or 'request too large' in err_str:
                        break
                    if any(k in err_str for k in (
                        'rate', '429', 'quota', 'limit', 'model', 'unavailable',
                        'overloaded', 'capacity',
                        'connection', 'connect', 'timeout', 'dns', 'resolve',
                        'eof', 'reset', 'abort', 'refused', 'unreachable',
                        'network', 'server error', '500', '502', '503',
                    )):
                        continue
                    break

        # ── 3rd GEMINI ──
        if self._gemini_key:
            try:
                logger.info("[AI] Gemini stream (FREE fallback)")
                for chunk_text in _call_gemini_stream(_prompt_text(contents), self._gemini_key):
                    yield _Chunk(chunk_text)
                return
            except Exception as e:
                logger.warning(f"[AI] Gemini stream failed: {type(e).__name__}: {str(e)[:200]}")

        raise RuntimeError("Hakuna AI provider iliyofanya kazi kwa streaming.")


class UnifiedClient:
    """Unified AI client: all providers use direct HTTP (no SDK).
    Chain: OpenRouter ($5 credits) → Groq → Gemini (FREE)."""

    def __init__(self, openrouter_key=None, groq_key=None, gemini_key=None):
        self._or_key = openrouter_key
        self._groq_key = groq_key
        self._gemini_key = gemini_key

        # Log what's configured
        if openrouter_key:
            logger.info(f"[AI] ✅ OpenRouter configured (direct HTTP) — PRIMARY")
        if groq_key:
            logger.info(f"[AI] ✅ Groq configured (direct HTTP) — fallback")
        if gemini_key:
            logger.info(f"[AI] ✅ Gemini configured (direct HTTP) — last resort FREE")
        if not any([openrouter_key, groq_key, gemini_key]):
            logger.error("[AI] ❌ NO AI PROVIDER CONFIGURED")

        self.models = _UnifiedModels(
            or_key=openrouter_key,
            groq_key=groq_key,
            gemini_key=gemini_key,
        )


# Initialize client
logger.info(f"[AI] OPENROUTER={'SET' if OPENROUTER_API_KEY else 'NOT SET'} | "
            f"GROQ={'SET' if GROQ_API_KEY else 'NOT SET'} | "
            f"GEMINI={'SET' if GOOGLE_API_KEY else 'NOT SET'}")

client = UnifiedClient(
    openrouter_key=OPENROUTER_API_KEY,
    groq_key=GROQ_API_KEY,
    gemini_key=GOOGLE_API_KEY,
) if (OPENROUTER_API_KEY or GROQ_API_KEY or GOOGLE_API_KEY) else None

model_name = PRIMARY_MODEL
logger.info(f"[AI] Model: {model_name} | Client ready: {client is not None}")
