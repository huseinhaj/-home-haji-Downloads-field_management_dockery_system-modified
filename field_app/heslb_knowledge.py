"""
HESLB Knowledge Updater
Scrapes HESLB website periodically and uses Gemini to extract
up-to-date loan requirements. Cached in Redis for fast access.
"""
import json
import logging
from datetime import datetime, timezone

import httpx
from celery import shared_task
from django.core.cache import cache

log = logging.getLogger(__name__)

CACHE_KEY    = "heslb_knowledge_v2"
CACHE_TTL    = 7 * 24 * 3600   # 1 week

SCRAPE_URLS = [
    "https://www.heslb.go.tz",
    "https://www.heslb.go.tz/en/content/news",
    "https://www.heslb.go.tz/en/content/announcements",
    "https://www.heslb.go.tz/en/content/guidelines-and-criteria",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "sw,en;q=0.9",
}


def _fetch_text(url: str) -> str:
    """Fetch URL and return clean plain text (strips HTML tags simply)."""
    try:
        with httpx.Client(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            resp = client.get(url)
            if not resp.is_success:
                return ""
            html = resp.text
            # Simple tag stripper — avoids bs4 dependency
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
            text = re.sub(r"<style[^>]*>.*?</style>",  " ", text,  flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s{3,}", "\n", text)
            return text.strip()[:4000]
    except Exception as e:
        log.warning("HESLB scrape failed (%s): %s", url, e)
        return ""


def _summarise_with_gemini(raw: str) -> str | None:
    """Ask Gemini to extract current HESLB loan requirements from raw text."""
    from field_app.ai_utils import client, FALLBACK_MODELS
    from google.genai import types as genai_types

    if not client or not raw.strip():
        return None

    prompt = (
        "Wewe ni msaidizi wa HESLB Tanzania. Soma maudhui haya kutoka tovuti ya "
        "HESLB na toa muhtasari wa taarifa zinazomhusu mwanafunzi anayeomba mkopo. "
        "Zungumzia hasa:\n"
        "1. Tarehe za dirisha la maombi (wazi/imefungwa/lini linafungua)\n"
        "2. Nyaraka mpya zinazohitajika (BV codes, NaPA reference, NIDA, nk)\n"
        "3. Mabadiliko yoyote ya masharti au vigezo vya kupata mkopo\n"
        "4. Ada za maombi na jinsi ya kulipa\n"
        "5. Tangazo lolote muhimu jipya\n\n"
        "Jibu kwa Kiswahili. Kuwa mfupi na wazi. Ukikosa taarifa, sema hivyo.\n\n"
        f"MAUDHUI:\n{raw}"
    )

    for mdl in FALLBACK_MODELS:
        try:
            cfg = genai_types.GenerateContentConfig(temperature=0.1, max_output_tokens=600)
            resp = client.models.generate_content(
                model=mdl,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config=cfg,
            )
            return (resp.text or "").strip() or None
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                continue
            log.warning("Gemini summarise failed (%s): %s", mdl, e)
            continue
    return None


def scrape_and_update() -> dict:
    """
    Main function: scrape HESLB → summarise → cache.
    Returns a result dict: {ok: bool, summary: str, updated_at: str, error: str}
    """
    parts = []
    for url in SCRAPE_URLS:
        text = _fetch_text(url)
        if text:
            parts.append(f"--- {url} ---\n{text}")

    if not parts:
        return {"ok": False, "error": "Tovuti ya HESLB haikusikika.", "summary": "", "updated_at": ""}

    combined = "\n\n".join(parts)[:8000]
    summary = _summarise_with_gemini(combined)

    if not summary:
        return {"ok": False, "error": "AI haikuweza kusoma maudhui.", "summary": "", "updated_at": ""}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    record = {
        "ok": True,
        "summary": summary,
        "updated_at": now,
        "error": "",
    }
    cache.set(CACHE_KEY, json.dumps(record), timeout=CACHE_TTL)
    log.info("HESLB knowledge updated at %s (%d chars)", now, len(summary))
    return record


def get_knowledge() -> dict | None:
    """Return cached knowledge dict, or None if not yet fetched."""
    raw = cache.get(CACHE_KEY)
    return json.loads(raw) if raw else None


@shared_task(name="heslb_knowledge.refresh", max_retries=2)
def refresh_heslb_knowledge():
    """Celery task — run via Beat schedule."""
    result = scrape_and_update()
    return result.get("ok"), result.get("updated_at", ""), result.get("error", "")
