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

import json

from django.contrib import messages
from django.contrib.auth import login
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

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
    """POST: the visitor picked a school.

    - If the school already has an Academic → tell them who to contact.
    - If not → register the visitor as the school's first Academic
      (full name + email + password), so their data is actually saved
      and they can log in immediately.
    """
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

    # ── Create the school's first Academic account (data is saved here) ──
    full_name = request.POST.get('full_name', '').strip()
    email = request.POST.get('email', '').strip().lower()
    password1 = request.POST.get('password1', '')
    password2 = request.POST.get('password2', '')

    # If the visitor only picked the school (no account form submitted yet),
    # show the registration form so they can create their account.
    if not (full_name and email):
        return render(request, 'results/register_school_contact_admin.html', {
            'school': school,
            'support_phone': SUPPORT_PHONE,
            'form_data': {'full_name': full_name, 'email': email},
        })

    if password1 != password2:
        messages.error(request, "Password hazifanani. Jaribu tena.")
        return render(request, 'results/register_school_contact_admin.html', {
            'school': school,
            'support_phone': SUPPORT_PHONE,
            'form_data': {'full_name': full_name, 'email': email},
        })

    if len(password1) < 8:
        messages.error(request, "Password inatakiwa iwe angalau herufi 8.")
        return render(request, 'results/register_school_contact_admin.html', {
            'school': school,
            'support_phone': SUPPORT_PHONE,
            'form_data': {'full_name': full_name, 'email': email},
        })

    if TeacherAccount.objects.filter(email__iexact=email).exists():
        messages.error(request, "Email hii tayari imesajiliwa kwenye mfumo. Ingia kwanza.")
        return render(request, 'results/register_school_contact_admin.html', {
            'school': school,
            'support_phone': SUPPORT_PHONE,
            'form_data': {'full_name': full_name, 'email': email},
        })

    account = TeacherAccount(
        email=email,
        full_name=full_name,
        role=TeacherAccount.ROLE_ACADEMIC,
        school=school,
    )
    account.set_password(password1)
    account.save(using='results')

    messages.success(
        request,
        f"Akaunti imeundwa kwa {school.name}! Karibu {full_name}."
    )
    # Log them in straight away — their account is already activated
    login(request, account, backend='results.backends.ResultsAuthBackend')
    response = redirect('academic_dashboard')
    # Kumbuka email kwenye list ya recent-logins (inavyotumiwa na login page)
    from .auth_views import RECENT_EMAILS_COOKIE, RECENT_EMAILS_MAX
    try:
        emails = json.loads(request.COOKIES.get(RECENT_EMAILS_COOKIE, '[]') or '[]')
        if not isinstance(emails, list):
            emails = []
    except (ValueError, TypeError):
        emails = []
    if email in emails:
        emails.remove(email)
    emails.insert(0, email)
    emails = emails[:RECENT_EMAILS_MAX]
    response.set_cookie(
        RECENT_EMAILS_COOKIE,
        json.dumps(emails),
        max_age=60 * 60 * 24 * 365,
        samesite='Lax',
        httponly=False,
    )
    return response
