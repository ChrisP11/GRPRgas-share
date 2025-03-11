import os
import django
from datetime import datetime

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from GRPR.models import Xdates

# Data to be inserted
xdates_data = [
    (1, '2025-06-15', datetime.now(), 24),
    (1, '2025-06-21', datetime.now(), 24),
    (1, '2025-08-02', datetime.now(), 24),
    (1, '2025-05-10', datetime.now(), 6),
    (1, '2025-05-31', datetime.now(), 6),
    (1, '2025-07-05', datetime.now(), 6),
    (1, '2025-05-03', datetime.now(), 7),
    (1, '2025-05-24', datetime.now(), 7),
    (1, '2025-07-05', datetime.now(), 7),
    (1, '2025-05-03', datetime.now(), 26),
    (1, '2025-05-24', datetime.now(), 26),
    (1, '2025-07-05', datetime.now(), 26),
    (1, '2025-07-12', datetime.now(), 22),
    (1, '2025-08-16', datetime.now(), 22),
    (1, '2025-08-23', datetime.now(), 22),
    (1, '2025-05-10', datetime.now(), 10),
    (1, '2025-06-07', datetime.now(), 10),
    (1, '2025-06-14', datetime.now(), 10),
    (1, '2025-04-12', datetime.now(), 28),
    (1, '2025-05-10', datetime.now(), 28),
    (1, '2025-06-07', datetime.now(), 13),
    (1, '2025-06-14', datetime.now(), 13),
    (1, '2025-07-05', datetime.now(), 13),
    (1, '2025-06-07', datetime.now(), 1),
    (1, '2025-06-14', datetime.now(), 1),
    (1, '2025-07-05', datetime.now(), 1),
    (1, '2025-04-26', datetime.now(), 23),
    (1, '2025-07-12', datetime.now(), 23),
    (1, '2025-07-19', datetime.now(), 23),
    (1, '2025-04-26', datetime.now(), 16),
    (1, '2025-05-03', datetime.now(), 16),
    (1, '2025-08-10', datetime.now(), 16),
    (1, '2025-04-26', datetime.now(), 22),
    (1, '2025-05-10', datetime.now(), 22),
    (1, '2025-05-17', datetime.now(), 22),
    (1, '2025-04-19', datetime.now(), 17),
    (1, '2025-04-26', datetime.now(), 17),
    (1, '2025-05-03', datetime.now(), 17),
    (1, '2025-05-10', datetime.now(), 17),
    (1, '2025-05-17', datetime.now(), 17),
    (1, '2025-05-24', datetime.now(), 17),
    (1, '2025-05-31', datetime.now(), 17),
    (1, '2025-04-19', datetime.now(), 27),
    (1, '2025-06-07', datetime.now(), 27),
    (1, '2025-06-14', datetime.now(), 27),
    (1, '2025-04-05', datetime.now(), 18),
    (1, '2025-05-03', datetime.now(), 18),
    (1, '2025-08-02', datetime.now(), 18),
    (1, '2025-05-31', datetime.now(), 21),
    (1, '2025-07-10', datetime.now(), 21),
    (1, '2025-08-09', datetime.now(), 21),
    (1, '2025-05-31', datetime.now(), 19),
    (1, '2025-07-10', datetime.now(), 19),
    (1, '2025-08-09', datetime.now(), 19),
    (1, '2025-04-19', datetime.now(), 12),
    (1, '2025-06-21', datetime.now(), 12),
    (1, '2025-06-11', datetime.now(), 15),
    (1, '2025-06-28', datetime.now(), 15),
    (1, '2025-07-05', datetime.now(), 15),
    (1, '2025-08-16', datetime.now(), 15),
    (1, '2025-05-03', datetime.now(), 9),
    (1, '2025-08-23', datetime.now(), 9),
    (1, '2025-08-30', datetime.now(), 9),
    (1, '2025-08-16', datetime.now(), 2),
    (1, '2025-08-23', datetime.now(), 2),
    (1, '2025-08-30', datetime.now(), 2),
]

# Insert data into Xdates table
print("Starting to insert Xdates data...")
for crew_id, x_date, r_date, pid_id in xdates_data:
    print(f"Adding Xdate: {crew_id} {x_date} {r_date} {pid_id}")
    Xdates.objects.create(
        CrewID=crew_id,
        xDate=x_date,
        rDate=r_date,
        PID_id=pid_id
    )
print("Finished inserting Xdates data.")