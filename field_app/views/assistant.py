"""
AI Application Assistant — helps students prepare HESLB and TCU applications
through guided Swahili conversation.
"""
import json
import time
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from google.genai import types as genai_types
from field_app.ai_utils import client, model_name

SYSTEM_PROMPT = """Wewe ni "Msaidizi" — AI inayosaidia wanafunzi wa Tanzania kuandaa maombi ya mkopo wa HESLB na udahili wa TCU kwa njia ya mazungumzo ya kawaida kwa Kiswahili.

KAZI YAKO:
Kukusanya taarifa zote zinazohitajika kwa mpangilio, ukiuliza swali MOJA kwa wakati mmoja. Kuwa rafiki, mwenye subira na msaada. Ukipata jibu lisilo wazi, omba ufafanuzi kwa upole.

TAARIFA UNAZOHITAJI KUKUSANYA (kwa mpangilio huu):

[SEHEMU 1 - TAARIFA ZA KIBINAFSI]
1. jina_kamili — Jina kamili la mwanafunzi
2. tarehe_kuzaliwa — Tarehe ya kuzaliwa (DD/MM/YYYY)
3. jinsia — Jinsia (Kiume / Kike)
4. namba_nida — Namba ya kitambulisho cha taifa (NIDA) — herufi 20
5. namba_simu — Namba ya simu ya mwanafunzi
6. barua_pepe — Barua pepe (optional — sema "Sina" kama hana)
7. mkoa_asili — Mkoa wa asili wa mwanafunzi
8. wilaya_asili — Wilaya ya asili

[SEHEMU 2 - MATOKEO YA KIDATO CHA NNE]
9. necta_olevel_index — Namba ya mtihani wa NECTA (O-Level), mfano: S.0123/0456/2020
10. mwaka_olevel — Mwaka wa kuhitimu kidato cha 4
11. daraja_olevel — Daraja (Division I / II / III / IV)

[SEHEMU 3 - MATOKEO YA KIDATO CHA SITA]
12. necta_alevel_index — Namba ya mtihani wa NECTA (A-Level), mfano: S.0123/0456/2022
13. mwaka_alevel — Mwaka wa kuhitimu kidato cha 6
14. masomo_alama — Masomo na alama za A-Level (mfano: Physics A, Chemistry B, Mathematics C)
15. gpa_alevel — GPA ya A-Level (mfano: 3.8 au 4.0)

[SEHEMU 4 - CHAGUO ZA PROGRAMU]
16. chuo_1 — Chuo cha kwanza na programu (mfano: University of Dar es Salaam — BSc Computer Science)
17. chuo_2 — Chuo cha pili na programu
18. chuo_3 — Chuo cha tatu na programu

[SEHEMU 5 - TAARIFA ZA FAMILIA (kwa HESLB)]
19. jina_baba — Jina la baba (au "Amefariki" kama hayupo)
20. jina_mama — Jina la mama (au "Amefariki" kama hayupo)
21. mlezi — Jina na namba ya simu ya mlezi/guardian (kama wazazi wote wamefariki)
22. mapato_familia — Mapato ya familia kwa mwezi (Tsh) — kama familia hana kipato sema "Sina kipato"
23. idadi_ndugu — Idadi ya ndugu wanaotegemea familia (ukijumuisha wewe mwenyewe)

MAELEKEZO YA MAZUNGUMZO:
- Anza kwa salamu fupi na maelezo ya lengo la mazungumzo
- Uliza swali moja kwa wakati — usijumlishe maswali mengi
- Ukipokea jibu, thibitisha kwa maneno mafupi (mfano: "Asante, nimeandika...") kisha endelea
- Namba za NECTA, NIDA, na simu — thibitisha muundo sahihi
- Kwa masomo ya A-Level, pokea kama orodha na ujaza kimoja kimoja
- Ukikamilisha taarifa ZOTE, andika hasa hivi mwishoni mwa ujumbe wako:
  [[DATA_READY]]
  kisha uandike JSON halisi kama hii:
  {"jina_kamili": "...", "tarehe_kuzaliwa": "...", ...fields zote...}
  [[/DATA_READY]]

MUHIMU SANA:
- Jibu DAIMA kwa Kiswahili tu
- Usitoe maelezo ya kisayansi au ya kiufundi — ongea kwa lugha rahisi
- Usiulize taarifa ambazo hazipo kwenye orodha hii
- Ukiwa umekusanya taarifa zote, toa muhtasari mzuri na alama [[DATA_READY]]"""


def _call_gemini(history: list) -> str:
    """Call Gemini with conversation history. Retries up to 3x on 429 quota errors."""
    if client is None:
        return "Samahani, huduma ya AI haitumiki kwa sasa. Wasiliana na msimamizi."

    contents = []
    for msg in history:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    cfg = genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.4,
        max_output_tokens=1024,
    )

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=cfg,
            )
            return response.text or "Samahani, jibu halijapatikana. Jaribu tena."
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                if attempt < 2:
                    time.sleep(8 * (attempt + 1))  # 8s then 16s
                    continue
                return "Samahani, mfumo una msongamano kwa sasa. Subiri sekunde 30 kisha jaribu tena."
            return f"Hitilafu ya AI: {err[:100]}. Jaribu tena."
    return "Samahani, mfumo haujaweza kujibu. Jaribu tena baadaye."


def _extract_data(text: str) -> dict | None:
    """Extract structured data from AI response if [[DATA_READY]] marker present."""
    if "[[DATA_READY]]" not in text:
        return None
    try:
        start = text.index("[[DATA_READY]]") + len("[[DATA_READY]]")
        end = text.index("[[/DATA_READY]]")
        json_str = text[start:end].strip()
        return json.loads(json_str)
    except Exception:
        return None


def application_assistant(request):
    """Main page — initializes a new chat session."""
    request.session["app_history"] = []
    request.session["app_data"] = {}
    request.session["app_status"] = "collecting"

    # Get opening message from AI
    history = [{"role": "user", "content": "Habari, nataka usaidizi wa kuandaa maombi ya HESLB na TCU."}]
    opening = _call_gemini(history)
    history.append({"role": "assistant", "content": opening})
    request.session["app_history"] = history

    return render(request, "field_app/application_assistant.html", {
        "opening_message": opening,
    })


@require_POST
def application_chat_send(request):
    """AJAX endpoint — receives student message, returns AI reply."""
    user_message = request.POST.get("message", "").strip()
    if not user_message:
        return JsonResponse({"error": "Ujumbe haujapatikana."}, status=400)

    history = request.session.get("app_history", [])
    status = request.session.get("app_status", "collecting")

    if status == "done":
        return JsonResponse({"reply": "Maombi yako yamekamilika tayari.", "status": "done"})

    history.append({"role": "user", "content": user_message})
    ai_reply = _call_gemini(history)

    extracted = _extract_data(ai_reply)
    if extracted:
        request.session["app_data"] = extracted
        request.session["app_status"] = "preview"
        # Clean reply — remove the JSON block before showing to user
        display_reply = ai_reply[:ai_reply.index("[[DATA_READY]]")].strip()
        if not display_reply:
            display_reply = "Asante! Nimekusanya taarifa zako zote. Tafadhali kagua muhtasari upande wa kulia na uthibitishe."
        history.append({"role": "assistant", "content": display_reply})
        request.session["app_history"] = history
        return JsonResponse({
            "reply": display_reply,
            "status": "preview",
            "data": extracted,
        })

    history.append({"role": "assistant", "content": ai_reply})
    request.session["app_history"] = history

    return JsonResponse({"reply": ai_reply, "status": status})


@require_POST
def application_confirm(request):
    """Student confirms the collected data — marks session as done."""
    data = request.session.get("app_data", {})
    if not data:
        return JsonResponse({"error": "Hakuna data iliyokusanywa."}, status=400)
    request.session["app_status"] = "done"
    # TODO: persist data / trigger browser automation
    return JsonResponse({"status": "done", "message": "Taarifa zako zimethibitishwa. Hatua inayofuata: AI itaingia mfumo wa HESLB kwa niaba yako."})


@require_POST
def application_edit_field(request):
    """Student edits a single field from the preview panel."""
    field = request.POST.get("field", "")
    value = request.POST.get("value", "").strip()
    data = request.session.get("app_data", {})
    # Allow saving any valid field key (for demo mode pre-population)
    VALID_FIELDS = {
        "jina_kamili","tarehe_kuzaliwa","jinsia","namba_nida","namba_simu",
        "barua_pepe","mkoa_asili","wilaya_asili","necta_olevel_index",
        "mwaka_olevel","daraja_olevel","necta_alevel_index","mwaka_alevel",
        "masomo_alama","gpa_alevel","chuo_1","chuo_2","chuo_3",
        "jina_baba","jina_mama","mlezi","mapato_familia","idadi_ndugu",
    }
    if field in VALID_FIELDS:
        data[field] = value
        request.session["app_data"] = data
        request.session["app_status"] = "preview"
        return JsonResponse({"status": "ok"})
    return JsonResponse({"error": "Sehemu haikupatikana."}, status=400)
