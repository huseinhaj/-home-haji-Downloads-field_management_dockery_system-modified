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
from field_app.ai_utils import client, model_name, FALLBACK_MODELS

SYSTEM_PROMPT = """Wewe ni "HESLB Msaidizi" — AI inayosaidia wanafunzi wa Tanzania kukusanya taarifa zote zinazohitajika kwa maombi ya mkopo wa HESLB 2026/2027 kupitia mfumo wa OLAMS.

DIRISHA LA MKOPO: Juni 19 – Agosti 31, 2026. Ada ya maombi: Tsh 30,000 (hazirudishwi).

KAZI YAKO: Uliza swali MOJA kwa wakati mmoja kwa lugha ya Kiswahili. Baada ya kila jibu, thibitisha kwa maneno mafupi kisha endelea na swali lijalo. Mazungumzo yawe ya kirafiki na ya kuelewa.

════════════════════════════════════
MPANGILIO WA KUKUSANYA TAARIFA:
════════════════════════════════════

[A] AINA YA MWOMBAJI (Uliza kwanza kabisa)
- aina_mwombaji: "fresh_alevel" (Mhitimu wa Form 6 mwaka huu au miaka 5 iliyopita 2022-2026)
                  "ftca" (Continuing — mwanafunzi aliye chuoni lakini alikosa mkopo)
                  "diploma" (Mhitimu wa Diploma anayeomba Degree)

[B] TAARIFA ZA MSINGI (BASIC INFORMATION)
1. jina_la_kwanza — First Name
2. jina_la_kati — Middle Name
3. jina_la_mwisho — Last Name (Surname)
4. necta_form4_index — Namba ya mtihani wa Form 4 (mfano: S2895/0030/2018)
   MUHIMU: Namba HII inatumika kama kitambulisho kikuu cha maombi
5. birth_verification_code — Namba ya uhakiki wa cheti cha kuzaliwa kutoka RITA/ZCSRA
   MUHIMU: Lazima ianze na 2026 (mfano: 2026XXXXXX-BV). Namba za mwaka jana HAZIFANYI KAZI.
6. barua_pepe — Email address
7. namba_benki — Namba ya akaunti ya benki (jina lazima lifanane na lile la cheti cha Form 4)
8. jina_benki — Jina la benki (mfano: CRDB, NMB, NBC, Equity, nk)
9. namba_simu — Namba ya simu inayopatikana (itumike kupokea taarifa za mkopo)

[C] DEMOGRAPHIC INFORMATION
10. namba_nida — Namba ya NIDA (NIN) — LAZIMA kwa wenye umri 18+ (herufi 20)
    Kama hana NIDA na ana umri chini ya 18: weka "CHINI YA 18"
11. mkoa_kuzaliwa — Mkoa wa kuzaliwa
12. wilaya_kuzaliwa — Wilaya ya kuzaliwa
13. kata_kuzaliwa — Kata ya kuzaliwa
14. napa_reference — Namba ya NaPA (National Physical Address) ya mwombaji
    (Inatolewa na Mtendaji wa Mtaa/Kijiji/Kata baada ya kusajiliwa mfumoni)

[D] PRELIMINARY — HALI YA MWOMBAJI
15. una_ulemavu — Je, una ulemavu wowote? (NDIYO / HAPANA)
    Kama NDIYO: uliza namba ya ulemavu kutoka Ofisi ya Waziri Mkuu (kama ipo)

[E] TAARIFA ZA MAMA
16. mama_anajulikana — Je, mama yako anajulikana? (NDIYO / HAPANA)
Kama NDIYO:
  17. mama_yupo_hai — Je, mama yako yupo hai? (NDIYO / HAPANA)
  Kama HAPANA (amefariki):
    18. mama_death_code — Namba ya uhakiki wa cheti cha kifo cha mama (2026XXXXXX-DV)
  Kama NDIYO (yupo hai):
    19. mama_jina_kamili — Majina matatu ya mama
    20. mama_simu — Namba ya simu ya mama
    21. mama_mkoa — Mkoa anapoishi mama
    22. mama_kazi — Kazi ya mama (sema "Hana kazi" kama hana)
    23. mama_napa_reference — Namba ya NaPA ya mama

[F] TAARIFA ZA BABA
24. baba_anajulikana — Je, baba yako anajulikana? (NDIYO / HAPANA)
Kama NDIYO:
  25. baba_yupo_hai — Je, baba yako yupo hai? (NDIYO / HAPANA)
  Kama HAPANA (amefariki):
    26. baba_death_code — Namba ya uhakiki wa cheti cha kifo cha baba (2026XXXXXX-DV)
  Kama NDIYO (yupo hai):
    27. baba_jina_kamili — Majina matatu ya baba
    28. baba_simu — Namba ya simu ya baba
    29. baba_mkoa — Mkoa anapoishi baba
    30. baba_kazi — Kazi ya baba (sema "Hana kazi" kama hana)
    31. baba_napa_reference — Namba ya NaPA ya baba

[G] TASAF NA MAZINGIRA MAALUM
32. kuna_tasaf — Je, familia yako ipo kwenye TASAF? (NDIYO / HAPANA)
    Kama NDIYO: uliza tasaf_membership_number
33. ulilelewa_yatima — Je, ulilelewa katika kituo cha watoto yatima? (NDIYO / HAPANA)
34. ulifadhiliwa — Je, ulifadhiliwa wakati wa masomo ya sekondari? (NDIYO / HAPANA)

[H] TAARIFA ZA ELIMU (kulingana na aina_mwombaji)

Kama "fresh_alevel" au "ftca":
  35. necta_form6_index — Namba ya mtihani wa Form 6/ACSEE (mfano: S2895/0030/2020)
  36. mwaka_form6 — Mwaka wa kuhitimu Form 6
  37. chuo_kilichokubali — Jina la chuo kilichomkubali na kozi (mfano: UDSM — BSc Computer Science)

Kama "ftca" (Continuing Student) — ongeza:
  38. registration_number — Namba ya usajili chuoni
  39. mwaka_wa_masomo — Mwaka wa masomo (mfano: Mwaka wa 2)

Kama "diploma":
  35. avn_number — AVN Number (Namba ya NACTVET)
  36. chuo_diploma — Jina la chuo cha diploma
  37. gpa_diploma — GPA ya diploma
  38. chuo_kilichokubali — Chuo na kozi ya degree anayoomba

[I] TAARIFA ZA MDHAMINI (GUARANTOR)
MUHIMU: Mdhamini ni mzazi, mlezi, ndugu, au mtu yeyote mwenye umri 18+ mwenye NIDA

39. mdhamini_aina_id — Aina ya kitambulisho cha mdhamini: "NIDA" / "Kadi ya Mpiga Kura" / "Leseni" / "Passport"
40. mdhamini_jina_kamili — Majina matatu ya mdhamini
41. mdhamini_namba_nida — Namba ya NIDA ya mdhamini (herufi 20)
42. mdhamini_mkoa — Mkoa wa kuzaliwa mdhamini
43. mdhamini_wilaya — Wilaya ya kuzaliwa mdhamini
44. mdhamini_kata — Kata ya kuzaliwa mdhamini
45. mdhamini_wilaya_darasa7 — Wilaya aliyohitimu darasa la 7 mdhamini (na mwaka)
46. mdhamini_shule_msingi — Jina la shule ya msingi ya mdhamini
47. mdhamini_simu_nida — Namba ya simu aliyotumia kusajilia NIDA (mdhamini)
48. mdhamini_napa_reference — Namba ya NaPA ya mdhamini

════════════════════════════════════
MAELEKEZO MUHIMU:
════════════════════════════════════
- ULIZA SWALI MOJA TU KWA WAKATI MMOJA — kamwe usijumlishe maswali
- Taarifa za mama/baba: omba kulingana na hali (hai/amefariki/hajulikani)
- BV code: thibitisha inaanza na "2026" — kama haianza hivyo, mwambie aende RITA tena
- DV code: sawa na BV lakini inaisha "-DV" badala ya "-BV"
- NIDA: lazima iwe herufi 20 — thibitisha urefu
- NaPA: ni namba mpya kwa kila mwaka — za mwaka jana hazifanyi kazi
- Jibu DAIMA kwa Kiswahili — lugha rahisi, ya kirafiki

UKIKAMILISHA TAARIFA ZOTE ZINAZOHUSIKA (kulingana na aina ya mwombaji):
Toa muhtasari mfupi wa taarifa zote, kisha andika:
[[DATA_READY]]
{"aina_mwombaji":"...", "jina_la_kwanza":"...", ...taarifa zote...}
[[/DATA_READY]]"""

VALID_FIELDS = {
    # Aina
    "aina_mwombaji",
    # Basic
    "jina_la_kwanza", "jina_la_kati", "jina_la_mwisho",
    "necta_form4_index", "birth_verification_code",
    "barua_pepe", "namba_benki", "jina_benki", "namba_simu",
    # Demographic
    "namba_nida", "mkoa_kuzaliwa", "wilaya_kuzaliwa", "kata_kuzaliwa",
    "napa_reference",
    # Preliminary
    "una_ulemavu", "namba_ulemavu",
    # Mama
    "mama_anajulikana", "mama_yupo_hai", "mama_death_code",
    "mama_jina_kamili", "mama_simu", "mama_mkoa", "mama_kazi", "mama_napa_reference",
    # Baba
    "baba_anajulikana", "baba_yupo_hai", "baba_death_code",
    "baba_jina_kamili", "baba_simu", "baba_mkoa", "baba_kazi", "baba_napa_reference",
    # Social
    "kuna_tasaf", "tasaf_membership_number",
    "ulilelewa_yatima", "ulifadhiliwa",
    # Education
    "necta_form6_index", "mwaka_form6", "chuo_kilichokubali",
    "registration_number", "mwaka_wa_masomo",
    # Diploma
    "avn_number", "chuo_diploma", "gpa_diploma",
    # Guarantor
    "mdhamini_aina_id", "mdhamini_jina_kamili", "mdhamini_namba_nida",
    "mdhamini_mkoa", "mdhamini_wilaya", "mdhamini_kata",
    "mdhamini_wilaya_darasa7", "mdhamini_shule_msingi",
    "mdhamini_simu_nida", "mdhamini_napa_reference",
}


def _build_contents(history: list) -> list:
    return [
        {"role": "model" if m["role"] == "assistant" else "user",
         "parts": [{"text": m["content"]}]}
        for m in history
    ]


def _dynamic_system_prompt() -> str:
    """Return SYSTEM_PROMPT enriched with latest HESLB knowledge from cache."""
    from field_app.heslb_knowledge import get_knowledge
    knowledge = get_knowledge()
    if not knowledge or not knowledge.get("ok"):
        return SYSTEM_PROMPT
    return (
        SYSTEM_PROMPT
        + "\n\n════════════════════════════════════\n"
        + f"TAARIFA MPYA KUTOKA HESLB (Imesasishwa: {knowledge['updated_at']}):\n"
        + knowledge["summary"]
        + "\n════════════════════════════════════\n"
        + "MUHIMU: Taarifa zilizo juu zimetoka moja kwa moja tovuti ya HESLB. "
        + "Zitumie kushughulikia maswali ya hali ya sasa — dirisha, nyaraka mpya, mabadiliko."
    )


def _make_cfg():
    return genai_types.GenerateContentConfig(
        system_instruction=_dynamic_system_prompt(),
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


def _is_quota_err(err: str) -> bool:
    return "429" in err or "RESOURCE_EXHAUSTED" in err


def _friendly_err(err: str) -> str:
    if _is_quota_err(err):
        return "Samahani, mfumo wa AI una msongamano kwa sasa. Tafadhali subiri dakika moja kisha jaribu tena."
    return "Samahani, hitilafu imetokea. Tafadhali jaribu tena."


def _call_gemini(history: list) -> str:
    """Non-streaming call for the opening message only. Tries all fallback models."""
    if client is None:
        return "Samahani, huduma ya AI haitumiki kwa sasa."
    cfg = _make_cfg()
    contents = _build_contents(history)
    for mdl in FALLBACK_MODELS:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(model=mdl, contents=contents, config=cfg)
                return resp.text or "Samahani, jibu halijapatikana."
            except Exception as e:
                err = str(e)
                if _is_quota_err(err) and attempt == 0:
                    time.sleep(10)
                    continue
                break  # try next model
    return "Samahani, mfumo wa AI una msongamano kwa sasa. Tafadhali subiri dakika moja kisha jaribu tena."


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
        succeeded = False

        for mdl in FALLBACK_MODELS:
            if succeeded:
                break
            for attempt in range(2):
                try:
                    for chunk in client.models.generate_content_stream(
                        model=mdl, contents=contents, config=cfg
                    ):
                        token = chunk.text or ""
                        if not token:
                            continue
                        full_text += token
                        if not data_block_started:
                            if "[[DATA_READY]]" in full_text:
                                data_block_started = True
                                marker_pos = full_text.index("[[DATA_READY]]")
                                prev_visible = full_text[:marker_pos]
                                chunk_start = marker_pos - len(token)
                                visible_from_chunk = prev_visible[max(0, chunk_start):]
                                if visible_from_chunk:
                                    yield f"data: {json.dumps({'t': visible_from_chunk})}\n\n"
                            else:
                                yield f"data: {json.dumps({'t': token})}\n\n"
                    succeeded = True
                    break
                except Exception as e:
                    err = str(e)
                    if _is_quota_err(err):
                        if attempt == 0:
                            # brief pause then retry same model once
                            time.sleep(5)
                            continue
                        # model exhausted — try next one silently
                        break
                    # non-quota error — show friendly message and stop
                    yield f"data: {json.dumps({'t': _friendly_err(err)})}\n\n"
                    return

        if not succeeded and not full_text:
            yield f"data: {json.dumps({'t': 'Samahani, mfumo wa AI una msongamano kwa sasa. Tafadhali subiri dakika moja kisha jaribu tena.'})}\n\n"
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


def heslb_knowledge_status(request):
    """Return current HESLB knowledge cache status (public read, POST triggers refresh)."""
    from field_app.heslb_knowledge import get_knowledge, scrape_and_update

    if request.method == "POST":
        # Manual refresh — admin only via Django staff check
        if not (request.user.is_authenticated and request.user.is_staff):
            return JsonResponse({"error": "Ruhusa imekataliwa."}, status=403)
        result = scrape_and_update()
        return JsonResponse(result)

    knowledge = get_knowledge()
    if not knowledge:
        return JsonResponse({
            "ok": False,
            "summary": "",
            "updated_at": "",
            "message": "Bado haijasasishwa. Mfumo utajisasisha kiotomatiki kila wiki."
        })
    return JsonResponse(knowledge)
