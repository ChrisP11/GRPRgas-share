# middleware.py
from django.conf import settings
from django.http import HttpResponsePermanentRedirect

class SSLRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.is_secure() and not settings.DEBUG:
            url = request.build_absolute_uri(request.get_full_path())
            secure_url = url.replace("http://", "https://")
            return HttpResponsePermanentRedirect(secure_url)
        return self.get_response(request)
    