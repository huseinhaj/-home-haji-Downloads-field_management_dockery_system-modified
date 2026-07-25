# National coat of arms for the Teaching & Learning Materials portal
# Served from Wikimedia Commons' CDN
TZ_EMBLEM_URL = "https://upload.wikimedia.org/wikipedia/commons/c/c2/Coat_of_arms_of_Tanzania.svg"

SUPPORT_PHONE = "0625607088"

from .models import TLMTeacher


def branding(request):
    """Branding context for the Teaching & Learning Materials portal."""
    # Get TLM teacher from session (if any) — so ALL templates can show/hide login/logout
    tlm_teacher = None
    teacher_id = request.session.get('tlm_teacher_id')
    if teacher_id:
        try:
            tlm_teacher = TLMTeacher.objects.get(id=teacher_id)
        except TLMTeacher.DoesNotExist:
            if 'tlm_teacher_id' in request.session:
                del request.session['tlm_teacher_id']
    
    return {
        'TZ_EMBLEM_URL': TZ_EMBLEM_URL,
        'SUPPORT_PHONE': SUPPORT_PHONE,
        'tlm_teacher': tlm_teacher,
    }
