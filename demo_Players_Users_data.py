### This code takes a list of new users (see new_players list below) and inserts them into 
### the Players table and the User table.  It then links the new players in the Players table by FK

import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')# Replace 'myproject' with your project name
django.setup()

from django.contrib.auth.models import User
from GRPR.models import Players



# new players to add
new_players = [
    ('Jimmy', 'McNulty', 'McNulty@gnail.com', '13125551212', None),
    ('William', 'Rawls', 'Rawls@gnail.com', '13125551212', None),
    ('Russell', 'Bell', 'Bell@gnail.com', '13125551212', None),
    ('Ervin', 'Burrell', 'Burrell@gnail.com', '13125551212', None),
    ('DAngelo', 'Barksdale', 'Barksdale@gnail.com', '13125551212', None),
    ('Avon', 'Barksdale', 'Barksdale@gnail.com', '13125551212', None),
    ('Rhonda', 'Pearlman', 'Pearlman@gnail.com', '13125551212', None),
    ('William', 'Moreland', 'Moreland@gnail.com', '13125551212', None),
    ('Cedric', 'Daniels', 'Daniels@gnail.com', '13125551212', None),
    ('Reginald', 'Cousins', 'Cousins@gnail.com', '13125551212', None),
    ('Kima', 'Greggs', 'Greggs@gnail.com', '13125551212', None),
    ('Frank', 'Sobotka', 'Sobotka@gnail.com', '13125551212', None),
    ('Spiros', 'Vondopoulos', 'Vondopoulos@gnail.com', '13125551212', None),
    ('Lester', 'Freamon', 'Freamon@gnail.com', '13125551212', None),
    ('Beatrice', 'Russell', 'Russell@gnail.com', '13125551212', None),
    ('Tommy', 'Carcetti', 'Carcetti@gnail.com', '13125551212', None),
    ('Roland', 'Pryzbylewski', 'Pryzbylewski@gnail.com', '13125551212', None),
    ('Howard', 'Colvin', 'Colvin@gnail.com', '13125551212', None),
    ('Ellis', 'Carver', 'Carver@gnail.com', '13125551212', None),
    ('Thomas', 'Hauk', 'Hauk@gnail.com', '13125551212', None),
    ('Preston', 'Broadus', 'Broadus@gnail.com', '13125551212', None),
    ('Omar', 'Little', 'Little@gnail.com', '13125551212', None),
    ('Leander', 'Sydnor', 'Sydnor@gnail.com', '13125551212', None),
    ('Norman', 'Wilson', 'Wilson@gnail.com', '13125551212', None),
    ('Dennis', 'Wise', 'Wise@gnail.com', '13125551212', None),
    ('Marlo', 'Stanfield', 'Stanfield@gnail.com', '13125551212', None),
    ('Clarence', 'Royce', 'Royce@gnail.com', '13125551212', None),
    ('Augustus', 'Haynes', 'Haynes@gnail.com', '13125551212', None),
    ('Chris', 'Partlow', 'Partlow@gnail.com', '13125551212', None),
    ('Homer', 'Simpson', 'Simpson@gnail.com', '13125551212', None),
    ('Scott', 'Galloway', 'Galloway@gnail.com', '13125551212', None),
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

