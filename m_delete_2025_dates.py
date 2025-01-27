# script to delete all tee times from 2025 and beyond

import os
import django

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')

# Initialize the Django environment
django.setup()

from GRPR.models import TeeTimesInd

# Delete all tee times from 2025 and beyond
TeeTimesInd.objects.filter(gDate__gt='2025-01-01').delete()