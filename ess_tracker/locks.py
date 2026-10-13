"""Lock ya kila mwalimu (profile) kwenye cache/Redis.

Huzuia run mbili za ESS kwa mwalimu mmoja zisiende kwa wakati mmoja. Hii
inaepusha: kuwasilisha entry mara mbili, 'Sub Task Progress' ya ghafla, na
kutumia browser (Chromium) mara mbili kwa mtu mmoja.

Cache inatumiwa (Redis kwenye production) kwa `cache.add` ambayo ni atomic
(SET NX) — hivyo kati ya readers wengi, mmoja tu hushika lock.
"""
from contextlib import contextmanager
import uuid

from django.conf import settings
from django.core.cache import cache

LOCK_PREFIX = 'ess:lock:profile:'


def _key(profile_id):
    return f'{LOCK_PREFIX}{profile_id}'


def is_locked(profile_id) -> bool:
    """True kama mwalimu huyu ana run inayoendelea sasa hivi."""
    return cache.get(_key(profile_id)) is not None


def _default_timeout() -> int:
    return int(getattr(settings, 'ESS_PROFILE_LOCK_SECONDS', 900))


@contextmanager
def profile_lock(profile_id, timeout=None):
    """Shika lock ya mwalimu; hutoa True kama imeshikwa, False kama mwingine anayo.

    Lock hujifuta yenyewe baada ya `timeout` (default ESS_PROFILE_LOCK_SECONDS)
    ili run iliyoanguka isimfunge mwalimu milele. Hurudisha lock tu ikiwa
    token yetu ndiyo iliyomo (kuepuka kumfuta mmiliki mpya).
    """
    if timeout is None:
        timeout = _default_timeout()
    key = _key(profile_id)
    token = uuid.uuid4().hex
    acquired = cache.add(key, token, timeout)
    try:
        yield acquired
    finally:
        try:
            if acquired and cache.get(key) == token:
                cache.delete(key)
        except Exception:
            pass
