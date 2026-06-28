import uuid
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import TeacherTransfer


def _get_regions():
    """Pata mikoa yote kutoka IMS database."""
    try:
        from field_app.models import Region
        return list(Region.objects.using('default').order_by('name').values('id', 'name'))
    except Exception:
        return []


def _get_districts(region_id):
    """Pata wilaya za mkoa husika kutoka IMS database."""
    try:
        from field_app.models import District
        return list(District.objects.using('default').filter(
            region_id=region_id
        ).order_by('name').values('id', 'name'))
    except Exception:
        return []


def _get_teacher(request):
    """Rudisha TeacherTransfer wa mtumiaji wa session hii, au None."""
    session_key = request.session.get('transfer_session_key')
    if not session_key:
        return None
    return TeacherTransfer.objects.using('transfer').filter(
        session_key=session_key, is_active=True
    ).first()


def home(request):
    """Ukurasa wa nyumbani — uliza kama mwalimu ameshajaza taarifa."""
    teacher = _get_teacher(request)
    return render(request, 'transfer/home.html', {'teacher': teacher})


def register(request):
    """Fomu ya kujisajili kwa mwalimu anayetaka kubadilishana."""
    errors = {}
    form_data = {}

    if request.method == 'POST':
        form_data = request.POST.dict()
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        current_school = request.POST.get('current_school', '').strip()
        level = request.POST.get('level', '').strip()
        subjects = request.POST.get('subjects', '').strip()
        region_name = request.POST.get('region_name', '').strip()
        district_name = request.POST.get('district_name', '').strip()
        location_type = request.POST.get('location_type', '').strip()
        willing_to_go = request.POST.get('willing_to_go', '').strip()

        if not name:
            errors['name'] = 'Jina linahitajika'
        if not phone:
            errors['phone'] = 'Namba ya simu inahitajika'
        if not current_school:
            errors['current_school'] = 'Jina la shule inahitajika'
        if not level:
            errors['level'] = 'Kiwango cha shule kinahitajika'
        if not region_name:
            errors['region_name'] = 'Mkoa unahitajika'
        if not district_name:
            errors['district_name'] = 'Wilaya inahitajika'
        if not location_type:
            errors['location_type'] = 'Aina ya eneo inahitajika'

        if not errors:
            # Tengeneza au sasisha rekodi ya mwalimu huyu
            if not request.session.session_key:
                request.session.create()

            session_key = request.session.get('transfer_session_key')
            if not session_key:
                session_key = str(uuid.uuid4())
                request.session['transfer_session_key'] = session_key

            TeacherTransfer.objects.using('transfer').update_or_create(
                session_key=session_key,
                defaults={
                    'name': name,
                    'phone': phone,
                    'current_school': current_school,
                    'level': level,
                    'subjects': subjects,
                    'region_name': region_name,
                    'district_name': district_name,
                    'location_type': location_type,
                    'willing_to_go': willing_to_go,
                    'is_active': True,
                }
            )
            return redirect('transfer:browse_regions')

    regions = _get_regions()
    return render(request, 'transfer/register.html', {
        'regions': regions,
        'errors': errors,
        'form_data': form_data,
    })


def get_districts_ajax(request):
    """AJAX — rudisha wilaya za mkoa ulioombwa."""
    region_id = request.GET.get('region_id')
    if not region_id:
        return JsonResponse([], safe=False)
    districts = _get_districts(region_id)
    return JsonResponse(districts, safe=False)


def browse_regions(request):
    """Orodha ya mikoa yote — mwalimu achague mkoa wa kutafuta."""
    teacher = _get_teacher(request)
    if not teacher:
        return redirect('transfer:home')
    regions = _get_regions()
    return render(request, 'transfer/browse_regions.html', {
        'teacher': teacher,
        'regions': regions,
    })


def browse_districts(request, region_id):
    """Wilaya za mkoa uliochangiwa."""
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
        'teacher': teacher,
        'region': region,
        'districts': districts,
    })


def teachers_in_district(request, region_id, district_id):
    """Orodha ya walimu wanaotaka kubadilishana katika wilaya husika."""
    teacher = _get_teacher(request)
    if not teacher:
        return redirect('transfer:home')

    try:
        from field_app.models import Region, District
        region = Region.objects.using('default').get(id=region_id)
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
        'teacher': teacher,
        'region': region,
        'district': district,
        'teachers': teachers,
        'level_filter': level_filter,
        'total': teachers.count(),
    })


def deactivate(request):
    """Mwalimu afute taarifa zake (toka kwenye orodha)."""
    if request.method == 'POST':
        teacher = _get_teacher(request)
        if teacher:
            teacher.is_active = False
            teacher.save(using='transfer')
        request.session.pop('transfer_session_key', None)
    return redirect('transfer:home')
