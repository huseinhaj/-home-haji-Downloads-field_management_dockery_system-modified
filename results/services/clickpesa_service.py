"""clickpesa_service.py — ClickPesa mobile money collection (USSD push).

Real endpoints per ClickPesa's published API reference
(docs.clickpesa.com/api-reference/...):

  POST https://api.clickpesa.com/third-parties/generate-token
       headers: client-id, api-key  ->  {"success": bool, "token": "<JWT>"}

  POST https://api.clickpesa.com/third-parties/payments/initiate-ussd-push-request
       headers: Authorization: Bearer <token>
       body: {amount, currency: "TZS", orderReference, phoneNumber}
       ->  {id, status, channel, orderReference, collectedAmount, ...}

Credentials come from Django settings (CLICKPESA_CLIENT_ID /
CLICKPESA_API_KEY), which read from the environment — nothing is
hardcoded here. Until those are configured, calling this raises
ClickPesaError immediately rather than pretending a payment succeeded.
"""

from __future__ import annotations

import requests
from django.conf import settings

BASE_URL = "https://api.clickpesa.com/third-parties"


class ClickPesaError(Exception):
    pass


def _require_credentials():
    client_id = getattr(settings, 'CLICKPESA_CLIENT_ID', '') or ''
    api_key = getattr(settings, 'CLICKPESA_API_KEY', '') or ''
    if not client_id or not api_key:
        raise ClickPesaError(
            "ClickPesa haijawekewa credentials (CLICKPESA_CLIENT_ID / CLICKPESA_API_KEY). "
            "Malipo hayawezi kufanywa mpaka msimamizi wa mfumo aweke hizo."
        )
    return client_id, api_key


def get_token() -> str:
    client_id, api_key = _require_credentials()
    try:
        resp = requests.post(
            f"{BASE_URL}/generate-token",
            headers={"client-id": client_id, "api-key": api_key},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise ClickPesaError(f"Imeshindwa kuwasiliana na ClickPesa: {exc}") from exc

    if resp.status_code != 200:
        raise ClickPesaError(f"ClickPesa token error ({resp.status_code}): {resp.text}")

    data = resp.json()
    token = data.get('token')
    if not token:
        raise ClickPesaError(f"ClickPesa haikurudisha token: {data}")
    return token


def initiate_ussd_push(*, amount: int, phone_number: str, order_reference: str) -> dict:
    """phone_number must be in 255XXXXXXXXX format (no leading +/0)."""
    token = get_token()
    payload = {
        "amount": str(amount),
        "currency": "TZS",
        "orderReference": order_reference,
        "phoneNumber": phone_number,
    }
    try:
        resp = requests.post(
            f"{BASE_URL}/payments/initiate-ussd-push-request",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise ClickPesaError(f"Imeshindwa kutuma ombi la malipo: {exc}") from exc

    if resp.status_code not in (200, 201):
        raise ClickPesaError(f"ClickPesa payment error ({resp.status_code}): {resp.text}")

    return resp.json()


def normalize_tz_phone(raw: str) -> str:
    """Accepts 07XXXXXXXX, 7XXXXXXXX, 2557XXXXXXXX, +2557XXXXXXXX -> 2557XXXXXXXX."""
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if digits.startswith('255') and len(digits) == 12:
        return digits
    if digits.startswith('0') and len(digits) == 10:
        return '255' + digits[1:]
    if len(digits) == 9:
        return '255' + digits
    return digits
