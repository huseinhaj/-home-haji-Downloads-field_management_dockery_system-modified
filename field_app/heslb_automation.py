"""
HESLB Playwright Automation
Fills the HESLB loan application form on behalf of the student.
Runs as a Celery task; saves screenshots at every step for preview.
"""
import asyncio
import base64
import json
import logging
from pathlib import Path

from celery import shared_task
from django.core.cache import cache

log = logging.getLogger(__name__)

HESLB_URL = "https://www.heslb.go.tz/online"

# Cache key prefix for automation status
_STATUS_PREFIX = "heslb_auto_"
_SHOTS_PREFIX  = "heslb_shots_"


def _key(session_id: str, kind: str) -> str:
    return f"heslb_{kind}_{session_id}"


def set_status(session_id: str, status: dict):
    cache.set(_key(session_id, "status"), json.dumps(status), timeout=3600)


def get_status(session_id: str) -> dict:
    raw = cache.get(_key(session_id, "status"))
    return json.loads(raw) if raw else {}


def add_screenshot(session_id: str, label: str, png_b64: str):
    shots = json.loads(cache.get(_key(session_id, "shots")) or "[]")
    shots.append({"label": label, "img": png_b64})
    cache.set(_key(session_id, "shots"), json.dumps(shots), timeout=3600)


def get_screenshots(session_id: str) -> list:
    return json.loads(cache.get(_key(session_id, "shots")) or "[]")


async def _take_shot(page, session_id: str, label: str):
    """Screenshot current page, store as base64."""
    try:
        png = await page.screenshot(type="png", full_page=False)
        b64 = base64.b64encode(png).decode()
        add_screenshot(session_id, label, b64)
    except Exception as e:
        log.warning("Screenshot failed (%s): %s", label, e)


async def _run_heslb(session_id: str, student: dict, credentials: dict):
    """Main Playwright coroutine — fills HESLB loan application."""
    from playwright.async_api import async_playwright

    def upd(msg: str, step: int = 0, done: bool = False, error: str = ""):
        set_status(session_id, {
            "msg": msg, "step": step, "done": done, "error": error
        })

    upd("Inaanzisha kivinjari...", step=1)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx  = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        try:
            # ── STEP 1: Navigate to HESLB ───────────────────────────────
            upd("Inafungua tovuti ya HESLB...", step=1)
            await page.goto(HESLB_URL, wait_until="networkidle", timeout=30000)
            await _take_shot(page, session_id, "1. Ukurasa wa HESLB")

            # ── STEP 2: Login ───────────────────────────────────────────
            upd("Inaingia kwenye akaunti yako...", step=2)
            # Click "Login as Registered User"
            await page.get_by_text("Login as Registered User").first.click()
            await page.wait_for_load_state("networkidle")

            # Fill login form
            await page.locator("input[name='username'], input[type='email']").first.fill(credentials["email"])
            await page.locator("input[type='password']").first.fill(credentials["password"])
            await page.locator("button[type='submit'], input[type='submit']").first.click()
            await page.wait_for_load_state("networkidle")
            await _take_shot(page, session_id, "2. Baada ya kuingia")

            # Check for login error
            body = await page.inner_text("body")
            if any(w in body.lower() for w in ["invalid", "incorrect", "failed", "error", "wrong"]):
                upd("", error="Nenosiri au barua pepe si sahihi. Tafadhali angalia na ujaribu tena.")
                return

            # ── STEP 3: Navigate to loan application ────────────────────
            upd("Inafungua fomu ya mkopo...", step=3)
            await page.get_by_text("Apply for loan").first.click()
            await page.wait_for_load_state("networkidle")
            await _take_shot(page, session_id, "3. Fomu ya Mkopo")

            # ── STEP 4: Select NECTA ────────────────────────────────────
            upd("Inachagua NECTA...", step=4)
            try:
                await page.get_by_text("NECTA Students").first.click()
                await page.wait_for_load_state("networkidle")
            except Exception:
                pass  # May already be on NECTA form

            # ── STEP 5: Fill NECTA O-Level index ────────────────────────
            upd("Inajaza namba ya mtihani (O-Level)...", step=5)

            # Candidate type (S or P dropdown/input)
            try:
                await page.locator("select").first.select_option(student["necta_olevel_aina"])
            except Exception:
                await page.locator("input").nth(0).fill(student["necta_olevel_aina"])

            await page.locator("input[placeholder*='School'], input[placeholder*='school'], input[placeholder*='1589']").first.fill(student["necta_olevel_shule"])
            await page.locator("input[placeholder*='Candidate'], input[placeholder*='candidate'], input[placeholder*='0001']").first.fill(student["necta_olevel_mtahiniwa"])
            await page.locator("input[placeholder*='Year'], input[placeholder*='year'], input[placeholder*='2007'], input[placeholder*='2008']").first.fill(student["mwaka_olevel"])

            # Submit index to fetch student info
            await page.locator("button[type='submit'], input[type='submit']").first.click()
            await page.wait_for_load_state("networkidle")
            await _take_shot(page, session_id, "5. Baada ya O-Level index")

            # ── STEP 6: Fill additional HESLB fields ────────────────────
            upd("Inajaza taarifa za ziada...", step=6)

            # Application Category
            try:
                cat_map = {
                    "Bachelor Degree": "LUG",
                    "Diploma": "LDG",
                    "Certificate": "LCG",
                    "Masters": "LPG",
                }
                cat_val = cat_map.get(student.get("aina_ya_elimu", ""), "LUG")
                await page.locator("select[name*='category'], select[name*='Category']").first.select_option(cat_val)
            except Exception:
                pass

            # Birth Place
            try:
                bp = student.get("mahali_kuzaliwa", "")
                bp_map = {"Mainland": "1", "Tanzania Bara": "1", "Zanzibar": "2", "Nje ya Tanzania": "3"}
                bp_val = next((v for k, v in bp_map.items() if k.lower() in bp.lower()), "1")
                await page.locator("select[name*='birth'], select[name*='Birth'], select[name*='place']").first.select_option(value=bp_val)
            except Exception:
                pass

            # RITA number
            try:
                await page.locator("input[name*='rita'], input[name*='Rita'], input[placeholder*='RITA']").first.fill(student.get("rita_namba", ""))
            except Exception:
                pass

            await _take_shot(page, session_id, "6. Taarifa za ziada zimejazwa")

            # ── STEP 7: Preview — DO NOT SUBMIT YET ─────────────────────
            upd("Imekamilika! Tafadhali kagua na uthibitishe.", step=7, done=True)
            await _take_shot(page, session_id, "7. Muhtasari wa fomu")

        except Exception as e:
            log.exception("HESLB automation error")
            upd("", error=f"Hitilafu: {str(e)[:200]}")
        finally:
            # Keep browser open for final submission; close after timeout
            await asyncio.sleep(300)  # 5 min window for user confirmation
            await browser.close()


@shared_task(bind=True, max_retries=0)
def run_heslb_automation(self, session_id: str, student: dict, credentials: dict):
    """Celery task — runs HESLB Playwright automation."""
    asyncio.run(_run_heslb(session_id, student, credentials))
