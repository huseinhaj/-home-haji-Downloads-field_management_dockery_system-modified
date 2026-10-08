import json

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from .backends import ResultsAuthBackend
from .forms import TeacherAccountForm, TeacherSubjectsForm
from .models import TeacherAccount
from .permissions import academic_required

RESULTS_BACKEND = 'results.backends.ResultsAuthBackend'

# ── Recent-logins cookie: kumbuka emails zilizotumika ili mtumiaji
#    achague tu kwenye login badala ya kuandika upya kila mara ───────────
RECENT_EMAILS_COOKIE = 'recent_emails'
RECENT_EMAILS_MAX = 6


def _get_recent_emails(request):
    raw = request.COOKIES.get(RECENT_EMAILS_COOKIE, '')
    if not raw:
        return []
    try:
        emails = json.loads(raw)
        if isinstance(emails, list):
            return [e for e in emails if isinstance(e, str)][:RECENT_EMAILS_MAX]
    except (ValueError, TypeError):
        pass
    return []


def _remember_email(request, response, email):
    """Add an email to the recent-logins cookie on the outgoing response.
    Pass the request (for existing cookies) and the response from
    redirect/render so the Set-Cookie ships with it."""
    if not email:
        return response
    emails = _get_recent_emails(request)
    if email in emails:
        emails.remove(email)
    emails.insert(0, email)
    emails = emails[:RECENT_EMAILS_MAX]
    response.set_cookie(
        RECENT_EMAILS_COOKIE,
        json.dumps(emails),
        max_age=60 * 60 * 24 * 365,  # 1 year
        samesite='Lax',
        httponly=False,
    )
    return response


def _redirect_for_role(account):
    if account.is_district_officer:
        return redirect('district_dashboard')
    if account.is_academic:
        return redirect('academic_dashboard')
    if account.is_printing_secretary:
        return redirect('printing_secretary_dashboard')
    return redirect('teacher_dashboard')


def _lookup_account(email):
    """Get a TeacherAccount by email, case-insensitive.
    Uses explicit database to avoid router mismatches."""
    try:
        return TeacherAccount.objects.using('results').get(email__iexact=email.strip())
    except TeacherAccount.DoesNotExist:
        return None


def _prg_login(request, step, email=''):
    """Post/Redirect/Get kwa login: stash step + email tayari kuchapishwa kwenye
    session, kisha redirect kwa GET URL ya login.

    Kabla ya hii, kila POST (password mbaya, reset yenye hitilafu, mabadiliko ya
    step) ilirender ukurasa moja kwa moja kutoka POST hiyo. Hivyo mtu akibonyeza
    F5/back kwenye ukurasa huo, browser ilionyesha "Confirm form resubmission"
    na kujaribu kutuma tena vitambulisho vile vile. Sasa refresh inare-GET ukurasa
    uliokwisha render — hakuna POST ya kujirudia.
    """
    request.session['login_step'] = step
    request.session['login_email'] = email
    return redirect('results_login')


def results_login(request):
    if request.user.is_authenticated and isinstance(request.user, TeacherAccount):
        return _redirect_for_role(request.user)

    # PRG: kila POST isiyo-thibitisha inarudi hapa kama GET; session inakumbuka
    # hatua (step) na email iliyokwisha chapa. GET haina POST body, kwa hiyo
    # refresh/back haileti tena "Confirm form resubmission".
    step = request.POST.get('step') or request.GET.get('step') or request.session.pop('login_step', None) or 'email'
    email = request.POST.get('email', '').strip() or request.session.pop('login_email', '') or ''

    # ───────────────────────────────────────────────────────────────────
    # STEP: email — enter email to proceed
    # ───────────────────────────────────────────────────────────────────
    if request.method == 'POST' and step == 'email':
        account = _lookup_account(email)
        if account is None:
            messages.error(request, "Email hii haipo kwenye mfumo. Wasiliana na Afisa Taaluma.")
            return _prg_login(request, 'email')
        next_step = 'login' if account.is_activated else 'activate'
        return _prg_login(request, next_step, email)

    # ───────────────────────────────────────────────────────────────────
    # STEP: forgot — GET request shows email prompt
    # ───────────────────────────────────────────────────────────────────
    if request.method == 'GET' and step == 'forgot':
        return render(request, 'results/login.html', {
            'step': 'forgot_email',
            'recent_emails': _get_recent_emails(request),
        })

    # ───────────────────────────────────────────────────────────────────
    # STEP: forgot_email — POST email to start password reset
    # ───────────────────────────────────────────────────────────────────
    if request.method == 'POST' and step == 'forgot_email':
        account = _lookup_account(email)
        if account is None:
            messages.error(request, "Email hii haipo kwenye mfumo.")
            return _prg_login(request, 'forgot_email')
        if not account.is_activated:
            messages.info(request, "Akaunti hii bado haijawasha. Tafadhali weka password yako kwanza.")
            return _prg_login(request, 'activate', email)
        return _prg_login(request, 'forgot', email)

    # ───────────────────────────────────────────────────────────────────
    # STEP: activate — first-time password setup
    # ───────────────────────────────────────────────────────────────────
    if request.method == 'POST' and step == 'activate':
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        account = _lookup_account(email)
        if account is None:
            messages.error(request, "Email hii haipo kwenye mfumo.")
            return _prg_login(request, 'email')

        if account.is_activated:
            messages.error(request, "Akaunti hii tayari ina password. Tafadhali ingia kawaida.")
            return _prg_login(request, 'login', email)

        if password1 != password2:
            messages.error(request, "Password hazifanani.")
            return _prg_login(request, 'activate', email)

        try:
            validate_password(password1, user=account)
        except ValidationError as exc:
            for err in exc.messages:
                messages.error(request, err)
            return _prg_login(request, 'activate', email)

        account.set_password(password1)
        account.save(using='results')
        # Verify password was persisted
        account.refresh_from_db(using='results')
        if not account.has_usable_password():
            messages.error(request, "Hitilafu ya mfumo: password haikuweza kuhifadhiwa. Jaribu tena.")
            return _prg_login(request, 'activate', email)

        login(request, account, backend=RESULTS_BACKEND)
        messages.success(request, "Akaunti imeundwa. Karibu!")
        return _remember_email(request, _redirect_for_role(account), account.email)

    # ───────────────────────────────────────────────────────────────────
    # STEP: login — existing password login
    # ───────────────────────────────────────────────────────────────────
    if request.method == 'POST' and step == 'login':
        password = request.POST.get('password', '')
        account = ResultsAuthBackend().authenticate(request, email=email, password=password)
        if account is None:
            messages.error(request, "Email au password si sahihi.")
            return _prg_login(request, 'login', email)
        login(request, account, backend=RESULTS_BACKEND)
        return _remember_email(request, _redirect_for_role(account), account.email)

    # ───────────────────────────────────────────────────────────────────
    # STEP: forgot — submit new password after email verified
    # ───────────────────────────────────────────────────────────────────
    if request.method == 'POST' and step == 'forgot':
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        account = _lookup_account(email)
        if account is None:
            messages.error(request, "Email hii haipo kwenye mfumo.")
            return _prg_login(request, 'email')

        if password1 != password2:
            messages.error(request, "Password hazifanani.")
            return _prg_login(request, 'forgot', email)

        try:
            validate_password(password1, user=account)
        except ValidationError as exc:
            for err in exc.messages:
                messages.error(request, err)
            return _prg_login(request, 'forgot', email)

        account.set_password(password1)
        account.save(using='results')
        # Verify password was persisted
        account.refresh_from_db(using='results')
        if not account.has_usable_password():
            messages.error(request, "Hitilafu ya mfumo: password haikuweza kuhifadhiwa. Jaribu tena.")
            return _prg_login(request, 'forgot', email)

        login(request, account, backend=RESULTS_BACKEND)
        messages.success(request, "Password yako imebadilishwa. Karibu tena!")
        return _remember_email(request, _redirect_for_role(account), account.email)

    # ── Default: show the step resolved above (or the plain email step) ──
    return render(request, 'results/login.html', {
        'step': step,
        'email': email,
        'recent_emails': _get_recent_emails(request),
    })


def results_logout(request):
    logout(request)
    messages.info(request, "Umetoka kwenye mfumo.")
    return redirect('results_login')


@academic_required
def manage_teachers(request):
    school = request.user.school

    if request.method == 'POST':
        action = request.POST.get('action', 'create')

        if action == 'edit_subjects':
            teacher = get_object_or_404(TeacherAccount, pk=request.POST.get('teacher_id'), school=school)
            subjects_form = TeacherSubjectsForm(request.POST, instance=teacher)
            if subjects_form.is_valid():
                subjects_form.save()
                messages.success(request, f"Masomo ya {teacher.email} yamesasishwa.")
            else:
                messages.error(request, "Imeshindwa kusasisha masomo. Jaribu tena.")
            return redirect('manage_teachers')

        if action == 'delete':
            teacher = get_object_or_404(TeacherAccount, pk=request.POST.get('teacher_id'), school=school)
            if teacher.pk == request.user.pk:
                messages.error(request, "Huwezi kujifuta mwenyewe.")
            else:
                email = teacher.email
                teacher.delete()
                messages.success(request, f"Akaunti ya {email} imeondolewa.")
            return redirect('manage_teachers')

        form = TeacherAccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.school = school
            account.set_unusable_password()
            account.save()
            form.save_m2m()
            messages.success(
                request,
                f"Mwalimu {account.email} ameongezwa. Ataweza kujiwekea password kwa kuingia na email hiyo.",
            )
            return redirect('manage_teachers')
    else:
        form = TeacherAccountForm()

    teachers = TeacherAccount.objects.filter(school=school).prefetch_related('subjects').order_by('-created_at')
    # Orodha ya masomo kwenye fomu zote hapa inafuata aina ya shule —
    # msingi anaona masomo ya msingi tu, sekondari ya sekondari tu.
    teachers_with_forms = [(t, TeacherSubjectsForm(instance=t, school=school)) for t in teachers]
    create_form = TeacherAccountForm(school=school)
    return render(request, 'results/manage_teachers.html', {
        'form': create_form,
        'teachers_with_forms': teachers_with_forms,
        'school': school,
    })
