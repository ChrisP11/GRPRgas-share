# filepath: /Users/cprouty/Dropbox/Dev/Python/Apps/GRPR/insert_courses.py

import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from GRPR.models import Courses

# Data to be inserted
courses_data = [
    {1, "The Preserve", "7:10"},
    {1, "The Preserve", "8:50"},
    {1, "The Preserve", "9:00"},
]

# Insert data into Courses table
for course_id, course_name, course_time_slot in courses_data:
    add_course = Courses.objects.create(
        CourseID=course_id,
        CourseName=course_name,
        CourseTimeSlot=course_time_slot
    )