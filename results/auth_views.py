from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from .backends import ResultsAuthBackend
from .forms import TeacherAccountForm
from .models import TeacherAccount
from .permissions import academic_required

RESULTS_BACKEND = 'results.backends.ResultsAuthBackend'


def _redirect_for_role(account):
    return redirect('academic_dashboard' if account.is_academic else 'teacher_dashboard')


def results_login(request):
    if request.user.is_authenticated and isinstance(request.user, TeacherAccount):
        return _redirect_for_role(request.user)

    step = request.POST.get('step', 'email')
    email = request.POST.get('email', '').strip()

    if request.method == 'POST' and step == 'email':
        try:
            account = TeacherAccount.objects.get(email__iexact=email)
        except TeacherAccount.DoesNotExist:
            messages.error(request, "Email hii haipo kwenye mfumo. Wasiliana na Afisa Taaluma.")
            return render(request, 'results/login.html', {'step': 'email'})
        next_step = 'login' if account.is_activated else 'activate'
        return render(request, 'results/login.html', {'step': next_step, 'email': email})

    if request.method == 'POST' and step == 'activate':
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        try:
            account = TeacherAccount.objects.get(email__iexact=email)
        except TeacherAccount.DoesNotExist:
            messages.error(request, "Email hii haipo kwenye mfumo.")
            return render(request, 'results/login.html', {'step': 'email'})
        if account.is_activated:
            messages.error(request, "Akaunti hii tayari ina password. Tafadhali ingia kawaida.")
            return render(request, 'results/login.html', {'step': 'login', 'email': email})
        if password1 != password2:
            messages.error(request, "Password hazifanani.")
            return render(request, 'results/login.html', {'step': 'activate', 'email': email})
        try:
            validate_password(password1, user=account)
        except ValidationError as exc:
            for err in exc.messages:
                messages.error(request, err)
            return render(request, 'results/login.html', {'step': 'activate', 'email': email})
        account.set_password(password1)
        account.save(update_fields=['password'])
        login(request, account, backend=RESULTS_BACKEND)
        messages.success(request, "Akaunti imeundwa. Karibu!")
        return _redirect_for_role(account)

    if request.method == 'POST' and step == 'login':
        password = request.POST.get('password', '')
        account = ResultsAuthBackend().authenticate(request, email=email, password=password)
        if account is None:
            messages.error(request, "Email au password si sahihi.")
            return render(request, 'results/login.html', {'step': 'login', 'email': email})
        login(request, account, backend=RESULTS_BACKEND)
        return _redirect_for_role(account)

    return render(request, 'results/login.html', {'step': 'email'})


def results_logout(request):
    logout(request)
    messages.info(request, "Umetoka kwenye mfumo.")
    return redirect('results_login')


@academic_required
def manage_teachers(request):
    if request.method == 'POST':
        form = TeacherAccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
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

    teachers = TeacherAccount.objects.all().order_by('-created_at')
    return render(request, 'results/manage_teachers.html', {
        'form': form,
        'teachers': teachers,
    })
