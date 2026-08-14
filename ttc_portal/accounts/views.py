from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .models import LoginAttempt

# ── Ulinzi dhidi ya brute-force (majaribio ya kuvunja nywila) ──
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15


def _client_ip(request):
    """IP ya mteja — inazingatia X-Forwarded-For (Django iko nyuma ya nginx)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or ''


def _lock_status(identifier, ip):
    """Rudi (locked_until) ikiwa akaunti imefungwa kwa muda, vinginevyo None."""
    if not identifier:
        return None
    attempt = LoginAttempt.objects.filter(
        username=identifier.lower(), ip_address=ip
    ).first()
    if attempt and attempt.locked_until and attempt.locked_until > timezone.now():
        return attempt.locked_until
    return None


def _record_failed(identifier, ip):
    """Ongeza jaribio lililoshindikana; fungua akaunti baada ya kikomo."""
    if not identifier:
        return
    attempt, _ = LoginAttempt.objects.get_or_create(
        username=identifier.lower(), ip_address=ip,
    )
    attempt.failed += 1
    if attempt.failed >= MAX_FAILED_ATTEMPTS:
        attempt.locked_until = timezone.now() + timedelta(minutes=LOCK_MINUTES)
        attempt.failed = 0
    attempt.save()


def _clear_attempts(identifier, ip):
    if identifier:
        LoginAttempt.objects.filter(
            username=identifier.lower(), ip_address=ip
        ).delete()


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

    next_url = request.POST.get('next') or request.GET.get('next') or ''

    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        ip = _client_ip(request)

        # 1) Akaunti imefungwa kwa muda? (brute-force lockout)
        locked = _lock_status(identifier, ip)
        if locked:
            mins = int((locked - timezone.now()).total_seconds() // 60) + 1
            messages.error(
                request,
                f'Akaunti imefungwa kwa muda kutokana na majaribio mengi '
                f'yaliyoshindikana. Jaribu tena baada ya dakika {mins}.',
            )
            return render(request, 'accounts/login.html')

        user = authenticate(request, username=identifier, password=password)
        if user is not None:
            _clear_attempts(identifier, ip)

            # Mwanafunzi aliye na akaunti ya user lakini HAKUNA wasifu wa
            # mwanafunzi (k.m. aliundwa kupitia Django admin bila Student):
            # amwache aingie kisha aelekezwe kwenye "Kamilisha Usajili" ili
            # achague chuo chake — badala ya kudundwa mara kwa mara.
            student = getattr(user, 'student_profile', None)
            if user.is_student and student is None:
                login(request, user)
                messages.info(
                    request,
                    'Karibu! Akaunti yako bado haijakamilika — '
                    'chagua chuo chako na jaza taarifa zako kuingia dashboard.',
                )
                return redirect('complete_profile')

            login(request, user)
            messages.success(
                request,
                f"Karibu tena, {user.first_name or user.username}! Umeingia kwenye mfumo.",
            )

            # 2) Endelea kwenye ukurasa uliokusudiwa (?next=) ikiwa ni salama
            #    (lokal pekee — kuzuia open-redirect attacks)
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect(_home_for_user(user))

        # 3) Jaribio lililoshindikana → rekodi + lockout baada ya kikomo
        _record_failed(identifier, ip)
        attempt = LoginAttempt.objects.filter(
            username=identifier.lower(), ip_address=ip
        ).first()
        if attempt and attempt.locked_until and attempt.locked_until > timezone.now():
            messages.error(
                request,
                f'Umefikia kikomo cha majaribio. Akaunti imefungwa kwa dakika {LOCK_MINUTES}.',
            )
        else:
            remaining = max(0, MAX_FAILED_ATTEMPTS - (attempt.failed if attempt else 0))
            messages.error(
                request,
                'Namba ya usajili/barua pepe au nywila si sahihi. '
                f'Majaribio yaliyobaki: {remaining}.',
            )
    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    messages.info(request, 'Umetoka kwenye mfumo. Kwaheri!')
    return redirect('home')
