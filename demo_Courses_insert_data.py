# filepath: /Users/cprouty/Dropbox/Dev/Python/Apps/GRPR/insert_courses.py

import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from GRPR.models import Courses

# Data to be inserted
courses_data = [
    (1, "The Preserve", "7:10"),
    (1, "The Preserve", "8:50"),
    (1, "The Preserve", "9:00"),
]

# Insert data into Courses table
print("Starting to insert courses data...")
# for course_id, course_name, course_time_slot in courses_data:
#     print(f"Adding course: {course_id} {course_name} {course_time_slot}")
    # add_course = Courses.objects.create(
    #     crewID=course_id,
    #     courseName=course_name,
    #     courseTimeSlot=course_time_slot
    # )

print("Finished inserting courses data.")