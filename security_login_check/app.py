"""Mini app ya Security Login Check (authorized testing only).

Inatumia test credentials unazoweka wewe mwenyewe kupima login na role
permissions kwenye system zako. Nywila hazihifadhiwi wala hazilogwi.
"""

from __future__ import annotations

import hmac
import os
import secrets

from flask import Flask, redirect, render_template, request, session, url_for

from checker import ALLOWED_HOSTS, PRESETS, run_check


ACCESS_TOKEN = os.environ.get("SECURITY_CHECK_ACCESS_TOKEN", "")
REQUIRE_TOKEN = os.environ.get("SECURITY_CHECK_REQUIRE_TOKEN", "0") == "1"
if REQUIRE_TOKEN and not ACCESS_TOKEN:
    raise RuntimeError("SECURITY_CHECK_ACCESS_TOKEN is required when "
                       "SECURITY_CHECK_REQUIRE_TOKEN=1")


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
app.config["SECRET_KEY"] = (
    os.environ.get("SECURITY_CHECK_SECRET") or secrets.token_hex(32)
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get(
    "SECURITY_CHECK_HTTPS", "0"
) == "1"


@app.before_request
def _require_access_token():
    if not ACCESS_TOKEN:
        return None
    if request.endpoint in ("login", "health", "static"):
        return None
    if session.get("security_check_ok") is True:
        return None
    return redirect(url_for("login", next=request.path))


@app.get("/health")
def health():
    return "ok", 200


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        supplied = request.form.get("token", "")
        if hmac.compare_digest(supplied, ACCESS_TOKEN):
            session["security_check_ok"] = True
            target = request.args.get("next", "")
            if not target.startswith("/") or target.startswith("//"):
                target = url_for("index")
            return redirect(target)
        error = "Token si sahihi."
    return render_template("login.html", error=error), (401 if error else 200)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _safe_form(form):
    return {
        "preset": form.get("preset", "custom"),
        "base_url": form.get("base_url", ""),
        "login_path": form.get("login_path", ""),
        "protected_path": form.get("protected_path", ""),
        "role": form.get("role", ""),
        "expect_access": form.get("expect_access") == "1",
        "check_wrong_password": form.get("check_wrong_password") == "1",
    }


@app.get("/")
def index():
    preset = PRESETS["results_admin"]
    return render_template(
        "index.html",
        presets=PRESETS,
        allowed_hosts=ALLOWED_HOSTS,
        result=None,
        error=None,
        token_enabled=bool(ACCESS_TOKEN),
        form={
            "preset": "results_admin",
            "base_url": preset["base_url"],
            "login_path": preset["login_path"],
            "protected_path": preset["protected_path"],
            "role": "",
            "expect_access": True,
            "check_wrong_password": True,
        },
    )


@app.post("/check")
def check():
    form = _safe_form(request.form)
    preset = PRESETS.get(form["preset"], PRESETS["custom"])

    result, error = run_check(
        base_url=form["base_url"],
        login_path=form["login_path"],
        protected_path=form["protected_path"],
        username=request.form.get("username", ""),
        password=request.form.get("password", ""),
        expect_access=form["expect_access"],
        check_wrong_password=form["check_wrong_password"],
        preset=preset,
    )

    return render_template(
        "index.html",
        presets=PRESETS,
        allowed_hosts=ALLOWED_HOSTS,
        result=result,
        error=error,
        token_enabled=bool(ACCESS_TOKEN),
        form=form,
    )


if __name__ == "__main__":
    app.run(
        host=os.environ.get("SECURITY_CHECK_HOST", "127.0.0.1"),
        port=int(os.environ.get("SECURITY_CHECK_PORT", "5055")),
        debug=False,
        use_reloader=False,
    )
