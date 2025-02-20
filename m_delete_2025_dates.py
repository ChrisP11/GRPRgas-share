# script to delete all tee times from 2025 and beyond

import os
import django

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from GRPR.models import TeeTimesInd

# Count the rows that will be deleted
rows_to_delete = TeeTimesInd.objects.filter(gDate__gt='2025-01-01')
count = rows_to_delete.count()
print(f"Number of rows to be deleted: {count}")

# Delete the rows
rows_to_delete.delete()


count = rows_to_delete.count()
print(f"Number of rows with a date greater than 1/1/25: {count}")