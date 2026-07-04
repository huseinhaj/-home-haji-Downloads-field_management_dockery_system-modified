"""registration_views.py — Self-service onboarding for a new school.

Lets anyone browse the nationwide Region -> District -> School list
(the same master data used by the internship/field_app side of this
project) and register as the first Academic officer for their school,
without a system administrator having to pre-create every school by
hand. New accounts start inactive (is_active=False) and must be
approved by a superuser in Django admin before they can log in — this
keeps the "automatic" self-service flow while still preventing a
stranger from silently claiming a school that isn't theirs.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from field_app.models import District, Region
from field_app.models import School as SourceSchool

from .models import School, TeacherAccount


def register_school_start(request):
    if request.user.is_authenticated:
        return render(request, 'results/register_already_logged_in.html')

    regions = Region.objects.order_by('name')
    return render(request, 'results/register_school.html', {'regions': regions})


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
    keyed by source_school_id so repeat registrations never duplicate it."""
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
    if request.user.is_authenticated:
        return render(request, 'results/register_already_logged_in.html')

    if request.method != 'POST':
        return render(request, 'results/register_school.html', {'regions': Region.objects.order_by('name')})

    source_school_id = request.POST.get('school_id')
    email = request.POST.get('email', '').strip().lower()
    full_name = request.POST.get('full_name', '').strip()
    password1 = request.POST.get('password1', '')
    password2 = request.POST.get('password2', '')

    source_school = get_object_or_404(SourceSchool, id=source_school_id, level='Secondary')
    school = _get_or_create_school(source_school)

    errors = []
    existing = TeacherAccount.objects.filter(school=school, role=TeacherAccount.ROLE_ACADEMIC).first()
    if existing:
        return render(request, 'results/register_school_exists.html', {
            'school': school,
            'academic_email': _mask_email(existing.email),
        })

    if not email:
        errors.append("Barua pepe inahitajika.")
    elif TeacherAccount.objects.filter(email__iexact=email).exists():
        errors.append("Barua pepe hii tayari ipo kwenye mfumo.")

    if password1 != password2:
        errors.append("Password hazifanani.")
    else:
        try:
            validate_password(password1)
        except ValidationError as exc:
            errors.extend(exc.messages)

    if errors:
        for err in errors:
            messages.error(request, err)
        return render(request, 'results/register_school.html', {
            'regions': Region.objects.order_by('name'),
            'preselect_school': source_school,
            'preselect_district_id': source_school.district_id,
            'preselect_region_id': source_school.district.region_id,
            'email': email,
            'full_name': full_name,
        })

    account = TeacherAccount(
        email=email, full_name=full_name, role=TeacherAccount.ROLE_ACADEMIC,
        school=school, is_active=False,
    )
    account.set_password(password1)
    account.save()

    return render(request, 'results/register_school_pending.html', {'school': school, 'email': email})
