import os

def enviro(request):
    from django.conf import settings
    return {
        'ENVIRO': settings.ENVIRO
    }

def twilio_enabled(request):
    return {
        'TWILIO_ENABLED': os.environ.get('TWILIO_ENABLED', 'False') == 'True'
    }