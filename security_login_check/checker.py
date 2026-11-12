"""Authorized login & access-control checker.

Hii haikamati wala kuhifadhi nywila za watumiaji wengine. Inatumia
test credentials unazotoa kwenye fomu kwa muda wa check tu; hazihifadhiwi
kwenye disk, hazilogwi, na hazirudishwi kwenye ukurasa.
"""

from __future__ import annotations

import os
import secrets
from urllib.parse import urljoin, urlparse

import requests
from playwright.sync_api import sync_playwright


DEFAULT_ALLOWED_HOSTS = (
    "localhost,127.0.0.1,studentschoolresultsystem.online,"
    "www.studentschoolresultsystem.online,internshipmanagementsystem.online,"
    "www.internshipmanagementsystem.online"
)

ALLOWED_HOSTS = [
    h.strip().lower()
    for h in os.environ.get(
        "SECURITY_CHECK_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS
    ).split(",")
    if h.strip()
]

USERNAME_SELECTORS = [
    "input[name=email]",
    "input[name=username]",
    "input#username",
    "input[autocomplete=username]",
    "input[type=email]",
    "input[type=text]",
]

PASSWORD_SELECTORS = [
    "input[name=password]",
    "input#password",
    "input[autocomplete=current-password]",
    "input[type=password]",
]

SUBMIT_SELECTORS = [
    "button[type=submit]",
    "input[type=submit]",
    "button:has-text('Ingia')",
    "button:has-text('Login')",
    "button:has-text('Sign in')",
    "button",
]

LOGIN_ERROR_MARKERS = (
    "si sahihi",
    "haukubaliwa",
    "haujafanikiwa",
    "invalid",
    "incorrect",
    "wrong password",
    "login failed",
    "jaribu tena",
    "not found",
)

DENIED_MARKERS = (
    "permission denied",
    "huna ruhusa",
    "haujaruhusiwa",
    "not allowed",
    "403 forbidden",
    "access denied",
    "hauna access",
)

PRESETS = {
    "results_admin": {
        "label": "Results — Admin / Academic",
        "base_url": "https://studentschoolresultsystem.online",
        "login_path": "/shule/ingia/",
        "protected_path": "/shule/academic/",
        "username_selectors": USERNAME_SELECTORS,
        "password_selectors": PASSWORD_SELECTORS,
        "submit_selectors": SUBMIT_SELECTORS,
    },
    "results_teacher": {
        "label": "Results — Mwalimu wa kawaida",
        "base_url": "https://studentschoolresultsystem.online",
        "login_path": "/shule/ingia/",
        "protected_path": "/shule/teacher/",
        "username_selectors": USERNAME_SELECTORS,
        "password_selectors": PASSWORD_SELECTORS,
        "submit_selectors": SUBMIT_SELECTORS,
    },
    "tlm": {
        "label": "TLM — Mwalimu (Curriculum)",
        "base_url": "https://studentschoolresultsystem.online",
        "login_path": "/accounts/login/",
        "protected_path": "/curriculum/dashboard/",
        "username_selectors": USERNAME_SELECTORS,
        "password_selectors": PASSWORD_SELECTORS,
        "submit_selectors": SUBMIT_SELECTORS,
    },
    "local_results": {
        "label": "Local dev — Results",
        "base_url": "http://127.0.0.1:8000",
        "login_path": "/shule/ingia/",
        "protected_path": "/shule/academic/",
        "username_selectors": USERNAME_SELECTORS,
        "password_selectors": PASSWORD_SELECTORS,
        "submit_selectors": SUBMIT_SELECTORS,
    },
    "custom": {
        "label": "Custom system",
        "base_url": "",
        "login_path": "",
        "protected_path": "",
        "username_selectors": USERNAME_SELECTORS,
        "password_selectors": PASSWORD_SELECTORS,
        "submit_selectors": SUBMIT_SELECTORS,
    },
}


def _host_allowed(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    return parsed.hostname.lower() in ALLOWED_HOSTS


def _first_visible(page, selectors):
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            first = locator.first
            if first.is_visible():
                return first, selector
        except Exception:
            continue
    return None, None


def _submit(page, selectors):
    button, selector = _first_visible(page, selectors)
    if button is not None:
        button.click()
        return selector
    page.keyboard.press("Enter")
    return "Enter"


def _settle(page, timeout=15000):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass
    page.wait_for_timeout(700)


def _on_login_page(page, login_path):
    path = (urlparse(page.url).path or "").rstrip("/")
    login = (login_path or "").rstrip("/")
    if not login:
        return False
    return path == login or path.endswith(login) or "next=" in page.url


def _page_text(page):
    try:
        return page.locator("body").inner_text(timeout=4000).lower()
    except Exception:
        return ""


def _login(page, login_url, username, password, selectors):
    steps = []
    try:
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:
        return {"ok": False, "error": f"Imeshindwa kufungua login page: {exc}", "steps": steps}

    _settle(page)

    username_input, used_username = _first_visible(page, selectors["username"])
    if username_input is None:
        return {
            "ok": False,
            "error": "Sehemu ya username/email haijapatikana kwenye ukurasa.",
            "steps": steps,
        }
    username_input.fill(username)
    steps.append(f"Username/email imejazwa ({used_username}).")

    password_input, used_password = _first_visible(page, selectors["password"])
    if password_input is None:
        _submit(page, selectors["submit"])
        steps.append("Hatua ya kwanza ya login imetumwa.")
        _settle(page)
        password_input, used_password = _first_visible(page, selectors["password"])

    if password_input is None:
        return {
            "ok": False,
            "error": "Sehemu ya password haijapatikana baada ya hatua ya kwanza.",
            "steps": steps,
        }

    password_input.fill(password)
    steps.append(f"Password imejazwa ({used_password}).")
    _submit(page, selectors["submit"])
    steps.append("Login imetumwa.")
    _settle(page)

    text = _page_text(page)
    marker = next((m for m in LOGIN_ERROR_MARKERS if m in text), "")
    if marker and _on_login_page(page, urlparse(login_url).path):
        return {
            "ok": False,
            "error": f"Login imekataliwa (alama: '{marker}').",
            "steps": steps,
            "final_url": page.url,
        }

    return {"ok": True, "error": "", "steps": steps, "final_url": page.url}


def _wrong_password_attempt(browser, login_url, username, selectors):
    context = browser.new_context()
    page = context.new_page()
    fake_password = "Wrong-" + secrets.token_urlsafe(9)
    try:
        attempt = _login(page, login_url, username, fake_password, selectors)
        text = _page_text(page)
        denied_marker = next((m for m in LOGIN_ERROR_MARKERS if m in text), "")
        still_on_login = _on_login_page(page, urlparse(login_url).path)
        rejected = still_on_login or bool(denied_marker)
        return {
            "tested": True,
            "rejected": bool(rejected),
            "login_page_after_attempt": still_on_login,
            "message": "Password isiyo sahihi imekataliwa." if rejected
            else "Password isiyo sahihi haijakataliwa waziwazi.",
            "error": attempt.get("error", ""),
        }
    finally:
        context.close()


def _header_checks(base_url):
    try:
        response = requests.get(base_url, timeout=20, allow_redirects=True)
    except Exception as exc:
        return {"error": str(exc), "checks": {}}

    headers = {key.lower(): value for key, value in response.headers.items()}
    checks = {
        "https": base_url.lower().startswith("https://"),
        "hsts": "strict-transport-security" in headers,
        "csp": "content-security-policy" in headers,
        "x_frame_options": "x-frame-options" in headers,
        "x_content_type_options": headers.get("x-content-type-options", "").lower() == "nosniff",
        "no_server_version": "server" not in headers
        or not any(ch.isdigit() for ch in headers.get("server", "")),
    }
    return {
        "error": "",
        "status": response.status_code,
        "checks": checks,
        "headers": {
            key: headers[key]
            for key in (
                "strict-transport-security",
                "content-security-policy",
                "x-frame-options",
                "x-content-type-options",
                "referrer-policy",
                "server",
            )
            if key in headers
        },
    }


def _cookie_checks(context, base_url):
    is_https = base_url.lower().startswith("https://")
    issues = []
    names = []
    for cookie in context.cookies():
        names.append(cookie.get("name", "?"))
        if is_https and not cookie.get("secure"):
            issues.append(f"Cookie '{cookie.get('name')}' haina Secure flag.")
        if not cookie.get("httpOnly"):
            issues.append(f"Cookie '{cookie.get('name')}' haina HttpOnly flag.")
        same_site = (cookie.get("sameSite") or "").lower()
        if same_site in ("", "none"):
            issues.append(f"Cookie '{cookie.get('name')}' haina SameSite imara.")
    return {"cookies": names, "issues": issues}


def _role_check(page, protected_url, login_path, expect_access):
    try:
        response = page.goto(protected_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Imeshindwa kufungua ukurasa wa role: {exc}",
            "url": protected_url,
            "status": None,
        }

    _settle(page)
    status = response.status if response is not None else None
    final_url = page.url
    text = _page_text(page)
    login_page = _on_login_page(page, login_path)
    denied = any(marker in text for marker in DENIED_MARKERS)
    http_error = status is not None and status >= 400

    if expect_access:
        ok = bool((not login_page) and (not denied) and (not http_error))
    else:
        ok = bool(login_page or denied or status in (401, 403))

    return {
        "ok": ok,
        "error": "",
        "url": final_url,
        "status": status,
        "login_page": login_page,
        "denied": denied,
        "expect_access": expect_access,
    }


def run_check(
    base_url,
    login_path,
    protected_path,
    username,
    password,
    expect_access=True,
    check_wrong_password=True,
    preset=None,
):
    preset = preset or {}
    base_url = (base_url or preset.get("base_url") or "").rstrip("/")
    login_path = login_path or preset.get("login_path") or ""
    protected_path = protected_path or preset.get("protected_path") or ""

    if not base_url or not login_path or not protected_path:
        return None, "Base URL, login path na protected path vinahitajika."
    if not username or not password:
        return None, "Test username na password vinahitajika."

    if not _host_allowed(base_url):
        return None, (
            "Host hii haijaruhusiwa. Weka kwenye SECURITY_CHECK_ALLOWED_HOSTS "
            "kama ni system yako halali."
        )

    login_url = login_path if login_path.startswith("http") else urljoin(base_url + "/", login_path.lstrip("/"))
    protected_url = (
        protected_path if protected_path.startswith("http")
        else urljoin(base_url + "/", protected_path.lstrip("/"))
    )
    if not _host_allowed(login_url) or not _host_allowed(protected_url):
        return None, "Login/protected URL lazima iwe kwenye host iliyoruhusiwa."

    selectors = {
        "username": preset.get("username_selectors") or USERNAME_SELECTORS,
        "password": preset.get("password_selectors") or PASSWORD_SELECTORS,
        "submit": preset.get("submit_selectors") or SUBMIT_SELECTORS,
    }

    result = {
        "login_url": login_url,
        "protected_url": protected_url,
        "login": {},
        "wrong_password": {"tested": False},
        "role": {},
        "headers": {},
        "cookies": {},
        "score": 0,
        "findings": [],
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            if check_wrong_password:
                result["wrong_password"] = _wrong_password_attempt(
                    browser, login_url, username, selectors,
                )

            result["login"] = _login(page, login_url, username, password, selectors)
            result["role"] = _role_check(
                page, protected_url, urlparse(login_url).path, expect_access,
            )
            result["cookies"] = _cookie_checks(context, base_url)
        finally:
            context.close()
            browser.close()

    result["headers"] = _header_checks(base_url)

    checks = []

    login_ok = bool(result["login"].get("ok"))
    checks.append(("Login na test account", login_ok, 30))
    if not login_ok:
        result["findings"].append(result["login"].get("error") or "Login imeshindwa.")

    role_ok = bool(result["role"].get("ok"))
    checks.append(("Role / access-control", role_ok, 20))
    if not role_ok:
        result["findings"].append(
            "Ukurasa wa role haukuonyesha matokeo yaliyotarajiwa "
            "(angalia URL/status kwenye ripoti)."
        )

    wrong = result["wrong_password"]
    if wrong.get("tested"):
        checks.append(("Password isiyo sahihi inakataliwa", bool(wrong.get("rejected")), 10))
        if not wrong.get("rejected"):
            result["findings"].append("Password isiyo sahihi haijakataliwa waziwazi.")

    header_checks = result["headers"].get("checks", {})
    if result["headers"].get("error"):
        result["findings"].append(
            f"Imeshindwa kuchunguza headers: {result['headers']['error']}"
        )
    else:
        for key, label, weight in (
            ("https", "Tovuti inatumia HTTPS", 10),
            ("hsts", "HSTS header", 5),
            ("csp", "Content-Security-Policy header", 5),
            ("x_frame_options", "X-Frame-Options header", 5),
            ("x_content_type_options", "X-Content-Type-Options: nosniff", 5),
            ("no_server_version", "Server haitoi version", 5),
        ):
            checks.append((label, bool(header_checks.get(key)), weight))
            if not header_checks.get(key):
                result["findings"].append(f"Hakuna/imekosekana: {label}.")

    cookie_issues = result["cookies"].get("issues", [])
    checks.append(("Cookies zina flags za usalama", not cookie_issues, 10))
    if cookie_issues:
        result["findings"].extend(cookie_issues)

    total = sum(weight for _, _, weight in checks)
    earned = sum(weight for _, ok, weight in checks if ok)
    result["score"] = round((earned / total) * 100) if total else 0
    result["checks"] = [
        {"label": label, "ok": ok, "weight": weight} for label, ok, weight in checks
    ]

    return result, None
