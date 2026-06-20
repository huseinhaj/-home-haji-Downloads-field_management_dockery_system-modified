class NoCacheAuthMiddleware:
    """
    Security middleware: prevents caching of authenticated pages and
    adds defence-in-depth HTTP security headers on every response.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Security headers for ALL responses (authenticated or not)
        response.setdefault('X-Content-Type-Options', 'nosniff')
        response.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.setdefault('X-XSS-Protection', '1; mode=block')

        if request.user.is_authenticated:
            # Prevent browsers and proxies from caching authenticated pages.
            # 'private' stops CDN/proxy caching; 'no-store' stops disk cache;
            # 'must-revalidate' forces recheck after any stored copy expires.
            response['Cache-Control'] = (
                'no-store, no-cache, must-revalidate, private, max-age=0'
            )
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            response['Vary'] = 'Cookie'

        return response
