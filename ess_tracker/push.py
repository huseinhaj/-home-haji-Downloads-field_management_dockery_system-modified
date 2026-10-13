"""Web Push (VAPID) — kutuma arifa kwa vifaa vya walimu.

Inatumia pywebpush kama ipo. Kama VAPID keys hazijawekwa (settings),
arifa huzimwa kwa upole (functions zinarudi bila kosa) ili app iendelee
kufanya kazi hata kama notifications hazijasanidiwa.
"""
import json
import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('ess_tracker')


def push_configured() -> bool:
    """True kama VAPID keys zimewekwa na pywebpush inapatikana."""
    if not (getattr(settings, 'VAPID_PUBLIC_KEY', '')
            and getattr(settings, 'VAPID_PRIVATE_KEY', '')):
        return False
    try:
        import pywebpush  # noqa: F401
    except Exception:
        return False
    return True


def _claims():
    sub = getattr(settings, 'VAPID_ADMIN_EMAIL', '') or 'support@example.com'
    if not sub.startswith('mailto:') and '@' in sub:
        sub = 'mailto:' + sub
    return {'sub': sub}


def send_to_subscription(sub, payload: dict):
    """Tuma push kwa subscription moja. Rudi (ok, gone).

    gone=True maana yake subscription imekwisha (410/404) — ifutwe.
    """
    from pywebpush import WebPushException, webpush
    info = {
        'endpoint': sub.endpoint,
        'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
    }
    try:
        webpush(
            subscription_info=info,
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims=_claims(),
            timeout=15,
        )
        return True, False
    except WebPushException as exc:
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status in (404, 410):
            return False, True
        logger.warning('push failed (%s): %s', status, exc)
        return False, False
    except Exception as exc:  # pragma: no cover - network/edge
        logger.warning('push error: %s', exc)
        return False, False


def send_to_profile(profile_or_id, *, title, body, url='/ess/',
                    tag='ess', renotify=False):
    """Tuma arifa kwa vifaa vyote vya mwalimu. Rudi {sent, gone, total}."""
    from .models import PushSubscription, TeacherProfile

    if not push_configured():
        return {'sent': 0, 'gone': 0, 'total': 0, 'skipped': 'not-configured'}

    if isinstance(profile_or_id, TeacherProfile):
        profile = profile_or_id
    else:
        profile = TeacherProfile.objects.filter(pk=profile_or_id).first()
    if profile is None:
        return {'sent': 0, 'gone': 0, 'total': 0, 'skipped': 'no-profile'}

    from django.templatetags.static import static
    icon = static('ess/icon-192.png')
    payload = {
        'title': title,
        'body': body,
        'url': url,
        'tag': tag,
        'renotify': renotify,
        'icon': icon,
        'badge': icon,
    }
    subs = list(profile.push_subscriptions.filter(active=True))
    sent = 0
    gone_ids = []
    now = timezone.now()
    for sub in subs:
        ok, gone = send_to_subscription(sub, payload)
        if ok:
            sent += 1
            PushSubscription.objects.filter(pk=sub.pk).update(last_seen=now)
        if gone:
            gone_ids.append(sub.pk)
    if gone_ids:
        PushSubscription.objects.filter(pk__in=gone_ids).update(active=False)
    return {'sent': sent, 'gone': len(gone_ids), 'total': len(subs)}
