"""Recompute every cached ProcessedResult row under the CURRENT rules.

Cached rows are stale whenever a rule changes. Two fixes so far needed
this command:

  1. migration 0054 (nullable position + INC/ABS divisions) — candidates
     who sat fewer than 7 CSEE subjects still carried a computed
     division, and fully-absent candidates carried a division AND a
     position.
  2. the grade-tie tiebreak fix in _best_first — when two subjects had
     the SAME grade points, the old sort tiebroke on subject NAME, so a
     student could lose a 44 to a 31 sitting in the same grade. Their
     points and division were right but total_score / average_score /
     counted_subjects — and sometimes position — were wrong.

That second fix is why the diff below covers EVERY stored field, not just
division: the tiebreak bug's signature is exactly "division unchanged,
total changed", which a division-only report would score as 0 changes.

This command re-runs recompute_processed_results_for_exam for every exam
that already has cached rows, reporting exactly what changed. It exists
as a command — not as a RunPython backfill — because recomputing every
exam inside an atomic data migration was too slow and too all-or-nothing
over the remote Postgres proxy. One process per exam (see handle()) so a
wedged TCP read on the flaky proxy costs one exam, not the whole run.

DC Joint exams need no special handling: attach_school() gives every
member school a plain Exam row with joint_exam set, and those rows are
recomputed like any other exam. Use --joint <id> to scope the run to one
wilaya's joint exam.

Usage:
    python manage.py recompute_all_processed_results --dry-run
    python manage.py recompute_all_processed_results            # writes
    python manage.py recompute_all_processed_results --exam 12
    python manage.py recompute_all_processed_results --form 1 --year 2026
    python manage.py recompute_all_processed_results --joint 3
"""
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

# NB: no `results.models` import at module level! With the 'spawn' mp
# context the child process imports this module *before* Django apps are
# ready, and an app-level import here raises AppRegistryNotReady and
# kills every worker. Import Django models lazily inside functions.

MAX_RETRIES = 4

# Every stored aggregate the recompute can rewrite. The diff must cover
# all of them: the tiebreak bug changes total/average/counted_subjects
# while leaving points and division untouched.
STORED_FIELDS = (
    'total_score', 'average_score', 'points',
    'division', 'position', 'counted_subjects',
)


def _snapshot(exam):
    """{row pk: (every STORED_FIELDS value, in order)} for one exam."""
    from results.models import ProcessedResult

    return {
        pr.pk: tuple(getattr(pr, f) for f in STORED_FIELDS)
        for pr in ProcessedResult.objects.filter(exam=exam).only(*STORED_FIELDS)
    }


class _Diff:
    """Field-level diff of one exam's cached rows, before vs after.

    Tracks per-field counts instead of a single "changed" flag so a run
    that only shifts totals (the tiebreak bug) is visibly different from
    a run that does nothing.
    """

    def __init__(self):
        self.fields = Counter()   # field name -> rows where it changed
        self.rows = 0             # rows whose value tuple changed at all
        self.added = 0            # rows that appeared
        self.removed = 0          # rows that disappeared (stale cleanup)
        self.division = Counter()  # (old division -> new division)

    def compare(self, before, after):
        for pk_, new in after.items():
            old = before.get(pk_)
            if old is None:
                self.added += 1
                continue
            if old == new:
                continue
            self.rows += 1
            for field, o, n in zip(STORED_FIELDS, old, new):
                if o != n:
                    self.fields[field] += 1
            self.division[(old[3], new[3])] += 1
        self.removed += sum(1 for pk_ in before if pk_ not in after)

    def merge(self, other):
        self.fields.update(other.fields)
        self.rows += other.rows
        self.added += other.added
        self.removed += other.removed
        self.division.update(other.division)

    @property
    def touched(self):
        return self.rows + self.added + self.removed

    def summary(self):
        parts = [f'{n} {f}' for f, n in sorted(self.fields.items())]
        return ', '.join(parts) if parts else 'hakuna'


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
        'that already has cached ProcessedResult rows, reporting a '
        'field-level diff of what changed.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--exam', type=int, default=None,
            help='Only recompute this exam PK instead of all of them.',
        )
        parser.add_argument(
            '--form', type=int, default=None,
            help='Only exams of this form (1-6). Use to scope a big run.',
        )
        parser.add_argument(
            '--year', type=int, default=None,
            help='Only exams of this year.',
        )
        parser.add_argument(
            '--joint', type=int, default=None,
            help='Only the Exam rows belonging to this JointExam PK (DC Joint).',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Compute and report the diff but roll everything back — nothing is saved.',
        )
        parser.add_argument(
            '--in-process', action='store_true',
            help=(
                'Recompute every exam in this process instead of forking a '
                'worker per exam. Slower and without the proxy-hang '
                'isolation, but the only mode that works when a spawned '
                'child cannot reach the same database (test database, or a '
                'proxy accepting one connection at a time).'
            ),
        )
        parser.add_argument(
            '--worker', action='store_true',
            help=(
                'Internal: do the actual recompute for --exam in this process '
                'and return, instead of forking a child (used by the '
                'per-exam multiprocessing orchestration).'
            ),
        )

    def _recompute_one(self, exam_pk, dry_run, out, db) -> _Diff:
        """Recompute one exam in THIS process and report its field-level diff.

        The single base case both execution paths share: the spawned worker
        (isolation from the flaky proxy) and --in-process (same process, no
        fork). --dry-run rolls the transaction back, so the diff is
        predicted-and-discarded rather than committed.
        """
        from django.db import transaction

        from results.models import Exam
        from results.services.upload_processing_service import (
            recompute_processed_results_for_exam,
        )

        exam = Exam.objects.filter(pk=exam_pk).first()
        if exam is None:
            raise CommandError(f'Exam #{exam_pk} haipo.')

        before = _snapshot(exam)
        with transaction.atomic(using=db):
            recompute_processed_results_for_exam(exam)
            after = _snapshot(exam)
            if dry_run:
                transaction.set_rollback(True, using=db)

        diff = _Diff()
        diff.compare(before, after)
        out.write(
            f'Exam #{exam_pk} "{exam.name}": rows zilizobadilika {diff.rows} '
            f'(zilizotoka {diff.added}, zilizokoma {diff.removed}) | '
            f'saraka: {diff.summary()}'
            + (' [DRY RUN — imeendeleza nyuma]' if dry_run else '')
        )
        for (old, new), n in sorted(diff.division.items(), key=lambda kv: -kv[1]):
            out.write(f'  {old or "(blank)"} -> {new or "(blank)"} : {n}')
        return diff

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
            self._recompute_one(exam_pk, dry_run, self.stdout, db)
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
        # Narrowing filters — the tiebreak bug only touches rows that
        # actually have grade ties, but a recompute is cheap enough to
        # re-run whole exams, so scope by exam/form/year/joint instead of
        # trying to detect affected students in SQL.
        if options['form'] is not None:
            exams = exams.filter(form=options['form'])
        if options['year'] is not None:
            exams = exams.filter(year=options['year'])
        if options['joint'] is not None:
            exams = exams.filter(joint_exam_id=options['joint'])

        total = exams.count()
        if not total:
            self.stdout.write(self.style.WARNING(
                'Hakuna exam inayolingana na vichujio ulivyotumia — hakuna kilichofanyika.'
            ))
            return
        scope = []
        for label, key in (('form', 'form'), ('year', 'year'), ('joint', 'joint')):
            if options[key] is not None:
                scope.append(f'{label}={options[key]}')
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Exams zenye cached results: {total}'
            + (f"  (vichujio: {', '.join(scope)})" if scope else '')
            + ('  [DRY RUN — hakuna kitakachohifadhiwa]' if dry_run else '')
        ), ending='\n')
        self.stdout.flush()

        total_diff = _Diff()
        failed = []

        per_exam_timeout = 150
        import multiprocessing as mp
        ctx = mp.get_context('spawn')
        in_process = options['in_process']

        for idx, exam in enumerate(exams, start=1):
            status = 'OK'
            # Snapshot the cached rows before anything rewrites them so the
            # run can be diffed either way (in-process, or by re-reading
            # after a spawned child committed).
            before = _snapshot(exam)
            if in_process:
                # Same process, no fork. Needed when a spawned child cannot
                # reach the database this process is talking to (a test
                # database, or a proxy that only accepts one connection).
                try:
                    total_diff.merge(self._recompute_one(exam.pk, dry_run, self.stdout, db))
                except Exception as exc:  # noqa: BLE001 - one bad exam must not stop the run
                    failed.append((exam.pk, str(exc)))
                    status = f'FAILED ({exc})'
            else:
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

                # Re-read what the worker actually changed. For a real run
                # this sees the committed rows; for --dry-run the worker
                # rolled its transaction back, so this always reads as
                # unchanged — the worker log dumped below (always, not just
                # on failure) is the only place the predicted dry-run diff
                # is visible.
                diff = _Diff()
                diff.compare(before, _snapshot(exam))
                total_diff.merge(diff)

            # Drop the persistent (conn_max_age) connection between exams
            # — through this proxy idle keep-alive connections come back
            # as "server closed the connection unexpectedly".
            try:
                connections[db].close()
            except Exception:
                pass

            if not in_process:
                self._dump_worker_log()
            self.stdout.write(
                f'  [{idx}/{total}] exam #{exam.pk} "{exam.name}" (form {exam.form}): {status}'
            )
            self.stdout.flush()

        self.stdout.write(self.style.MIGRATE_HEADING('\nMuhtasari wa mabadiliko:'))
        for field, n in sorted(total_diff.fields.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'  {field:<18} : {n}')

        if total_diff.division:
            self.stdout.write('  Mabadiliko ya division:')
            for (old, new), n in sorted(total_diff.division.items(), key=lambda kv: -kv[1]):
                self.stdout.write(f'    {old or "(blank)":>8} → {new or "(blank)":<8} : {n}')

        if dry_run:
            # The parent re-reads committed state, so its own counters are
            # always 0 for a dry run — the per-exam worker log dumped above
            # is where the predicted diff is visible.
            self.stdout.write(self.style.WARNING(
                'DRY RUN — hakuna kitu kilichohifadhiwa. Angalia "worker log '
                'tail" ya kila exam hapo juu kwa diff iliyotabiriwa, kisha '
                'endesha tena bila --dry-run.'
            ))
        elif total_diff.touched:
            self.stdout.write(self.style.SUCCESS(
                f'\nRows zilizobadilika: {total_diff.rows} '
                f'(mpya {total_diff.added}, zilizokoma {total_diff.removed}) | '
                f'saraka: {total_diff.summary()}'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                '\nHakuna mabadiliko — matokeo yaliyohifadhiwa yalikuwa tayari '
                'sahihi kwa sharia za sasa.'
            ))
        if failed:
            for pk, err in failed:
                self.stderr.write(self.style.ERROR(f'  exam #{pk} FAILED: {err}'))
            raise CommandError(f'{len(failed)} exam(s) zimeshindikana — zirudie.')
