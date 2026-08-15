from django.shortcuts import render
from .models import College, Program


def home(request):
    """Landing page rasmi — mwanafunzi anafikia chuo chake kupitia usajili/login."""
    return render(request, 'colleges/home.html')



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
