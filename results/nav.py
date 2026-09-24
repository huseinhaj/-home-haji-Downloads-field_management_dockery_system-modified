"""Menyu ya app ya results — makundi ya viungo kwa kila aina ya mtumiaji.

Kila kiungo ni jina la URL (url_name) + jina lake sw/en + ikoni. 'roles' =
nani anakiona. Context processor `nav` → NAV_GROUPS (base.html).
"""
from django.urls import NoReverseMatch, reverse

_A, _T, _P = 'academic', 'teacher', 'ps'

# (key, ikoni, jina sw, jina en, [(url_name, ikoni, sw, en, roles)])
NAV = [
    ('mitihani', 'fa-file-signature', 'Mitihani na Alama', 'Exams & Marks', [
        ('home', 'fa-list-check', 'Mitihani', 'Exams', {_A, _T}),
        ('upload_results', 'fa-plus-circle', 'Unda Mtihani Mpya', 'Create New Exam', {_A}),
        ('academic_dashboard', 'fa-chart-bar', 'Dashibodi ya Academic', 'Academic Dashboard', {_A}),
        ('teacher_dashboard', 'fa-chalkboard-teacher', 'Dashibodi ya Mwalimu', 'Teacher Dashboard', {_T}),
        ('marks_entry', 'fa-pen-to-square', 'Jaza Alama', 'Marks Entry', {_A, _T}),
        ('academic_add_student_marks', 'fa-user-pen', 'Ongeza Mwanafunzi & Alama', 'Add Student & Marks', {_A}),
        ('necta_ca_form', 'fa-file-lines', 'NECTA CA', 'NECTA CA', {_A, _T}),
        ('personal_upload', 'fa-file-arrow-up', 'Binafsi', 'Personal', {_T}),
    ]),
    ('shule', 'fa-school', 'Shule', 'School', [
        ('school_setup', 'fa-school', 'Shule Yangu', 'My School', {_A}),
        ('upload_form_students', 'fa-user-graduate', 'Orodha ya Wanafunzi', 'Student Roster', {_A}),
        ('manage_teachers', 'fa-users', 'Simamia Walimu', 'Manage Teachers', {_A}),
        ('school_subjects', 'fa-book', 'Masomo ya Shule', 'School Subjects', {_A}),
        ('select_my_subjects', 'fa-book-open-reader', 'Masomo Yangu', 'My Subjects', {_A, _T}),
        ('class_timetable_view', 'fa-calendar-days', 'Ratiba ya Darasa', 'Class Timetable', {_A, _T}),
    ]),
    ('ps', 'fa-print', 'Uchapishaji', 'Printing', [
        ('printing_secretary_dashboard', 'fa-print', 'Uchapishaji (PS)', 'Printing (PS)', {_P}),
    ]),
    ('matokeo', 'fa-magnifying-glass', 'Matokeo', 'Results', [
        ('student_results_search', 'fa-magnifying-glass', 'Tafuta Matokeo', 'Search Results', {_A, _T, _P}),
        ('user_guide', 'fa-book-open', 'Mwongozo', 'User Guide', {_A, _T, _P}),
    ]),
]


def _role(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    for attr, role in (('is_academic', _A), ('is_teacher', _T), ('is_printing_secretary', _P)):
        val = getattr(user, attr, False)
        if callable(val):
            val = val()
        if val:
            return role
    return None


def nav(request):
    """Context processor: menyu ya makundi kwa mtumiaji aliyeingia."""
    # Lugha ile ile ya field_app.context_processors.language (LANG).
    try:
        sw = request.session.get('ui_lang', 'en') == 'sw'
    except Exception:
        sw = False
    role = _role(getattr(request, 'user', None))
    if role is None:
        return {'NAV_GROUPS': []}
    match = getattr(request, 'resolver_match', None)
    current = match.url_name if match else None
    groups = []
    for key, icon, g_sw, g_en, items in NAV:
        links = []
        for name, item_icon, i_sw, i_en, roles in items:
            if role not in roles:
                continue
            try:
                url = reverse(name)
            except NoReverseMatch:
                continue
            links.append({'url': url, 'icon': item_icon, 'title': i_sw if sw else i_en,
                          'active': name == current})
        if links:
            groups.append({'key': key, 'icon': icon, 'title': g_sw if sw else g_en,
                           'items': links, 'active': any(l['active'] for l in links)})
    return {'NAV_GROUPS': groups}
