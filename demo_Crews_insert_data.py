# filepath: /Users/cprouty/Dropbox/Dev/Python/Apps/GRPR/insert_courses.py

import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from GRPR.models import Crews

# Data to be inserted
crews_data = [
    ('GAS', '6', 'Christopher_Coogan@rush.edu', '17083342800'),
]

# Insert data into Courses table
print("Starting to insert crews data...")
for crewName, crewCaptain, email, mobile in crews_data:
    print(f"Adding crew: {crewName}")
    add_course = Crews.objects.create(
        crewName=crewName,
        crewCaptain=crewCaptain,
        email=email,
        mobile=mobile
    )

print("Finished inserting crews data.")