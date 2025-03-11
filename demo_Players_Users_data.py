### This code takes a list of new users (see new_players list below) and inserts them into 
### the Players table and the User table.  It then links the new players in the Players table by FK

import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')# Replace 'myproject' with your project name
django.setup()

from django.contrib.auth.models import User
from GRPR.models import Players, Courses

# new players to add
new_players = [
('Jimmy', 'McNulty', 'JimmyMcNulty@gnail.com', '13125551212', None),
('William', 'Rawls', 'WilliamRawls@gnail.com', '13125551212', None),
('Russell', 'Bell', 'RussellBell@gnail.com', '13125551212', None),
('Ervin', 'Burrell', 'ErvinBurrell@gnail.com', '13125551212', None),
('DAngelo', 'Barksdale', 'DAngeloBarksdale@gnail.com', '13125551212', None),
('Avon', 'Barksdale', 'AvonBarksdale@gnail.com', '13125551212', None),
('Rhonda', 'Pearlman', 'RhondaPearlman@gnail.com', '13125551212', None),
('William', 'Moreland', 'WilliamMoreland@gnail.com', '13125551212', None),
('Cedric', 'Daniels', 'CedricDaniels@gnail.com', '13125551212', None),
('Reginald', 'Cousins', 'ReginaldCousins@gnail.com', '13125551212', None),
('Kima', 'Greggs', 'KimaGreggs@gnail.com', '13125551212', None),
('Frank', 'Sobotka', 'FrankSobotka@gnail.com', '13125551212', None),
('Spiros', 'Vondopoulos', 'SpirosVondopoulos@gnail.com', '13125551212', None),
('Lester', 'Freamon', 'LesterFreamon@gnail.com', '13125551212', None),
('Beatrice', 'Russell', 'BeatriceRussell@gnail.com', '13125551212', None),
('Tommy', 'Carcetti', 'TommyCarcetti@gnail.com', '13125551212', None),
('Roland', 'Pryzbylewski', 'RolandPryzbylewski@gnail.com', '13125551212', None),
('Howard', 'Colvin', 'HowardColvin@gnail.com', '13125551212', None),
('Ellis', 'Carver', 'EllisCarver@gnail.com', '13125551212', None),
('Thomas', 'Hauk', 'ThomasHauk@gnail.com', '13125551212', None),
('Preston', 'Broadus', 'PrestonBroadus@gnail.com', '13125551212', None),
('Omar', 'Little', 'OmarLittle@gnail.com', '13125551212', None),
('Leander', 'Sydnor', 'LeanderSydnor@gnail.com', '13125551212', None),
# ('Chris', 'Prouty', 'cprouty@gmail.com', '13122961817', None),
('Dennis', 'Wise', 'DennisWise@gnail.com', '13125551212', None),
('Marlo', 'Stanfield', 'MarloStanfield@gnail.com', '13125551212', None),
('Clarence', 'Royce', 'ClarenceRoyce@gnail.com', '13125551212', None),
('Andrew', 'Volckens', 'avolckens@huntsmanag.com', '14152901090', None),
('Chris', 'Partlow', 'ChrisPartlow@gnail.com', '13125551212', None),
('Homer', 'Simpson', 'HomerSimpson@gnail.com', '13125551212', None),
('Scott', 'Galloway', 'ScottGalloway@gnail.com', '13125551212', None),
]

crew_id = 1

# add new players to the Players table
for first_name, last_name, email, mobile, split_partner in new_players:
    add_player = Players.objects.create(
    CrewID=crew_id,
    FirstName=first_name,
    LastName=last_name,
    Email=email,
    Mobile=mobile,
    SplitPartner=split_partner
    )

    print(f"Added player: {first_name} {last_name} {email} {mobile} {split_partner} {crew_id}")



# then add the new players to the User table
for first_name, last_name, email, mobile, split_partner in new_players:
    user = User.objects.create_user(username=email, email=email, password='pword1', first_name=first_name, last_name=last_name)
    user.save()
    print(f"Added user: {first_name} {last_name} {email} {mobile} {split_partner} {crew_id}")



# then link the new players in the Players table to the User table
for first_name, last_name, email, mobile, split_partner in new_players:
    user = User.objects.get(username=email)
    player = Players.objects.get(FirstName=first_name, LastName=last_name)
    player.user = user
    player.save()
    print(f"Linked user: {first_name} {last_name} {email} {mobile} {split_partner} {crew_id}")



# New Courses to add
courses_data = [
    (1, "The Preserve", "7:10"),
    (1, "The Preserve", "8:50"),
    (1, "The Preserve", "9:00"),
]

# Insert data into Courses table
for course_id, course_name, course_time_slot in courses_data:
    add_course = Courses.objects.create(
        CourseID=course_id,
        CourseName=course_name,
        CourseTimeSlot=course_time_slot
    )