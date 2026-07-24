# National coat of arms for the Teaching & Learning Materials portal
# Served from Wikimedia Commons' CDN
TZ_EMBLEM_URL = "https://upload.wikimedia.org/wikipedia/commons/c/c2/Coat_of_arms_of_Tanzania.svg"

SUPPORT_PHONE = "0625607088"


def branding(request):
    """Branding context for the Teaching & Learning Materials portal."""
    return {
        'TZ_EMBLEM_URL': TZ_EMBLEM_URL,
        'SUPPORT_PHONE': SUPPORT_PHONE,
    }
