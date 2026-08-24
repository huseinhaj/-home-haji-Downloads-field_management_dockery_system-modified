"""ai_timetable_service.py — Natural language → timetable constraints.

Uses OpenRouter (Gemini flash) to parse plain-English instructions like
"Weka Math asubuhi" or "Chemistry ishirini siku ya Ijumaa" into structured
JSON constraints that the deterministic timetable generator can consume.

The AI only *parses* the instruction — it never generates the timetable
itself.  The actual scheduling is still done by the constraint-satisfaction
algorithm in class_timetable_service.py, which guarantees clash-free results.
"""
from __future__ import annotations

import json
import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

MODEL = "google/gemini-2.5-flash"

PARSER_PROMPT = """\
Wekea mfumo wa ratiba ya shule.  Mtu ameandika maagizo kwa lugha ya kawaida
(kiingereza au kiswahili).  Anisha JSON yenye constraints ambazo algorithm
ya ratiba itatumia.

Muundo wa JSON:
{
  "constraints": [
    {
      "type": "prefer_time",
      "subject": "Mathematics",
      "period_indices": [0, 1, 2, 3],
      "reason": "Weka Math asubuhi"
    },
    {
      "type": "avoid_time",
      "subject": "Chemistry",
      "period_indices": [10, 11],
      "reason": "Chemistry isiwe baada ya chakula"
    },
    {
      "type": "avoid_day",
      "subject": "History",
      "day_indices": [4],
      "reason": "History ishirini siku ya Ijumaa"
    },
    {
      "type": "spread",
      "subject": "Biology",
      "min_days_apart": 1,
      "reason": "Sambaza Biology angalau siku 2 tofauti"
    },
    {
      "type": "group_double",
      "subject": "English",
      "enabled": true,
      "reason": "English iwe na double period"
    }
  ]
}

Aina za constraints:
- "prefer_time": Weka somo hili kwenye vipindi vilivyoperiod_indices (0=kwanza).
  period_indices ni orodha ya namba za kipindi (teaching slots tu — usafi, mapumziko na chakula havijumuishwa).
- "avoid_time": Epuka kuweka somo hili kwenye vipindi vilivyoperiod_indices.
- "avoid_day": Epuka siku hii (0=Jumatatu, 1=Jumanne, 2=Jumatano, 3=Alhamisi, 4=Ijumaa).
- "spread": Sambaza somo hili angalau siku tofauti.
- "group_double": Weka somo hili kama double period (vipindi 2 mfululizo).

Siku: 0=Jumatatu, 1=Jumanne, 2=Jumatano, 3=Alhamisi, 4=Ijumaa

UISHO:
- Rudisha JSON TU, bila maelezo mengine.
- Kama maagizo ni tupu au hayana maana ya ratiba, rudisha {"constraints": []}.
- Usibuni constraints zisizoombwa — tega kile kilichoandikwa tu.
"""


def parse_natural_language_instructions(text: str, *, available_subjects: list[str] | None = None) -> dict:
    """Parse a natural-language timetable instruction into structured constraints.

    Returns {"constraints": [...]} ready for the generator to consume.
    Falls back to {"constraints": []} if the LLM is unavailable or the
    input is empty.
    """
    text = (text or "").strip()
    if not text:
        return {"constraints": []}

    # Build the prompt with available subjects for better matching
    subject_hint = ""
    if available_subjects:
        subject_hint = (
            f"\nMasomo yanayopatikana shuleni hii: {', '.join(available_subjects)}.\n"
            "Tumia majina sahihi ya masomo haya katika constraints.\n"
        )

    user_msg = f"{subject_hint}\nMaagizo ya mtumiaji:\n{text}"

    result = _call_llm(PARSER_PROMPT + "\n" + user_msg)
    if result is None:
        logger.warning("AI timetable parser: LLM unavailable, returning empty constraints")
        return {"constraints": []}

    # Try to extract JSON from the response
    try:
        # The model might wrap JSON in ```json ... ``` or just return raw JSON
        cleaned = result.strip()
        if cleaned.startswith("```"):
            # Remove markdown code block
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        parsed = json.loads(cleaned)
        if "constraints" not in parsed:
            parsed = {"constraints": []}
        return parsed
    except (json.JSONDecodeError, ValueError):
        logger.warning("AI timetable parser: could not parse LLM response as JSON")
        return {"constraints": []}


def generate_ai_suggestion(school, current_entries: list[dict]) -> dict:
    """After timetable generation, use AI to suggest improvements.

    Returns {"suggestions": [...]} with human-readable improvement tips.
    """
    if not current_entries:
        return {"suggestions": []}

    # Build a summary of the current timetable for the AI
    from ..models import Subject, TeacherAccount, TimeSlot

    slots = list(TimeSlot.objects.filter(school=school).order_by('day_of_week', 'order'))
    teaching_slots = [s for s in slots if s.is_teaching_slot]
    subjects = {s.id: s.name for s in Subject.objects.all()}
    teachers = {t.id: t.full_name or t.email for t in TeacherAccount.objects.filter(school=school)}

    # Build a compact representation
    day_names = ['Jumatatu', 'Jumanne', 'Jumatano', 'Alhamisi', 'Ijumaa']
    lines = []
    for entry in current_entries[:50]:  # Limit for prompt size
        slot = next((s for s in slots if s.id == entry.get('time_slot_id')), None)
        if slot:
            subj = subjects.get(entry.get('subject_id'), '?')
            teach = teachers.get(entry.get('teacher_id'), '?')
            day = day_names[slot.day_of_week] if slot.day_of_week < 5 else '?'
            lines.append(f"{day} {slot.start_time}-{slot.end_time}: {subj} ({teach})")

    timetable_summary = "\n".join(lines)

    suggestion_prompt = f"""\
Umeona ratiba ya shule.  Mapendekezo ya uboreshaji:

Ratiba ya sasa:
{timetable_summary}

Toa mapendekezo 1-3 ya uboreshaji kwa lugha rahisi (Kiswahili).
Kila recommendation iwe fupi (sentensi 1-2).

Rudisha JSON:
{{"suggestions": ["Recommendation 1", "Recommendation 2"]}}
"""
    result = _call_llm(suggestion_prompt)
    if result is None:
        return {"suggestions": []}

    try:
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        parsed = json.loads(cleaned)
        return {"suggestions": parsed.get("suggestions", [])}
    except (json.JSONDecodeError, ValueError):
        return {"suggestions": []}


def _call_llm(prompt: str) -> str | None:
    """Call OpenRouter (Gemini flash) and return the response text, or None."""
    if not OPENROUTER_API_KEY:
        return None

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000,
                "temperature": 0.3,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning("AI timetable: OpenRouter %d: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("AI timetable: LLM call failed: %s", exc)
        return None
