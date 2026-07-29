"""
AI utilities for the Curriculum app.
Provider chain: OpenRouter (paid $5) → Groq (free) → Gemini (FREE, if API key set).
"""
import os
import json
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # Gemini FREE — set this for fallback

# Groq model — Works! OpenRouter has auth issues on Railway, Gemini key expired
PRIMARY_MODEL = "llama-3.3-70b-versatile"

FALLBACK_MODELS_OPENROUTER = [
    "deepseek/deepseek-chat",
    "google/gemini-2.0-flash",
    "meta-llama/llama-3.3-70b-instruct",
    "mistralai/mistral-7b-instruct",
]

FALLBACK_MODELS_GROQ = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
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


def _call_gemini(prompt_text, api_key):
    """Call Gemini API directly via HTTP. Returns response text or raises."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 16384,
        }
    }
    resp = requests.post(url, json=payload, timeout=300)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini: no candidates in response: {str(data)[:200]}")
    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    if not text:
        raise RuntimeError(f"Gemini: empty response: {str(data)[:200]}")
    return text


def _call_gemini_stream(prompt_text, api_key):
    """Call Gemini API streaming. Yields text chunks."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?alt=sse&key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 16384,
        }
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


def _contents_to_messages(contents, system_instruction=None):
    """Convert Gemini-style contents to OpenAI-style messages."""
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
                if parts:
                    text = parts[0].get("text", "") if isinstance(parts[0], dict) else str(parts[0])
                else:
                    text = item.get("content", "")
                messages.append({"role": role, "content": text})
            else:
                messages.append({"role": "user", "content": str(item)})
    else:
        messages.append({"role": "user", "content": str(contents)})
    return messages


# =============================================================================
# UNIFIED AI CLIENT — Gemini (FREE) → OpenRouter → Groq
# =============================================================================

class _UnifiedModels:
    """Mimics models.generate_content() with OpenRouter ($5 credits) → Groq → Gemini (FREE) fallback chain."""

    def __init__(self, openrouter_client=None, groq_client=None, gemini_key=None):
        self._or = openrouter_client
        self._groq = groq_client
        self._gemini_key = gemini_key  # str, not a client object

    def _try_gemini(self, contents):
        """Try Gemini first. Returns response or None."""
        if not self._gemini_key:
            logger.warning("[AI] Gemini key not available, skipping")
            return None
        try:
            prompt_text = contents
            if isinstance(contents, list):
                prompt_text = '\n'.join(
                    item.get('parts', [{}])[0].get('text', str(item))
                    if isinstance(item, dict) else str(item)
                    for item in contents
                )
            logger.info("[AI] Trying Google Gemini (FREE — primary provider)")
            text = _call_gemini(prompt_text, self._gemini_key)
            logger.info("[AI] Gemini success!")
            return _Response(text)
        except Exception as e:
            logger.warning(f"[AI] Gemini failed: {type(e).__name__}: {str(e)[:200]}")
            return None

    def _try_gemini_stream(self, contents):
        """Try Gemini streaming. Returns list of _Chunk objects on success, None on failure."""
        if not self._gemini_key:
            logger.warning("[AI] Gemini key not available, skipping")
            return None
        try:
            prompt_text = contents
            if isinstance(contents, list):
                prompt_text = '\n'.join(
                    item.get('parts', [{}])[0].get('text', str(item))
                    if isinstance(item, dict) else str(item)
                    for item in contents
                )
            logger.info("[AI] Streaming with Google Gemini (FREE — primary)")
            chunks = []
            for chunk_text in _call_gemini_stream(prompt_text, self._gemini_key):
                chunks.append(_Chunk(chunk_text))
            if not chunks:
                return None
            return chunks
        except Exception as e:
            logger.warning(f"[AI] Gemini stream failed: {type(e).__name__}: {str(e)[:200]}")
            return None

    def generate_content(self, model, contents, config=None):
        system_instruction = None
        temperature = 0.7
        max_tokens = 16384
        if config:
            system_instruction = getattr(config, "system_instruction", None)
            temperature = getattr(config, "temperature", 0.7)
            max_tokens = getattr(config, "max_output_tokens", 16384)

        messages = _contents_to_messages(contents, system_instruction)

        # ── 1st TRY GROQ (WORKS!) ──
        _groq_error = None
        if self._groq:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_GROQ if m != model]
            for attempt_model in models_to_try:
                try:
                    logger.info(f"[AI] Trying Groq model: {attempt_model}")
                    response = self._groq.chat.completions.create(
                        model=attempt_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=8192,
                    )
                    logger.info(f"[AI] Groq success with model: {attempt_model}")
                    return _Response(response.choices[0].message.content)
                except Exception as e:
                    _groq_error = e
                    err_str = str(e).lower()
                    logger.warning(f"[AI] Groq model {attempt_model} error: {type(e).__name__}: {str(e)[:150]}")
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
                    logger.error(f"[AI] Groq non-retryable error: {str(e)[:200]}")
                    raise

        # ── 2nd TRY OPENROUTER ──
        _or_error = None
        if self._or:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_OPENROUTER if m != model]
            for attempt_model in models_to_try:
                try:
                    logger.info(f"[AI] Trying OpenRouter model: {attempt_model}")
                    response = self._or.chat.completions.create(
                        model=attempt_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        extra_headers={
                            "HTTP-Referer": "https://tlm-tanzania.railway.app",
                            "X-Title": "TLM Tanzania - Teaching & Learning Materials",
                        }
                    )
                    logger.info(f"[AI] OpenRouter success with model: {attempt_model}")
                    return _Response(response.choices[0].message.content)
                except Exception as e:
                    _or_error = e
                    err_str = str(e).lower()
                    logger.warning(f"[AI] OpenRouter model {attempt_model} error: {type(e).__name__}: {str(e)[:150]}")
                    if any(k in err_str for k in ('auth', '401', '403', 'api_key', 'unauthorized', 'forbidden')):
                        logger.error(f"[AI] OpenRouter auth error — falling through: {str(e)[:200]}")
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

        # ── 3rd TRY GEMINI (if key is set and valid) ──
        gemini_result = self._try_gemini(contents)
        if gemini_result is not None:
            return gemini_result

        # All providers failed
        if _groq_error:
            raise _groq_error
        if _or_error:
            raise _or_error
        raise RuntimeError("Hakuna AI provider iliyofanya kazi. Angalia GROQ_API_KEY kwenye mazingira.")

    def generate_content_stream(self, model, contents, config=None):
        system_instruction = None
        temperature = 0.7
        max_tokens = 16384
        if config:
            system_instruction = getattr(config, "system_instruction", None)
            temperature = getattr(config, "temperature", 0.7)
            max_tokens = getattr(config, "max_output_tokens", 16384)

        messages = _contents_to_messages(contents, system_instruction)

        # ── 1st TRY GROQ (WORKS!) ──
        if self._groq:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_GROQ if m != model]
            for attempt_model in models_to_try:
                try:
                    logger.info(f"[AI] Streaming with Groq model: {attempt_model}")
                    stream = self._groq.chat.completions.create(
                        model=attempt_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=8192,
                        stream=True,
                    )
                    logger.info(f"[AI] Groq stream started with {attempt_model}")
                    for chunk in stream:
                        content = chunk.choices[0].delta.content
                        if content:
                            yield _Chunk(content)
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
                    raise

        # ── 2nd TRY OPENROUTER ──
        if self._or:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_OPENROUTER if m != model]
            for attempt_model in models_to_try:
                try:
                    logger.info(f"[AI] Streaming with OpenRouter model: {attempt_model}")
                    stream = self._or.chat.completions.create(
                        model=attempt_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        extra_headers={
                            "HTTP-Referer": "https://tlm-tanzania.railway.app",
                            "X-Title": "TLM Tanzania - Teaching & Learning Materials",
                        }
                    )
                    logger.info(f"[AI] OpenRouter stream started with {attempt_model}")
                    for chunk in stream:
                        content = chunk.choices[0].delta.content
                        if content:
                            yield _Chunk(content)
                    return
                except Exception as e:
                    err_str = str(e).lower()
                    logger.warning(f"[AI] OpenRouter stream {attempt_model}: {type(e).__name__}: {str(e)[:150]}")
                    if any(k in err_str for k in ('auth', '401', '403', 'api_key', 'unauthorized', 'forbidden')):
                        break
                    if '413' in err_str or 'request too large' in err_str:
                        break
                    if any(k in err_str for k in (
                        'rate', '429', 'quota', 'limit', 'model', 'unavailable',
                        'overloaded', 'capacity', 'insufficient_quota', 'credits',
                    )):
                        continue
                    break

        # ── 3rd TRY GEMINI (if key set) ──
        gemini_chunks = self._try_gemini_stream(contents)
        if gemini_chunks is not None:
            for chunk in gemini_chunks:
                yield chunk
            return

        raise RuntimeError("Hakuna AI provider iliyofanya kazi kwa streaming.")


class UnifiedClient:
    """Unified AI client: Google Gemini (FREE, primary) → OpenRouter → Groq."""

    def __init__(self, openrouter_key=None, groq_key=None, gemini_key=None):
        self._or = None
        self._groq = None
        self._gemini_key = gemini_key  # Store API key as string, not SDK client

        # 1. OpenRouter (fallback)
        if openrouter_key:
            try:
                from openai import OpenAI
                key_preview = openrouter_key[:12] + '...' if openrouter_key else 'NONE'
                logger.info(f"[AI] Initializing OpenRouter client with key: {key_preview}")
                self._or = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_key,
                    timeout=300.0,
                    max_retries=3,
                )
                logger.info(f"[AI] OpenRouter client initialized successfully")
            except Exception as e:
                logger.error(f"[AI] OpenRouter initialization error: {e}")
        else:
            logger.warning(f"[AI] OPENROUTER_API_KEY not set!")

        # 2. Groq (last resort fallback)
        if groq_key:
            try:
                from groq import Groq
                logger.info(f"[AI] Initializing Groq client (fallback)")
                self._groq = Groq(api_key=groq_key)
                logger.info(f"[AI] Groq client initialized")
            except Exception as e:
                logger.error(f"[AI] Groq initialization error: {e}")
        else:
            logger.warning(f"[AI] GROQ_API_KEY not set!")

        # Gemini needs NO SDK — uses direct HTTP calls via `requests`
        if self._gemini_key:
            logger.info(f"[AI] ✅ Google Gemini (FREE) is PRIMARY provider — using direct HTTP (no SDK)")
        else:
            logger.info(f"[AI] GOOGLE_API_KEY not set — Gemini unavailable")

        self.models = _UnifiedModels(
            openrouter_client=self._or,
            groq_client=self._groq,
            gemini_key=self._gemini_key,  # Pass key string, not client
        )


# Initialize the unified client
logger.info(f"[AI] "
    f"OPENROUTER_API_KEY={'SET' if OPENROUTER_API_KEY else 'NOT SET'} | "
    f"GROQ_API_KEY={'SET' if GROQ_API_KEY else 'NOT SET'} | "
    f"GOOGLE_API_KEY={'SET' if GOOGLE_API_KEY else 'NOT SET'}")
client = UnifiedClient(
    openrouter_key=OPENROUTER_API_KEY,
    groq_key=GROQ_API_KEY,
    gemini_key=GOOGLE_API_KEY,
) if (OPENROUTER_API_KEY or GROQ_API_KEY or GOOGLE_API_KEY) else None

model_name = PRIMARY_MODEL
logger.info(f"[AI] Model: {model_name} | Client ready: {client is not None}")

if client:
    logger.info(f"[AI] ✅ Google Gemini is PRIMARY provider (FREE)")
    if client._or:
        logger.info(f"[AI] ✅ OpenRouter available as fallback")
    if client._groq:
        logger.info(f"[AI] ✅ Groq available as last resort")

if not client:
    logger.error(f"[AI] ❌ NO AI PROVIDER AVAILABLE. Set at least GOOGLE_API_KEY!")
