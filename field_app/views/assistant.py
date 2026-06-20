"""
AI Application Assistant — helps students prepare HESLB and TCU applications
through guided Swahili conversation. Uses streaming (SSE) for real-time responses.
"""
import json
import time
from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
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

[SEHEMU 1b - TAARIFA ZA ZIADA (HESLB)]
9. mahali_kuzaliwa — Mahali pa kuzaliwa: "Mainland" (Tanzania Bara) au "Zanzibar" au "Nje ya Tanzania"
10. aina_ya_elimu — Aina ya elimu unayoombea mkopo: "Bachelor Degree", "Diploma", "Certificate" au "Masters"
11. rita_namba — Namba ya uthibitisho wa RITA (kutoka cheti cha kuzaliwa) — mfano: 2342

[SEHEMU 2 - MATOKEO YA KIDATO CHA NNE]
12. necta_olevel_aina — Aina ya mtahiniwa: "S" (shule ya serikali/binafsi) au "P" (kibinafsi/private)
13. necta_olevel_shule — Namba ya shule (School Number) — mfano: 2895
14. necta_olevel_mtahiniwa — Namba ya mtahiniwa (Candidate Number) — mfano: 0030
15. mwaka_olevel — Mwaka wa kuhitimu kidato cha 4 — mfano: 2018
16. daraja_olevel — Daraja (Division I / II / III / IV)

[SEHEMU 3 - MATOKEO YA KIDATO CHA SITA]
17. necta_alevel_aina — Aina ya mtahiniwa: "S" au "P"
18. necta_alevel_shule — Namba ya shule (A-Level)
19. necta_alevel_mtahiniwa — Namba ya mtahiniwa (A-Level)
20. mwaka_alevel — Mwaka wa kuhitimu kidato cha 6
21. masomo_alama — Masomo na alama za A-Level (mfano: Physics A, Chemistry B, Mathematics C)
22. gpa_alevel — GPA ya A-Level (mfano: 3.2)

[SEHEMU 4 - CHAGUO ZA PROGRAMU (TCU)]
23. chuo_1 — Chuo cha kwanza na programu (mfano: University of Dar es Salaam — BSc Computer Science)
24. chuo_2 — Chuo cha pili na programu
25. chuo_3 — Chuo cha tatu na programu

[SEHEMU 5 - TAARIFA ZA FAMILIA (kwa HESLB)]
26. jina_baba — Jina la baba (au "Amefariki" kama hayupo)
27. jina_mama — Jina la mama (au "Amefariki" kama hayupo)
28. mlezi — Jina na namba ya simu ya mlezi/guardian (kama wazazi wote wamefariki, sema "Sina" kama wazazi wote wako)
29. mapato_familia — Mapato ya familia kwa mwezi (Tsh) — sema "Sina kipato" kama familia hana
30. idadi_ndugu — Idadi ya ndugu wanaotegemea familia (ukijumuisha wewe mwenyewe)

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

VALID_FIELDS = {
    "jina_kamili", "tarehe_kuzaliwa", "jinsia", "namba_nida", "namba_simu",
    "barua_pepe", "mkoa_asili", "wilaya_asili",
    # HESLB extra
    "mahali_kuzaliwa", "aina_ya_elimu", "rita_namba",
    # O-Level (split)
    "necta_olevel_aina", "necta_olevel_shule", "necta_olevel_mtahiniwa",
    "mwaka_olevel", "daraja_olevel",
    # A-Level (split)
    "necta_alevel_aina", "necta_alevel_shule", "necta_alevel_mtahiniwa",
    "mwaka_alevel", "masomo_alama", "gpa_alevel",
    # Programme choices
    "chuo_1", "chuo_2", "chuo_3",
    # Family
    "jina_baba", "jina_mama", "mlezi", "mapato_familia", "idadi_ndugu",
}


def _build_contents(history: list) -> list:
    return [
        {"role": "model" if m["role"] == "assistant" else "user",
         "parts": [{"text": m["content"]}]}
        for m in history
    ]


def _make_cfg():
    return genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.4,
        max_output_tokens=1024,
    )


def _extract_data(text: str) -> dict | None:
    if "[[DATA_READY]]" not in text:
        return None
    try:
        start = text.index("[[DATA_READY]]") + len("[[DATA_READY]]")
        end = text.index("[[/DATA_READY]]")
        return json.loads(text[start:end].strip())
    except Exception:
        return None


def _call_gemini(history: list) -> str:
    """Non-streaming call for the opening message only."""
    if client is None:
        return "Samahani, huduma ya AI haitumiki kwa sasa."
    cfg = _make_cfg()
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=model_name, contents=_build_contents(history), config=cfg)
            return resp.text or "Samahani, jibu halijapatikana."
        except Exception as e:
            err = str(e)
            if ("429" in err or "RESOURCE_EXHAUSTED" in err) and attempt < 2:
                time.sleep(8 * (attempt + 1))
                continue
            return f"Hitilafu ya AI: {err[:100]}."
    return "Samahani, mfumo haujaweza kujibu. Jaribu tena."


def application_assistant(request):
    """Main page — initializes session and gets opening AI message."""
    request.session["app_history"] = []
    request.session["app_data"] = {}
    request.session["app_status"] = "collecting"

    history = [{"role": "user", "content": "Habari, nataka usaidizi wa kuandaa maombi ya HESLB na TCU."}]
    opening = _call_gemini(history)
    history.append({"role": "assistant", "content": opening})
    request.session["app_history"] = history

    return render(request, "field_app/application_assistant.html", {
        "opening_message": opening,
    })


@require_POST
def application_chat_stream(request):
    """Streaming endpoint — returns AI response token by token as SSE."""
    user_message = request.POST.get("message", "").strip()

    def error_stream(msg):
        yield f"data: {json.dumps({'error': msg})}\n\n"

    if not user_message:
        return StreamingHttpResponse(
            error_stream("Ujumbe haujapatikana."), content_type="text/event-stream")

    if client is None:
        return StreamingHttpResponse(
            error_stream("Huduma ya AI haitumiki kwa sasa."), content_type="text/event-stream")

    status = request.session.get("app_status", "collecting")
    if status == "done":
        return StreamingHttpResponse(
            error_stream("Maombi yako yamekamilika tayari."), content_type="text/event-stream")

    history = list(request.session.get("app_history", []))
    history.append({"role": "user", "content": user_message})
    contents = _build_contents(history)
    cfg = _make_cfg()

    # Ensure session exists before generator starts
    if not request.session.session_key:
        request.session.save()

    def generate():
        full_text = ""
        data_block_started = False

        for attempt in range(3):
            try:
                for chunk in client.models.generate_content_stream(
                    model=model_name, contents=contents, config=cfg
                ):
                    token = chunk.text or ""
                    if not token:
                        continue
                    full_text += token

                    # Stream only text before [[DATA_READY]] marker
                    if not data_block_started:
                        if "[[DATA_READY]]" in full_text:
                            data_block_started = True
                            # Yield only the visible portion from this chunk
                            marker_pos = full_text.index("[[DATA_READY]]")
                            prev_visible = full_text[:marker_pos]
                            chunk_start = marker_pos - len(token)
                            visible_from_chunk = prev_visible[max(0, chunk_start):]
                            if visible_from_chunk:
                                yield f"data: {json.dumps({'t': visible_from_chunk})}\n\n"
                        else:
                            yield f"data: {json.dumps({'t': token})}\n\n"
                break  # success — exit retry loop

            except Exception as e:
                err = str(e)
                if ("429" in err or "RESOURCE_EXHAUSTED" in err) and attempt < 2:
                    yield f"data: {json.dumps({'t': ' [subiri kidogo...] '})}\n\n"
                    time.sleep(8 * (attempt + 1))
                    continue
                yield f"data: {json.dumps({'error': err[:120]})}\n\n"
                return

        # Extract structured data
        extracted = _extract_data(full_text)
        display_text = full_text
        if extracted:
            display_text = full_text[:full_text.index("[[DATA_READY]]")].strip()
            if not display_text:
                display_text = "Asante! Nimekusanya taarifa zako zote. Tafadhali kagua na uthibitishe."

        # Persist to session inside generator
        history.append({"role": "assistant", "content": display_text})
        request.session["app_history"] = history
        if extracted:
            request.session["app_data"] = extracted
            request.session["app_status"] = "preview"
        request.session.save()

        # Final SSE event
        final = {"done": True, "status": "preview" if extracted else "collecting"}
        if extracted:
            final["data"] = extracted
        yield f"data: {json.dumps(final)}\n\n"

    resp = StreamingHttpResponse(generate(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"   # disable nginx buffering
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


@require_POST
def application_confirm(request):
    data = request.session.get("app_data", {})
    if not data:
        return JsonResponse({"error": "Hakuna data iliyokusanywa."}, status=400)
    request.session["app_status"] = "confirmed"
    return JsonResponse({
        "status": "confirmed",
        "message": "Taarifa zako zimethibitishwa. Hatua inayofuata: weka nywila yako ya HESLB ili AI iingie mfumo.",
    })


@require_POST
def application_start_automation(request):
    """Receive HESLB credentials and launch Playwright automation task."""
    from field_app.heslb_automation import run_heslb_automation, set_status

    data = request.session.get("app_data", {})
    if not data:
        return JsonResponse({"error": "Taarifa hazipo. Rudi ukamilishe mazungumzo kwanza."}, status=400)

    email    = request.POST.get("heslb_email", "").strip()
    password = request.POST.get("heslb_password", "").strip()
    if not email or not password:
        return JsonResponse({"error": "Weka barua pepe na nywila ya HESLB."}, status=400)

    session_id = request.session.session_key or request.session.create()
    # Initial status
    set_status(session_id, {"msg": "Inaanzisha...", "step": 0, "done": False, "error": ""})

    # Launch async Celery task — credentials never stored, only passed in memory
    run_heslb_automation.delay(session_id, data, {"email": email, "password": password})

    request.session["heslb_session_id"] = session_id
    return JsonResponse({"status": "started", "session_id": session_id})


def application_auto_status(request):
    """Poll endpoint — returns automation progress + latest screenshots."""
    from field_app.heslb_automation import get_status, get_screenshots

    session_id = request.session.get("heslb_session_id", "")
    if not session_id:
        return JsonResponse({"error": "Hakuna automation inayoendelea."}, status=404)

    status  = get_status(session_id)
    shots   = get_screenshots(session_id)
    last_shot = shots[-1] if shots else None
    return JsonResponse({
        "msg":   status.get("msg", ""),
        "step":  status.get("step", 0),
        "done":  status.get("done", False),
        "error": status.get("error", ""),
        "screenshot": last_shot,
        "total_shots": len(shots),
    })


@require_POST
def application_edit_field(request):
    field = request.POST.get("field", "")
    value = request.POST.get("value", "").strip()
    if field in VALID_FIELDS:
        data = request.session.get("app_data", {})
        data[field] = value
        request.session["app_data"] = data
        request.session["app_status"] = "preview"
        return JsonResponse({"status": "ok"})
    return JsonResponse({"error": "Sehemu haikupatikana."}, status=400)
