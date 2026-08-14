from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages


def _home_for_user(user):
    """Peana ukurasa sahihi kulingana na jukumu (role) la mtumiaji."""
    if user.is_college_admin:
        return 'admin_dashboard'
    if user.is_super_admin:
        return 'super_admin_dashboard'
    return 'dashboard'


def login_view(request):
    # Tayari ameingia → mpeleke mahali sahihi (sio kudunda kwenye home)
    if request.user.is_authenticated:
        return redirect(_home_for_user(request.user))

    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=identifier, password=password)
        if user is not None:
            # Mwanafunzi aliye na akaunti ya user lakini HAKUNA wasifu wa
            # mwanafunzi (k.m. aliundwa kupitia Django admin bila Student):
            # usimwache aingie kisha adunduke — mwambie wazi cha kufanya.
            student = getattr(user, 'student_profile', None)
            if user.is_student and student is None:
                messages.error(
                    request,
                    'Akaunti yako bado haijaunganishwa na wasifu wa mwanafunzi. '
                    'Wasiliana na msimamizi wa chuo chako ili akamilishe usajili wako.',
                )
                return redirect('login')

            login(request, user)
            messages.success(
                request,
                f"Karibu tena, {user.first_name or user.username}! Umeingia kwenye mfumo.",
            )
            return redirect(_home_for_user(user))
        messages.error(
            request,
            'Namba ya usajili/barua pepe au nywila si sahihi. Tafadhali jaribu tena.',
        )
    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    messages.info(request, 'Umetoka kwenye mfumo. Kwaheri!')
    return redirect('home')
