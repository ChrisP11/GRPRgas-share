# middleware.py
from django.conf import settings
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import redirect
from django.urls import reverse

class SSLRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.is_secure() and not settings.DEBUG:
            url = request.build_absolute_uri(request.get_full_path())
            secure_url = url.replace("http://", "https://")
            return HttpResponsePermanentRedirect(secure_url)
        return self.get_response(request)
    

class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            user_profile = getattr(request.user, 'userprofile', None)
            if user_profile and user_profile.force_password_change:
                if request.path != reverse('password_change'):
                    return redirect('password_change')
        response = self.get_response(request)
        return response