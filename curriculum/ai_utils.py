"""
AI utilities for the Curriculum app — supports OpenRouter (primary) + Groq (fallback).
OpenRouter gives access to DeepSeek, Gemini, Llama, and many more models.
"""
import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Default model — cheap & capable via OpenRouter
# You can change this to any OpenRouter model ID: https://openrouter.ai/models
PRIMARY_MODEL = "deepseek/deepseek-chat"
# Alternative good & cheap models:
# "google/gemini-2.0-flash" (very cheap, fast)
# "meta-llama/llama-3.3-70b-instruct" (same as current Groq model)
# "qwen/qwen-2.5-72b-instruct" (great for structured output)

FALLBACK_MODELS_OPENROUTER = [
    "deepseek/deepseek-chat",
    "google/gemini-2.0-flash",
    "meta-llama/llama-3.3-70b-instruct",
    "qwen/qwen-2.5-72b-instruct",
]

FALLBACK_MODELS_GROQ = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]


import logging

logger = logging.getLogger(__name__)


class GenerateContentConfig:
    def __init__(self, system_instruction=None, temperature=0.7, max_output_tokens=4096, **kwargs):
        self.system_instruction = system_instruction
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens


class _Response:
    def __init__(self, text):
        self.text = text


class _Chunk:
    def __init__(self, text):
        self.text = text


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
# UNIFIED AI CLIENT — tries OpenRouter first, falls back to Groq
# =============================================================================

class _UnifiedModels:
    """Mimics Groq's models.generate_content() interface but uses OpenRouter + Groq fallback."""

    def __init__(self, openrouter_client=None, groq_client=None):
        self._or = openrouter_client
        self._groq = groq_client

    def generate_content(self, model, contents, config=None):
        system_instruction = None
        temperature = 0.7
        max_tokens = 4096
        if config:
            system_instruction = getattr(config, "system_instruction", None)
            temperature = getattr(config, "temperature", 0.7)
            max_tokens = getattr(config, "max_output_tokens", 4096)

        messages = _contents_to_messages(contents, system_instruction)

        # ── TRY OPENROUTER FIRST ──
        if self._or:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_OPENROUTER if m != model]
            last_error = None
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
                    last_error = e
                    err_str = str(e).lower()
                    logger.warning(f"[AI] OpenRouter model {attempt_model} error: {type(e).__name__}: {str(e)[:150]}")
                    # 413 = payload too large — not retryable for TPM limit
                    if '413' in err_str or 'request too large' in err_str:
                        logger.error(f"[AI] OpenRouter request too large for {attempt_model}, skipping all OpenRouter models")
                        break
                    if any(k in err_str for k in (
                        'rate', '429', 'quota', 'limit', 'model', 'unavailable',
                        'overloaded', 'capacity', 'insufficient_quota', 'credits'
                    )):
                        continue
                    logger.error(f"[AI] OpenRouter non-retryable error, raising: {str(e)[:200]}")
                    raise

        # ── FALLBACK TO GROQ ──
        if self._groq:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_GROQ if m != model]
            last_error = None
            for attempt_model in models_to_try:
                try:
                    logger.info(f"[AI] Trying Groq model: {attempt_model}")
                    response = self._groq.chat.completions.create(
                        model=attempt_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=2048,  # Lower for Groq (TPM limits are tight)
                    )
                    logger.info(f"[AI] Groq success with model: {attempt_model}")
                    return _Response(response.choices[0].message.content)
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    logger.warning(f"[AI] Groq model {attempt_model} error: {type(e).__name__}: {str(e)[:150]}")
                    # For Groq: 413 = TPM limit — non-retryable on same tier
                    if '413' in err_str or 'request too large' in err_str:
                        logger.error(f"[AI] Groq request too large for {attempt_model}, not retrying further Groq models")
                        # Don't continue — break immediately, this won't work on other Groq models either
                        raise last_error
                    if any(k in err_str for k in (
                        'rate', '429', 'quota', 'limit', 'model', 'unavailable',
                        'overloaded', 'capacity'
                    )):
                        continue
                    logger.error(f"[AI] Groq non-retryable error, raising: {str(e)[:200]}")
                    raise
            if last_error:
                raise last_error

        raise RuntimeError("Hakuna AI provider iliyosanidiwa. Weka OPENROUTER_API_KEY au GROQ_API_KEY kwenye .env")

    def generate_content_stream(self, model, contents, config=None):
        system_instruction = None
        temperature = 0.7
        max_tokens = 4096
        if config:
            system_instruction = getattr(config, "system_instruction", None)
            temperature = getattr(config, "temperature", 0.7)
            max_tokens = getattr(config, "max_output_tokens", 4096)

        messages = _contents_to_messages(contents, system_instruction)

        # Try OpenRouter first
        if self._or:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_OPENROUTER if m != model]
            last_error = None
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
                    last_error = e
                    err_str = str(e).lower()
                    logger.warning(f"[AI] OpenRouter stream {attempt_model}: {type(e).__name__}: {str(e)[:150]}")
                    if '413' in err_str or 'request too large' in err_str:
                        logger.error(f"[AI] OpenRouter stream request too large for {attempt_model}, skipping")
                        break
                    if any(k in err_str for k in (
                        'rate', '429', 'quota', 'limit', 'model', 'unavailable',
                        'overloaded', 'capacity', 'insufficient_quota', 'credits'
                    )):
                        continue
                    raise

        # Fallback to Groq
        if self._groq:
            models_to_try = [model] + [m for m in FALLBACK_MODELS_GROQ if m != model]
            last_error = None
            for attempt_model in models_to_try:
                try:
                    logger.info(f"[AI] Streaming with Groq model: {attempt_model}")
                    stream = self._groq.chat.completions.create(
                        model=attempt_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                    )
                    logger.info(f"[AI] Groq stream started with {attempt_model}")
                    for chunk in stream:
                        content = chunk.choices[0].delta.content
                        if content:
                            yield _Chunk(content)
                    return
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    logger.warning(f"[AI] Groq stream {attempt_model}: {type(e).__name__}: {str(e)[:150]}")
                    if '413' in err_str or 'request too large' in err_str:
                        raise
                    if any(k in err_str for k in (
                        'rate', '429', 'quota', 'limit', 'model', 'unavailable',
                        'overloaded', 'capacity'
                    )):
                        continue
                    raise
            if last_error:
                raise last_error

        raise RuntimeError("Hakuna AI provider iliyosanidiwa.")


class UnifiedClient:
    """Unified AI client: OpenRouter (primary) → Groq (fallback)."""

    def __init__(self, openrouter_key=None, groq_key=None):
        self._or = None
        self._groq = None

        # Try to set up OpenRouter
        if openrouter_key:
            try:
                from openai import OpenAI
                key_preview = openrouter_key[:12] + '...' if openrouter_key else 'NONE'
                logger.info(f"[AI] Initializing OpenRouter client with key: {key_preview}")
                self._or = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_key,
                )
                logger.info(f"[AI] OpenRouter client initialized successfully")
            except Exception as e:
                logger.error(f"[AI] OpenRouter initialization error: {e}")
        else:
            logger.warning(f"[AI] OPENROUTER_API_KEY not set!")

        # Try to set up Groq as fallback
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

        self.models = _UnifiedModels(
            openrouter_client=self._or,
            groq_client=self._groq,
        )


# Initialize the unified client
logger.info(f"[AI] "
    f"OPENROUTER_API_KEY={'SET' if OPENROUTER_API_KEY else 'NOT SET'} | "
    f"GROQ_API_KEY={'SET' if GROQ_API_KEY else 'NOT SET'}")
client = UnifiedClient(
    openrouter_key=OPENROUTER_API_KEY,
    groq_key=GROQ_API_KEY,
) if (OPENROUTER_API_KEY or GROQ_API_KEY) else None

model_name = PRIMARY_MODEL
logger.info(f"[AI] Model: {model_name} | Client ready: {client is not None}")

# Also log if client has OpenRouter available
if client and client._or:
    logger.info(f"[AI] OpenRouter provider is AVAILABLE")
if client and client._groq:
    logger.info(f"[AI] Groq provider is AVAILABLE as fallback")
