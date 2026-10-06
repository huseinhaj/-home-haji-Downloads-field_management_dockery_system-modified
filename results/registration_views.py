"""registration_views.py — School discovery (hujaungwi na shule hapa).

Lets anyone browse the nationwide Region -> District -> School list
(the same master data used by the internship/field_app side of this
project) to find their school.

Picking a school does NOT join or create anything: visitors are shown
"Hujaungwa na shule hii" plus the published support number and told to
contact the system administrator, who links them to the right school
and adds the account in Django admin (TeacherAccount.objects.create_pending).
Self-registration was removed after users reported being linked to a
different school than the one they picked. The chosen school is only
mirrored into results.School so the admin can pick it up.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from field_app.models import District, Region
from field_app.models import School as SourceSchool

from .context_processors import SUPPORT_PHONE
from .models import School


def register_school_start(request):
    if request.user.is_authenticated:
        return render(request, 'results/register_already_logged_in.html')

    regions = Region.objects.order_by('name')
    return render(request, 'results/register_school.html', {'regions': regions, 'support_phone': SUPPORT_PHONE})


def ajax_districts(request):
    region_id = request.GET.get('region_id')
    districts = District.objects.filter(region_id=region_id).order_by('name') if region_id else []
    return JsonResponse({'districts': [{'id': d.id, 'name': d.name} for d in districts]})


def ajax_schools(request):
    district_id = request.GET.get('district_id')
    schools = (
        SourceSchool.objects.filter(district_id=district_id).order_by('name')
        if district_id else []
    )
    # Msingi na sekondari zote zinaonekana — shule ya msingi pia inahitaji
    # kujiunga. Level inapelekwa ili UI iweze kuonyesha aina ya shule.
    return JsonResponse({'schools': [
        {'id': s.id, 'name': s.name, 'level': s.level or ''} for s in schools
    ]})


def _get_or_create_school(source_school):
    """Mirror a field_app.School into the results app's own School table,
    keyed by source_school_id so repeat lookups never duplicate it. This
    makes the school immediately available for the admin to pick in
    Django admin, without waiting for anyone to have registered yet.
    Level (msingi/sekondari) inakopiwa pia — shule ya msingi inaanza
    na Darasa 1-7, grading A-E, bila ku-subiri Academic aweweke."""
    level_map = {'Primary': 'primary', 'Secondary': 'secondary', 'Technical': 'secondary'}
    school, _ = School.objects.get_or_create(
        source_school_id=source_school.id,
        defaults={
            'name': source_school.name.strip().title(),
            'region': source_school.district.region.name,
            'district': source_school.district.name,
            'level': level_map.get(source_school.level, 'secondary'),
        },
    )
    # Row ya zamani (kabla ya primary support) inaweza kuwa bila level —
    # jaza kutoka kwa orodha kuu.
    if not school.level and source_school.level:
        school.level = level_map.get(source_school.level, 'secondary')
        school.save(update_fields=['level'])
    return school


def register_school_confirm(request):
    """POST: the visitor picked a school.

    Hujaungwi hapa. Kwa sababu watumiaji wameripoti kuunganishwa na shule
    tofauti ya ile walioichagua, utekelezaji wa kujiunga umefungwa kabisa:
    tunaonyesha tu ujumbe "Hujaungwa na shule hii" pamoja na namba ya Support
    ya Msimamizi (Admin) ambaye ndiye husajili akaunti na kuunganisha mtumiaji
    na shule sahihi.

    Shule iliyochaguliwa inanakiliwa kwenye results.School (kwa marupurupu ya
    admin) lakini hakuna akaunti inayoundwa wala mtumiaji kuunganishwa.
    """
    if request.user.is_authenticated:
        return render(request, 'results/register_already_logged_in.html')

    if request.method != 'POST':
        return redirect('register_school_start')

    source_school_id = request.POST.get('school_id')
    if not source_school_id:
        return redirect('register_school_start')

    # Msingi au sekondari — vyote vinaonekana.
    source_school = get_object_or_404(SourceSchool, id=source_school_id)
    school = _get_or_create_school(source_school)

    return render(request, 'results/register_school_not_joined.html', {
        'school': school,
        'support_phone': SUPPORT_PHONE,
    })
