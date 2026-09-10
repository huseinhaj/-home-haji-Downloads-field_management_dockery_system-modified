from django.http import HttpResponsePermanentRedirect

# Hosts ambazo zinapaswa kufungua mfumo wa results (app iliyopo /shule/)
RESULTS_DOMAIN_HOSTS = {
    'studentschoolresultsystem.online',
    'www.studentschoolresultsystem.online',
}

RESULTS_ROOT_PATH = '/shule/'


class ResultsDomainRedirectMiddleware:
    """Mtu akifungua root ya studentschoolresultsystem.online ampelekwe /shule/."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()
        if host in RESULTS_DOMAIN_HOSTS and request.path == '/':
            return HttpResponsePermanentRedirect(RESULTS_ROOT_PATH)
        return self.get_response(request)
