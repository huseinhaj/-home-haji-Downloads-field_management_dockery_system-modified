import random
import string

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count, Q
from django.shortcuts import render, redirect, get_object_or_404

from accounts.models import CustomUser
from colleges.models import College
from fees.services import create_bills_for_student, academic_year_now
from .forms import StudentRegistrationForm, AdminStudentForm, CompleteStudentForm, StudentProfileForm
from .models import Student


# ───────────────────────────── Registration ─────────────────────────────

def _create_student_from_form(form, *, user_role='student', created_by=None):
    """Shared creation logic for self-registration and admin add."""
    college = form.cleaned_data['college']
    program = form.cleaned_data.get('program')
    full_name = form.cleaned_data['full_name'].strip()
    reg_no = (form.cleaned_data['registration_number'] or '').strip()
    email = (form.cleaned_data.get('email') or '').strip()
    phone = form.cleaned_data.get('phone_number', '').strip()
    password = form.cleaned_data.get('password')

    username = reg_no or email
    user = CustomUser.objects.create_user(
        username=username,
        email=email or None,
        password=password or '',
        role=user_role,
        phone_number=phone,
    )
    # Default password for admin-created students: last 4 chars of reg no + college code
    if not password:
        default_pass = f"{reg_no.split('/')[-1] if reg_no else 'ttc'}{college.code.lower()}"
        user.set_password(default_pass)
        user.save()

    # Guard: programu lazima iwe ya chuo hicho (server-side)
    if program and program.college_id != college.id:
        program = None

    student = Student.objects.create(
        user=user,
        college=college,
        program=program,
        full_name=full_name,
        registration_number=reg_no or username,
        admission_year=form.cleaned_data['admission_year'],
        year_of_study=int(form.cleaned_data['year_of_study']),
        gender=form.cleaned_data.get('gender') or '',
        phone_number=phone,
        email=email,
    )

    # SR2-style: auto-create bills for every active fee item (ada, mchango, ...)
    create_bills_for_student(student)
    return student, user


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    locked_college = None
    college_code = request.GET.get('college', '').strip()
    if college_code:
        try:
            locked_college = College.objects.get(code=college_code.upper(), is_active=True)
        except College.DoesNotExist:
            locked_college = None

    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        # Kinga ya server-side: mwanafunzi aliyetoka kwenye ukurasa wa chuo
        # (?college=...) hawezi kubadilisha chuo hata kama POST imetengenezwa
        # upya — chuo kinafungwa kwa kile alichokichagua.
        if locked_college is not None and form.is_valid():
            form.cleaned_data['college'] = locked_college
        if form.is_valid():
            student, user = _create_student_from_form(form)
            # Multiple auth backends are configured → set the backend explicitly
            user.backend = 'accounts.backends.IdentifierBackend'
            login(request, user)
            messages.success(
                request,
                f"Hongera {student.full_name}! Umejiandikisha katika {student.college.short_name}. "
                f"Kuingia mara nyingine tumia: {student.registration_number} na nywila yako.",
            )
            return redirect('dashboard')
        # Ikiwa fomu imeshindikana, tungeza kuweka lock kwenye chuo kilichochaguliwa
        if locked_college is None and form.data.get('college'):
            try:
                locked_college = College.objects.get(id=form.data['college'], is_active=True)
            except (College.DoesNotExist, ValueError):
                locked_college = None
    else:
        initial = {'admission_year': 2026}
        if locked_college:
            initial['college'] = locked_college
        form = StudentRegistrationForm(initial=initial)
    return render(request, 'students/register.html', {
        'form': form,
        'locked_college': locked_college,
    })


# ───────────────────────────── Student dashboard ─────────────────────────────

@login_required
def dashboard(request):
    student = getattr(request.user, 'student_profile', None)
    if student is None:
        messages.error(request, 'Akaunti yako haijaunganishwa na wasifu wa mwanafunzi.')
        return redirect('home')

    # Mwanafunzi anaweza kubadilisha taarifa zake (My Information) — hii ni POST
    # kutoka kwenye modal ya edit profile kwenye dashboard yenyewe.
    profile_form = None
    if request.method == 'POST' and request.POST.get('profile_update') == '1':
        profile_form = StudentProfileForm(request.POST, instance=student)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, 'Taarifa zako zimebadilishwa kikamilifu.')
            return redirect('dashboard')
        messages.error(request, 'Taarifa hazikubaliki — angalia fomu na ujaribu tena.')

    bills = student.bills.select_related('fee_item').order_by('-academic_year', 'fee_item__category')
    payments = student.payments.select_related('bill__fee_item').order_by('-created_at')

    # Gawa bili kwa miaka ya masomo: mwaka huu (current) + miaka mingine.
    current_year = academic_year_now()
    bills_by_year = {}
    for bill in bills:
        bills_by_year.setdefault(bill.academic_year, []).append(bill)
    ordered_years = sorted(bills_by_year.keys(), reverse=True)
    current_bills = bills_by_year.get(current_year, [])
    other_years = [y for y in ordered_years if y != current_year]

    if profile_form is None:
        profile_form = StudentProfileForm(instance=student)

    context = {
        'student': student,
        'bills_by_year': bills_by_year,
        'current_bills': current_bills,
        'other_years': other_years,
        'payments': payments,
        'academic_year': current_year,
        'paid_percent': round((student.total_paid / student.total_billed * 100) if student.total_billed else 0),
        'profile_form': profile_form,
        # Akaunti ya College Contribution ni CONSTANT kwa vyuo vyote (settings)
        'contribution_account_number': getattr(settings, 'TTC_CONTRIBUTION_ACCOUNT_NUMBER', ''),
        'contribution_bank_name': getattr(settings, 'TTC_CONTRIBUTION_BANK_NAME', ''),
    }
    return render(request, 'students/dashboard.html', context)


# ────────────────────── Kamilisha usajili (orphan account) ─────────────────

@login_required
def complete_profile(request):
    """Kamilisha usajili kwa akaunti ya student ambayo bado haina Student profile.

    Hutokea kama akaunti iliundwa kupitia Django admin (CustomUser tu, bila
    Student). Badala ya kumwambia mwanafunzi "wasiliana na msimamizi", tunampa
    fomu ya kuchagua chuo/taarifa zake na profile inaundwa papo hapo.
    """
    student = getattr(request.user, 'student_profile', None)
    if student is not None:
        return redirect('dashboard')
    if not request.user.is_student:
        messages.error(request, 'Sehemu hii ni kwa wanafunzi pekee.')
        return redirect('home')

    if request.method == 'POST':
        form = CompleteStudentForm(request.POST)
        if form.is_valid():
            student = Student.objects.create(
                user=request.user,
                college=form.cleaned_data['college'],
                program=form.cleaned_data.get('program'),
                full_name=form.cleaned_data['full_name'].strip(),
                registration_number=form.cleaned_data['registration_number'],
                admission_year=form.cleaned_data['admission_year'],
                year_of_study=int(form.cleaned_data['year_of_study']),
                gender=form.cleaned_data.get('gender') or '',
                phone_number=form.cleaned_data.get('phone_number', ''),
                email=form.cleaned_data.get('email', ''),
            )
            # SR2-style: bili za ada na michango zinaundwa moja kwa moja
            create_bills_for_student(student)
            messages.success(
                request,
                f'Usajili wako umekamilika! Karibu, {student.full_name}. '
                'Bili zako zimeandaliwa.',
            )
            return redirect('dashboard')
    else:
        initial = {'admission_year': 2026, 'year_of_study': 1}
        if request.user.get_full_name():
            initial['full_name'] = request.user.get_full_name()
        if request.user.email:
            initial['email'] = request.user.email
        if request.user.phone_number:
            initial['phone_number'] = request.user.phone_number
        # Username inaweza kuwa namba ya usajili — ijaze mapema ikiwa inafanana
        uname = request.user.username or ''
        if uname and ('/' in uname or uname[:1].isalpha()):
            initial['registration_number'] = uname
        form = CompleteStudentForm(initial=initial)
    return render(request, 'students/complete_profile.html', {'form': form})


# ───────────────────────────── College admin ─────────────────────────────

def _get_admin_college(user):
    profile = getattr(user, 'college_admin_profile', None)
    return profile.college if profile else None


def _is_college_admin(user):
    return user.is_authenticated and user.is_college_admin and _get_admin_college(user)


def _is_super_admin(user):
    return user.is_authenticated and user.is_super_admin


@login_required
@user_passes_test(_is_college_admin, login_url='home')
def admin_dashboard(request):
    college = _get_admin_college(request.user)
    students = college.students.all()
    from fees.models import FeeBill, Payment

    pending_payments = Payment.objects.filter(
        bill__student__college=college, status='pending',
    ).select_related('bill__fee_item', 'student').order_by('-created_at')

    stats = {
        'students': students.count(),
        'unpaid_bills': FeeBill.objects.filter(
            student__college=college, status__in=['unpaid', 'partially_paid'],
        ).count(),
        'pending_payments': pending_payments.count(),
        'collected': Payment.objects.filter(
            bill__student__college=college, status='confirmed',
        ).aggregate(t=Sum('amount'))['t'] or 0,
    }
    context = {
        'college': college,
        'stats': stats,
        'pending_payments': pending_payments[:15],
        'recent_students': students.order_by('-created_at')[:8],
    }
    return render(request, 'students/admin_dashboard.html', context)


@login_required
@user_passes_test(_is_college_admin, login_url='home')
def admin_students(request):
    college = _get_admin_college(request.user)
    students = college.students.all()
    q = request.GET.get('q', '').strip()
    if q:
        students = students.filter(
            Q(full_name__icontains=q) | Q(registration_number__icontains=q)
        )
    context = {'college': college, 'students': students.order_by('full_name'), 'q': q}
    return render(request, 'students/admin_students.html', context)


@login_required
@user_passes_test(_is_college_admin, login_url='home')
def admin_student_detail(request, student_id):
    college = _get_admin_college(request.user)
    student = get_object_or_404(Student, id=student_id, college=college)
    bills = student.bills.select_related('fee_item').order_by('fee_item__category')
    payments = student.payments.order_by('-created_at')
    context = {
        'college': college,
        'student': student,
        'bills': bills,
        'payments': payments,
    }
    return render(request, 'students/admin_student_detail.html', context)


@login_required
@user_passes_test(_is_college_admin, login_url='home')
def admin_add_student(request):
    college = _get_admin_college(request.user)
    if request.method == 'POST':
        form = AdminStudentForm(request.POST)
        if form.is_valid():
            # FIX: chuo huwa cha msimamizi daima — sio cha kwenye POST
            form.cleaned_data['college'] = college
            student, user = _create_student_from_form(form, user_role='student')
            messages.success(
                request,
                f"Mwanafunzi {student.full_name} ameongezwa. "
                f"Username: {user.username}",
            )
            return redirect('admin_student_detail', student_id=student.id)
    else:
        form = AdminStudentForm(
            initial={'admission_year': 2026, 'college': college}
        )
    return render(request, 'students/admin_add_student.html', {'form': form, 'college': college})


# ───────────────────────────── Super admin ─────────────────────────────

@login_required
@user_passes_test(_is_super_admin, login_url='home')
def super_admin_dashboard(request):
    from fees.models import FeeBill, Payment

    stats = {
        'colleges': College.objects.filter(is_active=True).count(),
        'students': Student.objects.count(),
        'college_admins': CustomUser.objects.filter(role='college_admin').count(),
        'collected': Payment.objects.filter(status='confirmed').aggregate(t=Sum('amount'))['t'] or 0,
    }
    recent_students = Student.objects.select_related('college').order_by('-created_at')[:10]
    colleges = College.objects.annotate(
        s_count=Count('students', distinct=True),
        p_count=Count('programs', distinct=True),
    )
    context = {
        'stats': stats,
        'recent_students': recent_students,
        'colleges': colleges,
    }
    return render(request, 'students/super_admin_dashboard.html', context)
