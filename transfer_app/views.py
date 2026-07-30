import os
import uuid
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from .models import TeacherTransfer

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
    return render(request, 'transfer/browse_regions.html', {
        'teacher': teacher,
        'regions': regions,
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
    return render(request, 'transfer/browse_districts.html', {
        'teacher': teacher, 'region': region, 'districts': districts,
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

    teachers = TeacherTransfer.objects.using('transfer').filter(
        district_name__iexact=district.name,
        is_active=True,
    ).exclude(session_key=request.session.get('transfer_session_key', ''))

    level_filter = request.GET.get('level', '')
    if level_filter:
        teachers = teachers.filter(level=level_filter)

    return render(request, 'transfer/teachers_list.html', {
        'teacher':      teacher,
        'region':       region,
        'district':     district,
        'teachers':     teachers,
        'level_filter': level_filter,
        'total':        teachers.count(),
        'mpesa_number': MPESA_NUMBER,
        'mpesa_name':   MPESA_NAME,
    })


def donate(request):
    """Msaada wa hiari — TZS 1,000 kwa uendeshaji wa mfumo."""
    teacher = _get_teacher(request)
    if not teacher:
        return redirect('transfer:home')

    return render(request, 'transfer/donate.html', {
        'teacher':      teacher,
        'mpesa_number': MPESA_NUMBER,
        'mpesa_name':   MPESA_NAME,
    })


def login_returning(request):
    """Mwalimu aliyekwisha jaza taarifa aingie kwa namba ya simu + wilaya.
    Wilaya zote za Tanzania zinaonyeshwa kwenye dropdown inayoweza kusearch."""
    errors = {}
    form_data = {}

    # Pata wilaya zote za Tanzania pamoja na mikoa yake — kwa searchable dropdown
    try:
        from field_app.models import District
        districts_qs = District.objects.using('default').select_related('region').order_by('region__name', 'name')
        all_districts = [
            {'name': d.name, 'region': d.region.name}
            for d in districts_qs
        ]
    except Exception:
        all_districts = []

    if request.method == 'POST':
        form_data = request.POST.dict()
        phone    = request.POST.get('phone', '').strip()
        district = request.POST.get('district', '').strip()

        if not phone:
            errors['phone'] = 'Weka namba yako ya simu'
        if not district:
            errors['district'] = 'Chagua wilaya unayofundisha'

        if not errors:
            teacher = TeacherTransfer.objects.using('transfer').filter(
                phone=phone,
                district_name=district,
                is_active=True,
            ).first()

            if teacher:
                request.session['transfer_session_key'] = teacher.session_key
                messages.success(request, f'Karibu tena, {teacher.name}! Umeingia mfumo.')
                return redirect('transfer:home')
            else:
                errors['general'] = 'Namba ya simu au wilaya si sahihi. Hakikisha umechagua wilaya sahihi.'

    return render(request, 'transfer/login.html', {
        'errors': errors,
        'form_data': form_data,
        'all_districts': all_districts,
    })


def logout_transfer(request):
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
