"""
AUTO-LESSON ENGINE
=================
Inazalisha Lesson Plans kiotomatiki kutoka Scheme of Work ya mwalimu —
bila AI (template), kwa kuwa maudhui yote (competences, activities,
methods, resources, assessment) yamo tayari kwenye scheme.

Mtiririko:
  1. Scheme ina start_date, total_weeks, breaks, na scheme_data (rows kwa kila wiki).
  2. Tunahesabu "teaching Mondays" — Jumatatu ya kila wiki ya kufundisha,
     tukiruka wiki zilizo ndani ya breaks (mapumziko/mitihani).
  3. Kila row ya scheme (wiki N) inazalisha masomo ya siku za kufundisha
     za wiki hiyo (Jumatatu—Ijumaa, kikomo cha periods_per_week).
  4. auto_key ("scheme:wN:pP") inahakikisha somo halitokeni mara mbili.
  5. Tarehe inajazwa kutoka kalenda; attendance (idadi ya wanafunzi)
     na marekebisho mengine mwalimu anajaza kwenye ukurasa wa kuhariri.
"""
import logging
import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

EAT = ZoneInfo('Africa/Dar_es_Salaam')

MAX_TEACHING_DAYS = 5  # Jumatatu → Ijumaa


def today_eat():
    return timezone_now_eat().date()


def timezone_now_eat():
    from django.utils import timezone as dj_tz
    return dj_tz.localtime(dj_tz.now(), EAT)


def monday_of(d):
    """Jumatatu ya wiki ambayo tarehe `d` ipo."""
    return d - timedelta(days=d.weekday())


def _parse_date(v):
    if v is None:
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime_strptime(s[:len(fmt) + 2], fmt)
        except ValueError:
            continue
    # ISO fallback
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def datetime_strptime(s, fmt):
    from datetime import datetime as _dt
    return _dt.strptime(s, fmt).date()


def _row_get(row, *names, default=''):
    """Tafuta key kwenye row ya scheme bila kujali herufi kubwa/nafasi."""
    norm = {}
    for k, v in (row or {}).items():
        norm[str(k).strip().lower().replace('_', ' ')] = v
    for name in names:
        key = name.strip().lower()
        if key in norm and norm[key] not in (None, ''):
            return norm[key]
    return default


def _split_list(value, sep=','):
    """Gawa maandishi kuwa orodha (comma/semicolon/mstari mpya)."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if not value:
        return []
    out = []
    for chunk in str(value).replace('\n', sep).replace(';', sep).split(sep):
        chunk = chunk.strip().rstrip('.')
        if chunk:
            out.append(chunk)
    return out


def parse_breaks(scheme):
    """Breaks za scheme kuwa orodha ya (start, end) — defensive."""
    out = []
    for b in (scheme.breaks or []):
        if isinstance(b, dict):
            s = _parse_date(b.get('start') or b.get('from'))
            e = _parse_date(b.get('end') or b.get('to'))
            if s and e:
                out.append((s, e))
        elif isinstance(b, (list, tuple)) and len(b) >= 2:
            s = _parse_date(b[0])
            e = _parse_date(b[1])
            if s and e:
                out.append((s, e))
    return out


def _in_breaks(d, breaks):
    return any(s <= d <= e for (s, e) in breaks)


def compute_teaching_weeks(scheme, today=None):
    """Rudisha orodha ya (week_no, monday) ya wiki za kufundisha.

    Row ya kwanza ya scheme_data = wiki ya kwanza ya kufundisha (baada ya
    kuruka wiki za breaks). week_no ni 1-based index ya row.
    """
    today = today or today_eat()
    if not scheme.scheme_data:
        return []
    n_rows = len(scheme.scheme_data)
    n_weeks = min(int(scheme.total_weeks or n_rows), n_rows)
    if n_weeks <= 0:
        return []

    if scheme.start_date:
        anchor = monday_of(scheme.start_date)
    else:
        # Fallback: wiki ambayo scheme iliundwa ni mwanzo wa kufundisha
        anchor = monday_of(scheme.created_at.date())

    breaks = parse_breaks(scheme)

    weeks = []
    cursor = anchor
    guard = 0
    while len(weeks) < n_weeks and guard < 200:
        guard += 1
        if not _in_breaks(cursor, breaks):
            weeks.append((len(weeks) + 1, cursor))
        cursor += timedelta(days=7)
    return weeks


def current_week_number(weeks, today=None):
    """Namba ya wiki ya sasa (1-based) kati ya teaching weeks; 0 kama bado,
    -1 kama muhula umekwisha."""
    today = today or today_eat()
    if not weeks:
        return -1
    for i, (week_no, monday) in enumerate(weeks):
        next_monday = weeks[i + 1][1] if i + 1 < len(weeks) else monday + timedelta(days=7)
        if monday <= today < next_monday:
            return week_no
    if today < weeks[0][1]:
        return 0  # bado haijaanza — wiki ya kwanza ndiyo ijayo
    return -1  # imekwisha


def _split_duration(duration):
    """Gawa dakika kwa IDDR: I 15% / D 40% / D 30% / R 15% (min sensible)."""
    try:
        total = int(duration)
    except (TypeError, ValueError):
        total = 40
    intro = max(5, round(total * 0.15))
    realise = max(5, round(total * 0.15))
    develop = max(10, round(total * 0.40))
    design = max(8, total - intro - develop - realise)
    return intro, develop, design, realise


def lesson_fields_from_scheme_row(scheme, row, prev_row=None):
    """Jenga fields za LessonPlan kutoka row moja ya scheme (template, bila AI)."""
    subject = scheme.subject
    main_competence = _row_get(row, 'main competence', 'main competences')
    specific_competences = _row_get(row, 'specific competences', 'specific competence')
    main_activity = _row_get(row, 'main learning activities', 'main learning activity')
    specific_activities = _row_get(row, 'specific learning activities', 'specific learning activity')
    methods = _split_list(_row_get(row, 'teaching and learning methods', 'teaching methods'))
    resources = _split_list(_row_get(row, 'teaching and learning resources', 'teaching resources'))
    assessment = _row_get(row, 'assessment tools', 'assessment')

    objectives = _split_list(specific_activities, sep='\n') or _split_list(specific_competences)
    objectives = [re.sub(r'^\d+[\.\)]\s*', '', o) for o in objectives]

    # Topic: shughuli kuu ya wiki (mwalimu anaweza kuhariri baadaye)
    topic = str(main_activity or specific_competences or f"{subject.name} — Wiki hiyo").strip()
    if len(topic) > 180:
        topic = topic[:177] + '…'
    subtopic = (objectives[0] if objectives else '')[:180]

    prev_main = _row_get(prev_row, 'main learning activities', 'main learning activity')
    previous_knowledge = (
        f"Wanafunzi wameshajifunza: {prev_main}" if prev_main
        else "Maarifa ya msingi yanayohitajika kutoka masomo yaliyotangulia na maisha ya kila siku."
    )

    intro, develop, design, realise = _split_duration(40)
    methods_txt = ', '.join(methods[:3]) or 'Group discussion, Q&A'
    resources_txt = ', '.join(resources[:4]) or 'Textbook, Chalkboard, Charts'
    assess_txt = assessment or 'Oral questions, Quiz'

    lesson_development = [
        {
            'time': f'{intro} min',
            'stage': 'Introduction (I)',
            'methods': 'Q&A, Brainstorming',
            'teacher_activities': f"Kuamsha maarifa ya awali kwa maswali yanayohusiana na {topic}.",
            'student_activities': 'Kujibu maswali, kushiriki mjadala na kueleza waliyojifunza awali.',
            'assessment_criteria': 'Ushiriki hai na majibu sahihi ya maswali ya utangulizi.',
        },
        {
            'time': f'{develop} min',
            'stage': 'Competence Development (D)',
            'methods': methods_txt,
            'teacher_activities': f"Kuongoza wanafunzi kwenye shughuri kuu: {main_activity or topic}.",
            'student_activities': 'Kusoma, kujadili kwenye makundi, kuchunguza na kuwasilisha matokeo ya kazi zao.',
            'assessment_criteria': 'Usahihi wa ufahamu wa maudhui na ushiriki wa kikundi.',
        },
        {
            'time': f'{design} min',
            'stage': 'Design (D)',
            'methods': 'Problem solving, Role play',
            'teacher_activities': 'Kuongoza wanafunzi kutumia maarifa katika hali halisi (real-life contexts).',
            'student_activities': 'Kutatua matatizo halisi, kuunda modeli/mifano na kuwasilisha mbele ya darasa.',
            'assessment_criteria': 'Matumizi sahihi ya maarifa katika hali mpya na ubunifu.',
        },
        {
            'time': f'{realise} min',
            'stage': 'Realisation (R)',
            'methods': assess_txt,
            'teacher_activities': 'Kupima kufikia malengo kwa kutumia tathmini (quiz, portfolio, peer assessment).',
            'student_activities': 'Kujibu tathmini, kujithibitishia na kupima wenzao.',
            'assessment_criteria': 'Kufikia malengo ya kujifunza ya somo.',
        },
    ]

    return {
        'topic': topic,
        'subtopic': subtopic,
        'main_competence': str(main_competence),
        'specific_competence': str(specific_competences),
        'previous_knowledge': previous_knowledge,
        'learning_objectives': objectives[:6],
        'teaching_methods': (methods or ['Group discussion', 'Q&A', 'Brainstorming'])[:6],
        'teaching_resources': (resources or ['Textbook', 'Chalkboard', 'Charts'])[:6],
        'lesson_development': lesson_development,
        'assessment_tools': str(assess_txt),
    }


def generate_lessons_for_student(student, weeks_ahead=2, today=None):
    """Zalisha masomo ya wiki ya sasa + zilizotangulia mbele kwa mwanafunzi.

    Inarudisha dict ya muhtasari. Idempotent — auto_key inazuia rudufu.
    """
    from .models import LessonPlan, SchemeOfWork

    today = today or today_eat()
    summary = {
        'student': student.full_name,
        'schemes_seen': 0,
        'lessons_created': 0,
        'lessons_existing': 0,
        'schemes_skipped': [],
    }

    schemes = (SchemeOfWork.objects
               .filter(student=student)
               .exclude(scheme_data__isnull=True)
               .order_by('created_at'))
    school = student.selected_school

    for scheme in schemes:
        if not scheme.scheme_data:
            continue
        summary['schemes_seen'] += 1

        weeks = compute_teaching_weeks(scheme, today=today)
        if not weeks:
            summary['schemes_skipped'].append(f"{scheme}: hakuna wiki")
            continue
        current = current_week_number(weeks, today=today)
        if current == -1:
            summary['schemes_skipped'].append(f"{scheme}: muhula umekwisha")
            continue
        if current == 0:
            current = weeks[0][0]  # bado haijaanza — anza wiki ya 1

        # Wiki za kuzalisha: ya sasa + zilizotangulia mbele (idempotent)
        target = [w for w in weeks if current <= w[0] < current + weeks_ahead]
        if not target:
            summary['schemes_skipped'].append(f"{scheme}: hakuna wiki zijazo")
            continue

        n_days = min(int(scheme.periods_per_week or 1), MAX_TEACHING_DAYS)
        for week_no, monday in target:
            row = scheme.scheme_data[week_no - 1] if week_no - 1 < len(scheme.scheme_data) else None
            if row is None:
                continue
            prev_row = scheme.scheme_data[week_no - 2] if week_no >= 2 else None
            fields = lesson_fields_from_scheme_row(scheme, row, prev_row=prev_row)

            for p in range(1, n_days + 1):
                auto_key = f"s{scheme.id}:w{week_no}:p{p}"
                if LessonPlan.objects.filter(auto_key=auto_key).exists():
                    summary['lessons_existing'] += 1
                    continue
                lesson_date = monday + timedelta(days=p - 1)
                LessonPlan.objects.create(
                    student=student,
                    school=scheme.school or school,
                    subject=scheme.subject,
                    scheme=scheme,
                    education_level=scheme.education_level,
                    class_name=scheme.class_name,
                    term=scheme.term,
                    year=scheme.year,
                    topic=fields['topic'],
                    subtopic=fields['subtopic'],
                    date=lesson_date,
                    duration=40,
                    teacher_name=scheme.teacher_name or student.full_name,
                    main_competence=fields['main_competence'],
                    specific_competence=fields['specific_competence'],
                    previous_knowledge=fields['previous_knowledge'],
                    learning_objectives=fields['learning_objectives'],
                    teaching_methods=fields['teaching_methods'],
                    teaching_resources=fields['teaching_resources'],
                    lesson_development=fields['lesson_development'],
                    remarks='',
                    generated_by_ai=False,
                    ai_model_used='scheme-template',
                    scheme_week=week_no,
                    week_start_date=monday,
                    period_index=p,
                    status='auto',
                    source='scheme_template',
                    auto_key=auto_key,
                )
                summary['lessons_created'] += 1

    return summary


def generate_for_all_students(weeks_ahead=2, today=None):
    """Kwa scheduler: endesha kwa wanafunzi wote wenye schemes zenye data
    (rejected wameondolewa — scheme iliyopo inaonyesha mwanafunzi hai)."""
    from .models import StudentTeacher

    students = (StudentTeacher.objects
                .exclude(approval_status='rejected')
                .filter(schemes__scheme_data__isnull=False)
                .distinct())
    total_created = 0
    errors = []
    for student in students:
        try:
            s = generate_lessons_for_student(student, weeks_ahead=weeks_ahead, today=today)
            total_created += s['lessons_created']
        except Exception as exc:  # noqa: BLE001
            logger.exception("auto-lesson failed for %s", student)
            errors.append(f"{student.full_name}: {exc}")
    return {'students': students.count(), 'lessons_created': total_created, 'errors': errors}
