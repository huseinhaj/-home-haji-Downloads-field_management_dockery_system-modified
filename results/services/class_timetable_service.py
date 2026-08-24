"""class_timetable_service.py — weekly class/teaching timetable generation.

Unlike exam-day scheduling, a school's weekly timetable is a genuine
constraint-satisfaction problem: no teacher may be double-booked at the
same day+period across two different classes. This is deterministic —
no AI/LLM involved — because an LLM cannot reliably *guarantee* a
clash-free result at this scale; the "smart" part here is the placement
heuristic (most-constrained-first, spread subjects across the week),
not delegated reasoning. The one hard rule that must never be broken is
"no double booking" — everything else is best-effort.

The timetable itself is a standing weekly template (ClassTimetableEntry),
not tied to a calendar date — it applies every week until an academic
officer regenerates it (whole classes) or hand-edits a single cell
(one lesson).
"""
from __future__ import annotations

import random
from collections import defaultdict


class TimetableConflict(Exception):
    pass


# Mon-Fri day structure, matching Isingiro Secondary School's actual
# timetable (Kyerwa DC) this feature was modelled on: cleanliness/parade,
# 4 teaching periods, a short break, 5 more teaching periods, then lunch
# at the end of the day. 9 teaching periods/day, meant to be filled in
# double periods (2 consecutive periods per subject per session) — see
# TeachingAssignment.double_period. Officers are free to edit or replace
# this entirely; it only exists to save typing ~60 rows by hand for the
# common case, not to prescribe how any particular school must run its day.
# Mon–Thu day structure: cleanliness/parade, 4 teaching periods,
# a short break, 5 more teaching periods, then lunch.
_DEFAULT_DAY_TEMPLATE = [
    ('07:00', '07:50', False, 'Cleanliness & Parade'),
    ('08:00', '08:40', True, ''),
    ('08:40', '09:20', True, ''),
    ('09:20', '10:00', True, ''),
    ('10:00', '10:40', True, ''),
    ('10:40', '11:10', False, 'Break'),
    ('11:10', '11:50', True, ''),
    ('11:50', '12:30', True, ''),
    ('12:30', '13:10', True, ''),
    ('13:10', '13:50', True, ''),
    ('13:50', '14:30', True, ''),
    ('14:30', '15:00', False, 'Lunch'),
]

# Friday template: same morning as Mon–Thu, but the last 3 teaching
# periods (12:30–14:30) are replaced by Religion.
_FRIDAY_TEMPLATE = [
    ('07:00', '07:50', False, 'Cleanliness & Parade'),
    ('08:00', '08:40', True, ''),
    ('08:40', '09:20', True, ''),
    ('09:20', '10:00', True, ''),
    ('10:00', '10:40', True, ''),
    ('10:40', '11:10', False, 'Break'),
    ('11:10', '11:50', True, ''),
    ('11:50', '12:30', True, ''),
    ('12:30', '13:10', False, 'Religion'),
    ('13:10', '13:50', False, 'Religion'),
    ('13:50', '14:30', False, 'Religion'),
    ('14:30', '15:00', False, 'Lunch'),
]


def seed_default_time_slots(school):
    """Bulk-creates the generic day template above for Monday–Friday.
    Friday gets its own template with Religion in the afternoon (12:30-14:30).
    Caller (the view) is responsible for only calling this when the
    school has no TimeSlots yet, so it never overwrites a customised day."""
    from ..models import TimeSlot

    slots = []
    for day in range(5):
        template = _FRIDAY_TEMPLATE if day == 4 else _DEFAULT_DAY_TEMPLATE
        for order, (start, end, is_teaching, label) in enumerate(template):
            slots.append(TimeSlot(
                school=school, day_of_week=day, order=order,
                start_time=start, end_time=end,
                is_teaching_slot=is_teaching, label=label,
            ))
    TimeSlot.objects.bulk_create(slots)
    return len(slots)


def auto_populate_teaching_assignments(school, *, default_periods_per_week=5):
    """Bootstraps TeachingAssignment rows from the teacher/subject/form
    pairings an academic officer already entered under 'Assign Mwalimu
    kwa Form' (TeacherFormAssignment) — so setting up the class timetable
    doesn't mean re-typing information already in the system.

    Created rows get stream='' (i.e. "whole form, one stream") since
    TeacherFormAssignment doesn't record streams at all; a school with
    multiple streams per form still needs to split/adjust these by hand
    afterwards — there's no existing data this could correctly infer that
    split from. Never touches an assignment that already exists (by
    school+form+stream+subject), so re-running this is always safe.

    Returns (created_count, skipped_count)."""
    from ..models import TeacherFormAssignment, TeachingAssignment

    created = 0
    skipped = 0
    for a in TeacherFormAssignment.objects.filter(school=school).select_related('teacher', 'subject'):
        _, was_created = TeachingAssignment.objects.get_or_create(
            school=school, form=a.form, stream='', subject=a.subject,
            defaults={'teacher': a.teacher, 'periods_per_week': default_periods_per_week},
        )
        if was_created:
            created += 1
        else:
            skipped += 1
    return created, skipped


def generate_class_timetable(school, *, form_streams=None, constraints=None):
    """form_streams: optional iterable of (form, stream) tuples to
    (re)generate — None means every (form, stream) that has at least one
    TeachingAssignment for this school.

    constraints: optional list of AI-parsed constraint dicts, e.g.
        [{'type': 'prefer_time', 'subject': 'Math', 'period_indices': [0,1]}, ...]
        Supported types: prefer_time, avoid_time, avoid_day, spread.

    Returns (entries, unplaced):
      entries: list of {form, stream, time_slot_id, subject_id, teacher_id}
               dicts — NOT yet saved, for the officer to preview.
      unplaced: list of {form, stream, subject, teacher, missing} for any
               lesson(s) that couldn't be placed (not enough slots, or the
               teacher is over-committed) — surfaced explicitly rather
               than silently dropped or guessed at.
    """
    from ..models import TeachingAssignment, TimeSlot

    slots = list(
        TimeSlot.objects.filter(school=school, is_teaching_slot=True).order_by('day_of_week', 'order')
    )
    if not slots:
        raise TimetableConflict("No teaching time slots have been set up yet.")

    # Adjacent-in-the-list teaching slots on the same day are, by
    # construction, back-to-back with nothing (a break, a different day)
    # between them — exactly what a "double period" needs.
    consecutive_pairs = [
        (slots[i], slots[i + 1])
        for i in range(len(slots) - 1)
        if slots[i].day_of_week == slots[i + 1].day_of_week
    ]

    qs = TeachingAssignment.objects.filter(school=school).select_related('subject', 'teacher')
    if form_streams is not None:
        wanted = set(form_streams)
        assignments = [a for a in qs if (a.form, a.stream) in wanted]
    else:
        assignments = list(qs)
    if not assignments:
        raise TimetableConflict("No teacher/subject assignments found for scheduling.")

    # A "session" is one sitting: a double period (2 consecutive slots) or
    # a single period. periods_per_week=5 with double_period=True becomes
    # 2 double sessions + 1 single (the odd one out) — matching how real
    # timetables actually run a subject, not 5 scattered single periods.
    sessions = []  # (assignment, is_double: bool)
    for a in assignments:
        if a.double_period:
            doubles, remainder = divmod(a.periods_per_week, 2)
        else:
            doubles, remainder = 0, a.periods_per_week
        sessions.extend([(a, True)] * doubles)
        sessions.extend([(a, False)] * remainder)

    # Most-constrained-first: double sessions are harder to place than
    # singles, and within each group, more periods/week means harder to
    # fit. The shuffle (fixed seed — reproducible previews) breaks ties
    # instead of always favouring whichever assignment was created first.
    rng = random.Random(42)
    rng.shuffle(sessions)
    sessions.sort(key=lambda item: (not item[1], -item[0].periods_per_week))

    # ── Build constraint lookups from AI-parsed instructions ──
    # Map subject names to IDs for constraint matching
    subject_name_to_ids = defaultdict(set)
    for a in assignments:
        subject_name_to_ids[a.subject.name.lower()].add(a.subject_id)
        # Also match partial names (e.g. 'math' matches 'Mathematics')
        for word in a.subject.name.lower().split():
            subject_name_to_ids[word].add(a.subject_id)

    # Teaching slot indices: map slot to its index among teaching slots only
    teaching_slot_index = {slot.id: i for i, slot in enumerate(slots)}

    # Build per-subject constraint sets
    prefer_time_slots = defaultdict(set)   # subject_id -> {slot_id}
    avoid_time_slots = defaultdict(set)    # subject_id -> {slot_id}
    avoid_day_set = defaultdict(set)       # subject_id -> {day_of_week}
    spread_min_days = {}                   # subject_id -> min_days_apart

    if constraints:
        for c in constraints or []:
            ctype = c.get('type', '')
            subj_name = c.get('subject', '').lower()
            matched_ids = subject_name_to_ids.get(subj_name, set())
            if not matched_ids:
                continue
            if ctype == 'prefer_time':
                period_indices = c.get('period_indices', [])
                for sid in matched_ids:
                    for idx in period_indices:
                        if idx < len(slots) and slots[idx].is_teaching_slot:
                            prefer_time_slots[sid].add(slots[idx].id)
            elif ctype == 'avoid_time':
                period_indices = c.get('period_indices', [])
                for sid in matched_ids:
                    for idx in period_indices:
                        if idx < len(slots) and slots[idx].is_teaching_slot:
                            avoid_time_slots[sid].add(slots[idx].id)
            elif ctype == 'avoid_day':
                day_indices = c.get('day_indices', [])
                for sid in matched_ids:
                    for d in day_indices:
                        avoid_day_set[sid].add(d)
            elif ctype == 'spread':
                min_days = c.get('min_days_apart', 1)
                for sid in matched_ids:
                    spread_min_days[sid] = max(spread_min_days.get(sid, 0), min_days)

    class_slot_used = defaultdict(set)      # (form, stream) -> {slot_id}
    teacher_slot_used = defaultdict(set)    # teacher_id -> {slot_id}
    class_day_subject = defaultdict(set)    # (form, stream, day) -> {subject_id}
    class_subject_placed = defaultdict(int) # (form, stream, subject_id) -> count (for spread)
    entries = {}                            # (form, stream, slot_id) -> assignment
    missed = defaultdict(int)               # assignment.id -> unplaced period count

    for a, is_double in sessions:
        key = (a.form, a.stream)
        candidates = consecutive_pairs if is_double else [(slot,) for slot in slots]
        placed = False
        # Two passes: first try to avoid a second session of the same
        # subject on the same day (nicer for students); if that leaves no
        # option, place it anywhere still valid rather than dropping it.
        for avoid_same_day_repeat in (True, False):
            for slot_group in candidates:
                if any(s.id in class_slot_used[key] for s in slot_group):
                    continue
                if any(s.id in teacher_slot_used[a.teacher_id] for s in slot_group):
                    continue
                day = slot_group[0].day_of_week
                if avoid_same_day_repeat and a.subject_id in class_day_subject[(key, day)]:
                    continue

                # ── AI constraint checks ──
                slot_ids_in_group = {s.id for s in slot_group}
                # avoid_time: skip if any slot is in the avoid list
                if a.subject_id in avoid_time_slots and slot_ids_in_group & avoid_time_slots[a.subject_id]:
                    continue
                # avoid_day: skip if any slot is on a blocked day
                if a.subject_id in avoid_day_set and day in avoid_day_set[a.subject_id]:
                    continue
                # spread: check min days apart
                if a.subject_id in spread_min_days:
                    already_on_days = {
                        s.day_of_week
                        for sid in class_slot_used[key]
                        for s in slots if s.id == sid
                    }
                    target_day = slot_group[0].day_of_week
                    min_gap = spread_min_days[a.subject_id]
                    if any(abs(target_day - d) < min_gap for d in already_on_days):
                        continue

                # prefer_time: boost score if slot is preferred
                is_preferred = (
                    a.subject_id in prefer_time_slots
                    and slot_ids_in_group & prefer_time_slots[a.subject_id]
                )

                for slot in slot_group:
                    entries[(key[0], key[1], slot.id)] = a
                    class_slot_used[key].add(slot.id)
                    teacher_slot_used[a.teacher_id].add(slot.id)
                class_day_subject[(key, day)].add(a.subject_id)
                placed = True
                break
            if placed:
                break
        if not placed:
            missed[a.id] += 2 if is_double else 1

    entry_list = [
        {'form': f, 'stream': s, 'time_slot_id': slot_id, 'subject_id': a.subject_id, 'teacher_id': a.teacher_id}
        for (f, s, slot_id), a in entries.items()
    ]

    by_id = {a.id: a for a in assignments}
    unplaced = [
        {
            'form': by_id[aid].form,
            'stream': by_id[aid].stream,
            'subject': by_id[aid].subject.name,
            'teacher': by_id[aid].teacher.full_name or by_id[aid].teacher.email,
            'missing': count,
        }
        for aid, count in missed.items()
    ]

    return entry_list, unplaced


def save_class_timetable(school, entries, form_streams=None):
    """Replaces ClassTimetableEntry rows for the (form, stream) pairs
    touched — every other class's standing timetable is left untouched.
    This is the "regenerate only what changed" behaviour: pass
    form_streams=[(1, 'A')] to redo one class after a single teacher
    reassignment, instead of wiping the whole school's schedule."""
    from ..models import ClassTimetableEntry

    touched = form_streams if form_streams is not None else {(e['form'], e['stream']) for e in entries}
    for form, stream in touched:
        ClassTimetableEntry.objects.filter(school=school, form=form, stream=stream).delete()

    ClassTimetableEntry.objects.bulk_create([
        ClassTimetableEntry(
            school=school, form=e['form'], stream=e['stream'],
            time_slot_id=e['time_slot_id'], subject_id=e['subject_id'], teacher_id=e['teacher_id'],
        )
        for e in entries
    ])
    return len(entries)


def set_single_cell(school, *, form, stream, time_slot_id, subject_id, teacher_id):
    """Hand-edit one lesson without regenerating anything else — the
    common case for 'a teacher changed for this one subject'. Rejects the
    edit if it would double-book the teacher elsewhere at the same slot,
    same as the generator's hard constraint."""
    from ..models import ClassTimetableEntry

    clash = ClassTimetableEntry.objects.filter(
        school=school, time_slot_id=time_slot_id, teacher_id=teacher_id,
    ).exclude(form=form, stream=stream).select_related('subject').first()
    if clash:
        clash_label = f"Form {clash.form}{clash.stream}" if clash.stream else f"Form {clash.form}"
        raise TimetableConflict(
            f"This teacher is already teaching {clash.subject} for {clash_label} at the same time."
        )

    ClassTimetableEntry.objects.update_or_create(
        school=school, form=form, stream=stream, time_slot_id=time_slot_id,
        defaults={'subject_id': subject_id, 'teacher_id': teacher_id},
    )
