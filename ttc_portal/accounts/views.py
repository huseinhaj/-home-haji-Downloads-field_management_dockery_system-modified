from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=identifier, password=password)
        if user is not None:
            login(request, user)
            messages.success(
                request,
                f"Karibu tena, {user.first_name or user.username}! Umeingia kwenye mfumo.",
            )
            if user.is_college_admin:
                return redirect('admin_dashboard')
            if user.is_super_admin:
                return redirect('super_admin_dashboard')
            return redirect('dashboard')
        messages.error(
            request,
            'Namba ya usajili/barua pepe au nywila si sahihi. Tafadhali jaribu tena.',
        )
    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    messages.info(request, 'Umetoka kwenye mfumo. Kwaheri!')
    return redirect('home')
