import random
import string

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count, Q
from django.shortcuts import render, redirect, get_object_or_404

from accounts.models import CustomUser
from colleges.models import College
from fees.services import create_bills_for_student, academic_year_now
from .forms import StudentRegistrationForm, AdminStudentForm
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

    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            student, user = _create_student_from_form(form)
            # Multiple auth backends are configured → set the backend explicitly
            user.backend = 'accounts.backends.IdentifierBackend'
            login(request, user)
            messages.success(
                request,
                f"Hongera {student.full_name}! Umejiandikisha katika {student.college.short_name}. "
                f"Karibu kwenye mfumo.",
            )
            return redirect('dashboard')
    else:
        initial = {'admission_year': 2026}
        college_code = request.GET.get('college', '').strip()
        if college_code:
            try:
                initial['college'] = College.objects.get(code=college_code.upper(), is_active=True)
            except College.DoesNotExist:
                pass
        form = StudentRegistrationForm(initial=initial)
    return render(request, 'students/register.html', {'form': form})


# ───────────────────────────── Student dashboard ─────────────────────────────

@login_required
def dashboard(request):
    student = getattr(request.user, 'student_profile', None)
    if student is None:
        messages.error(request, 'Akaunti yako haijaunganishwa na wasifu wa mwanafunzi.')
        return redirect('home')

    bills = student.bills.select_related('fee_item').order_by('fee_item__category')
    payments = student.payments.select_related('bill__fee_item').order_by('-created_at')

    context = {
        'student': student,
        'bills': bills,
        'payments': payments,
        'academic_year': academic_year_now(),
        'paid_percent': round((student.total_paid / student.total_billed * 100) if student.total_billed else 0),
    }
    return render(request, 'students/dashboard.html', context)


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
