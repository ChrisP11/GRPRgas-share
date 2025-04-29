import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from GRPR.models import CourseTees

# Data to be inserted
course_tees_data = [
    ('The Preserves', 1, 'Tournament', 74.1, 142, 72, 6977),
    ('The Preserves', 2, 'Black', 72.4, 138, 72, 6611),
    ('The Preserves', 3, 'Blue/Black', 71.5, 136, 72, 6409),
    ('The Preserves', 4, 'Blue', 70.6, 134, 72, 6207),
    ('The Preserves', 5, 'White/Blue', 69.5, 132, 72, 5964),
    ('The Preserves', 6, 'White', 68.2, 128, 72, 5691),
]

# Insert data into CourseTees table
print("Starting to insert CourseTees data...")
for course_name, tee_id, tee_name, course_rating, slope_rating, par, yards in course_tees_data:
    print(f"Adding CourseTee: {course_name} {tee_id} {tee_name} {course_rating} {slope_rating} {par} {yards}")
    CourseTees.objects.create(
        CourseName=course_name,
        TeeID=tee_id,
        TeeName=tee_name,
        CourseRating=course_rating,
        SlopeRating=slope_rating,
        Par=par,
        Yards=yards
    )
print("Finished inserting CourseTees data.")