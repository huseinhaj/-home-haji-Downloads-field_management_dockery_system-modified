"""Usimbaji wa password ya ESS (kwa ajili ya auto-login).

Password haiwezi kusomwa (decrypt) bikia kitufe ambacho kiko kwenye env
`ESS_ENC_KEY` (Fernet key ya base64). Iwapo kitufe hakipo, tumia kitufe
kinachotokana na DJANGO_SECRET_KEY — hivyo hakuna password inayohifadhiwa
wazi kwenye DB.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_cache = {'fernet': None}


def _key() -> bytes:
    raw = os.environ.get('ESS_ENC_KEY') or ''
    if raw:
        try:
            return base64.urlsafe_b64decode(raw)
        except Exception:
            pass
    from django.conf import settings
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    if _cache['fernet'] is None:
        _cache['fernet'] = Fernet(_key())
    return _cache['fernet']


def encrypt_password(plain: str) -> str:
    if not plain:
        return ''
    try:
        return _fernet().encrypt((plain or '').encode('utf-8')).decode('ascii')
    except Exception:
        return ''


def decrypt_password(token: str) -> str:
    if not token:
        return ''
    try:
        return _fernet().decrypt(token.encode('ascii')).decode('utf-8')
    except Exception:
        return ''