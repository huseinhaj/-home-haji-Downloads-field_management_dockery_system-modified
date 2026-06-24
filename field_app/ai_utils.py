import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
model_name = "llama-3.3-70b-versatile"
FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]


class GenerateContentConfig:
    def __init__(self, system_instruction=None, temperature=0.7, max_output_tokens=8192, **kwargs):
        self.system_instruction = system_instruction
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens


class _GroqResponse:
    def __init__(self, text):
        self.text = text


class _GroqChunk:
    def __init__(self, text):
        self.text = text


def _contents_to_messages(contents, system_instruction=None):
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


class _GroqModels:
    def __init__(self, groq_client):
        self._groq = groq_client

    def generate_content(self, model, contents, config=None):
        system_instruction = None
        temperature = 0.7
        max_tokens = 8192
        if config:
            system_instruction = getattr(config, "system_instruction", None)
            temperature = getattr(config, "temperature", 0.7)
            max_tokens = getattr(config, "max_output_tokens", 8192)

        messages = _contents_to_messages(contents, system_instruction)

        # Try primary model first, then fallbacks
        models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]
        last_error = None
        for attempt_model in models_to_try:
            try:
                response = self._groq.chat.completions.create(
                    model=attempt_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return _GroqResponse(response.choices[0].message.content)
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                # Only continue to next model on rate-limit or model-unavailable errors
                if any(k in err_str for k in ('rate', '429', 'quota', 'limit', 'model', 'unavailable', 'overloaded', 'capacity')):
                    continue
                # For other errors (auth, bad request, etc.) raise immediately
                raise
        raise last_error

    def generate_content_stream(self, model, contents, config=None):
        system_instruction = None
        temperature = 0.7
        max_tokens = 8192
        if config:
            system_instruction = getattr(config, "system_instruction", None)
            temperature = getattr(config, "temperature", 0.7)
            max_tokens = getattr(config, "max_output_tokens", 8192)

        messages = _contents_to_messages(contents, system_instruction)

        models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]
        last_error = None
        for attempt_model in models_to_try:
            try:
                stream = self._groq.chat.completions.create(
                    model=attempt_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
                for chunk in stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield _GroqChunk(content)
                return
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if any(k in err_str for k in ('rate', '429', 'quota', 'limit', 'model', 'unavailable', 'overloaded', 'capacity')):
                    continue
                raise
        raise last_error


class GroqClient:
    def __init__(self, api_key):
        from groq import Groq
        self._groq = Groq(api_key=api_key)
        self.models = _GroqModels(self._groq)


client = GroqClient(api_key=api_key) if api_key else None
