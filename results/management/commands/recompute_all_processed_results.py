"""Backfill cached ProcessedResult rows with the INC/ABS rules.

After migration 0054 (nullable position + INC/ABS division choices) the
cached rows processed under the older rules are stale: candidates who sat
fewer than 7 CSEE subjects still carry a computed division (often the old
capped IV or '0'), and fully-absent candidates carry a division AND a
position even though they should show ABS / '-' / unranked.

This command re-runs recompute_processed_results_for_exam for every exam
that already has cached rows, reporting exactly what changed. It exists
as a command — not as a RunPython backfill inside 0054 — because
recomputing every exam inside an atomic data migration was too slow and
too all-or-nothing over the remote Postgres proxy.

Usage:
    python manage.py recompute_all_processed_results --dry-run
    python manage.py recompute_all_processed_results            # writes
    python manage.py recompute_all_processed_results --exam 12
"""
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

# NB: no `results.models` import at module level! With the 'spawn' mp
# context the child process imports this module *before* Django apps are
# ready, and an app-level import here raises AppRegistryNotReady and
# kills every worker. Import Django models lazily inside functions.

MAX_RETRIES = 4


def _run_single_exam(exam_pk: int, dry_run: bool) -> int:
    """Run this command for one exam in a fresh process, in --worker mode.

    Called via multiprocessing from handle() so a wedged TCP read on the
    flaky remote proxy can only ever cost one exam (the parent kills and
    restarts the worker), not the whole run. --worker is what makes the
    child actually do the recompute instead of forking yet another
    subprocess (see handle()'s worker branch).
    """
    import sys

    import django

    django.setup()

    from django.core.management import call_command

    args = ['recompute_all_processed_results', '--exam', str(exam_pk), '--worker']
    if dry_run:
        args.append('--dry-run')
    old_stdout = sys.stdout
    sys.stdout = open('/tmp/_recompute_single.log', 'w')
    try:
        call_command(*args)
    finally:
        sys.stdout.close()
        sys.stdout = old_stdout
    return 0


class Command(BaseCommand):
    help = (
        'Re-run the division/aggregate/position recompute for every exam '
        'that already has cached ProcessedResult rows (INC/ABS backfill).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--exam', type=int, default=None,
            help='Only recompute this exam PK instead of all of them.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Compute and report the diff but roll everything back — nothing is saved.',
        )
        parser.add_argument(
            '--worker', action='store_true',
            help=(
                'Internal: do the actual recompute for --exam in this process '
                'and return, instead of forking a child (used by the '
                'per-exam multiprocessing orchestration).'
            ),
        )

    def _dump_worker_log(self, tail: int = 20) -> None:
        """Show the end of the child's captured stdout to explain a failure."""
        try:
            with open('/tmp/_recompute_single.log') as fh:
                lines = fh.readlines()[-tail:]
        except OSError:
            return
        if lines:
            self.stdout.write('    --- worker log tail ---')
            for line in lines:
                self.stdout.write(f'    {line.rstrip()}')

    def handle(self, *args, **options):
        from results.models import Exam, ProcessedResult

        exam_pk = options['exam']
        dry_run = options['dry_run']
        db = ProcessedResult.objects.db  # router-routed alias

        # The Railway Postgres proxy drops/hangs idle connections: bound
        # how long psycopg2 waits, detect dead peers fast, and never keep
        # a persistent connection across exams.
        cfg = connections.databases[db]
        opts = cfg.setdefault('OPTIONS', {})
        opts.setdefault('connect_timeout', 15)
        opts.setdefault('keepalives', 1)
        opts.setdefault('keepalives_idle', 30)
        opts.setdefault('keepalives_interval', 10)
        opts.setdefault('keepalives_count', 3)
        opts.setdefault('options', '-c statement_timeout=60000')
        cfg['CONN_MAX_AGE'] = 0
        cfg['CONN_HEALTH_CHECKS'] = True

        if options['worker']:
            # Actually do the recompute for one exam, in this process — no
            # further forking. This is the base case the multiprocessing
            # orchestrator below bottoms out on.
            if exam_pk is None:
                raise CommandError('--worker requires --exam.')

            from django.db import transaction

            from results.services.upload_processing_service import (
                recompute_processed_results_for_exam,
            )

            exam = Exam.objects.filter(pk=exam_pk).first()
            if exam is None:
                raise CommandError(f'Exam #{exam_pk} haipo.')

            before = {
                pr.pk: (pr.division, pr.points, pr.position)
                for pr in ProcessedResult.objects.filter(exam=exam)
            }
            with transaction.atomic(using=db):
                recompute_processed_results_for_exam(exam)
                after = {
                    pr.pk: (pr.division, pr.points, pr.position)
                    for pr in ProcessedResult.objects.filter(exam=exam)
                }
                if dry_run:
                    transaction.set_rollback(True, using=db)

            transitions = Counter()
            rows_changed = 0
            position_changed = 0
            for pk_, new in after.items():
                old = before.get(pk_)
                if old is not None and old != new:
                    rows_changed += 1
                    if old[2] != new[2]:
                        position_changed += 1
                    transitions[(old[0], new[0])] += 1

            self.stdout.write(
                f'Exam #{exam_pk} "{exam.name}": rows changed {rows_changed}, '
                f'position changed {position_changed}'
                + (' [DRY RUN — rolled back]' if dry_run else '')
            )
            for (old, new), n in sorted(transitions.items(), key=lambda kv: -kv[1]):
                self.stdout.write(f'  {old or "(blank)"} -> {new or "(blank)"} : {n}')
            return

        exam_ids = set(
            ProcessedResult.objects.values_list('exam_id', flat=True).distinct()
        )
        if exam_pk is not None:
            if exam_pk not in exam_ids:
                # Not an error: the per-exam orchestrator calls this for
                # every exam and some simply have no cached rows.
                self.stdout.write(self.style.WARNING(
                    f'Exam #{exam_pk} haina processed results — imeuka.'
                ))
                return
            exam_ids = {exam_pk}

        exams = Exam.objects.filter(pk__in=exam_ids).order_by('pk')
        total = exams.count()
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Exams zenye cached results: {total}'
            + ('  [DRY RUN — hakuna kitakachohifadhiwa]' if dry_run else '')
        ), ending='\n')
        self.stdout.flush()

        transitions = Counter()
        position_changed = 0
        rows_changed = 0
        failed = []

        per_exam_timeout = 150
        import multiprocessing as mp
        ctx = mp.get_context('spawn')

        for idx, exam in enumerate(exams, start=1):
            status = 'OK'
            # Snapshot the cached rows before the child rewrites them so
            # the parent can diff each exam and aggregate the totals.
            before = {
                pr.pk: (pr.division, pr.points, pr.position)
                for pr in ProcessedResult.objects.filter(exam=exam)
            }
            # Fresh process per exam: a hung proxy read dies with the
            # worker and only that exam retries, instead of wedging the
            # whole run in an uninterruptible socket read (D-state).
            proc = ctx.Process(target=_run_single_exam, args=(exam.pk, dry_run))
            proc.start()
            proc.join(per_exam_timeout)
            if proc.is_alive():
                proc.terminate()
                proc.join(10)
                if proc.is_alive():
                    proc.kill()
                    proc.join()
                err = f'timed out after {per_exam_timeout}s'
                failed.append((exam.pk, err))
                status = f'FAILED ({err})'
            elif proc.exitcode not in (0, None):
                err = f'worker exit code {proc.exitcode}'
                failed.append((exam.pk, err))
                status = f'FAILED ({err})'

            # Re-read what the worker actually changed. For a real run this
            # sees the committed rows; for --dry-run the worker rolled its
            # transaction back, so this always reads as unchanged — the
            # worker log dumped below (always, not just on failure) is the
            # only place the predicted dry-run diff is visible.
            after = {
                pr.pk: (pr.division, pr.points, pr.position)
                for pr in ProcessedResult.objects.filter(exam=exam)
            }
            for pk_, new in after.items():
                old = before.get(pk_)
                if old is not None and old != new:
                    rows_changed += 1
                    if old[2] != new[2]:
                        position_changed += 1
                    transitions[(old[0], new[0])] += 1

            # Drop the persistent (conn_max_age) connection between exams
            # — through this proxy idle kept-alive connections come back
            # as "server closed the connection unexpectedly".
            try:
                connections[db].close()
            except Exception:
                pass

            self._dump_worker_log()
            self.stdout.write(
                f'  [{idx}/{total}] exam #{exam.pk} "{exam.name}" (form {exam.form}): {status}'
            )
            self.stdout.flush()

        self.stdout.write(self.style.MIGRATE_HEADING('\nMuhtasari wa mabadiliko ya division:'))
        for (old, new), n in sorted(transitions.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'  {old or "(blank)":>8} → {new or "(blank)":<8} : {n}')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                'DRY RUN — rows/position counts above are always 0 (nothing '
                'was committed); angalia "worker log tail" ya kila exam hapo '
                'juu kwa diff halisi iliyotabiriwa.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\nRows zilizogusa: {rows_changed} | position zilizobadilika: {position_changed}'
            ))
        if failed:
            for pk, err in failed:
                self.stderr.write(self.style.ERROR(f'  exam #{pk} FAILED: {err}'))
            raise CommandError(f'{len(failed)} exam(s) zimeshindikana — zirudie.')
