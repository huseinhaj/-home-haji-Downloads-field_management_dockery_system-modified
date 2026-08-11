from django.shortcuts import render, get_object_or_404
from django.db.models import Count
from .models import College, Program


def home(request):
    """Orodha ya vyuo vyote vya ualimi — mgombea anachagua chuo chake."""
    colleges = College.objects.filter(is_active=True).annotate(
        num_students=Count('students', distinct=True),
        num_programs=Count('programs', distinct=True),
    )
    regions = (
        College.objects.filter(is_active=True)
        .exclude(region='')
        .values_list('region', flat=True)
        .distinct()
        .order_by('region')
    )

    query = request.GET.get('q', '').strip()
    region = request.GET.get('region', '').strip()
    if query:
        colleges = colleges.filter(name__icontains=query)
    if region:
        colleges = colleges.filter(region=region)

    context = {
        'colleges': colleges,
        'regions': regions,
        'total_colleges': College.objects.filter(is_active=True).count(),
        'total_regions': len(regions),
        'query': query,
        'region': region,
    }
    return render(request, 'colleges/home.html', context)


def college_detail(request, code):
    college = get_object_or_404(College, code=code.upper(), is_active=True)
    programs = college.programs.all()
    fee_items = college.fee_items.filter(is_active=True)
    context = {
        'college': college,
        'programs': programs,
        'fee_items': fee_items,
    }
    return render(request, 'colleges/college_detail.html', context)


def programs_api(request):
    """JSON list of programs for a college (used by the register form dropdown)."""
    from django.http import JsonResponse
    college_id = request.GET.get('college')
    programs = Program.objects.all()
    if college_id:
        programs = programs.filter(college_id=college_id)
    return JsonResponse(
        [{'id': p.id, 'name': p.name} for p in programs.order_by('name')],
        safe=False,
    )
