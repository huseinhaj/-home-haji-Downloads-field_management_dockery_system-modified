"""Kuanzisha EssFillRun — kiini kimoja kwa views zote za ESS.

Kila kitufe cha "Jaza/Soma/Sync/Tuma/Idhinisha" kilianzisha run kwa mkono:
kuunda run, jaribu Celery (`apply_async`), fallback kwa thread, kisha weka
cache ya mwanzo. `launch_run` hukusanya hatua hizo nne ili zisijarudiwe
kwenye views tano (na kutowekwa baadaye).
"""
from __future__ import annotations

import threading

from django.core.cache import cache

from .essfill import CACHE_PREFIX
from .models import EssFillRun


def launch_run(*, profile, kind='fill', task=None, thread_target=None,
               thread_args=(), run_fields=None, initial_log='',
               use_async=True) -> EssFillRun:
    """Fungua run mpya ya 'running' na ianze kwenye Celery au thread.

    Paramita:
      - `profile`       — TeacherProfile mmiliki wa run.
      - `kind`          — 'fill' | 'read' | 'sync' | 'push' | 'approve'.
      - `task`          — kazi ya Celery (mf. `tasks.run_ess_fill`) inayopokea
                          `(profile_id, run_id[, *thread_args])`. Ikikosea
                          kuanza (broker hapo), thread hutumika.
      - `thread_target` — kazi ya fallback (mf. `essfill.run_fill`), muundo
                          uleule kama wa `task`.
      - `thread_args`   — hoja za ziada kwa zote mbili (mf. `(dry_run,)`).
      - `run_fields`    — sehemu za ziada za run kabla ya kuanza
                          (mf. `{'only_subtasks': '1,2'}`).
      - `initial_log`   — log ya mwanzo (mf. 'Uhidhinishaji umeanza...').
      - `use_async`     — False = tumia thread moja kwa moja (approve ya mkono).

    Rudisha `EssFillRun` iliyoundwa (tayari 'running' na cache imeandikwa).
    """
    run = EssFillRun.objects.create(profile=profile, kind=kind,
                                    **(run_fields or {}))
    run.status = 'running'
    if initial_log:
        run.log = initial_log
    run.save()

    started = False
    if use_async and task is not None:
        try:
            res = task.apply_async(args=[profile.id, run.id, *thread_args],
                                   queue='essfill')
            run.task_id = res.id
            run.save(update_fields=['task_id'])
            started = True
        except Exception:  # noqa: BLE001 - broker/routing hayapo → thread
            started = False
    if not started and thread_target is not None:
        def _wrapped(*extra):
            try:
                return thread_target(*extra)
            finally:
                # Thread fallback haipiti Celery — tuma matokeo hapa
                # (mwalimu + admins kama run ilivunjika).
                try:
                    from .tasks import notify_run_result
                    notify_run_result(extra[1])
                except Exception:  # noqa: BLE001 - arifa si hitaji la msingi
                    pass

        threading.Thread(target=_wrapped,
                         args=(profile.id, run.id, *thread_args),
                         daemon=True).start()

    cache.set(CACHE_PREFIX + str(run.id),
              {'msg': 'Inaanzisha...', 'step': 0, 'done': False, 'error': ''},
              timeout=3600)
    return run
