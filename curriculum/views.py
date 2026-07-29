"""
Curriculum app views — standalone Scheme of Work, Lesson Plan & Logbook.
Uses models from field_app but provides its own views, templates, and URLs.
"""
import json
import os
import re
import threading
from io import BytesIO
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.utils import IntegrityError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth import logout as django_logout

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, PageBreak

import logging

# Optional PIL for watermark support
try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None


from .ai_utils import client, model_name
from .forms import SchemeOfWorkForm, LogbookForm

logger = logging.getLogger(__name__)

from field_app.models import (
    StudentTeacher, Subject, SchemeOfWork, LessonPlan,
    LogbookEntry, EducationLevel, ClassLevel, School,
    SchoolSubjectCapacity, StudentApplication, SchoolAssessment,
    AcademicYear, Textbook, BoardMember, BoardComment, Region, District,
)
from field_app.views.utils import (
    _cached_active_year, _cached_subjects, _cached_today_logbook,
    _invalidate_today_logbook, get_or_create_student_profile,
    get_current_academic_year, invalidate_student_cache,
)

from .models import TLMTeacher, Testimonial, LessonNote, SubjectTopic, TopicSubtopic


def _sanitize_json_control_chars(text):
    """Replace control characters inside JSON strings with their escaped forms.
    This handles AI responses that include literal newlines/tabs in string values,
    which would otherwise cause json.loads() to fail with 'Invalid control character'."""
    result = []
    in_str = False
    prev = ''
    for ch in text:
        if ch == '"' and prev != '\\':
            in_str = not in_str
        if in_str and ch in ('\n', '\r', '\t'):
            result.append({'\n': '\\n', '\r': '\\r', '\t': '\\t'}[ch])
        else:
            result.append(ch)
        prev = ch
    return ''.join(result)


# =============================================================================
# HELPER: Generate one batch of Scheme of Work data
# =============================================================================

def _generate_scheme_batch(prompt_text):
    """Make a single AI call for one batch of scheme data and parse the JSON response.
    Returns (scheme_data_list, response_text) or (None, response_text) on failure."""
    response = client.models.generate_content(model=model_name, contents=prompt_text)
    response_text = response.text
    logger.info(f"[Scheme Batch] AI response length: {len(response_text)} chars")

    # Strip markdown code blocks
    cleaned = re.sub(r'```(?:json)?\s*', '', response_text)
    cleaned = re.sub(r'```\s*', '', cleaned).strip()

    # Helper: parse first valid JSON array from text using bracket matching
    def _extract(text):
        start = text.find('[')
        if start == -1:
            return None
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if esc:
                esc = False
                continue
            if ch == '\\' and in_str:
                esc = True
                continue
            if ch == '"' and not esc:
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    candidate = text[start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        try:
                            return json.loads(_sanitize_json_control_chars(candidate))
                        except json.JSONDecodeError:
                            continue
        # No closing bracket - extract complete objects
        candidate = text[start:]
        complete_objs = []
        i = 0
        obj_start = None
        obj_depth = 0
        in_str2 = False
        esc2 = False
        while i < len(candidate):
            ch = candidate[i]
            if esc2:
                esc2 = False
                i += 1
                continue
            if ch == '\\' and in_str2:
                esc2 = True
                i += 1
                continue
            if ch == '"' and not esc2:
                in_str2 = not in_str2
                i += 1
                continue
            if in_str2:
                i += 1
                continue
            if ch == '{':
                if obj_depth == 0:
                    obj_start = i
                obj_depth += 1
            elif ch == '}':
                obj_depth -= 1
                if obj_depth == 0 and obj_start is not None:
                    complete_objs.append(candidate[obj_start:i+1])
                    obj_start = None
            i += 1
        if complete_objs:
            rebuilt = '[' + ','.join(complete_objs) + ']'
            try:
                return json.loads(rebuilt)
            except json.JSONDecodeError:
                try:
                    return json.loads(_sanitize_json_control_chars(rebuilt))
                except json.JSONDecodeError:
                    pass
        # Bracket-closing fallback
        if candidate.count('"') % 2 == 1:
            candidate += '"'
        open_b = candidate.count('{')
        close_b = candidate.count('}')
        if open_b > close_b:
            candidate += '}' * (open_b - close_b)
        open_arr = candidate.count('[')
        close_arr = candidate.count(']')
        if open_arr > close_arr:
            candidate += ']' * (open_arr - close_arr)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            try:
                return json.loads(_sanitize_json_control_chars(candidate))
            except json.JSONDecodeError:
                return None

    scheme_data = _extract(cleaned)
    
    # Fallbacks
    if scheme_data is None:
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list):
                        scheme_data = v
                        break
            elif isinstance(parsed, list):
                scheme_data = parsed
        except (json.JSONDecodeError, TypeError):
            try:
                parsed = json.loads(_sanitize_json_control_chars(cleaned))
                if isinstance(parsed, dict):
                    for v in parsed.values():
                        if isinstance(v, list):
                            scheme_data = v
                            break
                elif isinstance(parsed, list):
                        scheme_data = parsed
            except (json.JSONDecodeError, TypeError):
                pass

    if scheme_data is None:
        for attempt in [cleaned, _sanitize_json_control_chars(cleaned)]:
            try:
                m = re.search(r'\[.*?\]', attempt, re.DOTALL)
                candidate = m.group() if m else None
                if not candidate:
                    start = attempt.find('[')
                    if start != -1:
                        candidate = attempt[start:]
                if candidate:
                    open_b = candidate.count('{')
                    close_b = candidate.count('}')
                    if open_b > close_b:
                        candidate += '}' * (open_b - close_b)
                    open_arr = candidate.count('[')
                    close_arr = candidate.count(']')
                    if open_arr > close_arr:
                        candidate += ']' * (open_arr - close_arr)
                    try:
                        scheme_data = json.loads(candidate)
                    except json.JSONDecodeError:
                        try:
                            scheme_data = json.loads(_sanitize_json_control_chars(candidate))
                        except json.JSONDecodeError:
                            continue
                    if scheme_data:
                        break
            except (json.JSONDecodeError, TypeError):
                continue

    # Post-process: convert arrays to strings
    if scheme_data and isinstance(scheme_data, list):
        for row in scheme_data:
            for key in row:
                if isinstance(row[key], list):
                    row[key] = ', '.join(str(v) for v in row[key] if v)
                elif not isinstance(row[key], str):
                    row[key] = str(row[key] or '')

    return scheme_data, response_text



# =============================================================================
# HELPER: Check/Get TLM teacher from session
# =============================================================================

def get_tlm_teacher(request):
    """Get the registered TLM teacher from session, or None."""
    teacher_id = request.session.get('tlm_teacher_id')
    if teacher_id:
        try:
            return TLMTeacher.objects.get(id=teacher_id)
        except TLMTeacher.DoesNotExist:
            del request.session['tlm_teacher_id']
    return None


# =============================================================================
# LANDING PAGE (public)
# =============================================================================

def landing(request):
    """Public landing page — shows tools. If teacher is registered, greet them."""
    teacher = get_tlm_teacher(request)
    
    # Real DB statistics for the landing page
    from django.db.models import Count
    total_teachers = TLMTeacher.objects.count()
    total_schemes = SchemeOfWork.objects.count()
    total_lesson_plans = LessonPlan.objects.count()
    total_logbooks = LogbookEntry.objects.count()
    
    # Real testimonials from teachers
    testimonials = Testimonial.objects.filter(is_approved=True).select_related('teacher__school')[:6]
    
    return render(request, 'curriculum/landing.html', {
        'teacher': teacher,
        'total_teachers': total_teachers,
        'total_schemes': total_schemes,
        'total_lesson_plans': total_lesson_plans,
        'total_logbooks': total_logbooks,
        'testimonials': testimonials,
    })


# =============================================================================
# TEMPLATE LIBRARY — browse saved schemes & lesson plans
# =============================================================================

def template_library(request):
    """Browse ALL saved schemes and lesson plans from all teachers."""
    teacher = get_tlm_teacher(request)
    
    # Show ALL schemes and lesson plans from ALL teachers — not just the logged-in user
    # This creates a shared library where everyone can see what others have created
    all_schemes = SchemeOfWork.objects.all().select_related(
        'subject', 'school'
    ).order_by('-updated_at')[:50]
    
    all_lessons = LessonPlan.objects.all().select_related(
        'subject'
    ).order_by('-created_at')[:50]
    
    # Counts for stats
    total_schemes_count = SchemeOfWork.objects.count()
    total_lessons_count = LessonPlan.objects.count()
    
    return render(request, 'curriculum/library.html', {
        'teacher': teacher,
        'schemes': all_schemes,
        'lesson_plans': all_lessons,
        'total_schemes_count': total_schemes_count,
        'total_lessons_count': total_lessons_count,
    })


# =============================================================================
# TLM LOGOUT — clear session for TLM teachers
# =============================================================================

def tlm_logout(request):
    """Logout from TLM system — clears the TLM teacher session and Django auth."""
    # Clear the TLM teacher session
    if 'tlm_teacher_id' in request.session:
        del request.session['tlm_teacher_id']
    # Also clear Django auth session (in case user is both TLM + Django logged in)
    django_logout(request)
    return redirect('curriculum:landing')


# =============================================================================
# SUBMIT TESTIMONIAL / FEEDBACK
# =============================================================================

@require_POST
def ajax_submit_testimonial(request):
    """Submit a testimonial/feedback from a teacher."""
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        teacher_name = data.get('teacher_name', '').strip()
        school_name = data.get('school_name', '').strip()
        
        if not message or not teacher_name:
            return JsonResponse({'success': False, 'error': 'Tafadhali jaza jina na ujumbe.'}, status=400)
        
        teacher = get_tlm_teacher(request)
        
        testimonial = Testimonial.objects.create(
            teacher=teacher,
            teacher_name=teacher_name,
            school_name=school_name,
            message=message,
            is_approved=True,  # Auto-approve for now
        )
        
        return JsonResponse({'success': True, 'id': testimonial.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)[:200]}, status=500)


# =============================================================================
# TEACHER REGISTRATION (simple — no login needed)
# =============================================================================

def teacher_register(request):
    """
    Registration page: teacher selects Region → District → School → 
    (auto Education Level) → Class → Stream → Subject → Registered Students.
    If already registered (session), redirect to landing.
    """
    # Check if already registered
    teacher = get_tlm_teacher(request)
    if teacher:
        # Already registered — redirect where they were going
        next_url = request.GET.get('next', 'curriculum:landing')
        return redirect(next_url)

    regions = Region.objects.all().order_by('name')
    subjects = Subject.objects.all().order_by('name')
    
    import json as _json
    education_levels = EducationLevel.objects.all().order_by('order')
    classes_by_level = {}
    for cl in ClassLevel.objects.select_related('education_level').order_by('education_level', 'order'):
        classes_by_level.setdefault(cl.education_level_id, []).append({'id': cl.id, 'name': cl.name})
    
    return render(request, 'curriculum/teacher_register.html', {
        'regions': regions,
        'subjects': subjects,
        'education_levels': education_levels,
        'classes_by_level_json': _json.dumps(classes_by_level),
    })


def ajax_get_districts(request):
    """AJAX: Get districts for a given region."""
    region_id = request.GET.get('region_id')
    if not region_id:
        return JsonResponse([], safe=False)
    districts = District.objects.filter(region_id=region_id).order_by('name')
    return JsonResponse([{'id': d.id, 'name': d.name} for d in districts], safe=False)


def ajax_get_schools(request):
    """AJAX: Get schools for a given district."""
    district_id = request.GET.get('district_id')
    if not district_id:
        return JsonResponse([], safe=False)
    schools = School.objects.filter(district_id=district_id).order_by('name')
    return JsonResponse([{'id': s.id, 'name': s.name, 'level': s.level} for s in schools], safe=False)


def ajax_save_teacher(request):
    """AJAX: Save teacher registration."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=400)
    
    data = json.loads(request.body)
    
    full_name = data.get('full_name', '').strip()
    phone_number = data.get('phone_number', '').strip()
    region_id = data.get('region_id')
    district_id = data.get('district_id')
    school_id = data.get('school_id')
    class_name = data.get('class_name', '').strip()
    stream = data.get('stream', '').strip()
    subject_id = data.get('subject_id')
    total_boys = data.get('total_boys', 0)
    total_girls = data.get('total_girls', 0)
    
    if not all([full_name, phone_number, region_id, district_id, school_id, subject_id]):
        return JsonResponse({'success': False, 'error': 'Tafadhali jaza sehemu zote.'}, status=400)
    
    # ENFORCE unique phone number: reject if already registered to another user
    existing = TLMTeacher.objects.filter(phone_number=phone_number).first()
    if existing:
        return JsonResponse({
            'success': False,
            'error': 'Namba hii ya simu tayari imesajiliwa kwa mwalimu mwingine. Tafadhali tumia sehemu ya "Tayari umesajiliwa?" juu ya ukurasa au wasiliana na msimamizi.',
            'phone_exists': True,
        }, status=409)
    
    # Wrap in try-except for security: prevent duplicate phone numbers (race condition)
    try:
        teacher = TLMTeacher.objects.create(
            full_name=full_name,
            phone_number=phone_number,
            region_id=region_id,
            district_id=district_id,
            school_id=school_id,
            class_name=class_name,
            stream=stream,
            subject_id=subject_id,
            total_boys=int(total_boys) if total_boys else 0,
            total_girls=int(total_girls) if total_girls else 0,
        )
        request.session['tlm_teacher_id'] = teacher.id
        return JsonResponse({'success': True, 'is_new': True})
    except IntegrityError:
        # Race condition: another request got there first
        return JsonResponse({
            'success': False,
            'error': 'Namba hii ya simu tayari imesajiliwa. Tafadhali tumia sehemu ya utafutaji juu ya ukurasa.',
            'phone_exists': True,
        }, status=409)


def ajax_lookup_teacher(request):
    """AJAX: Lookup returning teacher by phone number."""
    phone = request.GET.get('phone', '').strip()
    if not phone:
        return JsonResponse({'found': False})
    
    teacher = TLMTeacher.objects.filter(phone_number=phone).first()
    if teacher:
        request.session['tlm_teacher_id'] = teacher.id
        return JsonResponse({
            'found': True,
            'full_name': teacher.full_name,
            'school_name': teacher.school.name if teacher.school else '',
        })
    return JsonResponse({'found': False})


# =============================================================================
# DASHBOARD (login required)
# =============================================================================

@login_required
def dashboard(request):
    """Standalone curriculum dashboard — overview of schemes, lesson plans & logbooks."""
    try:
        student = StudentTeacher.objects.select_related('selected_school').get(user=request.user)
    except StudentTeacher.DoesNotExist:
        messages.error(request, "Tafadhali jaza wasifu wako kwanza.")
        return redirect(reverse('curriculum:dashboard'))

    school = student.selected_school
    today = timezone.now().date()

    # Stats
    schemes_count = SchemeOfWork.objects.filter(student=student).count()
    lesson_plans_count = LessonPlan.objects.filter(student=student).count()
    logbook_today = LogbookEntry.objects.filter(student=student, date=today).first()
    logbook_count = LogbookEntry.objects.filter(student=student).count()
    this_month_logbooks = LogbookEntry.objects.filter(
        student=student, date__year=today.year, date__month=today.month
    ).count()

    # Recent items
    recent_schemes = SchemeOfWork.objects.filter(student=student).select_related('subject').order_by('-updated_at')[:3]
    recent_lessons = LessonPlan.objects.filter(student=student).select_related('subject').order_by('-created_at')[:3]
    recent_logbooks = LogbookEntry.objects.filter(student=student).select_related('subject_taught').order_by('-date')[:5]

    return render(request, 'curriculum/dashboard.html', {
        'student': student,
        'school': school,
        'schemes_count': schemes_count,
        'lesson_plans_count': lesson_plans_count,
        'logbook_today': logbook_today,
        'logbook_count': logbook_count,
        'this_month_logbooks': this_month_logbooks,
        'recent_schemes': recent_schemes,
        'recent_lessons': recent_lessons,
        'recent_logbooks': recent_logbooks,
        'today': today,
    })


# =============================================================================
# SCHEME OF WORK
# =============================================================================

def generate_scheme_view(request):
    """Display scheme of work generator form — requires TLM registration."""
    teacher = get_tlm_teacher(request)
    if not teacher:
        # Need to register first
        return redirect(f"{reverse('curriculum:teacher_register')}?next={reverse('curriculum:generate_scheme')}")
    
    form = SchemeOfWorkForm()
    education_levels = EducationLevel.objects.all().order_by('order')

    import json as _json
    classes_by_level = {}
    for cl in ClassLevel.objects.select_related('education_level').order_by('education_level', 'order'):
        classes_by_level.setdefault(cl.education_level_id, []).append({'id': cl.id, 'name': cl.name})

    # Filter subjects by education level (Primary → primary, Advanced → advanced, Ordinary → secondary)
    def _subjects_for_level(level_name):
        name_lower = level_name.lower()
        if 'primary' in name_lower:
            return list(Subject.objects.filter(level='primary').order_by('name').values('id', 'name'))
        elif 'advanced' in name_lower:
            return list(Subject.objects.filter(level='advanced').order_by('name').values('id', 'name'))
        else:
            # Ordinary Level → secondary subjects
            return list(Subject.objects.filter(level='secondary').order_by('name').values('id', 'name'))

    subjects_by_level = {
        lvl.id: _subjects_for_level(lvl.name)
        for lvl in education_levels
    }

    student = None
    school = None
    if request.user.is_authenticated:
        try:
            student = StudentTeacher.objects.select_related('selected_school').get(user=request.user)
            school = student.selected_school
            if not school:
                app = StudentApplication.objects.filter(
                    student=student, status='approved'
                ).select_related('school').first()
                if app:
                    school = app.school
        except StudentTeacher.DoesNotExist:
            pass

    # Get teacher info for auto-fill
    teacher_name = teacher.full_name if teacher else ''
    teacher_school_name = teacher.school.name if teacher and teacher.school else ''
    teacher_school_level = teacher.school.level if teacher and teacher.school else ''
    teacher_subject_id = teacher.subject.id if teacher and teacher.subject else ''
    teacher_subject_name = teacher.subject.name if teacher and teacher.subject else ''
    teacher_subject_level = teacher.subject.level if teacher and teacher.subject else ''
    teacher_class_name = teacher.class_name if teacher else ''
    teacher_stream = teacher.stream if teacher else ''
    teacher_total_boys = teacher.total_boys if teacher else 0
    teacher_total_girls = teacher.total_girls if teacher else 0

    return render(request, 'curriculum/generate_scheme.html', {
        'form': form,
        'education_levels': education_levels,
        'classes_by_level_json': _json.dumps(classes_by_level),
        'subjects_by_level_json': _json.dumps(subjects_by_level),
        'student': student,
        'school': school,
        'teacher': teacher,
        'teacher_name': teacher_name,
        'teacher_school_name': teacher_school_name,
        'teacher_school_level': teacher_school_level,
        'teacher_subject_id': teacher_subject_id,
        'teacher_subject_name': teacher_subject_name,
        'teacher_subject_level': teacher_subject_level,
        'teacher_class_name': teacher_class_name,
        'teacher_stream': teacher_stream,
        'teacher_total_boys': teacher_total_boys,
        'teacher_total_girls': teacher_total_girls,
    })


def ajax_generate_scheme(request):
    """AI generates a Scheme of Work."""
    if client is None:
        return JsonResponse({
            'success': False,
            'error': 'Huduma ya AI haitumiki. Ufunguo wa API haujawekwa. Wasiliana na msimamizi.'
        }, status=503)

    if request.method != 'POST':
        return JsonResponse({'success': False}, status=400)

    try:
        data = json.loads(request.body)

        education_level = data.get('education_level')
        class_name = data.get('class_name')
        stream = data.get('stream', '')
        subject = data.get('subject')
        term = data.get('term')
        year = data.get('year')
        syllabus = data.get('syllabus', 'New Syllabus')
        total_weeks = int(data.get('total_weeks', 12))
        periods_per_week = int(data.get('periods_per_week', 8))
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        teacher_name = data.get('teacher_name')
        school_name = data.get('school_name')
        reference_source = data.get('reference_source', '')
        breaks = data.get('breaks', [])

        full_class_name = f"{class_name}{stream}" if stream else class_name

        # ── Build comprehensive term scope with MONTH RANGES ──
        term_scope_map = {
            'Full Year': f'FULL YEAR: Cover ALL topics in the syllabus from start to finish. Distribute across ALL months: JANUARY to NOVEMBER ({total_weeks} weeks total). Each month gets different topics. Do NOT concentrate everything in January only.',
            'I': f'TERM I only: Cover topics from the FIRST HALF of the syllabus. Months: JANUARY to JUNE ({total_weeks} weeks). Start from Topic 1. Do NOT include Term II or III topics.',
            'II': f'TERM II only: Cover topics from the SECOND HALF of the syllabus. Months: JULY to NOVEMBER/DECEMBER ({total_weeks} weeks). Continue from where Term I ends. Do NOT include Term I or III topics.',
            'III': f'TERM III only: Cover the FINAL PART of the syllabus. Months: SEPTEMBER to NOVEMBER/DECEMBER ({total_weeks} weeks). Complete remaining topics. Do NOT include Term I or II topics.',
        }
        term_scope = term_scope_map.get(term, f'Cover content for {total_weeks} weeks.')

        # ── Breaks & Holidays — FULL ROWS with merged break text ──
        breaks_text = ''
        if breaks:
            for b in breaks:
                name = b.get('name', 'Break')
                start = b.get('start', '')
                end = b.get('end', '')
                full_label = f"{name.upper()}\n({start} – {end})"
                if 'exam' in name.lower() or 'test' in name.lower() or 'midterm' in name.lower() or 'terminal' in name.lower():
                    breaks_text += f"""
- BREAK ROW: ALL 12 columns MUST contain this exact text: "{full_label}"
  Month: Based on start date ({start}), Week: Based on calendar position, No. of Periods: "2" for exams, "0" for holidays"""
                else:
                    breaks_text += f"""
- BREAK ROW: ALL 12 columns MUST contain this exact text: "{full_label}"
  Month: Based on start date ({start}), Week: Based on calendar position, No. of Periods: "0" for holidays"""
            breaks_text = f"\n\n🎯 CRITICAL — YOU MUST INCLUDE EACH OF THESE BREAKS/HOLIDAYS AS A FULL ROW IN YOUR OUTPUT:\n{breaks_text}\n\nEACH BREAK ROW: ALL 12 columns must have the SAME text — the break name with dates.\nFAILURE TO INCLUDE THESE BREAK ROWS = INCOMPLETE SCHEME."

        # ── Reference source ──
        ref_text = f"\nReference source: {reference_source}" if reference_source else ''

        # ── Determine language instruction based on school level ──
        _lang_tlm = get_tlm_teacher(request)
        _school_level = _lang_tlm.school.level if _lang_tlm and _lang_tlm.school else ''
        _subject_lower = subject.lower()
        if _school_level == 'Primary':
            if _subject_lower in ('english', 'english language'):
                language_instruction = "LANGUAGE: Write ALL content in ENGLISH because this is an English subject for Primary school."
            else:
                language_instruction = "LANGUAGE: Write ALL content in KISWAHILI (Swahili). Only column headers can stay in English. All explanations, activities, and descriptions MUST be in Swahili language. This is a Primary school subject."
        elif _school_level == 'Secondary':
            if _subject_lower in ('kiswahili', 'swahili'):
                language_instruction = "LANGUAGE: Write ALL content in KISWAHILI (Swahili) because this is a Kiswahili subject for Secondary school."
            else:
                language_instruction = "LANGUAGE: Write ALL content in ENGLISH. This is a Secondary school subject taught in English."
        else:
            language_instruction = ""

        # ── Build base prompt template (shared between batches) ──
        def _make_prompt(scope_text, weeks_count):
            return f"""You are a Tanzanian curriculum expert (TIE/SEQUIP). Generate a REAL, AUTHENTIC Scheme of Work for a Tanzanian {education_level} class following the OFFICIAL TAMISEMI (Prime Minister's Office - Regional Administration and Local Government) format EXACTLY.

============================================
PRIME MINISTER'S OFFICE
REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT
SCHEME OF WORK
============================================

TEACHER'S NAME: {teacher_name or '____________________'}
SCHOOL NAME: {school_name or '____________________'}
SUBJECT: {subject}
CLASS: {full_class_name}
TERM: {term}
YEAR: {year}
SYLLABUS: {syllabus}
TOTAL WEEKS: {weeks_count}
PERIODS/WEEK: {periods_per_week}{ref_text}

{language_instruction}

{breaks_text}

OUTPUT FORMAT:
Return a JSON array of objects. Each object MUST have EXACTLY these 12 keys with these EXACT spellings:
"Main Competence", "Specific Competences", "Main Learning Activities", "Specific Learning Activities", "Month", "Week", "Number of Periods", "Teaching and Learning Methods", "Teaching and Learning Resources", "Assessment Tools", "References", "Remarks"

{scope_text}

═══════════════════════════════════════════════════
STRICT RULES — FOLLOW EXACTLY:
═══════════════════════════════════════════════════

📌 1. MAIN COMPETENCE (Mada Kuu):
   - Format: "1.0 [Competence Statement]" e.g., "1.0 Demonstrate mastery of the concepts, principles and procedures of nutrition and transportation"
   - Use REAL numbered competences from the TIE syllabus for {subject} {full_class_name}
   - ONE Main Competence can span MANY months (January through October with different subtopics)
   - Example from real scheme: "1.0 Demonstrate mastery of the concepts, principles and procedures of nutrition and transportation"

📌 2. SPECIFIC COMPETENCES (Mada Ndogo):
   - Format: "2.1 [Subtopic Description]" e.g., "2.1 Describe the physiological, anatomical and ecological principles used in nutrition and transportation"
   - Each Specific Competence falls under a Main Competence (e.g., 1.1, 1.2, 2.1, 2.2)
   - Multiple rows can have the SAME Specific Competence number if covering different aspects

📌 3. MAIN LEARNING ACTIVITIES (Shughuli Kuu):
   - Use lettered format: "(a) Describe nutrition in human and ruminants (nutrients, digestion, absorption, assimilation)"
   - "(b) Describe the mechanism of transportation of materials in plants and animals"
   - "(c) Describe the mechanisms of gaseous exchange and respiration in living organisms"
   - Each letter groups a major topic area

📌 4. SPECIFIC LEARNING ACTIVITIES (Shughuli Maalum):
   - Start with "To..." format: "To describe the meaning of human nutrition" or "To explain the concept of transportation of materials in plants"
   - Each row has ONE focused specific learning activity
   - VERY IMPORTANT: Each row MUST have a DIFFERENT specific learning activity

📌 5. MONTH:
   - Uppercase: JANUARY, FEBRUARY, MARCH, APRIL, MAY, JUNE, JULY, AUGUST, SEPTEMBER, OCTOBER, NOVEMBER
   - Months MUST appear in CHRONOLOGICAL ORDER
   - EACH month MUST have 3-8 rows (comprehensive coverage)
   - If a break falls in a month, still include real topic rows before and after

📌 6. WEEK:
   - Format: "1st", "2nd", "3rd", "4th" or ranges like "2nd & 3rd", "3rd & 4th"
   - EXAM weeks: fewer periods (2-3)
   - Normal weeks: 6-12 periods depending on subject

📌 7. NUMBER OF PERIODS:
   - Realistic values: 3, 6, 9, 12 (NOT "{periods_per_week}" for every row)
   - Each row gets a portion of the weekly periods
   - Exam/break rows: "2" for exams, "0" for holidays

📌 8. TEACHING AND LEARNING METHODS:
   - CBC-aligned methods: "Brainstorming", "Group discussion", "ICT-Based learning", "Jigsaw", "Guided inquiry", "Question and answer", "Demonstration", "Experimentation", "Field trip", "Guest speaker", "Project", "Problem solving"
   - Include 3-5 methods per row
   - EXAMPLES: "Brainstorming, ICT-Based learning, Jigsaw, Group discussion, Gallery walk"

📌 9. TEACHING AND LEARNING RESOURCES:
   - Specific to the topic: "TIE textbook, Charts/model/photographs, Real specimens, Manila sheets, Markers, Online resources"
   - Example: "Mammalian heart models, charts of blood circulatory system, photographs of blood components"

📌 10. ASSESSMENT TOOLS:
   - Variety: "Quizzes", "Tests", "Exercises", "Assignment", "Questions and answers", "Practical work", "Project", "Portfolio"
   - Use 2-4 per row

📌 11. REFERENCES:
   - APA v7 format using LATEST TIE textbooks
   - Example: "Tanzania Institute of Education. (2024). BIOLOGY for Ordinary Secondary Schools Student's Book Form Two. Tanzania Institute of Education."
   - For Primary: "Tanzania Institute of Education. (2024). {subject} for Primary Schools Pupil's Book. Tanzania Institute of Education."

📌 12. REMARKS:
   - Meaningful teacher reflection: "Students participated well" or "More practice needed on calculations" or "Use more real specimens next time"

═══════════════════════════════════════════════════
CRITICAL REQUIREMENTS:
═══════════════════════════════════════════════════

🔴 ROWS PER MONTH: Each month MUST have 3-8 rows. A comprehensive scheme for a full year should have 40-80+ total rows.
🔴 REAL SYLLABUS: Use REAL TIE syllabus topics for {subject} {full_class_name}. Do NOT fabricate fake topics.
🔴 PROPER NUMBERING: Main Competence numbered 1.0, 2.0, 3.0... Specific Competence numbered 1.1, 1.2, 2.1, 2.2...
🔴 MONTH ORDER: JANUARY → FEBRUARY → MARCH → APRIL → MAY → JUNE → JULY → AUGUST → SEPTEMBER → OCTOBER → NOVEMBER (strict chronological)
🔴 BREAKS: Include ALL listed breaks as FULL rows where all 12 columns have the SAME break text
🔴 CONTENT QUALITY: Rich, detailed, specific to the subject. NOT generic.
🔴 All values MUST be plain strings, NEVER arrays.

Return ONLY the JSON array. No other text."""

        all_scheme_data = []
        all_response_texts = []

        # ── Batch logic: For Full Year with >= 24 weeks, split into 2 batches ──
        if term == 'Full Year' and total_weeks >= 24:
            half_weeks = total_weeks // 2
            remaining_weeks = total_weeks - half_weeks
            logger.info(f"[Scheme] BATCHING: {total_weeks} weeks -> {half_weeks}+{remaining_weeks}")

            # Batch 1: First half (January to June, first topics)
            scope1 = f'FIRST HALF of the full year. Cover the FIRST topics from the syllabus (January to June, {half_weeks} weeks). Start from the very beginning. Cover JANUARY, FEBRUARY, MARCH, APRIL, MAY, JUNE. Do NOT include topics from Term II.'
            prompt1 = _make_prompt(scope1, half_weeks)
            data1, resp1 = _generate_scheme_batch(prompt1)
            if data1:
                all_scheme_data.extend(data1)
                all_response_texts.append(resp1)
                logger.info(f"[Scheme] Batch 1 done: {len(data1)} rows")

            # Batch 2: Second half (July to November, remaining topics)
            scope2 = f'SECOND HALF of the full year. Cover the REMAINING topics from the syllabus (July to November, {remaining_weeks} weeks). Continue from where the first half ended. Cover JULY, AUGUST, SEPTEMBER, OCTOBER, NOVEMBER. You MUST include content for NOVEMBER - do NOT end in October. Do NOT repeat topics from the first half.'
            prompt2 = _make_prompt(scope2, remaining_weeks)
            data2, resp2 = _generate_scheme_batch(prompt2)
            if data2:
                all_scheme_data.extend(data2)
                all_response_texts.append(resp2)
                logger.info(f"[Scheme] Batch 2 done: {len(data2)} rows")

        else:
            # Single generation (Term I/II/III or small Full Year)
            logger.info(f"[Scheme] Single generation: {total_weeks} weeks")
            data, resp = _generate_scheme_batch(_make_prompt(term_scope, total_weeks))
            if data:
                all_scheme_data.extend(data)
            all_response_texts.append(resp)

        if not all_scheme_data:
            preview = (all_response_texts[0] if all_response_texts else '')[:600]
            logger.error(f"[Scheme] ALL batches failed! Raw: {preview}")
            return JsonResponse({
                'success': False,
                'error': f"AI haikurudisha data sahihi. Sehemu ya majibu: {preview}",
            }, status=422)

        scheme_data = all_scheme_data
        response_text = '\n'.join(all_response_texts)

        # Save to DB (works for both Django users AND TLM teachers)
        saved_id = None
        try:
            tlm_teacher = get_tlm_teacher(request)
            student = None
            school = None
            if request.user.is_authenticated:
                try:
                    student = StudentTeacher.objects.get(user=request.user)
                    school = student.selected_school
                except StudentTeacher.DoesNotExist:
                    pass
            elif tlm_teacher and tlm_teacher.school:
                school = tlm_teacher.school
            
            if school:
                level_map = {'primary school': 'primary', 'ordinary level': 'ordinary', 'advanced level': 'advanced'}
                edu_level = level_map.get((education_level or '').lower(), 'ordinary')
                subj_obj = Subject.objects.filter(name__iexact=subject).first()
                if subj_obj:
                    start_dt = None
                    end_dt = None
                    if start_date:
                        try:
                            from datetime import date as _dt
                            start_dt = _dt.fromisoformat(start_date)
                        except Exception:
                            pass
                    if end_date:
                        try:
                            from datetime import date as _dt
                            end_dt = _dt.fromisoformat(end_date)
                        except Exception:
                            pass
                    
                    defaults = {
                        'school': school,
                        'education_level': edu_level,
                        'class_name': class_name,
                        'syllabus': syllabus,
                        'total_weeks': int(total_weeks),
                        'periods_per_week': int(periods_per_week),
                        'start_date': start_dt,
                        'end_date': end_dt,
                        'teacher_name': teacher_name,
                        'reference_source': reference_source,
                        'breaks': breaks,
                        'scheme_data': scheme_data,
                        'generated_by_ai': True,
                    }
                    
                    if student:
                        # Authenticated user: update existing or create new
                        scheme_obj, _ = SchemeOfWork.objects.update_or_create(
                            student=student,
                            subject=subj_obj,
                            term=term,
                            year=int(year),
                            defaults=defaults,
                        )
                    else:
                        # TLM teacher: always create new record
                        scheme_obj = SchemeOfWork.objects.create(
                            student=None,
                            **defaults,
                        )
                    saved_id = scheme_obj.id
        except Exception as save_err:
            logger.warning(f"[Curriculum] Scheme save error (non-fatal): {save_err}")

        return JsonResponse({
            'success': True,
            'data': scheme_data,
            'saved_id': saved_id,
            'debug': {
                'response_length': len(response_text),
                'rows_found': len(scheme_data),
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        raw = str(e)
        logger.error(f"[Scheme Gen Error] {type(e).__name__}: {raw[:300]}")
        if 'PERMISSION_DENIED' in raw or 'suspended' in raw.lower() or '403' in raw:
            msg = "Huduma ya AI imesimamishwa. Wasiliana na msimamizi."
        elif 'quota' in raw.lower() or '429' in raw or 'rate' in raw.lower():
            msg = f"Kikomo cha matumizi: {raw[:200]}"
        elif '413' in raw or 'request too large' in raw.lower():
            msg = f"Ombi ni kubwa mno kwa AI. Jaribu kupunguza maelezo (wiki, vipindi) au kubadili somo. Hitilafu: {raw[:200]}"
        elif 'API_KEY' in raw or 'api_key' in raw.lower():
            msg = "Ufunguo wa API ya AI haujawekwa. Wasiliana na msimamizi."
        else:
            msg = f"Hitilafu: {raw[:200]}"
        return JsonResponse({'success': False, 'error': msg}, status=500)


def download_scheme_pdf(request):
    """Generate PDF ya Scheme of Work."""
    if request.method != 'POST':
        return HttpResponse("Invalid request", status=400)

    data = json.loads(request.body)
    scheme_data = data.get('scheme_data') or []
    subject = data.get('subject', '')
    class_name = data.get('class_name', '')
    term = data.get('term', '')
    year = data.get('year', '')
    syllabus = data.get('syllabus', '')
    teacher_name = data.get('teacher_name', '')
    school_name = data.get('school_name', '')
    total_weeks = data.get('total_weeks', '')

    NAVY = colors.HexColor('#0A2B5E')
    GOLD = colors.HexColor('#C8900A')
    DARK_GOLD = colors.HexColor('#A67B07')
    STRIPE = colors.HexColor('#EBF0FB')
    BORDER = colors.HexColor('#9BAAC4')


    # ── Create Tanzania flag watermark ──
    _tz_watermark = None
    if PILImage:
        try:
            _flag_path = os.path.join(os.path.dirname(__file__), 'static', 'curriculum', 'tz_flag.png')
            if os.path.exists(_flag_path):
                _pil_img = PILImage.open(_flag_path).convert('RGBA')
                _r, _g, _b, _a = _pil_img.split()
                _new_a = _a.point(lambda x: int(x * 0.10))
                _faded = PILImage.merge('RGBA', (_r, _g, _b, _new_a))
                _buf = BytesIO()
                _faded.save(_buf, format='PNG')
                _buf.seek(0)
                _tz_watermark = _buf
        except Exception:
            pass

    # ── Cover page: professional border drawing ──
    def _scheme_cover(can, doc_obj):
        """Draw professional double-border frame with flag watermark."""
        can.saveState()
        pw = doc_obj.pagesize[0]
        ph = doc_obj.pagesize[1]
        # Outer gold border (thick)
        can.setStrokeColor(GOLD)
        can.setLineWidth(3.5)
        can.rect(12, 12, pw - 24, ph - 24)
        # Inner navy border (thin)
        can.setStrokeColor(NAVY)
        can.setLineWidth(1.5)
        can.rect(18, 18, pw - 36, ph - 36)
        # Top gold accent bar
        can.setStrokeColor(GOLD)
        can.setLineWidth(4)
        can.line(18, ph - 55, pw - 18, ph - 55)
        # Bottom gold accent bar
        can.line(18, 55, pw - 18, 55)
        # Top-left corner square
        can.setFillColor(GOLD)
        can.rect(18, ph - 26, 14, 8, fill=1, stroke=0)
        # Top-right corner square
        can.rect(pw - 32, ph - 26, 14, 8, fill=1, stroke=0)
        # Bottom-left corner square
        can.rect(18, 18, 14, 8, fill=1, stroke=0)
        # Bottom-right corner square
        can.rect(pw - 32, 18, 14, 8, fill=1, stroke=0)
        # ── Draw Tanzania flag watermark ──
        if _tz_watermark:
            try:
                _tz_watermark.seek(0)
                fw = pw * 0.50
                fh = fw * 2.0 / 3.0
                can.drawImage(_tz_watermark, pw/2 - fw/2, ph/2 - fh/2,
                              width=fw, height=fh, mask='auto')
            except Exception:
                pass
        can.restoreState()

    # ── Page header (appears from page 2 onwards) ──
    def _scheme_header(can, doc_obj):
        """Draw NAME OF SCHOOL / TEACHER header bar on pages 2+."""
        can.saveState()
        can.setFont('Helvetica-Bold', 7)
        can.setFillColor(NAVY)
        pw = doc_obj.pagesize[0]
        ph = doc_obj.pagesize[1]
        # Row 1: School | Subject | Class
        can.drawString(18, ph - 18, f"NAME OF SCHOOL: {school_name or '____________________'}")
        can.drawCentredString(pw / 2, ph - 18, f"SUBJECT: {subject}")
        can.drawRightString(pw - 18, ph - 18, f"CLASS: {class_name}")
        # Row 2: Teacher | Term | Year
        can.drawString(18, ph - 30, f"TEACHER'S NAME: {teacher_name or '____________________'}")
        can.drawCentredString(pw / 2, ph - 30, f"TERM: {term}")
        can.drawRightString(pw - 18, ph - 30, f"YEAR: {year}")
        # Gold underline
        can.setStrokeColor(GOLD)
        can.setLineWidth(0.8)
        can.line(18, ph - 34, pw - 18, ph - 34)
        can.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=18, leftMargin=18, topMargin=40, bottomMargin=25)
    elements = []

    # ── Cover page: decorative top lines ──
    elements.append(HRFlowable(width="100%", thickness=3, color=GOLD, spaceAfter=2))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=12))

    cell_style = ParagraphStyle('SchCell', fontName='Helvetica', fontSize=7,
                                leading=10, wordWrap='LTR')
    hdr_style = ParagraphStyle('SchHdr', fontName='Helvetica-Bold', fontSize=7,
                               leading=10, textColor=colors.white, wordWrap='LTR', alignment=1)

    # ── TAMISEMI Header (centered, bold) ──
    elements.append(Paragraph(
        "PRIME MINISTER'S OFFICE",
        ParagraphStyle('MH1', fontName='Helvetica-Bold', fontSize=13, alignment=1,
                       textColor=NAVY, spaceAfter=2)))
    elements.append(Paragraph(
        "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT",
        ParagraphStyle('MH2', fontName='Helvetica-Bold', fontSize=10, alignment=1,
                       textColor=NAVY, spaceAfter=2)))
    elements.append(HRFlowable(width="50%", thickness=1, color=GOLD, spaceAfter=8))

    # ── Title ──
    elements.append(Paragraph("SCHEME OF WORK",
        ParagraphStyle('ST', fontName='Helvetica-Bold', fontSize=18, alignment=1,
                       textColor=NAVY, spaceAfter=10)))

    # ── Cover info: styled table ──
    lbl = ParagraphStyle('lbl', fontName='Helvetica-Bold', fontSize=10, textColor=colors.white, leading=14)
    val = ParagraphStyle('val', fontName='Helvetica', fontSize=10, textColor=colors.HexColor('#222222'), leading=14)
    info_rows = [
        [Paragraph("Teacher's Name", lbl), Paragraph(teacher_name, val)],
        [Paragraph('School Name', lbl), Paragraph(school_name or '____________________', val)],
        [Paragraph('Subject', lbl), Paragraph(subject, val)],
        [Paragraph('Class', lbl), Paragraph(class_name, val)],
        [Paragraph('Term', lbl), Paragraph(term, val)],
        [Paragraph('Year', lbl), Paragraph(str(year), val)],
        [Paragraph('Total Weeks', lbl), Paragraph(str(total_weeks), val)],
        [Paragraph('Syllabus', lbl), Paragraph(syllabus, val)],
    ]
    info_table = Table(info_rows, colWidths=[180, 280])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), NAVY),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.white),
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#FAFBFD')),
        ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.HexColor('#FAFBFD'), STRIPE]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('BOX', (0, 0), (-1, -1), 2, GOLD),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, GOLD),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(info_table)
    # ── PageBreak: Cover page ends here, data table starts on page 2 ──
    elements.append(PageBreak())

    if scheme_data:
        headers = list(scheme_data[0].keys())
        WIDTH_MAP = {
            'Main Competence': 72, 'Specific Competences': 72,
            'Main Learning Activities': 68, 'Specific Learning Activities': 76,
            'Month': 38, 'Week': 34, 'Number of Periods': 32,
            'Teaching and Learning Methods': 64,
            'Teaching and Learning Resources': 64,
            'Assessment Tools': 54, 'References': 64, 'Remarks': 68,
        }
        TOTAL = 806
        col_widths = []
        for h in headers:
            w = WIDTH_MAP.get(h)
            if w is None:
                for k, v in WIDTH_MAP.items():
                    if k.lower() in h.lower() or h.lower() in k.lower():
                        w = v
                        break
            col_widths.append(w if w else TOTAL // len(headers))
        scale = TOTAL / sum(col_widths)
        col_widths = [w * scale for w in col_widths]

        table_data = [[Paragraph(h, hdr_style) for h in headers]]
        for row in scheme_data:
            table_data.append([Paragraph(str(row.get(h, '') or ''), cell_style) for h in headers])

        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        ts = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.35, BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, 0), 1.2, GOLD),
        ]
        for i in range(1, len(table_data)):
            bg = STRIPE if i % 2 == 0 else colors.white
            ts.append(('BACKGROUND', (0, i), (-1, i), bg))
        tbl.setStyle(TableStyle(ts))
        elements.append(tbl)

    doc.build(elements, onFirstPage=_scheme_cover, onLaterPages=_scheme_header)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Scheme_of_Work_{subject}_{class_name}.pdf"'
    return response


def download_scheme_word(request):
    """Export Scheme of Work as Word (.docx)."""
    if request.method != 'POST':
        return HttpResponse("Invalid request", status=400)

    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    data = json.loads(request.body)
    scheme_data = data.get('scheme_data', [])
    subject = data.get('subject', '')
    class_name = data.get('class_name', '')
    term = data.get('term', '')
    year = data.get('year', '')
    teacher_name = data.get('teacher_name', '')
    school_name = data.get('school_name', '')

    doc = Document()
    doc.core_properties.title = f"Scheme of Work — {subject}"

    title = doc.add_heading(f"{subject} — {class_name} — Term {term} {year}", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    info = doc.add_paragraph(f"Teacher: {teacher_name}    School: {school_name}")
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()

    if scheme_data:
        headers = list(scheme_data[0].keys())
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = 'Table Grid'

        WIDTH_CM = {
            'Main Competence': 2.6, 'Specific Competences': 2.6,
            'Main Learning Activities': 2.4, 'Specific Learning Activities': 2.8,
            'Month': 1.3, 'Week': 1.2, 'Number of Periods': 1.1,
            'Teaching and Learning Methods': 2.2,
            'Teaching and Learning Resources': 2.2,
            'Assessment Tools': 1.9, 'References': 2.2, 'Remarks': 2.5,
        }
        TOTAL_CM = 24.0
        col_cms = []
        for h in headers:
            w = WIDTH_CM.get(h)
            if w is None:
                for k, v in WIDTH_CM.items():
                    if k.lower() in h.lower() or h.lower() in k.lower():
                        w = v
                        break
            col_cms.append(w if w else TOTAL_CM / len(headers))
        scale_cm = TOTAL_CM / sum(col_cms)
        col_cms = [w * scale_cm for w in col_cms]

        section = doc.sections[0]
        section.page_width = Cm(29.7)
        section.page_height = Cm(21.0)
        section.left_margin = section.right_margin = Cm(1.2)
        section.top_margin = section.bottom_margin = Cm(1.2)

        hdr_cells = table.rows[0].cells
        for i, h in enumerate(headers):
            hdr_cells[i].text = h
            hdr_cells[i].width = Cm(col_cms[i])
            p = hdr_cells[i].paragraphs[0]
            if p.runs:
                p.runs[0].bold = True
                p.runs[0].font.size = Pt(8)
                p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            tc = hdr_cells[i]._tc
            tcPr = tc.get_or_add_tcPr()
            shd = OxmlElement('w:shd')
            shd.set(qn('w:val'), 'clear')
            shd.set(qn('w:color'), 'auto')
            shd.set(qn('w:fill'), '0A2B5E')
            tcPr.append(shd)

        for ri, row in enumerate(scheme_data):
            row_cells = table.add_row().cells
            fill_hex = 'EBF0FB' if ri % 2 == 0 else 'FFFFFF'
            for i, h in enumerate(headers):
                row_cells[i].width = Cm(col_cms[i])
                row_cells[i].text = str(row.get(h, '') or '')
                p = row_cells[i].paragraphs[0]
                if p.runs:
                    p.runs[0].font.size = Pt(8)
                tc = row_cells[i]._tc
                tcPr = tc.get_or_add_tcPr()
                shd = OxmlElement('w:shd')
                shd.set(qn('w:val'), 'clear')
                shd.set(qn('w:color'), 'auto')
                shd.set(qn('w:fill'), fill_hex)
                tcPr.append(shd)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    safe_name = f"Scheme_{subject}_{class_name}".replace(' ', '_')
    response = HttpResponse(buffer, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{safe_name}.docx"'
    return response


def ajax_load_saved_scheme(request):
    """Load most recent saved SchemeOfWork from DB (works for both Django users & TLM teachers)."""
    try:
        tlm_teacher = get_tlm_teacher(request)
        scheme = None
        if request.user.is_authenticated:
            try:
                student = StudentTeacher.objects.get(user=request.user)
                scheme = (SchemeOfWork.objects
                          .filter(student=student)
                          .select_related('subject')
                          .order_by('-updated_at')
                          .first())
            except StudentTeacher.DoesNotExist:
                pass
        if not scheme and tlm_teacher and tlm_teacher.school:
            # TLM teacher: load by school and teacher_name
            scheme = (SchemeOfWork.objects
                      .filter(school=tlm_teacher.school, teacher_name=tlm_teacher.full_name)
                      .select_related('subject')
                      .order_by('-updated_at')
                      .first())
        if not scheme or not scheme.scheme_data:
            return JsonResponse({'success': False, 'error': 'Hakuna mpango uliohifadhiwa. Tengeneza kwanza.'}, status=404)
        return JsonResponse({
            'success': True,
            'data': scheme.scheme_data,
            'saved_id': scheme.id,
            'meta': {
                'subject': scheme.subject.name,
                'class_name': scheme.class_name,
                'term': scheme.term,
                'year': scheme.year,
                'teacher_name': scheme.teacher_name,
                'school_name': scheme.school.name if scheme.school else '',
                'total_weeks': scheme.total_weeks,
                'syllabus': scheme.syllabus,
                'updated_at': scheme.updated_at.strftime('%d %b %Y, %H:%M'),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Hitilafu: ' + str(e)[:100]}, status=500)


def ajax_load_scheme_by_id(request, scheme_id):
    """Load a specific SchemeOfWork by ID for viewing/editing from the library."""
    try:
        scheme = SchemeOfWork.objects.select_related('subject', 'school').get(id=scheme_id)
        if not scheme.scheme_data:
            return JsonResponse({'success': False, 'error': 'Scheme haina data.'}, status=404)
        return JsonResponse({
            'success': True,
            'data': scheme.scheme_data,
            'saved_id': scheme.id,
            'meta': {
                'subject': scheme.subject.name if scheme.subject else '',
                'class_name': scheme.class_name,
                'term': scheme.term,
                'year': scheme.year,
                'teacher_name': scheme.teacher_name or '',
                'school_name': scheme.school.name if scheme.school else '',
                'total_weeks': scheme.total_weeks,
                'syllabus': scheme.syllabus,
                'updated_at': scheme.updated_at.strftime('%d %b %Y, %H:%M'),
            }
        })
    except SchemeOfWork.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Scheme haipatikani.'}, status=404)


# =============================================================================
# LESSON PLAN
# =============================================================================

def lesson_plan_view(request):
    """Display lesson plan generator form — requires TLM registration."""
    teacher = get_tlm_teacher(request)
    if not teacher:
        return redirect(f"{reverse('curriculum:teacher_register')}?next={reverse('curriculum:lesson_plan')}")
    
    education_levels = EducationLevel.objects.all().order_by('order')

    import json as _json
    classes_by_level = {}
    for cl in ClassLevel.objects.select_related('education_level').order_by('education_level', 'order'):
        classes_by_level.setdefault(cl.education_level_id, []).append({'id': cl.id, 'name': cl.name})

    # Filter subjects by education level (Primary → primary, Advanced → advanced, Ordinary → secondary)
    def _subjects_for_level(level_name):
        name_lower = level_name.lower()
        if 'primary' in name_lower:
            return list(Subject.objects.filter(level='primary').order_by('name').values('id', 'name'))
        elif 'advanced' in name_lower:
            return list(Subject.objects.filter(level='advanced').order_by('name').values('id', 'name'))
        else:
            # Ordinary Level → secondary subjects
            return list(Subject.objects.filter(level='secondary').order_by('name').values('id', 'name'))

    subjects_by_level = {
        lvl.id: _subjects_for_level(lvl.name)
        for lvl in education_levels
    }

    student = None
    school = None
    if request.user.is_authenticated:
        try:
            student = StudentTeacher.objects.select_related('selected_school').get(user=request.user)
            school = student.selected_school
            if not school:
                app = StudentApplication.objects.filter(
                    student=student, status='approved'
                ).select_related('school').first()
                if app:
                    school = app.school
        except StudentTeacher.DoesNotExist:
            pass

    # Get teacher info for auto-fill
    teacher_name = teacher.full_name if teacher else ''
    teacher_school_name = teacher.school.name if teacher and teacher.school else ''
    teacher_school_level = teacher.school.level if teacher and teacher.school else ''
    teacher_subject_id = teacher.subject.id if teacher and teacher.subject else ''
    teacher_subject_name = teacher.subject.name if teacher and teacher.subject else ''
    teacher_subject_level = teacher.subject.level if teacher and teacher.subject else ''
    teacher_class_name = teacher.class_name if teacher else ''
    teacher_stream = teacher.stream if teacher else ''
    teacher_total_boys = teacher.total_boys if teacher else 0
    teacher_total_girls = teacher.total_girls if teacher else 0

    return render(request, 'curriculum/lesson_plan.html', {
        'education_levels': education_levels,
        'classes_by_level_json': _json.dumps(classes_by_level),
        'subjects_by_level_json': _json.dumps(subjects_by_level),
        'student': student,
        'school': school,
        'teacher': teacher,
        'teacher_name': teacher_name,
        'teacher_school_name': teacher_school_name,
        'teacher_school_level': teacher_school_level,
        'teacher_subject_id': teacher_subject_id,
        'teacher_subject_name': teacher_subject_name,
        'teacher_subject_level': teacher_subject_level,
        'teacher_class_name': teacher_class_name,
        'teacher_stream': teacher_stream,
        'teacher_total_boys': teacher_total_boys,
        'teacher_total_girls': teacher_total_girls,
    })


def ajax_generate_lessonplan(request):
    """Generate lesson plan using AI — follows Tanzanian Teacher's Lesson Plan format."""
    if client is None:
        return JsonResponse({'success': False, 'error': 'Huduma ya AI haitumiki.'}, status=503)

    if request.method != 'POST':
        return JsonResponse({'success': False}, status=400)

    try:
        data = json.loads(request.body)

        education_level = data.get('education_level', '')
        class_name = data.get('class_name', '')
        stream = data.get('stream', '')
        subject = data.get('subject', '')
        subject_id = data.get('subject_id', '')
        topic = data.get('topic', '')
        subtopic = data.get('subtopic', '')
        term = data.get('term', 'I')
        year = data.get('year', 2026)
        duration = int(data.get('duration', 40))
        total_boys = data.get('total_boys', '')
        total_girls = data.get('total_girls', '')
        total_students = data.get('total_students', '')
        present_boys = data.get('present_boys', '')
        present_girls = data.get('present_girls', '')
        present_students = data.get('present_students', '')
        teacher_name = data.get('teacher_name', '')
        school_name = data.get('school_name', '')

        full_class = f"{class_name}{stream}" if stream else class_name

        # Calculate IDDR time allocation
        intro_time = max(5, int(duration * 0.15))
        dev_time = max(10, int(duration * 0.40))
        design_time = max(8, int(duration * 0.30))
        real_time = max(5, int(duration * 0.15))

        # ── Determine language for lesson plan (based on school level) ──
        _lp_tlm = get_tlm_teacher(request)
        _lp_school_level = _lp_tlm.school.level if _lp_tlm and _lp_tlm.school else ''
        _lp_subject_lower = subject.lower()
        if _lp_school_level == 'Primary':
            if _lp_subject_lower in ('english', 'english language'):
                lp_language_instruction = "LANGUAGE: Write ALL content in ENGLISH because this is an English subject for Primary school."
            else:
                lp_language_instruction = "LANGUAGE: Write ALL lesson content in KISWAHILI (Swahili). Only the headings/section titles can stay in English. ALL descriptions, activities, explanations, and assessment criteria MUST be in Swahili language. This is a Primary school subject."
        elif _lp_school_level == 'Secondary':
            if _lp_subject_lower in ('kiswahili', 'swahili'):
                lp_language_instruction = "LANGUAGE: Write ALL content in KISWAHILI (Swahili) because this is a Kiswahili subject for Secondary school."
            else:
                lp_language_instruction = "LANGUAGE: Write ALL content in ENGLISH. This is a Secondary school subject taught in English."
        else:
            lp_language_instruction = ""

        prompt = f"""Generate a TEACHER'S LESSON PLAN for a Tanzanian {education_level} classroom following the OFFICIAL TAMISEMI (PRIME MINISTER'S OFFICE - REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT) format.

============================================
PRIME MINISTER'S OFFICE
REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT
TEACHER'S LESSON PLAN
============================================

School: {school_name or '[School Name]'}
Teacher's Name: {teacher_name}
Subject: {subject}
Form/Class: {full_class}
Date: {datetime.now().strftime("%d/%m/%Y")}

Main Topic: {topic}
Sub-topic: {subtopic or 'N/A'}

Main Competence: Numbered format "1.0 Topic Name" - the REAL numbered competence from the Tanzanian syllabus for this subject/class.
Specific Competence: The REAL specific competence from the syllabus for this subtopic.

Term: {term}, Year: {year}
Duration: {duration} minutes

{lp_language_instruction}

-- STUDENT STATISTICS --
Registered Boys: {total_boys or 'N/A'}, Registered Girls: {total_girls or 'N/A'}, Total: {total_students or 'N/A'}
Present Boys: {present_boys or 'N/A'}, Present Girls: {present_girls or 'N/A'}, Present Total: {present_students or 'N/A'}

-- TEACHING PROCESS (IDDR Model) --

CRITICAL REQUIREMENTS - MUST FOLLOW EXACTLY:

!!! CONTENT MATCHING (CRITICAL): ALL content below MUST be specifically about:
   - Subject: {subject} (do NOT use a different subject)
   - Class: {full_class} (do NOT use a different form level)
   - Main Topic: "{topic}" (ALL content must relate DIRECTLY to this topic)
   - Sub-topic: "{subtopic or 'N/A'}" (ALL content must relate DIRECTLY to this subtopic)
   FAILURE: If you use content for a different topic, subject, or class, the output is WRONG.

1. main_competence: Use numbered format like "1.0 Topic Name" - the REAL Tanzanian syllabus competence for {subject} {full_class}
2. specific_competence: REAL subtopic-specific competence from the {subject} syllabus for this subtopic
3. specific_activity: Start with "By the end of this lesson, students should be able to:" then list 2-3 measurable outcomes SPECIFIC to "{topic}" and "{subtopic}"
4. references: Use the LATEST TIE textbook format - "Tanzania Institute of Education. (2024). {subject} for Secondary Schools Student's Book. Tanzania Institute of Education." If primary: "Tanzania Institute of Education. (2024). {subject} for Primary Schools Pupil's Book. Tanzania Institute of Education."
5. teaching_resources: MUST include specific, real resources for THIS topic (not generic) - e.g. TIE textbook pages, charts, real specimens, manila sheets, markers
6. remarks: Must be a detailed paragraph evaluating student achievement, specific challenges faced, and concrete way forward
7. student_statistics: Provide registered/present counts for girls and boys

!!! ALL lesson_development stages MUST use the EXACT topic "{topic}" and subtopic "{subtopic}":
   - Introduction: relate directly to "{topic}"
   - Competence Development: explore "{topic}" / "{subtopic}" specifically
   - Design: apply "{topic}" in real-life contexts
   - Realisation: assess understanding of "{topic}" / "{subtopic}"

Lesson Development uses the IDDR Model with these 5 columns per stage: stage, time, teaching_activities, learning_activities, assessment_criteria. Each stage MUST have detailed, Tanzania-specific content using CBC methodologies.

Output ONLY valid JSON with this EXACT structure:
{{
    "main_competence": "1.0 Topic Name - Overall competence statement",
    "specific_competence": "By the end of this topic, students should be able to...",
    "main_activity": "Within 1 period students should be able to...",
    "specific_activity": "By the end of this lesson, students should be able to:\n- (list 2-3 specific measurable outcomes)",
    "teaching_resources": "List specific resources for THIS lesson",
    "references": "Tanzania Institute of Education. (2024). {subject} for Secondary Schools Student's Book. Tanzania Institute of Education.",
    "student_statistics": {{"registered_girls": "", "registered_boys": "", "present_girls": "", "present_boys": ""}},
    "lesson_development": [
        {{"stage": "Introduction", "time": "{intro_time:02d}", "teaching_activities": "what the teacher does to activate prior knowledge (e.g. display pictures, ask questions)", "learning_activities": "what students do (e.g. observe images, respond to questions)", "assessment_criteria": "how to assess readiness (e.g. questions answered correctly)"}},
        {{"stage": "Competence Development", "time": "{dev_time:02d}", "teaching_activities": "guide students to explore the topic through group work and discussions", "learning_activities": "investigate, discuss in groups, and share findings", "assessment_criteria": "mastery of the competence (e.g. concepts clearly explained)"}},
        {{"stage": "Design", "time": "{design_time:02d}", "teaching_activities": "guide students to apply knowledge in real-life contexts through exercises or projects", "learning_activities": "complete exercises, create models, solve problems, present work", "assessment_criteria": "correct application of concepts in practical tasks"}},
        {{"stage": "Realisation", "time": "{real_time:02d}", "teaching_activities": "assess learning through formative assessment (oral questions, quiz) and provide feedback", "learning_activities": "respond to assessment questions, reflect on learning", "assessment_criteria": "achievement of lesson objectives"}}
    ],
    "remarks": "Detailed evaluation: strengths observed, specific challenges faced by students, and concrete way forward for the next lesson."
}}

All text values must be plain strings. Use REAL Tanzanian content. Return ONLY the JSON object, no extra text."""

        response = client.models.generate_content(model=model_name, contents=prompt)
        response_text = response.text

        cleaned = re.sub(r'```json\s*', '', response_text)
        cleaned = re.sub(r'```\s*', '', cleaned).strip()

        start_idx = cleaned.find('{')
        end_idx = cleaned.rfind('}')
        if start_idx != -1 and end_idx != -1:
            json_str = cleaned[start_idx:end_idx + 1]
            try:
                lesson_data = json.loads(json_str)
            except json.JSONDecodeError:
                logger.warning(f"[Lesson] JSON parse error - sanitizing control chars...")
                try:
                    lesson_data = json.loads(_sanitize_json_control_chars(json_str))
                except json.JSONDecodeError:
                    lesson_data = None
        else:
            lesson_data = None
        
        if lesson_data is None:
            # Could not parse JSON, use fallback default data
            # Fallback: generate sensible defaults
            lesson_data = {
                "main_competence": f"1.0 {topic} - Demonstrate understanding of {topic}",
                "specific_competence": f"Explain key concepts of {topic} based on the Tanzanian syllabus",
                "main_activity": f"Within 1 period students should be able to describe and apply {topic}",
                "specific_activity": f"By the end of this lesson, students should be able to:\n- Define {topic}\n- Explain key concepts of {topic}\n- Apply {topic} in real-life situations",
                "teaching_resources": "TIE textbook, Chalkboard/Whiteboard, Charts, Real objects, Manila sheets, Markers",
                "references": f"Tanzania Institute of Education. (2024). {subject} for Secondary Schools Student's Book. Tanzania Institute of Education.",
                "lesson_development": [
                    {"stage": "Introduction", "time": f"{intro_time:02d}", "teaching_activities": f"Display pictures/video about {topic}. Ask students questions to activate prior knowledge.", "learning_activities": "Observe pictures and respond to questions.", "assessment_criteria": "Questions about the lesson are answered."},
                    {"stage": "Competence Development", "time": f"{dev_time:02d}", "teaching_activities": f"Guide students in groups to explore {topic}. Provide guiding questions and resources.", "learning_activities": "Discuss in groups and share findings.", "assessment_criteria": "Concepts taught are clearly explained."},
                    {"stage": "Design", "time": f"{design_time:02d}", "teaching_activities": f"Ask students to apply knowledge of {topic} in real-life contexts through exercises.", "learning_activities": "Complete exercises and present findings.", "assessment_criteria": "Correct application of concepts."},
                    {"stage": "Realisation", "time": f"{real_time:02d}", "teaching_activities": "Assess student understanding through oral questions or short quiz. Provide feedback.", "learning_activities": "Respond to assessment questions and reflect.", "assessment_criteria": "Achievement of lesson objectives."}
                ],
                "student_statistics": {"registered_girls": "", "registered_boys": "", "present_girls": "", "present_boys": ""},
                "remarks": f"The students were able to explain {topic} due to the use of interactive teaching and learning methods. However, some students need more clarification. I will address this in the next lesson through remedial activities."
            }

        saved_id = None
        try:
            tlm_teacher = get_tlm_teacher(request)
            student = None
            school = None
            if request.user.is_authenticated:
                try:
                    student = StudentTeacher.objects.get(user=request.user)
                    school = student.selected_school
                except StudentTeacher.DoesNotExist:
                    pass
            elif tlm_teacher and tlm_teacher.school:
                school = tlm_teacher.school
            
            if school:
                level_map = {'primary school': 'primary', 'ordinary level': 'ordinary', 'advanced level': 'advanced'}
                edu_level = level_map.get((education_level or '').lower(), 'ordinary')
                subj_obj = None
                if subject_id:
                    try:
                        subj_obj = Subject.objects.get(id=int(subject_id))
                    except (Subject.DoesNotExist, ValueError):
                        pass
                if not subj_obj and subject:
                    subj_obj = Subject.objects.filter(name__iexact=subject).first()
                if subj_obj:
                    # Build lesson_development for DB (map new keys to old keys)
                    lp_development = []
                    for stage in lesson_data.get('lesson_development', []):
                        lp_development.append({
                            'stage': stage.get('stage', ''),
                            'time': stage.get('time', '') + ' min',
                            'teacher_activities': stage.get('teaching_activities', ''),
                            'student_activities': stage.get('learning_activities', ''),
                            'assessment_criteria': stage.get('assessment_criteria', ''),
                        })
                    lp_obj = LessonPlan.objects.create(
                        student=student, school=school, subject=subj_obj,
                        education_level=edu_level, class_name=class_name,
                        term=term, year=int(year), topic=topic, subtopic=subtopic or '',
                        date=timezone.now().date(), duration=duration,
                        total_boys=int(total_boys) if total_boys else 0,
                        total_girls=int(total_girls) if total_girls else 0,
                        total_students=int(total_students) if total_students else 0,
                        present_boys=int(present_boys) if present_boys else 0,
                        present_girls=int(present_girls) if present_girls else 0,
                        present_students=int(present_students) if present_students else 0,
                        teacher_name=teacher_name or (student.full_name if student else ''),
                        main_competence=lesson_data.get('main_competence', ''),
                        specific_competence=lesson_data.get('specific_competence', ''),
                        previous_knowledge=lesson_data.get('specific_activity', ''),
                        learning_objectives=[lesson_data.get('specific_activity', '')],
                        teaching_methods=[],
                        teaching_resources=[lesson_data.get('teaching_resources', '')],
                        lesson_development=lp_development,
                        remarks=lesson_data.get('remarks', ''),
                        generated_by_ai=True,
                    )
                    saved_id = lp_obj.id
        except Exception as save_err:
            logger.warning(f"[Curriculum] LessonPlan save error: {save_err}")

        return JsonResponse({'success': True, 'data': lesson_data, 'saved_id': saved_id})

    except Exception as e:
        import traceback
        traceback.print_exc()
        raw = str(e)
        logger.error(f"[Lesson Gen Error] {type(e).__name__}: {raw[:300]}")
        if '413' in raw or 'request too large' in raw.lower():
            msg = f"Ombi ni kubwa mno kwa AI. Jaribu kupunguza maelezo au kubadili somo. Hitilafu: {raw[:200]}"
        elif 'quota' in raw.lower() or '429' in raw or 'rate' in raw.lower():
            msg = f"Kikomo cha matumizi: {raw[:200]}"
        else:
            msg = f"Hitilafu ya AI: {raw[:200]}"
        return JsonResponse({'success': False, 'error': msg}, status=500)


def download_lesson_plan_pdf(request):
    """Export Lesson Plan as PDF — supports new Tanzanian format + old format."""
    if request.method != 'POST':
        return HttpResponse("Invalid request", status=400)

    data = json.loads(request.body)
    lesson = data.get('lesson_data', {})
    form = data.get('form_data', {})

    # Helper: get value from new key or old key
    def _get(new_key, old_key, default=''):
        return lesson.get(new_key, lesson.get(old_key, default))

    # ── Create Tanzania flag watermark ──
    _tz_watermark = None
    if PILImage:
        try:
            _flag_path = os.path.join(os.path.dirname(__file__), 'static', 'curriculum', 'tz_flag.png')
            if os.path.exists(_flag_path):
                _pil_img = PILImage.open(_flag_path).convert('RGBA')
                _r, _g, _b, _a = _pil_img.split()
                _new_a = _a.point(lambda x: int(x * 0.10))
                _faded = PILImage.merge('RGBA', (_r, _g, _b, _new_a))
                _buf = BytesIO()
                _faded.save(_buf, format='PNG')
                _buf.seek(0)
                _tz_watermark = _buf
        except Exception:
            pass

    # ── Cover page: professional border drawing ──
    def _lp_cover(can, doc_obj):
        """Draw professional double-border frame with flag watermark."""
        can.saveState()
        pw = doc_obj.pagesize[0]
        ph = doc_obj.pagesize[1]
        # Outer gold border (thick)
        can.setStrokeColor(GOLD)
        can.setLineWidth(3.5)
        can.rect(30, 30, pw - 60, ph - 60)
        # Inner navy border (thin)
        can.setStrokeColor(NAVY)
        can.setLineWidth(1.5)
        can.rect(36, 36, pw - 72, ph - 72)
        # Top gold accent bar
        can.setStrokeColor(GOLD)
        can.setLineWidth(4)
        can.line(36, ph - 55, pw - 36, ph - 55)
        # Bottom gold accent bar
        can.line(36, 55, pw - 36, 55)
        # Top-left corner square
        can.setFillColor(GOLD)
        can.rect(36, ph - 26, 14, 8, fill=1, stroke=0)
        # Top-right corner square
        can.rect(pw - 50, ph - 26, 14, 8, fill=1, stroke=0)
        # Bottom-left corner square
        can.rect(36, 36, 14, 8, fill=1, stroke=0)
        # Bottom-right corner square
        can.rect(pw - 50, 36, 14, 8, fill=1, stroke=0)
        # ── Draw Tanzania flag watermark ──
        if _tz_watermark:
            try:
                _tz_watermark.seek(0)
                fw = pw * 0.45
                fh = fw * 2.0 / 3.0
                can.drawImage(_tz_watermark, pw/2 - fw/2, ph/2 - fh/2,
                              width=fw, height=fh, mask='auto')
            except Exception:
                pass
        can.restoreState()

    # ── Page header (appears from page 2 onwards) ──
    def _lp_header(can, doc_obj):
        """Draw NAME OF SCHOOL / TEACHER header bar on pages 2+."""
        can.saveState()
        can.setFont('Helvetica-Bold', 7)
        can.setFillColor(NAVY)
        pw = doc_obj.pagesize[0]
        ph = doc_obj.pagesize[1]
        sn = form.get('school_name', '____________________')
        tn = form.get('teacher_name', '____________________')
        sbj = form.get('subject', '')
        cls = form.get('class_name', '')
        trm = form.get('term', '')
        yr = form.get('year', '')
        can.drawString(36, ph - 18, f"NAME OF SCHOOL: {sn}")
        can.drawCentredString(pw / 2, ph - 18, f"SUBJECT: {sbj}")
        can.drawRightString(pw - 36, ph - 18, f"CLASS: {cls}")
        can.drawString(36, ph - 30, f"TEACHER'S NAME: {tn}")
        can.drawCentredString(pw / 2, ph - 30, f"TERM: {trm}")
        can.drawRightString(pw - 36, ph - 30, f"YEAR: {yr}")
        can.setStrokeColor(GOLD)
        can.setLineWidth(0.8)
        can.line(36, ph - 34, pw - 36, ph - 34)
        can.restoreState()

    NAVY = colors.HexColor('#0A2B5E')
    GOLD = colors.HexColor('#C8900A')
    DARK_GOLD = colors.HexColor('#A67B07')
    LIGHT = colors.HexColor('#EEF1F6')
    STRIPE = colors.HexColor('#F4F7FF')
    BORDER = colors.HexColor('#9BAAC4')

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=36, leftMargin=36, topMargin=40, bottomMargin=30)
    elements = []

    normal = ParagraphStyle('LP_N', fontName='Helvetica', fontSize=9, leading=13, wordWrap='LTR', spaceAfter=3)
    section_hdr = ParagraphStyle('LP_H', fontName='Helvetica-Bold', fontSize=10, textColor=NAVY, spaceBefore=10, spaceAfter=4)
    cell_s = ParagraphStyle('LP_C', fontName='Helvetica', fontSize=8, leading=11, wordWrap='LTR')
    hdr_s = ParagraphStyle('LP_CH', fontName='Helvetica-Bold', fontSize=8, leading=11, textColor=colors.white, wordWrap='LTR', alignment=1)
    label_s = ParagraphStyle('LP_L', fontName='Helvetica-Bold', fontSize=8, leading=11, textColor=NAVY)
    title_s = ParagraphStyle('LP_TITLE', fontName='Helvetica-Bold', fontSize=16, alignment=1, textColor=NAVY, spaceAfter=1)
    subtitle_s = ParagraphStyle('LP_SUBTITLE', fontName='Helvetica-Bold', fontSize=8, alignment=1, textColor=DARK_GOLD, spaceAfter=1)

    # ── Cover page: decorative top lines ──
    elements.append(HRFlowable(width="100%", thickness=2.5, color=GOLD, spaceAfter=2))
    elements.append(HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceAfter=10))

    # ── TAMISEMI Header (centered, bold) ──
    elements.append(Paragraph(
        "PRIME MINISTER'S OFFICE",
        ParagraphStyle('MH1', fontName='Helvetica-Bold', fontSize=13, alignment=1,
                       textColor=NAVY, spaceAfter=2)))
    elements.append(Paragraph(
        "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT",
        ParagraphStyle('MH2', fontName='Helvetica-Bold', fontSize=10, alignment=1,
                       textColor=NAVY, spaceAfter=2)))
    elements.append(HRFlowable(width="50%", thickness=1, color=GOLD, spaceAfter=6))

    # ── Title ──
    elements.append(Paragraph("TEACHER'S LESSON PLAN",
        ParagraphStyle('LP_T', fontName='Helvetica-Bold', fontSize=14, alignment=1,
                       textColor=NAVY, spaceAfter=2)))
    elements.append(Paragraph(
        f"{form.get('subject','')}  |  {form.get('class_name','')}  |  Term {form.get('term','')} {form.get('year','')}",
        ParagraphStyle('LP_S', fontSize=9, alignment=1, textColor=colors.grey, spaceAfter=6)))

    # ── Cover info: styled table ──
    lbl = ParagraphStyle('lbl', fontName='Helvetica-Bold', fontSize=10, textColor=colors.white, leading=14)
    val = ParagraphStyle('val', fontName='Helvetica', fontSize=10, textColor=colors.HexColor('#222222'), leading=14)
    info_rows = [
        [Paragraph("Teacher's Name", lbl), Paragraph(form.get('teacher_name',''), val)],
        [Paragraph('School Name', lbl), Paragraph(form.get('school_name','____________________'), val)],
        [Paragraph('Subject', lbl), Paragraph(form.get('subject',''), val)],
        [Paragraph('Class', lbl), Paragraph(form.get('class_name',''), val)],
        [Paragraph('Term', lbl), Paragraph(form.get('term',''), val)],
        [Paragraph('Year', lbl), Paragraph(str(form.get('year','')), val)],
        [Paragraph('Duration', lbl), Paragraph(form.get('duration','') + ' min', val)],
        [Paragraph('Topic', lbl), Paragraph(form.get('topic',''), val)],
    ]
    info_table = Table(info_rows, colWidths=[180, 220])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), NAVY),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.white),
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#FAFBFD')),
        ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.HexColor('#FAFBFD'), STRIPE]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('BOX', (0, 0), (-1, -1), 2, GOLD),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, GOLD),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(info_table)
    # ── PageBreak: Cover page ends here, lesson content starts on page 2 ──
    elements.append(PageBreak())

    def P(txt, st=normal):
        return Paragraph(str(txt or ''), st)

    meta_rows = [
        [P('Teacher', label_s), P(form.get('teacher_name', '')),
         P('Subject', label_s), P(form.get('subject', ''))],
        [P('Class', label_s), P(form.get('class_name', '')),
         P('Term/Year', label_s), P(f"Term {form.get('term','')} {form.get('year','')}")],
        [P('Topic', label_s), P(form.get('topic', '')),
         P('Subtopic', label_s), P(form.get('subtopic', ''))],
        [P('Duration', label_s), P(f"{form.get('duration','')} minutes"),
         P('Date', label_s), P(str(timezone.now().date()))],
        [P('Students', label_s),
         P(f"Registered: B:{form.get('total_boys','')} G:{form.get('total_girls','')} T:{form.get('total_students','')} | Present: B:{form.get('present_boys','')} G:{form.get('present_girls','')} T:{form.get('present_students','')}"),
         P(''), P('')],
    ]
    meta_tbl = Table(meta_rows, colWidths=[72, 188, 72, 191])
    meta_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), LIGHT),
        ('BACKGROUND', (2, 0), (2, -1), LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, -1), (-1, -1), 1.2, GOLD),
    ]))
    elements.append(meta_tbl)
    elements.append(Spacer(1, 10))

    for label, key, fallback in [('Main Competence', 'main_competence', ''),
                       ('Specific Competence', 'specific_competence', ''),
                       ('Main Activity', 'main_activity', ''),
                       ('Specific Activity', 'specific_activity', 'previous_knowledge')]:
        val = lesson.get(key, lesson.get(fallback, '')) if fallback else lesson.get(key, '')
        if val:
            elements.append(Paragraph(f"<b>{label}:</b>  {val}", normal))

    # Teaching & Learning Resources (string in new format, array in old)
    tlr = lesson.get('teaching_resources', '')
    if tlr:
        elements.append(Paragraph("Teaching & Learning Resources", section_hdr))
        if isinstance(tlr, list):
            for item in tlr:
                elements.append(Paragraph(f"<bullet>•</bullet> {item}",
                    ParagraphStyle('LP_B', fontName='Helvetica', fontSize=9, leading=13, leftIndent=14, wordWrap='LTR')))
        else:
            elements.append(Paragraph(f"{tlr}", normal))

    # References
    ref = lesson.get('references', '')
    if ref:
        elements.append(Paragraph("References", section_hdr))
        elements.append(Paragraph(f"{ref}", normal))

    ld = lesson.get('lesson_development', [])
    if ld:
        elements.append(Paragraph("Lesson Development (IDDR Model)", section_hdr))
        ld_headers = ['Stage', 'Time', 'Teaching Activities', 'Learning Activities', 'Assessment Criteria']
        ld_data = [[Paragraph(h, hdr_s) for h in ld_headers]]
        for i, stage in enumerate(ld):
            bg = colors.white if i % 2 == 0 else STRIPE
            ld_data.append([
                Paragraph(str(stage.get('stage', stage.get('phase', '')) or ''), cell_s),
                Paragraph(str(stage.get('time', '') or ''), cell_s),
                Paragraph(str(stage.get('teaching_activities', stage.get('teacher_activities', '')) or ''), cell_s),
                Paragraph(str(stage.get('learning_activities', stage.get('student_activities', '')) or ''), cell_s),
                Paragraph(str(stage.get('assessment_criteria', '') or ''), cell_s),
            ])
        ld_tbl = Table(ld_data, colWidths=[72, 38, 118, 118, 105], repeatRows=1)
        ld_ts = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('LINEBELOW', (0, 0), (-1, 0), 1.2, GOLD),
            ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(ld_data)):
            ld_ts.append(('BACKGROUND', (0, i), (-1, i), STRIPE if i % 2 == 0 else colors.white))
        ld_tbl.setStyle(TableStyle(ld_ts))
        elements.append(ld_tbl)

    remarks = lesson.get('remarks', '')
    if remarks:
        elements.append(Spacer(1, 8))
        elements.append(Paragraph("Remarks", section_hdr))
        if isinstance(remarks, dict):
            for label, key in [('1. Strength', 'strength'), ('2. Weakness', 'weakness'), ('3. Way Forward', 'way_forward')]:
                val = remarks.get(key, '') or '...............................................'
                elements.append(Paragraph(f"<b>{label}:</b>  {val}", normal))
        else:
            elements.append(Paragraph(str(remarks), normal))

    doc.build(elements, onFirstPage=_lp_cover, onLaterPages=_lp_header)
    buffer.seek(0)
    safe_name = f"LessonPlan_{form.get('subject','')}_{form.get('topic','')}".replace(' ', '_')
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{safe_name}.pdf"'
    return response


def download_lesson_plan_word(request):
    """Export Lesson Plan as Word (.docx)."""
    if request.method != 'POST':
        return HttpResponse("Invalid request", status=400)

    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    data = json.loads(request.body)
    lesson = data.get('lesson_data', {})
    form = data.get('form_data', {})

    doc = Document()
    doc.add_heading('LESSON PLAN', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta_table = doc.add_table(rows=5, cols=4)
    meta_table.style = 'Table Grid'
    rows = meta_table.rows

    def _set(r, c, text, bold=False):
        cell = rows[r].cells[c]
        cell.text = text
        if bold and cell.paragraphs[0].runs:
            cell.paragraphs[0].runs[0].bold = True

    _set(0, 0, 'Teacher:', True)
    _set(0, 1, form.get('teacher_name', ''))
    _set(0, 2, 'Subject:', True)
    _set(0, 3, form.get('subject', ''))
    _set(1, 0, 'Class:', True)
    _set(1, 1, form.get('class_name', ''))
    _set(1, 2, 'Term/Year:', True)
    _set(1, 3, f"Term {form.get('term','')} {form.get('year','')}")
    _set(2, 0, 'Topic:', True)
    _set(2, 1, form.get('topic', ''))
    _set(2, 2, 'Subtopic:', True)
    _set(2, 3, form.get('subtopic', ''))
    _set(3, 0, 'Duration:', True)
    _set(3, 1, f"{form.get('duration','')} min")
    _set(3, 2, 'Date:', True)
    _set(3, 3, str(timezone.now().date()))
    _set(4, 0, 'Students:', True)
    tb = form.get('total_boys', '')
    tg = form.get('total_girls', '')
    ts = form.get('total_students', '')
    pb = form.get('present_boys', '')
    pg = form.get('present_girls', '')
    ps = form.get('present_students', '')
    _set(4, 1, f"Reg: B:{tb} G:{tg} T:{ts} | Pres: B:{pb} G:{pg} T:{ps}")

    doc.add_paragraph()

    for label, key in [('Main Competence', 'main_competence'),
                       ('Specific Competence', 'specific_competence'),
                       ('Main Activity', 'main_activity'),
                       ('Specific Activity', 'specific_activity')]:
        val = lesson.get(key, '')
        if not val:
            val = lesson.get({'Main Activity': None, 'Specific Activity': 'previous_knowledge'}.get(key, ''), '')
        if val:
            p = doc.add_paragraph()
            p.add_run(f"{label}: ").bold = True
            p.add_run(str(val))

    # Teaching & Learning Resources
    tlr = lesson.get('teaching_resources', '')
    if tlr:
        doc.add_heading('Teaching & Learning Resources', level=2)
        if isinstance(tlr, list):
            for item in tlr:
                doc.add_paragraph(str(item), style='List Bullet')
        else:
            doc.add_paragraph(str(tlr))

    # References
    ref = lesson.get('references', '')
    if ref:
        p = doc.add_paragraph()
        p.add_run('References: ').bold = True
        p.add_run(str(ref))

    ld = lesson.get('lesson_development', [])
    if ld:
        doc.add_heading('Lesson Development (IDDR Model)', level=2)
        ld_table = doc.add_table(rows=1, cols=5)
        ld_table.style = 'Table Grid'
        hdr = ld_table.rows[0].cells
        for i, h in enumerate(['Stage', 'Time', 'Teaching Activities', 'Learning Activities', 'Assessment Criteria']):
            hdr[i].text = h
            hdr[i].paragraphs[0].runs[0].bold = True
        for stage in ld:
            row = ld_table.add_row().cells
            row[0].text = stage.get('stage', stage.get('phase', ''))
            row[1].text = stage.get('time', '')
            row[2].text = stage.get('teaching_activities', stage.get('teacher_activities', ''))
            row[3].text = stage.get('learning_activities', stage.get('student_activities', ''))
            row[4].text = stage.get('assessment_criteria', '')
            row[4].text = stage.get('assessment_criteria', '')

    remarks = lesson.get('remarks', '')
    if remarks:
        doc.add_heading('Remarks', level=2)
        if isinstance(remarks, dict):
            for label, key in [('1. Strength', 'strength'), ('2. Weakness', 'weakness'), ('3. Way Forward', 'way_forward')]:
                p = doc.add_paragraph()
                p.add_run(f"{label}: ").bold = True
                p.add_run(remarks.get(key, '') or '...............................................')
        else:
            p = doc.add_paragraph()
            p.add_run('Remarks: ').bold = True
            p.add_run(str(remarks))

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    safe_name = f"LessonPlan_{form.get('subject','')}_{form.get('topic','')}".replace(' ', '_')
    response = HttpResponse(buffer, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{safe_name}.docx"'
    return response


# =============================================================================
# SAVE EDITED SCHEME / LESSON PLAN
# =============================================================================

@require_POST
def ajax_save_scheme_edits(request):
    """Save edited scheme data back to DB."""
    try:
        data = json.loads(request.body)
        scheme_id = data.get('saved_id')
        scheme_data = data.get('scheme_data', [])
        
        if not scheme_data:
            return JsonResponse({'success': False, 'error': 'Hakuna data'}, status=400)
        
        if scheme_id:
            try:
                scheme = SchemeOfWork.objects.get(id=scheme_id)
                scheme.scheme_data = scheme_data
                scheme.save(update_fields=['scheme_data'])
            except SchemeOfWork.DoesNotExist:
                pass
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)[:200]}, status=500)


@require_POST
def ajax_save_lesson_edits(request):
    """Save edited lesson plan data back to DB (supports new + old key formats)."""
    try:
        data = json.loads(request.body)
        lesson_id = data.get('saved_id')
        lesson_data = data.get('lesson_data', {})
        form_data = data.get('form_data', {})
        
        if lesson_id:
            try:
                lp = LessonPlan.objects.get(id=lesson_id)
                # Map new keys AND old keys to DB fields
                # Main competence
                if lesson_data.get('main_competence'):
                    lp.main_competence = lesson_data['main_competence']
                # Specific competence
                if lesson_data.get('specific_competence'):
                    lp.specific_competence = lesson_data['specific_competence']
                # Previous knowledge (new: specific_activity, old: previous_knowledge)
                spec_act = lesson_data.get('specific_activity', lesson_data.get('previous_knowledge', ''))
                if spec_act:
                    lp.previous_knowledge = spec_act
                # Learning objectives (new data may not have this)
                if lesson_data.get('learning_objectives'):
                    lp.learning_objectives = lesson_data['learning_objectives']
                elif spec_act:
                    lp.learning_objectives = [spec_act]
                # Teaching methods (new data may not have this)
                if lesson_data.get('teaching_methods'):
                    lp.teaching_methods = lesson_data['teaching_methods']
                # Teaching resources (new: string, old: array)
                tlr = lesson_data.get('teaching_resources', '')
                if tlr:
                    if isinstance(tlr, str):
                        lp.teaching_resources = [tlr]
                    else:
                        lp.teaching_resources = tlr
                # Lesson development - map new keys to old keys for DB storage
                if lesson_data.get('lesson_development'):
                    mapped_dev = []
                    for stage in lesson_data['lesson_development']:
                        mapped_dev.append({
                            'stage': stage.get('stage', stage.get('phase', '')),
                            'time': stage.get('time', ''),
                            'teacher_activities': stage.get('teaching_activities', stage.get('teacher_activities', '')),
                            'student_activities': stage.get('learning_activities', stage.get('student_activities', '')),
                            'methods': stage.get('methods', ''),
                            'assessment_criteria': stage.get('assessment_criteria', ''),
                        })
                    lp.lesson_development = mapped_dev
                # Remarks (new: string, old: dict with strength/weakness/way_forward)
                if lesson_data.get('remarks'):
                    lp.remarks = lesson_data['remarks']
                # Teacher name
                if form_data.get('teacher_name'):
                    lp.teacher_name = form_data['teacher_name']
                # Topic
                if form_data.get('topic'):
                    lp.topic = form_data['topic']
                # Subtopic
                if form_data.get('subtopic') is not None:
                    lp.subtopic = form_data['subtopic']
                # Student statistics breakdown
                if form_data.get('total_boys'):
                    lp.total_boys = int(form_data['total_boys'])
                if form_data.get('total_girls'):
                    lp.total_girls = int(form_data['total_girls'])
                if form_data.get('present_boys'):
                    lp.present_boys = int(form_data['present_boys'])
                if form_data.get('present_girls'):
                    lp.present_girls = int(form_data['present_girls'])
                if form_data.get('total_students'):
                    lp.total_students = int(form_data['total_students'])
                if form_data.get('present_students'):
                    lp.present_students = int(form_data['present_students'])
                lp.save()
            except LessonPlan.DoesNotExist:
                pass
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)[:200]}, status=500)


def ajax_load_saved_lessonplan(request):
    """Load most recent saved LessonPlan from DB (works for both Django users & TLM teachers)."""
    try:
        tlm_teacher = get_tlm_teacher(request)
        lp = None
        if request.user.is_authenticated:
            try:
                student = StudentTeacher.objects.get(user=request.user)
                lp = (LessonPlan.objects
                      .filter(student=student)
                      .select_related('subject')
                      .order_by('-created_at')
                      .first())
            except StudentTeacher.DoesNotExist:
                pass
        if not lp and tlm_teacher and tlm_teacher.school:
            lp = (LessonPlan.objects
                  .filter(school=tlm_teacher.school, teacher_name=tlm_teacher.full_name)
                  .select_related('subject')
                  .order_by('-created_at')
                  .first())
        if not lp or not lp.lesson_development:
            return JsonResponse({'success': False, 'error': 'Hakuna mpango wa somo uliohifadhiwa.'}, status=404)
        # Build lesson_data with backward-compatible keys
        lesson_data = {
            'lesson_title': f"{lp.subject.name} - {lp.topic}",
            'main_competence': lp.main_competence,
            'specific_competence': lp.specific_competence,
            'main_activity': None,  # Not stored in old model
            'specific_activity': lp.previous_knowledge or '',
            'previous_knowledge': lp.previous_knowledge,
            'learning_objectives': lp.learning_objectives,
            'teaching_methods': lp.teaching_methods,
            'teaching_resources': lp.teaching_resources,
            'references': None,  # Not stored in old model
            'lesson_development': lp.lesson_development,
            'remarks': lp.remarks,
        }
        form_data = {
            'subject': lp.subject.name, 'class_name': lp.class_name,
            'term': lp.term, 'year': lp.year, 'topic': lp.topic,
            'subtopic': lp.subtopic, 'teacher_name': lp.teacher_name,
            'duration': lp.duration, 'total_students': lp.total_students,
            'present_students': lp.present_students,
        }
        return JsonResponse({'success': True, 'data': lesson_data, 'form_data': form_data, 'saved_id': lp.id})
    except StudentTeacher.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Wasifu haupatikani.'}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': 'Hitilafu: ' + str(e)[:200]}, status=500)


def ajax_load_lesson_by_id(request, lesson_id):
    """Load a specific LessonPlan by ID for viewing/editing from the library."""
    try:
        lp = LessonPlan.objects.select_related('subject', 'school').get(id=lesson_id)
        if not lp.lesson_development:
            return JsonResponse({'success': False, 'error': 'Lesson Plan haina data.'}, status=404)
        # Build lesson_data with backward-compatible keys
        lesson_data = {
            'lesson_title': f"{lp.subject.name} - {lp.topic}",
            'main_competence': lp.main_competence,
            'specific_competence': lp.specific_competence,
            'main_activity': None,  # Not stored in old model
            'specific_activity': lp.previous_knowledge or '',
            'previous_knowledge': lp.previous_knowledge,
            'learning_objectives': lp.learning_objectives,
            'teaching_methods': lp.teaching_methods,
            'teaching_resources': lp.teaching_resources,
            'references': None,  # Not stored in old model
            'lesson_development': lp.lesson_development,
            'remarks': lp.remarks,
        }
        form_data = {
            'subject': lp.subject.name, 'class_name': lp.class_name,
            'term': lp.term, 'year': lp.year, 'topic': lp.topic,
            'subtopic': lp.subtopic, 'teacher_name': lp.teacher_name,
            'duration': lp.duration, 'total_students': lp.total_students,
            'present_students': lp.present_students,
        }
        return JsonResponse({'success': True, 'data': lesson_data, 'form_data': form_data, 'saved_id': lp.id})
    except LessonPlan.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Lesson Plan haipatikani.'}, status=404)


# =============================================================================
# LOGBOOK
# =============================================================================

@login_required
def submit_logbook(request):
    """Submit daily logbook entry."""
    student = get_or_create_student_profile(request.user)
    today = timezone.now().date()

    if today.weekday() >= 5:
        messages.info(request, "Hakuna kazi ya uwanjani wikendi. Rudi tena Jumatatu.")
        return redirect(reverse('curriculum:dashboard'))

    if not student.selected_school:
        messages.error(request, "Lazima uchague shule kabla ya kujaza logbook.")
        return redirect(reverse('curriculum:dashboard'))

    school = student.selected_school
    logbook_entry = _cached_today_logbook(student, school, today)

    if request.method == 'POST':
        if logbook_entry is None:
            logbook_entry, _ = LogbookEntry.objects.get_or_create(
                student=student, date=today,
                defaults={'school': school, 'morning_check_in': timezone.now()}
            )
            _invalidate_today_logbook(student, today)

        form = LogbookForm(request.POST, instance=logbook_entry)

        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        is_location_verified = request.POST.get('is_location_verified', 'false') == 'true'

        days_swahili = {0: 'Jumatatu', 1: 'Jumanne', 2: 'Jumatano', 3: 'Alhamisi', 4: 'Ijumaa'}

        if not is_location_verified:
            messages.error(request, "Thibiti eneo lako kwanza kabla ya kuwasilisha logbook.")
            return render(request, 'curriculum/logbook.html', {
                'form': form, 'student': student, 'logbook_entry': logbook_entry,
                'today': today, 'today_name': days_swahili.get(today.weekday(), 'Leo'),
                'school': school, 'subjects': _cached_subjects(student),
                'location_error': True,
            })

        if not latitude or not longitude:
            messages.error(request, "Eneo halipatikani. Washa GPS na ujaribu tena.")
            return render(request, 'curriculum/logbook.html', {
                'form': form, 'student': student, 'logbook_entry': logbook_entry,
                'today': today, 'today_name': days_swahili.get(today.weekday(), 'Leo'),
                'school': school, 'subjects': _cached_subjects(student),
                'location_error': True,
            })

        try:
            lat = float(latitude)
            lng = float(longitude)
            logbook_entry.latitude = lat
            logbook_entry.longitude = lng
            logbook_entry.location_address = request.POST.get('location_address', '')

            if school and school.latitude and school.longitude:
                from geopy.distance import geodesic
                distance_m = geodesic((lat, lng), (school.latitude, school.longitude)).meters
                school_verified = distance_m <= 1000
            else:
                school_verified = (-11.8 <= lat <= -1.0) and (29.3 <= lng <= 40.5)

            logbook_entry.is_location_verified = school_verified
            logbook_entry.is_at_school = school_verified
        except (ValueError, TypeError) as e:
            messages.error(request, f"Hitilafu ya eneo: {e}")
            return render(request, 'curriculum/logbook.html', {
                'form': form, 'student': student, 'logbook_entry': logbook_entry,
                'today': today, 'today_name': days_swahili.get(today.weekday(), 'Leo'),
                'school': school, 'subjects': _cached_subjects(student),
            })

        if form.is_valid():
            entry = form.save(commit=False)
            try:
                entry.lessons_data = json.loads(request.POST.get('lessons_data', '[]'))
            except (ValueError, TypeError):
                entry.lessons_data = []

            entry.latitude = logbook_entry.latitude
            entry.longitude = logbook_entry.longitude
            entry.is_location_verified = logbook_entry.is_location_verified
            entry.is_at_school = logbook_entry.is_at_school
            entry.location_address = logbook_entry.location_address
            entry.save()
            _invalidate_today_logbook(student, today)

            if entry.is_location_verified:
                messages.success(request, "✅ Logbook imesajiliwa kikamilifu!")
            else:
                messages.warning(request, "⚠️ Logbook imesajiliwa. Eneo halikuthibitishwa.")

            return redirect(reverse('curriculum:logbook_history'))
        else:
            messages.error(request, "Tafadhali kagua makosa yaliyomo kwenye fomu.")
    else:
        form = LogbookForm(instance=logbook_entry)

    subjects = _cached_subjects(student)
    days_swahili = {0: 'Jumatatu', 1: 'Jumanne', 2: 'Jumatano', 3: 'Alhamisi', 4: 'Ijumaa'}

    return render(request, 'curriculum/logbook.html', {
        'form': form, 'student': student, 'logbook_entry': logbook_entry,
        'today': today, 'today_name': days_swahili.get(today.weekday(), 'Leo'),
        'school': school, 'subjects': subjects,
    })


@login_required
def logbook_history(request):
    """View logbook history."""
    student = get_or_create_student_profile(request.user)

    week_filter = request.GET.get('week')
    month_filter = request.GET.get('month')

    entries = LogbookEntry.objects.filter(student=student).select_related('subject_taught', 'school')

    if week_filter:
        try:
            year, week = map(int, week_filter.split('-W'))
            start_date = datetime.strptime(f'{year}-W{week}-1', "%Y-W%W-%w").date()
            entries = entries.filter(date__range=[start_date, start_date + timedelta(days=6)])
        except ValueError:
            messages.error(request, "Tarehe ya wiki si sahihi.")

    elif month_filter:
        try:
            year, month = map(int, month_filter.split('-'))
            entries = entries.filter(date__year=year, date__month=month)
        except ValueError:
            messages.error(request, "Tarehe ya mwezi si sahihi.")

    else:
        today = timezone.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        entries = entries.filter(date__range=[start_of_week, start_of_week + timedelta(days=4)])

    return render(request, 'curriculum/logbook_history.html', {
        'entries': entries.order_by('-date'), 'student': student,
    })


@login_required
def download_logbook_pdf(request, period_type=None):
    """Download logbook as PDF."""
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet

    student = get_or_create_student_profile(request.user)
    period_value = period_type or 'week'
    today = timezone.now().date()

    if period_value == 'today':
        entries = LogbookEntry.objects.filter(student=student, date=today)
        filename = f"logbook_{today}.pdf"
        title = f"Logbook — {today}"
    elif period_value == 'week':
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=4)
        entries = LogbookEntry.objects.filter(student=student, date__range=[start_of_week, end_of_week])
        filename = f"logbook_wiki_{start_of_week}.pdf"
        title = f"Logbook — Wiki {start_of_week} hadi {end_of_week}"
    elif period_value == 'month':
        start_of_month = today.replace(day=1)
        next_month = today.replace(day=28) + timedelta(days=4)
        end_of_month = next_month - timedelta(days=next_month.day)
        entries = LogbookEntry.objects.filter(student=student, date__range=[start_of_month, end_of_month])
        filename = f"logbook_mwezi_{today.year}_{today.month:02d}.pdf"
        title = f"Logbook — Mwezi {today.month}/{today.year}"
    else:
        entries = LogbookEntry.objects.filter(student=student)
        filename = f"logbook_zote_{today}.pdf"
        title = "Logbook Zote"

    entries = entries.order_by('date')

    NAVY = colors.HexColor('#0A2B5E')
    GOLD = colors.HexColor('#C8900A')
    LIGHT = colors.HexColor('#EEF1F6')
    WHITE = colors.white

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)

    styles = getSampleStyleSheet()
    s_title = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=14, textColor=NAVY, spaceAfter=4)
    s_sub = ParagraphStyle('sub', fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#4A5568'), spaceAfter=2)
    s_head = ParagraphStyle('head', fontName='Helvetica-Bold', fontSize=10, textColor=WHITE)
    s_label = ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=8, textColor=NAVY)
    s_body = ParagraphStyle('body', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#1A1A2E'), leading=11)
    s_small = ParagraphStyle('small', fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#4A5568'), leading=10)

    school_name = student.selected_school.name if student.selected_school else '—'
    district_name = (student.selected_school.district.name if student.selected_school and student.selected_school.district else '—')
    current_year = _cached_active_year()
    year_label = str(current_year) if current_year else '—'

    story = []
    story.append(Paragraph("WIZARA YA ELIMU, SAYANSI NA TEKNOLOJIA",
                           ParagraphStyle('gov', fontName='Helvetica-Bold', fontSize=11, textColor=NAVY, alignment=1)))
    story.append(Paragraph("Mfumo wa Ufuatiliaji wa Walimu Wanafunzi (IMS)",
                           ParagraphStyle('gov2', fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#4A5568'), alignment=1, spaceAfter=6)))
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=6))
    story.append(Paragraph(title, s_title))

    info_data = [
        [Paragraph('<b>Jina la Mwanafunzi:</b>', s_label), Paragraph(student.full_name, s_body),
         Paragraph('<b>Shule:</b>', s_label), Paragraph(school_name, s_body)],
        [Paragraph('<b>Wilaya:</b>', s_label), Paragraph(district_name, s_body),
         Paragraph('<b>Mwaka wa Masomo:</b>', s_label), Paragraph(year_label, s_body)],
        [Paragraph('<b>Tarehe ya Chapisha:</b>', s_label), Paragraph(str(today), s_body),
         Paragraph('<b>Idadi ya Siku:</b>', s_label), Paragraph(str(entries.count()), s_body)],
    ]
    info_tbl = Table(info_data, colWidths=[3.5 * cm, 5.5 * cm, 3.5 * cm, 5.5 * cm])
    info_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, NAVY),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CBD5E0')),
        ('PADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 10))

    day_names = {'Monday': 'Jumatatu', 'Tuesday': 'Jumanne', 'Wednesday': 'Jumatano',
                 'Thursday': 'Alhamisi', 'Friday': 'Ijumaa', 'Saturday': 'Jumamosi', 'Sunday': 'Jumapili'}

    for entry in entries:
        day_sw = day_names.get(entry.date.strftime('%A'), entry.date.strftime('%A'))
        gps_status = "✓ Imehakikiwa" if entry.is_location_verified else "✗ Haijahakikiwa"
        gps_color = colors.HexColor('#10B981') if entry.is_location_verified else colors.HexColor('#F59E0B')

        day_hdr = Table(
            [[Paragraph(f"{day_sw} — {entry.date}", s_head),
              Paragraph(f"GPS: {gps_status}", ParagraphStyle('gps', fontName='Helvetica-Bold', fontSize=8, textColor=gps_color))]],
            colWidths=[13 * cm, 5 * cm]
        )
        day_hdr.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), NAVY),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        story.append(day_hdr)

        lessons = entry.lessons_data if entry.lessons_data else []
        if not lessons:
            if entry.other_activities or entry.challenges_faced:
                extra_rows = []
                if entry.other_activities:
                    extra_rows.append([Paragraph('<b>Shughuli Nyingine</b>', s_label), Paragraph(entry.other_activities, s_body)])
                if entry.challenges_faced:
                    extra_rows.append([Paragraph('<b>Changamoto</b>', s_label), Paragraph(entry.challenges_faced, s_body)])
                if extra_rows:
                    extra_tbl = Table(extra_rows, colWidths=[4 * cm, 14 * cm])
                    extra_tbl.setStyle(TableStyle([
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
                        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CBD5E0')),
                        ('BACKGROUND', (0, 0), (0, -1), LIGHT),
                        ('PADDING', (0, 0), (-1, -1), 4),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ]))
                    story.append(extra_tbl)
            else:
                story.append(Paragraph("Hakuna data ya masomo.", s_small))
        else:
            for lesson in lessons:
                period_num = lesson.get('period', '?')
                subj = lesson.get('subject', '—')
                cls = lesson.get('class', '—')
                main_topic = lesson.get('main_topic', '—')
                activity = lesson.get('activity_type', '—')
                enrolled = lesson.get('enrolled', '—')
                present = lesson.get('present', '—')

                period_hdr = Table(
                    [[Paragraph(
                        f"Kipindi {period_num}  |  {subj}  |  Darasa: {cls}  |  Waliojumuishwa: {enrolled}  |  Waliopo: {present}  |  Aina: {activity}",
                        ParagraphStyle('ph', fontName='Helvetica-Bold', fontSize=8, textColor=WHITE))]],
                    colWidths=[18 * cm]
                )
                period_hdr.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), GOLD),
                    ('PADDING', (0, 0), (-1, -1), 5),
                ]))
                story.append(period_hdr)

                lesson_rows = [
                    [Paragraph('<b>Mada Kuu</b>', s_label), Paragraph(main_topic, s_body),
                     Paragraph('<b>Mada Ndogo</b>', s_label), Paragraph(lesson.get('subtopic', '—'), s_body)],
                    [Paragraph('<b>Mbinu</b>', s_label), Paragraph(lesson.get('methods', '—'), s_body),
                     Paragraph('<b>Vifaa</b>', s_label), Paragraph(lesson.get('teaching_aids', '—'), s_body)],
                ]
                lesson_tbl = Table(lesson_rows, colWidths=[3.5 * cm, 5.5 * cm, 3.5 * cm, 5.5 * cm])
                lesson_tbl.setStyle(TableStyle([
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
                    ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CBD5E0')),
                    ('BACKGROUND', (0, 0), (0, -1), LIGHT),
                    ('BACKGROUND', (2, 0), (2, -1), LIGHT),
                    ('PADDING', (0, 0), (-1, -1), 4),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(lesson_tbl)

        if entry.supervisor_remarks:
            sr_tbl = Table(
                [[Paragraph('<b>Maoni ya Msimamizi</b>', s_label), Paragraph(entry.supervisor_remarks, s_body)]],
                colWidths=[4 * cm, 14 * cm]
            )
            sr_tbl.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
                ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CBD5E0')),
                ('BACKGROUND', (0, 0), (0, -1), LIGHT),
                ('PADDING', (0, 0), (-1, -1), 4),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(sr_tbl)

        story.append(Spacer(1, 10))

    if not entries:
        story.append(Spacer(1, 20))
        story.append(Paragraph("Hakuna rekodi za logbook kwa kipindi kilichochaguliwa.", s_sub))

    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceBefore=10, spaceAfter=4))
    story.append(Paragraph("© Wizara ya Elimu, Sayansi na Teknolojia — IMS v2.1.0",
                           ParagraphStyle('footer', fontName='Helvetica', fontSize=7, textColor=colors.HexColor('#4A5568'), alignment=1)))

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def logbook_download_options(request):
    """Page for choosing download options."""
    student = get_or_create_student_profile(request.user)
    total_entries = LogbookEntry.objects.filter(student=student).count()
    this_week_entries = LogbookEntry.objects.filter(
        student=student, date__gte=timezone.now().date() - timedelta(days=7)
    ).count()

    return render(request, 'curriculum/logbook_download.html', {
        'student': student, 'total_entries': total_entries, 'this_week_entries': this_week_entries,
    })


# =============================================================================
# API HELPERS
# =============================================================================

def get_topics_by_subject(request):
    """AJAX: Get topics (from textbooks) for a given subject and class level."""
    subject_id = request.GET.get('subject_id')
    class_level_id = request.GET.get('class_level_id')
    
    if not subject_id:
        return JsonResponse([], safe=False)
    
    subject = Subject.objects.filter(id=subject_id).first()
    if not subject:
        return JsonResponse([], safe=False)
    
    # Map subject level to textbook education_level
    if subject.level == 'primary':
        edu_level = 'primary'
    else:
        # For secondary, check class level to determine ordinary vs advanced
        if class_level_id:
            cl = ClassLevel.objects.filter(id=class_level_id).first()
            if cl:
                cl_name = cl.name.lower()
                if 'form 5' in cl_name or 'form 6' in cl_name or 'advanced' in cl_name:
                    edu_level = 'advanced'
                else:
                    edu_level = 'ordinary'
            else:
                edu_level = 'ordinary'
        else:
            edu_level = 'ordinary'
    
    textbooks = Textbook.objects.filter(
        subject=subject,
        education_level=edu_level,
        is_active=True
    ).order_by('title').values('id', 'title')
    
    topics = list(textbooks)
    
    # If no textbooks found, return empty list
    return JsonResponse(topics, safe=False)


def get_classes_by_level(request):
    """AJAX: Get classes for a given education level."""
    level_id = request.GET.get('level_id')
    if not level_id:
        return JsonResponse([], safe=False)
    classes = ClassLevel.objects.filter(education_level_id=level_id).order_by('order')
    return JsonResponse([{'id': c.id, 'name': c.name} for c in classes], safe=False)


def get_subjects_by_level(request):
    """AJAX: Get subjects for a given education level.
    Primary School → primary subjects
    Ordinary/Advanced Level → secondary subjects
    """
    level_id = request.GET.get('level_id')
    if not level_id:
        return JsonResponse([], safe=False)
    level = EducationLevel.objects.filter(id=level_id).first()
    if not level:
        return JsonResponse([], safe=False)
    if 'primary' in level.name.lower():
        subjects = Subject.objects.filter(level='primary').order_by('name')
    elif 'advanced' in level.name.lower():
        subjects = Subject.objects.filter(level='advanced').order_by('name')
    else:
        # Ordinary Level → secondary subjects
        subjects = Subject.objects.filter(level='secondary').order_by('name')
    return JsonResponse([{'id': s.id, 'name': s.name} for s in subjects], safe=False)


def get_topics_ai(request):
    """
    AJAX: Use AI to generate a list of topics for a given subject and class level.
    Returns a JSON array of topic strings.
    """
    if client is None:
        return JsonResponse({'success': False, 'error': 'AI haitumiki'}, status=503)

    subject_id = request.GET.get('subject_id')
    class_name = request.GET.get('class_name', '')
    education_level = request.GET.get('education_level', '')

    if not subject_id:
        return JsonResponse({'success': False, 'error': 'subject_id inahitajika'}, status=400)

    subject = Subject.objects.filter(id=subject_id).first()
    if not subject:
        return JsonResponse({'success': False, 'error': 'Somo halipatikani'}, status=404)

    # ── Determine language based on school level (Primary vs Secondary) ──
    _is_primary = ('primary' in education_level.lower())
    _subject_lower = subject.name.lower()

    if _is_primary:
        if _subject_lower in ('english', 'english language'):
            language_rule = (
                f"LUGHA: Hii ni SHULE YA MSINGI na somo ni ENGLISH. "
                f"Topics ZOTE zirejeshwe kwa KIINGEREZA (English). "
                f"Kwa mfano: 'Parts of Speech', 'Tenses', 'Comprehension', 'Nouns', 'Verbs', 'Reading', 'Writing' n.k."
            )
        else:
            language_rule = (
                f"LUGHA: Hii ni SHULE YA MSINGI. Somo la {subject.name} linafundishwa kwa KISWAHILI. "
                f"Topics ZOTE lazima zirejeshwe kwa KISWAHILI. "
                f"Hata kama jina la somo ni Kiingereza (kama Science, Geography, civics), "
                f"topics zake kwa shule ya msingi lazima ziwe kwa KISWAHILI. "
                f"Kwa mfano: "
                f"- Sayansi (Science) → 'Viumbe Hai', 'Mwili na Afya', 'Mimea', 'Wanyama', 'Hali ya Hewa' n.k. "
                f"- Hisabati → 'Namba', 'Jiometri', 'Aljebra', 'Vipimo', 'Takwimu' n.k. "
                f"- Maarifa ya Jamii → 'Familia', 'Jamii', 'Uchumi', 'Utamaduni' n.k. "
                f"- Uraia na Maadili → 'Haki za Binadamu', 'Majukumu', 'Maadili' n.k. "
                f"- Mwili na Afya → 'Mwili wa Binadamu', 'Lishe', 'Afya na Usafi' n.k. "
                f"USIANDIKE topics kwa Kiingereza isipokuwa kwa somo la English pekee."
            )
    else:
        # Secondary / Advanced level
        if _subject_lower in ('kiswahili', 'swahili'):
            language_rule = (
                f"LUGHA: Hii ni SHULE YA SEKONDARI na somo ni Kiswahili. "
                f"Topics ZOTE zirejeshwe kwa KISWAHILI. "
                f"Kwa mfano: 'Fasihi Simulizi', 'Uchambuzi wa Riwaya', 'Matumizi ya Lugha' n.k."
            )
        else:
            language_rule = (
                f"LUGHA: Hii ni SHULE YA SEKONDARI. "
                f"Somo la {subject.name} linafundishwa kwa KIINGEREZA (isipokuwa Kiswahili). "
                f"Topics ZOTE zirejeshwe kwa KIINGEREZA. "
                f"Kwa mfano: 'Living Things', 'Matter', 'Energy', 'Algebra', 'Trigonometry', 'Cell Biology' n.k."
            )

    prompt = (
            f"Wewe ni mtaalamu wa mtaala wa Tanzania (TIE/SEQUIP). "
            f"Orodhesha mada kuu (topics) za somo la {subject.name} kwa darasa la {class_name} "
            f"katika ngazi ya {education_level} kwa mujibu wa mtaala wa TIE Tanzania. "
            f"\n\n"
            f"!!! HII NI MUHIMU SANA: TOPICS LAZIMA ZIWE ZA DARASA LA {class_name} PEKEE. "
            f"USIORODHESHE topics za darasa jingine! Kwa mfano: "
            f"- Kama ni Form 2 → orodhesha topics za Form 2 PEKEE (sio Form 1, sio Form 3, sio Form 4) "
            f"- Kama ni Form 1 → orodhesha topics za Form 1 PEKEE "
            f"- Kama ni Form 3 → orodhesha topics za Form 3 PEKEE "
            f"- Kama ni Form 4 → orodhesha topics za Form 4 PEKEE \n\n"
            f"MAKOSI: Topics lazima zilingane hasa na zile za vitabu vya TIE kwa darasa la {class_name}. "
            f"KAGUA: Hakikisha kila topic uliyoorodhesha ni ya {class_name} kulingana na silabasi ya TIE. "
            f"USIORODHESHE topic zozote za Form 1, Form 3, au Form 4 kama unataka topics za Form 2. \n"
            f"{language_rule}"
            f"\n"
            f"Rudisha TU JSON array ya string: [\"Topic 1\", \"Topic 2\", ...]. "
            f"USIANDIKE chochote kingine — JSON pekee."
        )

    try:
        response = client.models.generate_content(model=model_name, contents=prompt)
        text = response.text.strip()
        # Strip markdown code fences if present
        text = re.sub(r'```(?:json)?', '', text).strip()
        topics = json.loads(text)
        if isinstance(topics, list):
            return JsonResponse({'success': True, 'topics': topics})
        return JsonResponse({'success': True, 'topics': []})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)[:200]}, status=500)


def get_subtopics_ai(request):
    """
    AJAX: Use AI to generate subtopics for a given subject, class level, and topic.
    Returns a JSON array of subtopic strings.
    """
    if client is None:
        return JsonResponse({'success': False, 'error': 'AI haitumiki'}, status=503)

    subject_id = request.GET.get('subject_id')
    topic = request.GET.get('topic', '')
    class_name = request.GET.get('class_name', '')
    education_level = request.GET.get('education_level', '')

    if not subject_id or not topic:
        return JsonResponse({'success': False, 'error': 'subject_id na topic vinahitajika'}, status=400)

    subject = Subject.objects.filter(id=subject_id).first()
    if not subject:
        return JsonResponse({'success': False, 'error': 'Somo halipatikani'}, status=404)

    # ── Determine language based on school level (Primary vs Secondary) ──
    _is_primary = ('primary' in education_level.lower())
    _subject_lower = subject.name.lower()

    if _is_primary:
        if _subject_lower in ('english', 'english language'):
            language_rule = (
                f"LUGHA: Hii ni SHULE YA MSINGI na somo ni ENGLISH. "
                f"Subtopics ZOTE zirejeshwe kwa KIINGEREZA (English). "
                f"Kwa mfano: 'Nouns', 'Verbs', 'Pronouns', 'Present Tense', 'Past Tense', 'Comprehension' n.k."
            )
        else:
            language_rule = (
                f"LUGHA: Hii ni SHULE YA MSINGI. Somo la {subject.name} linafundishwa kwa KISWAHILI. "
                f"Subtopics ZOTE lazima zirejeshwe kwa KISWAHILI. "
                f"Hata kama jina la somo ni Kiingereza (kama Science, Geography, Civics), "
                f"subtopics zake kwa shule ya msingi lazima ziwe kwa KISWAHILI. "
                f"Kwa mfano: "
                f"- Sayansi (Science) → 'Viumbe Hai', 'Mimea', 'Wanyama', 'Mfumo wa Mwili' n.k. "
                f"- Hisabati → 'Namba Asilia', 'Sehemu', 'Desimali', 'Mizani', 'Ulinganifu' n.k. "
                f"- Maarifa ya Jamii → 'Familia yangu', 'Jamii yetu', 'Shughuli za Kiuchumi' n.k. "
                f"- Uraia na Maadili → 'Haki na Wajibu', 'Maadili ya Kiislamu/Kikristo', 'Usalama Barabarani' n.k. "
                f"USIANDIKE subtopics kwa Kiingereza isipokuwa kwa somo la English pekee."
            )
    else:
        # Secondary / Advanced level
        if _subject_lower in ('kiswahili', 'swahili'):
            language_rule = (
                f"LUGHA: Hii ni SHULE YA SEKONDARI na somo ni Kiswahili. "
                f"Subtopics ZOTE zirejeshwe kwa KISWAHILI. "
                f"Kwa mfano: 'Tamthilia', 'Ushairi', 'Insha', 'Sarufi', 'Matumizi ya Lugha' n.k."
            )
        else:
            language_rule = (
                f"LUGHA: Hii ni SHULE YA SEKONDARI. "
                f"Somo la {subject.name} linafundishwa kwa KIINGEREZA (isipokuwa Kiswahili). "
                f"Subtopics ZOTE zirejeshwe kwa KIINGEREZA. "
                f"Kwa mfano: 'Cell Division', 'Quadratic Equations', 'Chemical Bonding', 'Market Structure' n.k."
            )

    prompt = (
            f"Wewe ni mtaalamu wa mtaala wa Tanzania (TIE/SEQUIP). "
            f"Orodhesha mada ndogo (subtopics) za somo la {subject.name}, kwa mada kuu '{topic}', "
            f"kwa darasa la {class_name} ({education_level}) kwa mujibu wa mtaala wa TIE Tanzania. "
            f"\n\n"
            f"!!! HII NI MUHIMU SANA: SUBTOPICS LAZIMA ZIWE ZA DARASA LA {class_name} PEKEE. "
            f"USIORODHESHE subtopics za darasa jingine! Kama mada kuu '{topic}' inapatikana kwa darasa zaidi ya moja, "
            f"chagua subtopics za {class_name} PEKEE, sio za darasa lingine. \n\n"
            f"MAKOSI: Subtopics lazima zilingane na zile za vitabu vya TIE kwa darasa la {class_name}. "
            f"KAGUA mara mbili: Hakikisha subtopics zote ni za {class_name} kulingana na silabasi ya TIE. "
            f"{language_rule}"
            f"\n"
            f"Rudisha TU JSON array ya string: [\"Subtopic 1\", \"Subtopic 2\", ...]. "
            f"Kama hakuna subtopics, rudisha [] (array tupu). "
            f"USIANDIKE chochote kingine — JSON pekee."
        )

    try:
        response = client.models.generate_content(model=model_name, contents=prompt)
        text = response.text.strip()
        text = re.sub(r'```(?:json)?', '', text).strip()
        subtopics = json.loads(text)
        if isinstance(subtopics, list):
            return JsonResponse({'success': True, 'subtopics': subtopics})
        return JsonResponse({'success': True, 'subtopics': []})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)[:200]}, status=500)


def get_textbooks_by_level(request):
    """AJAX: Get textbooks/references for a given education level."""
    level_id = request.GET.get('level_id')
    if not level_id:
        return JsonResponse([], safe=False)
    level = EducationLevel.objects.filter(id=level_id).first()
    if not level:
        return JsonResponse([], safe=False)
    level_name = level.name.lower()
    level_map = {'primary': 'primary', 'ordinary': 'ordinary', 'advanced': 'advanced'}
    mapped = 'primary'
    for k, v in level_map.items():
        if k in level_name:
            mapped = v
            break
    textbooks = Textbook.objects.filter(education_level=mapped, is_active=True).order_by('title')
    return JsonResponse([{'id': t.id, 'title': t.title, 'publisher': t.publisher} for t in textbooks], safe=False)


# =============================================================================
# AJAX: Search schools (autocomplete)
# =============================================================================

def ajax_search_schools(request):
    """
    AJAX: Search schools by name (for autocomplete on registration).
    Returns JSON array of matching schools with id, name, level, district__name.
    """
    q = request.GET.get('q', '').strip()
    district_id = request.GET.get('district_id', '')
    if len(q) < 2 and not district_id:
        return JsonResponse([], safe=False)
    
    schools = School.objects.all()
    if q and len(q) >= 2:
        schools = schools.filter(name__icontains=q)
    if district_id:
        schools = schools.filter(district_id=district_id)
    
    schools = schools.select_related('district').order_by('name')[:30]
    return JsonResponse([{
        'id': s.id,
        'name': s.name,
        'level': s.level,
        'district_name': s.district.name,
    } for s in schools], safe=False)


# =============================================================================
# AJAX: Submit update comment/feedback
# =============================================================================

@require_POST
def ajax_submit_update_comment(request):
    """Submit a comment/feedback about system updates from teachers."""
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        teacher_name = data.get('teacher_name', '').strip()
        
        if not message:
            return JsonResponse({'success': False, 'error': 'Tafadhali andika maoni yako.'}, status=400)
        if not teacher_name:
            return JsonResponse({'success': False, 'error': 'Tafadhali ingiza jina lako.'}, status=400)
        
        teacher = get_tlm_teacher(request)
        teacher_school_name = teacher.school.name if teacher and teacher.school else ''
        
        testimonial = Testimonial.objects.create(
            teacher=teacher,
            teacher_name=teacher_name,
            school_name=teacher_school_name,
            message=message,
            is_approved=True,
        )
        
        return JsonResponse({'success': True, 'id': testimonial.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)[:200]}, status=500)


# =============================================================================
# LESSON NOTES — standalone teacher notes
# =============================================================================

def lesson_notes_view(request):
    """
    Lesson Notes page — teachers write their own reflections, methods, challenges.
    Notes are linked to the teacher's school level for language support.
    """
    teacher = get_tlm_teacher(request)
    if not teacher:
        return redirect(f"{reverse('curriculum:teacher_register')}?next={reverse('curriculum:lesson_notes')}")
    
    school_level = teacher.school.level if teacher and teacher.school else ''
    
    # Get all notes for this teacher
    notes = LessonNote.objects.filter(teacher=teacher).order_by('-created_at')[:50]
    
    # Subjects for dropdown
    subjects = Subject.objects.all().order_by('name')
    education_levels = EducationLevel.objects.all().order_by('order')
    
    return render(request, 'curriculum/lesson_notes.html', {
        'teacher': teacher,
        'school_level': school_level,
        'notes': notes,
        'subjects': subjects,
        'education_levels': education_levels,
        'teacher_name': teacher.full_name if teacher else '',
        'teacher_school_name': teacher.school.name if teacher and teacher.school else '',
    })


@require_POST
def ajax_save_lesson_note(request):
    """AJAX: Save a new lesson note or update existing one."""
    try:
        data = json.loads(request.body)
        teacher = get_tlm_teacher(request)
        if not teacher:
            return JsonResponse({'success': False, 'error': 'Tafadhali jisajili kwanza.'}, status=401)
        
        note_id = data.get('note_id')
        content = data.get('content', '').strip()
        subject = data.get('subject', '').strip()
        class_name = data.get('class_name', '').strip()
        topic = data.get('topic', '').strip()
        education_level = data.get('education_level', '').strip()
        
        if not content:
            return JsonResponse({'success': False, 'error': 'Tafadhali andika maelezo ya somo.'}, status=400)
        
        school = teacher.school if teacher.school else None
        
        if note_id:
            # Update existing note
            note = get_object_or_404(LessonNote, id=note_id, teacher=teacher)
            note.content = content
            note.subject = subject
            note.class_name = class_name
            note.topic = topic
            note.education_level = education_level
            note.save()
        else:
            # Create new note
            note = LessonNote.objects.create(
                teacher=teacher,
                teacher_name=teacher.full_name,
                school=school,
                school_name=school.name if school else '',
                education_level=education_level or 'ordinary',
                class_name=class_name,
                subject=subject,
                topic=topic,
                content=content,
            )
        
        return JsonResponse({'success': True, 'note_id': note.id, 'created': note.created_at.isoformat()})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)[:200]}, status=500)


def ajax_get_lesson_note(request, note_id):
    """AJAX: Get a single lesson note for editing."""
    teacher = get_tlm_teacher(request)
    if not teacher:
        return JsonResponse({'success': False, 'error': 'Una hitaji kujiandikisha.'}, status=401)
    try:
        note = LessonNote.objects.get(id=note_id, teacher=teacher)
        return JsonResponse({
            'success': True,
            'note': {
                'id': note.id,
                'content': note.content,
                'subject': note.subject,
                'class_name': note.class_name,
                'topic': note.topic,
                'education_level': note.education_level,
                'created_at': note.created_at.strftime('%d %b %Y, %H:%M'),
            }
        })
    except LessonNote.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Note haipatikani.'}, status=404)


@require_POST
def ajax_delete_lesson_note(request):
    """AJAX: Delete a lesson note."""
    teacher = get_tlm_teacher(request)
    if not teacher:
        return JsonResponse({'success': False}, status=401)
    try:
        data = json.loads(request.body)
        note_id = data.get('note_id')
        note = LessonNote.objects.get(id=note_id, teacher=teacher)
        note.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)[:200]}, status=500)

# =============================================================================
# TEACHER PROFILE UPDATE — auto-save teacher's class/stream/subject/students
# =============================================================================

@require_POST
def ajax_update_teacher_profile(request):
    """
    Update the TLM teacher's profile with data from scheme/lesson plan forms.
    Ensures OLD users who registered before auto-fill fields were added
    get their class_name, stream, subject, total_boys, total_girls saved.
    """
    teacher = get_tlm_teacher(request)
    if not teacher:
        return JsonResponse({'success': False, 'error': 'Haujasajiliwa. Tafadhali jisajili kwanza.'}, status=401)
    
    try:
        data = json.loads(request.body)
        changed = False
        
        class_name = data.get('class_name', '').strip()
        if class_name and teacher.class_name != class_name:
            teacher.class_name = class_name
            changed = True
        
        stream = data.get('stream', '').strip()
        if stream and teacher.stream != stream:
            teacher.stream = stream
            changed = True
        
        subject_name = data.get('subject_name', '').strip()
        if subject_name:
            subj = Subject.objects.filter(name__iexact=subject_name).first()
            if subj and teacher.subject != subj:
                teacher.subject = subj
                changed = True
        
        total_boys = data.get('total_boys')
        if total_boys:
            try:
                val = int(total_boys)
                if val > 0 and teacher.total_boys != val:
                    teacher.total_boys = val
                    changed = True
            except (ValueError, TypeError):
                pass
        
        total_girls = data.get('total_girls')
        if total_girls:
            try:
                val = int(total_girls)
                if val > 0 and teacher.total_girls != val:
                    teacher.total_girls = val
                    changed = True
            except (ValueError, TypeError):
                pass
        
        if changed:
            teacher.save(update_fields=['class_name', 'stream', 'subject', 'total_boys', 'total_girls'])
            logger.info(f"[Profile] Updated teacher {teacher.id} ({teacher.full_name})")
            return JsonResponse({'success': True, 'updated': True, 'message': 'Profile imehifadhiwa!'})
        
        return JsonResponse({'success': True, 'updated': False, 'message': 'Hakuna mabadiliko.'})
        
    except Exception as e:
        logger.error(f"[Profile Update Error] {e}")
        return JsonResponse({'success': False, 'error': str(e)[:200]}, status=500)


# =============================================================================
# SYLLABUS TOPICS & SUBTOPICS — Database-powered (TIE Syllabus)
# =============================================================================

def ajax_get_topics_db(request):
    """
    AJAX: Get topics from DB for a given subject and class name.
    Uses the TIE syllabus data seeded via the seed_tie_syllabus management command.
    Returns a JSON array of topic objects with id and name.
    """
    subject_id = request.GET.get('subject_id')
    class_name = request.GET.get('class_name', '').strip()
    
    if not subject_id or not class_name:
        return JsonResponse({'success': False, 'error': 'subject_id na class_name vinahitajika'}, status=400)
    
    # Map common class names (e.g., "Form 1" matches "Form 1" in DB)
    topics = SubjectTopic.objects.filter(
        subject_id=subject_id,
        class_name__iexact=class_name
    ).order_by('order').values('id', 'name')
    
    # If no topics found, try with broader matching
    if not topics.exists():
        # Try just with the form number (e.g., "1" from "Form 1")
        words = class_name.split()
        for w in words:
            if w.isdigit():
                topics = SubjectTopic.objects.filter(
                    subject_id=subject_id,
                    class_name__icontains=w
                ).order_by('order').values('id', 'name')
                break
    
    return JsonResponse({
        'success': True,
        'topics': list(topics),
        'count': topics.count(),
        'source': 'database'
    })


def ajax_get_subtopics_db(request):
    """
    AJAX: Get subtopics from DB for a given topic.
    Uses the TIE syllabus data seeded via the seed_tie_syllabus management command.
    Returns a JSON array of subtopic strings.
    """
    topic_id = request.GET.get('topic_id')
    
    if not topic_id:
        return JsonResponse({'success': False, 'error': 'topic_id inahitajika'}, status=400)
    
    subtopics = TopicSubtopic.objects.filter(
        topic_id=topic_id
    ).order_by('order').values('id', 'name')
    
    return JsonResponse({
        'success': True,
        'subtopics': list(subtopics),
        'count': subtopics.count(),
        'source': 'database'
    })
