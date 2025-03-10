def enviro(request):
    from django.conf import settings
    return {
        'ENVIRO': settings.ENVIRO
    }