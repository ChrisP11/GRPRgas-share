# filepath: /Users/cprouty/Dropbox/Dev/Python/Apps/GRPR/insert_courses.py

import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from GRPR.models import Courses

# Data to be inserted
courses_data = [
    {"crewID": 1, "courseName": "The Preserve", "courseTimeSlot": "7:10"},
    {"crewID": 1, "courseName": "The Preserve", "courseTimeSlot": "8:50"},
    {"crewID": 1, "courseName": "The Preserve", "courseTimeSlot": "9:00"},
]

# Insert data into Courses table
for course in courses_data:
    Courses.objects.create(**course)
