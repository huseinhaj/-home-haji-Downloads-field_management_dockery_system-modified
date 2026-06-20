"""
HESLB OLAMS Playwright Automation — 2026/2027
Fills the HESLB loan application on https://olas.heslb.go.tz/
on behalf of the student. Runs as a Celery task.
Credentials are NEVER stored — passed in memory only.
"""
import asyncio
import base64
import json
import logging

from celery import shared_task
from django.core.cache import cache

log = logging.getLogger(__name__)

OLAMS_URL = "https://olas.heslb.go.tz/"

_STATUS_TTL = 3600   # 1 hour
_SHOTS_TTL  = 3600


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _key(sid: str, kind: str) -> str:
    return f"heslb_{kind}_{sid}"


def set_status(sid: str, status: dict):
    cache.set(_key(sid, "status"), json.dumps(status), timeout=_STATUS_TTL)


def get_status(sid: str) -> dict:
    raw = cache.get(_key(sid, "status"))
    return json.loads(raw) if raw else {}


def add_screenshot(sid: str, label: str, png_b64: str):
    shots = json.loads(cache.get(_key(sid, "shots")) or "[]")
    shots.append({"label": label, "img": png_b64})
    cache.set(_key(sid, "shots"), json.dumps(shots), timeout=_SHOTS_TTL)


def get_screenshots(sid: str) -> list:
    return json.loads(cache.get(_key(sid, "shots")) or "[]")


# ── Playwright helpers ────────────────────────────────────────────────────────

async def _shot(page, sid: str, label: str):
    try:
        png = await page.screenshot(type="png", full_page=False)
        add_screenshot(sid, label, base64.b64encode(png).decode())
    except Exception as e:
        log.warning("Screenshot failed (%s): %s", label, e)


async def _fill(page, selectors: list[str], value: str) -> bool:
    """Try each selector in order; return True on first success."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.fill(str(value))
                return True
        except Exception:
            continue
    return False


async def _select(page, selectors: list[str], value: str) -> bool:
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.select_option(str(value))
                return True
        except Exception:
            continue
    return False


async def _click(page, selectors: list[str]) -> bool:
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click()
                return True
        except Exception:
            continue
    return False


async def _wait_angular(page, timeout: int = 8000):
    """Wait for Angular's pending HTTP requests to settle."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        await asyncio.sleep(1.5)


# ── Main automation coroutine ─────────────────────────────────────────────────

async def _run_olams(sid: str, student: dict, credentials: dict):
    from playwright.async_api import async_playwright

    def upd(msg: str, step: int = 0, done: bool = False, error: str = ""):
        set_status(sid, {"msg": msg, "step": step, "done": done, "error": error})

    upd("Inaanzisha kivinjari...", step=1)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx  = await browser.new_context(viewport={"width": 1366, "height": 768})
        page = await ctx.new_page()
        page.set_default_timeout(20000)

        try:

            # ── STEP 1: Open HESLB OLAMS ──────────────────────────────────
            upd("Inafungua HESLB OLAMS...", step=1)
            await page.goto(OLAMS_URL, wait_until="domcontentloaded", timeout=40000)
            await _wait_angular(page)
            await _shot(page, sid, "1. Ukurasa wa HESLB OLAMS")

            # ── STEP 2: Login ─────────────────────────────────────────────
            upd("Inaingia kwenye akaunti yako...", step=2)

            # OLAMS uses Form 4 index as username + password
            await _click(page, [
                "text=Login as Registered User",
                "a:has-text('Login')",
                "[routerlink*='login']",
            ])
            await _wait_angular(page)

            # Fill credentials
            await _fill(page, [
                "input[formcontrolname='username']",
                "input[name='username']",
                "input[type='text']",
                "input[placeholder*='username' i]",
                "input[placeholder*='index' i]",
            ], credentials["email"])

            await _fill(page, [
                "input[formcontrolname='password']",
                "input[type='password']",
            ], credentials["password"])

            await _click(page, [
                "button[type='submit']",
                "button:has-text('Login')",
                "button:has-text('Ingia')",
                "input[type='submit']",
            ])
            await _wait_angular(page)
            await _shot(page, sid, "2. Baada ya login")

            # Detect login failure
            body = await page.inner_text("body")
            if any(w in body.lower() for w in ["invalid", "incorrect", "failed", "wrong", "si sahihi"]):
                upd("", error="Jina la mtumiaji au nenosiri si sahihi. Angalia na ujaribu tena.")
                return

            # ── STEP 3: Navigate to New Application ───────────────────────
            upd("Inafungua fomu ya ombi jipya...", step=3)

            await _click(page, [
                "text=Apply for Loan",
                "text=Apply for loan",
                "a:has-text('Apply')",
                "[routerlink*='apply']",
                "[routerlink*='loan']",
            ])
            await _wait_angular(page)
            await _shot(page, sid, "3. Fomu ya Ombi")

            # ── STEP 4: Basic Information ──────────────────────────────────
            upd("Inajaza Form 4 index na Birth Verification Code...", step=4)

            # Form 4 Index Number
            await _fill(page, [
                "input[formcontrolname='form4IndexNo']",
                "input[formcontrolname='indexNo']",
                "input[placeholder*='Form 4' i]",
                "input[placeholder*='index' i]",
                "input[name*='form4']",
            ], student.get("necta_form4_index", ""))

            # Birth Verification Code (2026-BV)
            await _fill(page, [
                "input[formcontrolname='birthVerificationCode']",
                "input[formcontrolname='bvCode']",
                "input[placeholder*='BV' i]",
                "input[placeholder*='verification' i]",
                "input[placeholder*='birth' i]",
            ], student.get("birth_verification_code", ""))

            # Names
            await _fill(page, [
                "input[formcontrolname='firstName']",
                "input[placeholder*='first name' i]",
            ], student.get("jina_la_kwanza", ""))

            await _fill(page, [
                "input[formcontrolname='middleName']",
                "input[placeholder*='middle' i]",
            ], student.get("jina_la_kati", ""))

            await _fill(page, [
                "input[formcontrolname='surname']",
                "input[formcontrolname='lastName']",
                "input[placeholder*='surname' i]",
            ], student.get("jina_la_mwisho", ""))

            # Email + Phone + Bank
            await _fill(page, [
                "input[formcontrolname='email']",
                "input[type='email']",
            ], student.get("barua_pepe", ""))

            await _fill(page, [
                "input[formcontrolname='phoneNo']",
                "input[formcontrolname='mobile']",
                "input[placeholder*='phone' i]",
            ], student.get("namba_simu", ""))

            await _fill(page, [
                "input[formcontrolname='bankAccountNo']",
                "input[placeholder*='account' i]",
            ], student.get("namba_benki", ""))

            await _select(page, [
                "select[formcontrolname='bankName']",
                "select[formcontrolname='bank']",
            ], student.get("jina_benki", ""))

            await _shot(page, sid, "4. Basic Info imejazwa")

            # Next page / tab
            await _click(page, [
                "button:has-text('Next')",
                "button:has-text('Endelea')",
                "button:has-text('Continue')",
                "button[type='submit']:not([disabled])",
            ])
            await _wait_angular(page)

            # ── STEP 5: Demographic + NaPA ────────────────────────────────
            upd("Inajaza NIDA, eneo la kuzaliwa na NaPA...", step=5)

            await _fill(page, [
                "input[formcontrolname='nin']",
                "input[formcontrolname='nidaNo']",
                "input[placeholder*='NIDA' i]",
                "input[placeholder*='NIN' i]",
            ], student.get("namba_nida", ""))

            # Birth region/district/ward — try selects first, then text fields
            await _select(page, [
                "select[formcontrolname='birthRegion']",
                "select[formcontrolname='region']",
            ], student.get("mkoa_kuzaliwa", ""))

            await _select(page, [
                "select[formcontrolname='birthDistrict']",
                "select[formcontrolname='district']",
            ], student.get("wilaya_kuzaliwa", ""))

            await _select(page, [
                "select[formcontrolname='birthWard']",
                "select[formcontrolname='ward']",
            ], student.get("kata_kuzaliwa", ""))

            # NaPA Reference
            await _fill(page, [
                "input[formcontrolname='napaRef']",
                "input[formcontrolname='napReference']",
                "input[placeholder*='NaPA' i]",
                "input[placeholder*='napa' i]",
            ], student.get("napa_reference", ""))

            # Disability
            has_disability = student.get("una_ulemavu", "HAPANA").upper() == "NDIYO"
            await _select(page, [
                "select[formcontrolname='hasDisability']",
            ], "1" if has_disability else "0")

            await _shot(page, sid, "5. Demographic imejazwa")

            await _click(page, [
                "button:has-text('Next')",
                "button:has-text('Endelea')",
            ])
            await _wait_angular(page)

            # ── STEP 6: Parent Information ────────────────────────────────
            upd("Inajaza taarifa za wazazi...", step=6)

            # — MAMA —
            mama_known = student.get("mama_anajulikana", "NDIYO").upper() == "NDIYO"
            await _select(page, ["select[formcontrolname='motherKnown']"], "1" if mama_known else "0")

            if mama_known:
                mama_alive = student.get("mama_yupo_hai", "NDIYO").upper() == "NDIYO"
                await _select(page, ["select[formcontrolname='motherAlive']"], "1" if mama_alive else "0")

                if not mama_alive:
                    await _fill(page, [
                        "input[formcontrolname='motherDeathVerificationCode']",
                        "input[placeholder*='DV' i]",
                    ], student.get("mama_death_code", ""))
                else:
                    await _fill(page, ["input[formcontrolname='motherFullName']"], student.get("mama_jina_kamili", ""))
                    await _fill(page, ["input[formcontrolname='motherPhone']"], student.get("mama_simu", ""))
                    await _select(page, ["select[formcontrolname='motherRegion']"], student.get("mama_mkoa", ""))
                    await _fill(page, ["input[formcontrolname='motherOccupation']"], student.get("mama_kazi", ""))
                    await _fill(page, [
                        "input[formcontrolname='motherNapaRef']",
                        "input[placeholder*='mother.*napa' i]",
                    ], student.get("mama_napa_reference", ""))

            # — BABA —
            baba_known = student.get("baba_anajulikana", "NDIYO").upper() == "NDIYO"
            await _select(page, ["select[formcontrolname='fatherKnown']"], "1" if baba_known else "0")

            if baba_known:
                baba_alive = student.get("baba_yupo_hai", "NDIYO").upper() == "NDIYO"
                await _select(page, ["select[formcontrolname='fatherAlive']"], "1" if baba_alive else "0")

                if not baba_alive:
                    await _fill(page, [
                        "input[formcontrolname='fatherDeathVerificationCode']",
                    ], student.get("baba_death_code", ""))
                else:
                    await _fill(page, ["input[formcontrolname='fatherFullName']"], student.get("baba_jina_kamili", ""))
                    await _fill(page, ["input[formcontrolname='fatherPhone']"], student.get("baba_simu", ""))
                    await _select(page, ["select[formcontrolname='fatherRegion']"], student.get("baba_mkoa", ""))
                    await _fill(page, ["input[formcontrolname='fatherOccupation']"], student.get("baba_kazi", ""))
                    await _fill(page, [
                        "input[formcontrolname='fatherNapaRef']",
                    ], student.get("baba_napa_reference", ""))

            # TASAF
            has_tasaf = student.get("kuna_tasaf", "HAPANA").upper() == "NDIYO"
            await _select(page, ["select[formcontrolname='hasTasaf']"], "1" if has_tasaf else "0")
            if has_tasaf:
                await _fill(page, [
                    "input[formcontrolname='tasafMembershipNo']",
                    "input[placeholder*='TASAF' i]",
                ], student.get("tasaf_membership_number", ""))

            # Orphanage
            orphan = student.get("ulilelewa_yatima", "HAPANA").upper() == "NDIYO"
            await _select(page, ["select[formcontrolname='orphanage']"], "1" if orphan else "0")

            await _shot(page, sid, "6. Taarifa za wazazi zimejazwa")

            await _click(page, [
                "button:has-text('Next')",
                "button:has-text('Endelea')",
            ])
            await _wait_angular(page)

            # ── STEP 6b: Education Information ───────────────────────────
            upd("Inajaza taarifa za elimu...", step=6)

            applicant_type = student.get("aina_mwombaji", "fresh_alevel")

            # Type selector
            type_map = {"fresh_alevel": "FRESH", "ftca": "FTCA", "diploma": "DIPLOMA"}
            await _select(page, [
                "select[formcontrolname='applicantType']",
                "select[formcontrolname='studentType']",
            ], type_map.get(applicant_type, "FRESH"))

            if applicant_type in ("fresh_alevel", "ftca"):
                await _fill(page, [
                    "input[formcontrolname='form6IndexNo']",
                    "input[placeholder*='Form 6' i]",
                    "input[placeholder*='A-Level' i]",
                ], student.get("necta_form6_index", ""))

            if applicant_type == "ftca":
                await _fill(page, [
                    "input[formcontrolname='registrationNo']",
                    "input[placeholder*='registration' i]",
                ], student.get("registration_number", ""))
                await _fill(page, [
                    "input[formcontrolname='yearOfStudy']",
                ], student.get("mwaka_wa_masomo", ""))

            if applicant_type == "diploma":
                await _fill(page, [
                    "input[formcontrolname='avnNumber']",
                    "input[placeholder*='AVN' i]",
                ], student.get("avn_number", ""))
                await _fill(page, [
                    "input[formcontrolname='diplomaInstitution']",
                ], student.get("chuo_diploma", ""))
                await _fill(page, [
                    "input[formcontrolname='diplomaGpa']",
                ], student.get("gpa_diploma", ""))

            await _fill(page, [
                "input[formcontrolname='admittedInstitution']",
                "input[placeholder*='institution' i]",
            ], student.get("chuo_kilichokubali", ""))

            # Was sponsored (ulifadhiliwa)?
            sponsored = student.get("ulifadhiliwa", "HAPANA").upper() == "NDIYO"
            await _select(page, ["select[formcontrolname='wasSponsored']"], "1" if sponsored else "0")

            await _shot(page, sid, "6b. Elimu imejazwa")

            await _click(page, [
                "button:has-text('Next')",
                "button:has-text('Endelea')",
            ])
            await _wait_angular(page)

            # ── STEP 6c: Guarantor Information ────────────────────────────
            upd("Inajaza taarifa za mdhamini...", step=6)

            await _select(page, [
                "select[formcontrolname='guarantorIdType']",
            ], student.get("mdhamini_aina_id", "NIDA"))

            await _fill(page, ["input[formcontrolname='guarantorNin']",
                                "input[placeholder*='guarantor.*nida' i]"],
                         student.get("mdhamini_namba_nida", ""))

            await _fill(page, ["input[formcontrolname='guarantorFullName']"],
                         student.get("mdhamini_jina_kamili", ""))

            await _select(page, ["select[formcontrolname='guarantorRegion']"],
                          student.get("mdhamini_mkoa", ""))

            await _select(page, ["select[formcontrolname='guarantorDistrict']"],
                          student.get("mdhamini_wilaya", ""))

            await _select(page, ["select[formcontrolname='guarantorWard']"],
                          student.get("mdhamini_kata", ""))

            await _fill(page, ["input[formcontrolname='guarantorStd7District']"],
                         student.get("mdhamini_wilaya_darasa7", ""))

            await _fill(page, ["input[formcontrolname='guarantorPrimarySchool']"],
                         student.get("mdhamini_shule_msingi", ""))

            await _fill(page, ["input[formcontrolname='guarantorNidaPhone']",
                                "input[placeholder*='guarantor.*phone' i]"],
                         student.get("mdhamini_simu_nida", ""))

            await _fill(page, ["input[formcontrolname='guarantorNapaRef']"],
                         student.get("mdhamini_napa_reference", ""))

            await _shot(page, sid, "6c. Mdhamini imejazwa")

            await _click(page, [
                "button:has-text('Next')",
                "button:has-text('Endelea')",
            ])
            await _wait_angular(page)

            # ── STEP 7: Summary / Preview ─────────────────────────────────
            upd("Imekamilika! Kagua maelezo yako kwenye picha — USIBONYEZE Submit bado.", step=7, done=True)
            await _wait_angular(page)
            await _shot(page, sid, "7. Muhtasari — Kagua Kabla ya Kutuma")

        except Exception as e:
            log.exception("HESLB OLAMS automation error")
            upd("", error=f"Hitilafu: {str(e)[:300]}")
        finally:
            await asyncio.sleep(120)   # 2-min window for user to review
            await browser.close()


# ── Celery task ───────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=0, time_limit=600)
def run_heslb_automation(self, session_id: str, student: dict, credentials: dict):
    """Celery task — runs HESLB OLAMS Playwright automation (2026/2027)."""
    asyncio.run(_run_olams(session_id, student, credentials))
