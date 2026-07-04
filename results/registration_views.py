"""registration_views.py — School discovery for onboarding a new school.

Lets anyone browse the nationwide Region -> District -> School list
(the same master data used by the internship/field_app side of this
project) to find their school and check whether it already has an
Academic officer registered.

Accounts themselves are NOT created here. The system administrator
adds each school's first Academic manually in Django admin (using
TeacherAccount.objects.create_pending, same as an Academic adding
their own teachers) after the person contacts the admin directly using
the published support phone number. The Academic then activates their
own account the normal way, by logging in with that email for the
first time and setting their own password.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from field_app.models import District, Region
from field_app.models import School as SourceSchool

from .context_processors import SUPPORT_PHONE
from .models import School, TeacherAccount


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
        SourceSchool.objects.filter(district_id=district_id, level='Secondary').order_by('name')
        if district_id else []
    )
    return JsonResponse({'schools': [{'id': s.id, 'name': s.name} for s in schools]})


def _mask_email(email: str) -> str:
    """Show just enough of an email to be recognizable without leaking it in full."""
    local, _, domain = email.partition('@')
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(len(local) - len(visible), 2)}@{domain}"


def _get_or_create_school(source_school):
    """Mirror a field_app.School into the results app's own School table,
    keyed by source_school_id so repeat lookups never duplicate it. This
    makes the school immediately available for the admin to pick in
    Django admin, without waiting for anyone to have registered yet."""
    school, _ = School.objects.get_or_create(
        source_school_id=source_school.id,
        defaults={
            'name': source_school.name.strip().title(),
            'region': source_school.district.region.name,
            'district': source_school.district.name,
        },
    )
    return school


def register_school_confirm(request):
    """POST: the visitor picked a school. Show whether it already has an
    Academic (contact them) or needs one set up (contact the admin)."""
    if request.user.is_authenticated:
        return render(request, 'results/register_already_logged_in.html')

    if request.method != 'POST':
        return render(request, 'results/register_school.html', {
            'regions': Region.objects.order_by('name'), 'support_phone': SUPPORT_PHONE,
        })

    source_school_id = request.POST.get('school_id')
    source_school = get_object_or_404(SourceSchool, id=source_school_id, level='Secondary')
    school = _get_or_create_school(source_school)

    existing = TeacherAccount.objects.filter(school=school, role=TeacherAccount.ROLE_ACADEMIC).first()
    if existing:
        return render(request, 'results/register_school_exists.html', {
            'school': school,
            'academic_email': _mask_email(existing.email),
        })

    return render(request, 'results/register_school_contact_admin.html', {
        'school': school,
        'support_phone': SUPPORT_PHONE,
    })
