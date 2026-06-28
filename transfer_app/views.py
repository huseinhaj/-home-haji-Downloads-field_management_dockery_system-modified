import os
import uuid
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import TeacherTransfer, CreditBalance, UnlockedContact, PaymentRequest, CREDIT_PACKAGES

# ── Badilisha namba hii na namba yako halisi ya Lipa Namba ──
MPESA_NUMBER = os.environ.get('TRANSFER_MPESA_NUMBER', '0625607088')
MPESA_NAME   = os.environ.get('TRANSFER_MPESA_NAME',   'Haji Hamisi Huseni')


def _get_regions():
    try:
        from field_app.models import Region
        return list(Region.objects.using('default').order_by('name').values('id', 'name'))
    except Exception:
        return []


def _get_districts(region_id):
    try:
        from field_app.models import District
        return list(District.objects.using('default').filter(
            region_id=region_id
        ).order_by('name').values('id', 'name'))
    except Exception:
        return []


def _get_teacher(request):
    session_key = request.session.get('transfer_session_key')
    if not session_key:
        return None
    return TeacherTransfer.objects.using('transfer').filter(
        session_key=session_key, is_active=True
    ).first()


def _get_credits(session_key):
    try:
        return CreditBalance.objects.using('transfer').get(session_key=session_key).credits
    except CreditBalance.DoesNotExist:
        return 0


def _get_unlocked_ids(session_key):
    return set(
        UnlockedContact.objects.using('transfer')
        .filter(session_key=session_key)
        .values_list('unlocked_teacher_id', flat=True)
    )


def home(request):
    teacher = _get_teacher(request)
    return render(request, 'transfer/home.html', {'teacher': teacher})


def register(request):
    errors = {}
    form_data = {}

    if request.method == 'POST':
        form_data = request.POST.dict()
        name          = request.POST.get('name', '').strip()
        phone         = request.POST.get('phone', '').strip()
        current_school = request.POST.get('current_school', '').strip()
        level         = request.POST.get('level', '').strip()
        subjects      = request.POST.get('subjects', '').strip()
        region_name   = request.POST.get('region_name', '').strip()
        district_name = request.POST.get('district_name', '').strip()
        location_type = request.POST.get('location_type', '').strip()
        willing_to_go = request.POST.get('willing_to_go', '').strip()

        if not name:          errors['name']          = 'Jina linahitajika'
        if not phone:         errors['phone']         = 'Namba ya simu inahitajika'
        if not current_school: errors['current_school'] = 'Jina la shule inahitajika'
        if not level:         errors['level']         = 'Kiwango cha shule kinahitajika'
        if not region_name:   errors['region_name']   = 'Mkoa unahitajika'
        if not district_name: errors['district_name'] = 'Wilaya inahitajika'
        if not location_type: errors['location_type'] = 'Aina ya eneo inahitajika'

        if not errors:
            if not request.session.session_key:
                request.session.create()
            session_key = request.session.get('transfer_session_key')
            if not session_key:
                session_key = str(uuid.uuid4())
                request.session['transfer_session_key'] = session_key

            TeacherTransfer.objects.using('transfer').update_or_create(
                session_key=session_key,
                defaults={
                    'name': name, 'phone': phone, 'current_school': current_school,
                    'level': level, 'subjects': subjects, 'region_name': region_name,
                    'district_name': district_name, 'location_type': location_type,
                    'willing_to_go': willing_to_go, 'is_active': True,
                }
            )
            return redirect('transfer:browse_regions')

    regions = _get_regions()
    return render(request, 'transfer/register.html', {
        'regions': regions, 'errors': errors, 'form_data': form_data,
    })


def get_districts_ajax(request):
    region_id = request.GET.get('region_id')
    if not region_id:
        return JsonResponse([], safe=False)
    return JsonResponse(_get_districts(region_id), safe=False)


def browse_regions(request):
    teacher = _get_teacher(request)
    if not teacher:
        return redirect('transfer:home')
    regions = _get_regions()
    session_key = request.session.get('transfer_session_key', '')
    return render(request, 'transfer/browse_regions.html', {
        'teacher': teacher,
        'regions': regions,
        'credits': _get_credits(session_key),
    })


def browse_districts(request, region_id):
    teacher = _get_teacher(request)
    if not teacher:
        return redirect('transfer:home')
    try:
        from field_app.models import Region
        region = Region.objects.using('default').get(id=region_id)
    except Exception:
        return redirect('transfer:browse_regions')
    districts = _get_districts(region_id)
    session_key = request.session.get('transfer_session_key', '')
    return render(request, 'transfer/browse_districts.html', {
        'teacher': teacher, 'region': region, 'districts': districts,
        'credits': _get_credits(session_key),
    })


def teachers_in_district(request, region_id, district_id):
    teacher = _get_teacher(request)
    if not teacher:
        return redirect('transfer:home')

    try:
        from field_app.models import Region, District
        region   = Region.objects.using('default').get(id=region_id)
        district = District.objects.using('default').get(id=district_id)
    except Exception:
        return redirect('transfer:browse_regions')

    session_key = request.session.get('transfer_session_key', '')

    teachers = TeacherTransfer.objects.using('transfer').filter(
        district_name__iexact=district.name,
        is_active=True,
    ).exclude(session_key=session_key)

    level_filter = request.GET.get('level', '')
    if level_filter:
        teachers = teachers.filter(level=level_filter)

    unlocked_ids = _get_unlocked_ids(session_key)
    credits      = _get_credits(session_key)

    return render(request, 'transfer/teachers_list.html', {
        'teacher':      teacher,
        'region':       region,
        'district':     district,
        'teachers':     teachers,
        'level_filter': level_filter,
        'total':        teachers.count(),
        'unlocked_ids': unlocked_ids,
        'credits':      credits,
    })


@require_POST
def unlock_contact(request, teacher_id):
    teacher = _get_teacher(request)
    if not teacher:
        return redirect('transfer:home')

    session_key = request.session.get('transfer_session_key', '')

    # Already unlocked → free
    if UnlockedContact.objects.using('transfer').filter(
        session_key=session_key, unlocked_teacher_id=teacher_id
    ).exists():
        return redirect(request.META.get('HTTP_REFERER', 'transfer:browse_regions'))

    balance, _ = CreditBalance.objects.using('transfer').get_or_create(
        session_key=session_key, defaults={'credits': 0}
    )

    if balance.credits < 1:
        messages.warning(request, 'Huna credits. Nunua credits ili uone namba za simu.')
        return redirect('transfer:buy_credits')

    balance.credits -= 1
    balance.save(using='transfer')
    UnlockedContact.objects.using('transfer').create(
        session_key=session_key,
        unlocked_teacher_id=teacher_id,
    )
    return redirect(request.META.get('HTTP_REFERER', 'transfer:browse_regions'))


def buy_credits(request):
    teacher = _get_teacher(request)
    if not teacher:
        return redirect('transfer:home')

    session_key = request.session.get('transfer_session_key', '')
    credits     = _get_credits(session_key)

    return render(request, 'transfer/buy_credits.html', {
        'teacher':      teacher,
        'credits':      credits,
        'packages':     CREDIT_PACKAGES,
        'mpesa_number': MPESA_NUMBER,
        'mpesa_name':   MPESA_NAME,
    })


def submit_payment(request):
    teacher = _get_teacher(request)
    if not teacher:
        return redirect('transfer:home')

    if request.method != 'POST':
        return redirect('transfer:buy_credits')

    session_key = request.session.get('transfer_session_key', '')
    package_key = request.POST.get('package', '').strip()
    mpesa_ref   = request.POST.get('mpesa_ref', '').strip().upper()

    if package_key not in CREDIT_PACKAGES:
        messages.error(request, 'Chagua kifurushi sahihi.')
        return redirect('transfer:buy_credits')

    if not mpesa_ref or len(mpesa_ref) < 6:
        messages.error(request, 'Weka kumbukumbu nzuri ya malipo (angalau herufi 6).')
        return redirect('transfer:buy_credits')

    pkg = CREDIT_PACKAGES[package_key]

    PaymentRequest.objects.using('transfer').create(
        session_key=session_key,
        teacher_name=teacher.name,
        contact_phone=teacher.phone,
        package=package_key,
        mpesa_ref=mpesa_ref,
        amount=pkg['price'],
    )

    messages.success(
        request,
        f"Ombi lako la {pkg['label']} limepokelewa! "
        f"Credits zitaongezwa ndani ya saa 1-2 baada ya kuthibitisha malipo yako."
    )
    return redirect('transfer:buy_credits')


def login_returning(request):
    """Mwalimu aliyekwisha jaza taarifa aingie kwa namba ya simu + wilaya."""
    errors = {}
    form_data = {}

    if request.method == 'POST':
        form_data = request.POST.dict()
        phone    = request.POST.get('phone', '').strip()
        district = request.POST.get('district', '').strip()

        if not phone:
            errors['phone'] = 'Weka namba yako ya simu'
        if not district:
            errors['district'] = 'Weka wilaya unayofundisha'

        if not errors:
            teacher = TeacherTransfer.objects.using('transfer').filter(
                phone=phone,
                district_name__iexact=district,
                is_active=True,
            ).first()

            if teacher:
                request.session['transfer_session_key'] = teacher.session_key
                messages.success(request, f'Karibu tena, {teacher.name}! Umeingia mfumo.')
                return redirect('transfer:home')
            else:
                errors['general'] = 'Namba ya simu au wilaya si sahihi. Hakikisha umeandika vizuri kama ulivyojaza kwanza.'

    return render(request, 'transfer/login.html', {
        'errors': errors,
        'form_data': form_data,
    })


def logout_transfer(request):
    """Toka tu — session inafutwa lakini taarifa zinabaki kwenye orodha."""
    if request.method == 'POST':
        request.session.pop('transfer_session_key', None)
    return redirect('transfer:home')


def deactivate(request):
    if request.method == 'POST':
        teacher = _get_teacher(request)
        if teacher:
            teacher.is_active = False
            teacher.save(using='transfer')
        request.session.pop('transfer_session_key', None)
    return redirect('transfer:home')
