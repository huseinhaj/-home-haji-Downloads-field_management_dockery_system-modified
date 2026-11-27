"""Backend contract for the redesigned curriculum screens.

Implements section 3 ("Backend contract the new screens expect") of the
frontend-redesign handover: the page views, the context the new templates
use, the JSON helpers and the document editors.  Generation and PDF
rendering are delegated to the existing generator/PDF pipeline in
``curriculum.views`` so there is exactly one implementation of each.
"""
import json
import re
from datetime import date, timedelta
from types import SimpleNamespace

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import views as V

# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

MONTHS = ['Januari', 'Februari', 'Machi', 'Aprili', 'Mei', 'Juni', 'Julai',
          'Agosti', 'Septemba', 'Oktoba', 'Novemba', 'Desemba']
MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
             'August', 'September', 'October', 'November', 'December']

HOLIDAY_PRESETS = ['Mtihani wa Kati', 'Mtihani wa Muhula', 'Pasaka', 'Krismasi',
                   'Eid el-Fitr', 'Eid el-Adha', 'Maulid']

LEVEL_CHOICES = [
    ('primary', 'Shule ya Msingi'),
    ('olevel', 'Sekondari · O-Level'),
    ('alevel', 'Sekondari · A-Level'),
]

# Our short level code -> the value the AI pipeline stores/expects
EDU_LEVEL = {
    'primary': 'Primary School',
    'olevel': 'Ordinary Level',
    'alevel': 'Advanced Level',
}
SUBJECT_LEVEL = {'primary': 'primary', 'olevel': 'secondary', 'alevel': 'advanced'}

CLASSES = {
    'primary': ['Darasa la %d' % n for n in range(1, 8)],
    'olevel': ['Form 1', 'Form 2', 'Form 3', 'Form 4'],
    'alevel': ['Form 5', 'Form 6'],
}


class _JsonRequest:
    """A request whose body is JSON, so the existing AJAX views can be reused."""

    def __init__(self, request, payload):
        self._request = request
        self.body = json.dumps(payload).encode('utf-8')
        self.method = 'POST'

    def __getattr__(self, name):
        return getattr(self._request, name)


def _call(view, request, payload):
    return view(_JsonRequest(request, payload))


def _teacher(request):
    return V.get_tlm_teacher(request)


def _teacher_ctx(teacher):
    """The exact ``tlm_teacher`` shape the new screens read (Hati 1 §3).

    The templates compare ``tlm_teacher.subject`` with a subject name and print
    ``tlm_teacher.boys`` / ``tlm_teacher.girls``, so this exposes strings and
    numbers instead of the model's FK objects and ``total_*`` field names.
    """
    if teacher is None:
        return None
    return SimpleNamespace(
        full_name=getattr(teacher, 'full_name', '') or '',
        school_name=getattr(teacher, 'school_name', '') or '',
        initials=getattr(teacher, 'initials', '') or '',
        level=_teacher_level(teacher),
        class_name=getattr(teacher, 'class_name', '') or '',
        stream=getattr(teacher, 'stream', '') or '',
        subject=(teacher.subject.name if getattr(teacher, 'subject_id', None) else ''),
        boys=getattr(teacher, 'total_boys', 0) or 0,
        girls=getattr(teacher, 'total_girls', 0) or 0,
    )


def _teacher_level(teacher):
    level = getattr(teacher, 'level', '') or ''
    if level in CLASSES:
        return level
    name = getattr(getattr(teacher, 'school', None), 'level', '') or ''
    name = name.lower()
    if 'primary' in name or 'msingi' in name:
        return 'primary'
    if 'advanced' in name or 'a-level' in name or 'a level' in name:
        return 'alevel'
    return 'olevel'


def _class_choices(level):
    return CLASSES.get(level, CLASSES['olevel'])


def _subject_choices(level):
    """Subject NAMES for a level — the new screens and api_subjects expect
    ``["Biology", …]``, not the model rows the cached helper returns."""
    lvl = SUBJECT_LEVEL.get(level, level)
    names = []
    try:
        for row in (V._subjects_for_level(lvl) or []):
            name = row.get('name') if isinstance(row, dict) else getattr(row, 'name', None)
            if name:
                names.append(name)
    except Exception:
        names = []
    if names:
        return sorted(set(names), key=str.lower)
    try:
        from field_app.models import Subject
        return sorted(set(Subject.objects.filter(level=lvl).values_list('name', flat=True)),
                      key=str.lower)
    except Exception:
        return []


def _topic_choices(teacher, class_name=''):
    try:
        from .models import SubjectTopic
        qs = SubjectTopic.objects.all()
        if teacher is not None and getattr(teacher, 'subject_id', None):
            qs = qs.filter(subject_id=teacher.subject_id)
        if class_name:
            qs = qs.filter(class_name__iexact=class_name)
        return list(qs.order_by('order', 'name').values_list('name', flat=True)[:400])
    except Exception:
        return []


def _subtopic_choices(teacher, topic_name='', class_name=''):
    try:
        from .models import SubjectTopic, TopicSubtopic
        qs = SubjectTopic.objects.all()
        if teacher is not None and getattr(teacher, 'subject_id', None):
            qs = qs.filter(subject_id=teacher.subject_id)
        if class_name:
            qs = qs.filter(class_name__iexact=class_name)
        topic = qs.filter(name__iexact=topic_name).first() if topic_name else qs.first()
        if not topic:
            return []
        return list(TopicSubtopic.objects.filter(topic=topic).order_by('order', 'name')
                    .values_list('name', flat=True)[:400])
    except Exception:
        return []


def _term_starts():
    today = timezone.now().date()
    first = date(today.year, 1, 12)
    second = date(today.year, 7, 6)
    return json.dumps({'1': first.isoformat(), '2': second.isoformat()})


def _stats():
    teachers, schemes, lessons, logbooks = 0, 0, 0, 0
    try:
        from .models import TLMTeacher
        teachers = TLMTeacher.objects.count()
    except Exception:
        pass
    try:
        from field_app.models import SchemeOfWork
        schemes = SchemeOfWork.objects.count()
    except Exception:
        pass
    try:
        from field_app.models import LessonPlan
        lessons = LessonPlan.objects.count()
    except Exception:
        pass
    try:
        from .models import TLMTopicLogbook
        logbooks = TLMTopicLogbook.objects.count()
    except Exception:
        pass
    if lessons >= 1000:
        lesson_k = '%s<small>K</small>' % (round(lessons / 1000.0, 1))
    else:
        lesson_k = str(lessons)
    return {'teachers': teachers, 'lesson_plans_k': lesson_k,
            'schemes': schemes, 'logbooks': logbooks}


def _coat_of_arms():
    """The coat of arms that belongs on the official PDFs (Hati 1 §1)."""
    from django.templatetags.static import static
    return static('images/tz_coat_of_arms.png')


def page_context(request, teacher=None):
    """Everything the redesigned tool pages read from the view."""
    teacher = teacher if teacher is not None else _teacher(request)
    level = _teacher_level(teacher) if teacher else 'olevel'
    class_name = getattr(teacher, 'class_name', '') or ''
    topic = (request.POST.get('topic') or request.GET.get('topic') or ''
             if request is not None else '')
    my_classes = _class_choices(level)
    if class_name:
        my_classes = [class_name] + [c for c in my_classes if c != class_name]
    return {
        'tlm_teacher': _teacher_ctx(teacher),
        'level_choices': LEVEL_CHOICES,
        'class_choices': _class_choices(level),
        'subject_choices': _subject_choices(level),
        'topic_choices': _topic_choices(teacher, class_name),
        'subtopic_choices': _subtopic_choices(teacher, topic, class_name),
        'holiday_presets': HOLIDAY_PRESETS,
        'my_classes': my_classes,
        'saved_count': _saved_count(teacher),
        'term_starts_json': _term_starts(),
        'coat_of_arms_url': _coat_of_arms(),
    }


def _saved_count(teacher):
    if teacher is None:
        return 0
    try:
        from .models import TLMTopicLogbook
        return TLMTopicLogbook.objects.filter(teacher=teacher).count()
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def home(request):
    """Nyumbani — also the landing page for guests (no tlm_teacher → Jisajili)."""
    teacher = _teacher(request)
    return render(request, 'curriculum/dashboard.html', {
        'tlm_teacher': _teacher_ctx(teacher),
        'stats': _stats(),
    })


def scheme_page(request):
    teacher = _teacher(request)
    if not teacher:
        return redirect('%s?next=%s' % (reverse('curriculum:teacher_register'),
                                        reverse('curriculum:generate_scheme')))
    return render(request, 'curriculum/generate_scheme.html', page_context(request, teacher))


def lesson_page(request):
    teacher = _teacher(request)
    if not teacher:
        return redirect('%s?next=%s' % (reverse('curriculum:teacher_register'),
                                        reverse('curriculum:lesson_plan')))
    return render(request, 'curriculum/lesson_plan.html', page_context(request, teacher))


def hariri(request):
    """Hariri — ?tab=scheme|lesson|logbook with counts and newest-first items."""
    tab = request.GET.get('tab') or 'scheme'
    if tab not in ('scheme', 'lesson', 'logbook'):
        tab = 'scheme'
    items, counts = [], {'scheme': 0, 'lesson': 0, 'logbook': 0}

    if tab == 'scheme':
        try:
            from field_app.models import SchemeOfWork
            qs = SchemeOfWork.objects.select_related('subject').order_by('-updated_at')
            counts['scheme'] = qs.count()
            items = [{'id': s.id, 'subject': s.subject.name if s.subject else '',
                      'topic': '', 'class_label': s.class_name or '',
                      'created': s.updated_at} for s in qs[:50]]
        except Exception:
            pass
        try:
            from field_app.models import SchemeOfWork
            counts['lesson'] = LessonPlan_count()
        except Exception:
            pass
    elif tab == 'lesson':
        try:
            from field_app.models import LessonPlan
            qs = LessonPlan.objects.select_related('subject').order_by('-created_at')
            counts['lesson'] = qs.count()
            items = [{'id': l.id, 'subject': l.subject.name if l.subject else '',
                      'topic': l.topic or '', 'class_label': l.class_name or '',
                      'created': l.created_at} for l in qs[:50]]
        except Exception:
            pass
    else:
        try:
            from .models import TLMTopicLogbook
            qs = TLMTopicLogbook.objects.select_related('subject').order_by('-date_ended')
            counts['logbook'] = qs.count()
            items = [{'id': e.id, 'subject': e.subject.name if e.subject else '',
                      'topic': e.main_topic or '', 'class_label': e.class_name or '',
                      'created': e.date_ended} for e in qs[:50]]
        except Exception:
            pass

    if tab != 'scheme':
        try:
            from field_app.models import SchemeOfWork
            counts['scheme'] = SchemeOfWork.objects.count()
        except Exception:
            pass
    if tab != 'lesson':
        counts['lesson'] = LessonPlan_count()
    if tab != 'logbook':
        try:
            from .models import TLMTopicLogbook
            counts['logbook'] = TLMTopicLogbook.objects.count()
        except Exception:
            pass

    return render(request, 'curriculum/library.html', {
        'tlm_teacher': _teacher_ctx(_teacher(request)), 'tab': tab,
        'counts': counts, 'items': items,
    })


def LessonPlan_count():
    try:
        from field_app.models import LessonPlan
        return LessonPlan.objects.count()
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Hariri editors
# ---------------------------------------------------------------------------

_ROW_KEYS = {
    'week': ('Week', 'WEEK', 'Wiki', 'WIKI'),
    'periods': ('Number of Periods', 'No. of Periods', 'VIPINDI', 'Vipindi'),
    'month': ('Month', 'MONTH', 'Mwezi', 'MWEZI'),
    'main_competence': ('Main Competence', 'UMAHIRI MKUU', 'Umahiri Mkuu'),
    'specific_competence': ('Specific Competences', 'Specific Competence',
                            'UMAHIRI MAHUSUSI', 'Umahiri Mahususi'),
    'main_activity': ('Main Learning Activities', 'SHUGHULI KUU ZA UJIFUNZAJI',
                      'Shughuli Kuu'),
    'specific_activity': ('Specific Learning Activities', 'SHUGHULI NDOGO ZA UJIFUNZAJI',
                          'Shughuli Ndogo'),
    'methods': ('Teaching and Learning Methods', 'MBINU ZA UJIFUNZAJI NA UFUNDISHAJI',
                'Mbinu za Ufundishaji'),
    'resources': ('Teaching and Learning Resources', 'ZANA ZA UJIFUNZAJI NA UFUNDISHAJI',
                  'Zana za Kufundishia'),
    'assessment': ('Assessment Tools', 'ZANA ZA UPIMAJI', 'Zana za Upimaji'),
    'references': ('References', 'REJEA', 'Rejea', 'Marejeo'),
    'remarks': ('Remarks', 'MAONI', 'Maoni'),
}


def _row_get(row, field, default=''):
    for key in _ROW_KEYS.get(field, ()):
        if key in row and row[key] not in (None, ''):
            return row[key]
    return default


def _scheme_months(data):
    """Group scheme rows into months, keeping the document order."""
    months = []
    index = 0
    for row in data or []:
        if not isinstance(row, dict):
            continue
        name = str(_row_get(row, 'month', '') or '').strip()
        if not name:
            name = months[-1]['name'] if months else MONTHS[0]
        if not months or months[-1]['name'] != name:
            months.append({'name': name, 'weeks': []})
        weeks = months[-1]['weeks']
        weeks.append({
            'idx': index,
            'week': _row_get(row, 'week'),
            'periods': _row_get(row, 'periods'),
            'main_competence': _row_get(row, 'main_competence'),
            'specific_competence': _row_get(row, 'specific_competence'),
            'main_activity': _row_get(row, 'main_activity'),
            'specific_activity': _row_get(row, 'specific_activity'),
            'methods': _row_get(row, 'methods'),
            'resources': _row_get(row, 'resources'),
            'assessment': _row_get(row, 'assessment'),
            'references': _row_get(row, 'references'),
            'remarks': _row_get(row, 'remarks'),
        })
        index += 1
    return months


_LESSON_STAGE_KEYS = {
    'name': ('name', 'stage', 'hatua', 'title'),
    'minutes': ('minutes', 'time', 'muda', 'duration'),
    'teaching': ('teaching', 'teacher_activity', 'shughuli_za_ufundishaji'),
    'learning': ('learning', 'student_activity', 'shughuli_za_ujifunzaji'),
    'assessment': ('assessment', 'criteria', 'vigezo'),
}


def _stage_get(stage, field, default=''):
    for key in _LESSON_STAGE_KEYS[field]:
        if isinstance(stage, dict) and stage.get(key) not in (None, ''):
            return stage.get(key)
    return default


def _lesson_stages(lp):
    stages = []
    for stage in (lp.lesson_development or []):
        stages.append({
            'name': _stage_get(stage, 'name'),
            'minutes': _stage_get(stage, 'minutes'),
            'teaching': _stage_get(stage, 'teaching'),
            'learning': _stage_get(stage, 'learning'),
            'assessment': _stage_get(stage, 'assessment'),
        })
    return stages


def edit_doc(request, kind, pk):
    """GET the editor / POST the edited document ("Imehifadhiwa")."""
    if kind == 'scheme':
        return _edit_scheme(request, pk)
    return _edit_lesson(request, pk)


def _edit_scheme(request, pk):
    from field_app.models import SchemeOfWork
    obj = SchemeOfWork.objects.filter(pk=pk).select_related('subject', 'school').first()
    if obj is None:
        return redirect('%s?tab=scheme' % reverse('curriculum:library'))

    if request.method == 'POST':
        rows = list(obj.scheme_data or [])
        pattern = re.compile(r'^w(\d+)_(\w+)$')
        updates = {}
        for key, value in request.POST.items():
            match = pattern.match(key)
            if match:
                updates.setdefault(int(match.group(1)), {})[match.group(2)] = value
        for idx, fields in updates.items():
            if idx >= len(rows) or not isinstance(rows[idx], dict):
                continue
            row = rows[idx]
            for field, value in fields.items():
                for target in _ROW_KEYS.get(field, ()):
                    if target in row:
                        row[target] = value
                        break
                else:
                    row[{'week': 'Week', 'periods': 'Number of Periods',
                         'main_competence': 'Main Competence',
                         'specific_competence': 'Specific Competences',
                         'main_activity': 'Main Learning Activities',
                         'specific_activity': 'Specific Learning Activities',
                         'methods': 'Teaching and Learning Methods',
                         'resources': 'Teaching and Learning Resources',
                         'assessment': 'Assessment Tools',
                         'references': 'References',
                         'remarks': 'Remarks'}.get(field, field)] = value
        obj.scheme_data = rows
        if request.POST.get('term'):
            obj.term = request.POST['term']
        for attr in ('year', 'weeks', 'periods'):
            value = request.POST.get(attr)
            if value:
                target = {'weeks': 'total_weeks', 'periods': 'periods_per_week'}.get(attr, attr)
                try:
                    setattr(obj, target, int(value))
                except (TypeError, ValueError):
                    pass
        obj.save()
        messages.success(request, 'Imehifadhiwa')
        return redirect('%s?tab=scheme' % reverse('curriculum:library'))

    doc = SimpleNamespace(
        id=obj.id,
        subject=obj.subject.name if obj.subject else '',
        class_label=obj.class_name or '',
        created=obj.updated_at,
        term=obj.term,
        year=obj.year,
        weeks=obj.total_weeks,
        periods=obj.periods_per_week,
        months=_scheme_months(obj.scheme_data),
    )
    return render(request, 'curriculum/edit_scheme.html',
                  {'doc': doc, 'tlm_teacher': _teacher_ctx(_teacher(request))})


def _edit_lesson(request, pk):
    from field_app.models import LessonPlan
    lp = LessonPlan.objects.filter(pk=pk).select_related('subject', 'school').first()
    if lp is None:
        return redirect('%s?tab=lesson' % reverse('curriculum:library'))

    if request.method == 'POST':
        p = request.POST
        lp.topic = p.get('topic', lp.topic)
        lp.subtopic = p.get('subtopic', lp.subtopic)
        lp.duration = _int(p.get('duration'), lp.duration)
        lp.present_boys = _int(p.get('present_boys'), lp.present_boys)
        lp.present_girls = _int(p.get('present_girls'), lp.present_girls)
        lp.present_students = (lp.present_boys or 0) + (lp.present_girls or 0)
        if lp.total_boys is not None and lp.present_boys is not None:
            lp.total_students = (lp.total_boys or 0) + (lp.total_girls or 0)
        for field in ('main_competence', 'specific_competence', 'remarks'):
            if field in p:
                setattr(lp, field, p[field])
        if 'lesson_date' in p and p['lesson_date']:
            try:
                lp.date = date.fromisoformat(p['lesson_date'])
            except ValueError:
                pass
        stages = []
        index = 0
        while ('stage_%d_minutes' % index) in p:
            stages.append({
                'name': p.get('stage_%d_name' % index, ''),
                'minutes': p.get('stage_%d_minutes' % index, ''),
                'teaching': p.get('stage_%d_teaching' % index, ''),
                'learning': p.get('stage_%d_learning' % index, ''),
                'assessment': p.get('stage_%d_assessment' % index, ''),
            })
            index += 1
        if stages:
            lp.lesson_development = stages
        lp.save()
        messages.success(request, 'Imehifadhiwa')
        return redirect('%s?tab=lesson' % reverse('curriculum:library'))

    doc = SimpleNamespace(
        id=lp.id,
        subject=lp.subject.name if lp.subject else '',
        class_label=lp.class_name or '',
        lesson_date=lp.date,
        topic=lp.topic or '',
        subtopic=lp.subtopic or '',
        duration=lp.duration,
        boys=lp.total_boys or 0,
        girls=lp.total_girls or 0,
        present_boys=lp.present_boys if lp.present_boys is not None else '',
        present_girls=lp.present_girls if lp.present_girls is not None else '',
        main_competence=lp.main_competence or '',
        specific_competence=lp.specific_competence or '',
        main_activity='',
        specific_activity=lp.previous_knowledge or '',
        resources=', '.join(lp.teaching_resources or []),
        references='',
        remarks=lp.remarks or '',
        stages=_lesson_stages(lp),
    )
    return render(request, 'curriculum/edit_lesson.html',
                  {'doc': doc, 'tlm_teacher': _teacher_ctx(_teacher(request))})


def _int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# PDFs (inline so the phone opens them in its viewer)
# ---------------------------------------------------------------------------

def doc_pdf(request, kind, pk):
    if kind == 'scheme':
        from field_app.models import SchemeOfWork
        obj = SchemeOfWork.objects.filter(pk=pk).select_related('subject', 'school').first()
        if obj is None:
            return HttpResponse('Hati haipatikani', status=404)
        payload = {
            'scheme_data': obj.scheme_data or [],
            'subject': obj.subject.name if obj.subject else '',
            'class_name': obj.class_name or '',
            'term': obj.term,
            'year': obj.year,
            'syllabus': obj.syllabus,
            'teacher_name': obj.teacher_name,
            'school_name': obj.school.name if obj.school else '',
            'total_weeks': obj.total_weeks,
            'education_level': obj.education_level,
            'format': obj.format,
        }
        response = V.download_scheme_pdf(_JsonRequest(request, payload))
    else:
        from field_app.models import LessonPlan
        lp = LessonPlan.objects.filter(pk=pk).select_related('subject', 'school').first()
        if lp is None:
            return HttpResponse('Hati haipatikani', status=404)
        lesson_data, form_data = V._lp_to_dicts(lp)
        # The saved row may predate the teacher fields — the official PDF still
        # has to print the teacher's name on the cover.
        if not form_data.get('teacher_name'):
            teacher = _teacher(request)
            form_data['teacher_name'] = getattr(teacher, 'full_name', '') or ''
        response = V.download_lesson_plan_pdf(
            _JsonRequest(request, {'lesson_data': lesson_data, 'form_data': form_data}))

    if getattr(response, 'status_code', 200) != 200:
        return response
    response['Content-Type'] = 'application/pdf'
    response['Content-Disposition'] = 'inline; filename="TLM-%s-%s.pdf"' % (kind, pk)
    return response


def logbook_download(request):
    """?month=1..12 (optional) → the official Subject Log-Book PDF."""
    month = request.GET.get('month')
    period = 'month' if month else 'all'
    response = V.download_logbook_pdf(request, period)
    if getattr(response, 'status_code', 200) == 200:
        response['Content-Type'] = 'application/pdf'
        response['Content-Disposition'] = 'inline; filename="logbook.pdf"'
    return response


# ---------------------------------------------------------------------------
# Logbook page (one topic per save; term/month/week derived on the server)
# ---------------------------------------------------------------------------

def logbook_page(request):
    teacher = _teacher(request)
    if not teacher:
        return redirect('%s?next=%s' % (reverse('curriculum:teacher_register'),
                                        reverse('curriculum:logbook')))
    if request.method == 'POST':
        return _save_logbook(request, teacher)
    return render(request, 'curriculum/logbook.html', page_context(request, teacher))


def _save_logbook(request, teacher):
    from .models import TLMTopicLogbook

    p = request.POST
    topic = (p.get('topic') or p.get('topic_custom') or '').strip()
    subtopic = (p.get('subtopic') or p.get('subtopic_custom') or '').strip()
    if not topic:
        messages.error(request, 'Chagua au andika mada kuu.')
        return redirect('curriculum:logbook')

    subject = getattr(teacher, 'subject', None)
    if subject is None:
        try:
            from field_app.models import Subject
            subject = Subject.objects.filter(name__iexact=p.get('subject', '')).first()
        except Exception:
            subject = None

    started = _parse_date(p.get('date_started'))
    ended = _parse_date(p.get('date_ended')) or timezone.now().date()

    entry = TLMTopicLogbook(
        teacher=teacher,
        school=getattr(teacher, 'school', None),
        subject=subject,
        class_name=p.get('class_label', '') or getattr(teacher, 'class_name', ''),
        main_topic=topic,
        subtopic=subtopic,
        date_started=started,
        date_ended=ended,
        teacher_comment=p.get('teacher_comment', ''),
        teacher_name=getattr(teacher, 'full_name', ''),
        hod_comment=p.get('hod_comment', ''),
        hod_name=p.get('hod_name', ''),
        head_comment=p.get('head_remarks', ''),
        head_name=p.get('head_name', ''),
    )
    # Term / month / week come from the dates — the server is the source of truth.
    entry.term = 'I' if ended.month < 7 else 'II'
    entry.month = MONTHS[ended.month - 1]
    starts = json.loads(_term_starts())
    base = date.fromisoformat(starts['1'] if ended.month < 7 else starts['2'])
    entry.week = str(max(1, (ended - base).days // 7 + 1))
    entry.save()

    messages.success(request, 'Mada imehifadhiwa kwenye Logbook')
    return redirect('curriculum:logbook')


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# JSON endpoints
# ---------------------------------------------------------------------------

def api_check_phone(request):
    phone = (request.GET.get('phone') or '').strip()
    digits = re.sub(r'\D', '', phone)
    exists = False
    try:
        from .models import TLMTeacher
        if phone and TLMTeacher.objects.filter(phone_number=phone).exists():
            exists = True
        elif len(digits) >= 9:
            exists = TLMTeacher.objects.filter(phone_number__endswith=digits[-9:]).exists()
    except Exception:
        pass
    return JsonResponse({'exists': bool(exists)})


def api_locations(request):
    kind = request.GET.get('kind', 'region')
    parent = request.GET.get('parent', '')
    rows = []
    try:
        from field_app.models import Region, District, School
        if kind == 'region':
            rows = list(Region.objects.order_by('name').values('id', 'name'))
        elif kind == 'district':
            rows = list(District.objects.filter(region_id=parent).order_by('name').values('id', 'name'))
        else:
            rows = list(School.objects.filter(district_id=parent).order_by('name').values('id', 'name'))
    except Exception:
        rows = []
    return JsonResponse(rows, safe=False)


def api_subjects(request):
    return JsonResponse(_subject_choices(request.GET.get('level', 'olevel')), safe=False)


def api_subtopics(request):
    teacher = _teacher(request)
    return JsonResponse(
        _subtopic_choices(teacher, request.GET.get('topic', ''), request.GET.get('class', '')),
        safe=False)


@csrf_exempt
def api_generate_scheme(request):
    """Generate + save a scheme, then hand the browser a PDF url (G1 flow)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    teacher = _teacher(request)
    if not teacher:
        return JsonResponse({'error': 'Ingia kwanza.'}, status=403)

    p = request.POST
    level = p.get('level') or _teacher_level(teacher)
    try:
        holidays = json.loads(p.get('holidays_json') or '[]')
    except ValueError:
        holidays = []

    payload = {
        'education_level': EDU_LEVEL.get(level, 'Ordinary Level'),
        'class_name': p.get('class_name', ''),
        'stream': p.get('stream', ''),
        'subject': p.get('subject', '') or getattr(teacher.subject, 'name', ''),
        'term': {'full': 'Full Year'}.get(p.get('term', ''), p.get('term', 'Full Year') or 'Full Year'),
        'year': p.get('year', ''),
        'syllabus': 'Old Syllabus' if p.get('syllabus') == 'old' else 'New Syllabus',
        'total_weeks': p.get('weeks', '36'),
        'periods_per_week': p.get('periods', '8'),
        'start_date': p.get('start_date', ''),
        'end_date': p.get('end_date', ''),
        'teacher_name': p.get('teacher_name', '') or getattr(teacher, 'full_name', ''),
        'school_name': p.get('school_name', '') or getattr(getattr(teacher, 'school', None), 'name', ''),
        'reference_source': '',
        'breaks': holidays,
        'format': p.get('format', 'table'),
        'language': p.get('language', 'auto'),
    }
    result = _call(V.ajax_generate_scheme, request, payload).content
    try:
        data = json.loads(result)
    except ValueError:
        return JsonResponse({'error': 'Jibu batili kutoka kwa huduma ya AI.'}, status=502)
    if not data.get('success'):
        return JsonResponse({'error': data.get('error') or 'Imeshindikana kutengeneza.'}, status=502)
    saved_id = data.get('saved_id')
    if not saved_id:
        return JsonResponse({'error': 'Hati haikuhifadhiwa. Jaribu tena.'}, status=502)
    return JsonResponse({'id': saved_id,
                         'pdf_url': reverse('curriculum:doc_pdf', args=['scheme', saved_id])})


@csrf_exempt
def api_generate_lesson(request):
    """Generate + save lesson plan(s), then hand the browser a PDF url."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    teacher = _teacher(request)
    if not teacher:
        return JsonResponse({'error': 'Ingia kwanza.'}, status=403)

    p = request.POST
    level = p.get('level') or _teacher_level(teacher)
    boys = getattr(teacher, 'total_boys', 0) or 0
    girls = getattr(teacher, 'total_girls', 0) or 0
    payload = {
        'education_level': EDU_LEVEL.get(level, 'Ordinary Level'),
        'class_name': p.get('class_name', ''),
        'stream': p.get('stream', ''),
        'subject': p.get('subject', '') or getattr(teacher.subject, 'name', ''),
        'topic': p.get('topic') or p.get('topic_custom', ''),
        'subtopic': p.get('subtopic') or p.get('subtopic_custom', ''),
        'term': p.get('term', 'I'),
        'year': p.get('year', ''),
        'duration': p.get('duration', '40'),
        'total_boys': boys,
        'total_girls': girls,
        'total_students': boys + girls,
        'present_boys': p.get('present_boys', ''),
        'present_girls': p.get('present_girls', ''),
        'present_students': _int(p.get('present_boys')) + _int(p.get('present_girls')),
        'teacher_name': p.get('teacher_name', '') or getattr(teacher, 'full_name', ''),
        'school_name': p.get('school_name', '') or getattr(getattr(teacher, 'school', None), 'name', ''),
        'format': 'notable' if p.get('format') == 'notable' else 'table',
        'language': p.get('language', 'auto'),
        'scope': p.get('scope', 'one'),
    }
    if payload['scope'] == 'all':
        # "Mada zote": one combined PDF for every topic of the subject.
        payload.pop('topic', None)
        payload.pop('subtopic', None)

    result = _call(V.ajax_generate_lessonplan, request, payload).content
    try:
        data = json.loads(result)
    except ValueError:
        return JsonResponse({'error': 'Jibu batili kutoka kwa huduma ya AI.'}, status=502)
    if not data.get('success'):
        return JsonResponse({'error': data.get('error') or 'Imeshindikana kutengeneza.'}, status=502)
    saved_id = data.get('saved_id')
    if not saved_id:
        return JsonResponse({'error': 'Hati haikuhifadhiwa. Jaribu tena.'}, status=502)
    return JsonResponse({'id': saved_id,
                         'pdf_url': reverse('curriculum:doc_pdf', args=['lesson', saved_id])})
