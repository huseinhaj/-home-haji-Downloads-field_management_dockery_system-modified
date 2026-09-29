# National coat of arms, served from Wikimedia Commons' CDN rather than a
# copy in our own static files.
TZ_EMBLEM_URL = "https://upload.wikimedia.org/wikipedia/commons/c/c2/Coat_of_arms_of_Tanzania.svg"

# Published contact number academics across every school can use to reach
# the system administrator (also shown in registration_views.py's
# school-needs-an-academic page).
SUPPORT_PHONE = "0625607088"


def branding(request):
    """Per-district branding for the masthead/header/footer.

    The results app now serves any secondary school in Tanzania, not just
    Kyerwa DC, so the district name (and whether we actually have that
    council's logo on file) must come from the logged-in user's own
    school rather than being hardcoded.
    """
    user = getattr(request, 'user', None)
    school = getattr(user, 'school', None) if user and getattr(user, 'is_authenticated', False) else None
    district = school.district if school else None
    is_kyerwa = bool(district) and 'kyerwa' in district.lower()
    # "Join <Wilaya> DC Joint Exams" — Mtaaluma wa wilaya yenye joint program tu
    district_joint = None
    if school and getattr(user, 'is_academic', False):
        from .district_models import district_program_name
        district_joint = district_program_name(school)
    return {
        'DISTRICT_JOINT_NAME': district_joint,
        'DISTRICT_NAME': district,
        'IS_KYERWA': is_kyerwa,
        'TZ_EMBLEM_URL': TZ_EMBLEM_URL,
        'SUPPORT_PHONE': SUPPORT_PHONE,
    }
