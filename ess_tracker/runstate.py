"""Usafi wa runs za ESS zilizokwama ('stale').

Run inaweza kubaki `running` milele kama worker akianguka au process ikikatika
(kwa mfano wakati wa kufunga browser). Run kama hiyo huzuia kujaza mpya:
`ess_fill` hukataa kuanzisha run nyingine ya `fill` yenye status `running`
(Mwenyewe), na `auto_fill_decision` huiona kama 'already' siku hiyo.

`reap_stale_runs` huweka runs zilizopita muda wa kutosha kuwa `error` ili
zisikwame milele.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def _stale_seconds() -> int:
    return int(getattr(settings, 'ESS_RUN_STALE_SECONDS', 1800))


def reap_stale_runs(profile=None) -> int:
    """Funga runs zilizokwama ('running' kwa muda mrefu) kama 'error'.

    Hurudisha idadi ya runs zilizofungwa. `profile` akipewa, hushughulikia
    mwalimu huyo pekee.
    """
    from .models import EssFillRun

    cutoff = timezone.now() - timedelta(seconds=_stale_seconds())
    qs = EssFillRun.objects.filter(status='running', started__lt=cutoff)
    if profile is not None:
        qs = qs.filter(profile=profile)
    note = 'Run iliyokwama (haikukamilika kwa muda mrefu); imefungwa kiotomatiki.'
    reaped = 0
    for run in qs:
        run.status = 'error'
        run.finished = timezone.now()
        run.log = (run.log + '\n' + note) if run.log else note
        run.save(update_fields=['status', 'finished', 'log'])
        reaped += 1
    return reaped
