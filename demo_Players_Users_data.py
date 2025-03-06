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
    ('Jimmy', 'McNulty', 'cprouty@gmail.com', '13125551212', None),
    ('William', 'Rawls', 'cprouty@gmail.com', '13125551212', None),
    ('Russell', 'Bell', 'cprouty@gmail.com', '13125551212', None),
    ('Ervin', 'Burrell', 'cprouty@gmail.com', '13125551212', None),
    ('DAngelo', 'Barksdale', 'cprouty@gmail.com', '13125551212', None),
    ('Avon', 'Barksdale', 'cprouty@gmail.com', '13125551212', None),
    ('Rhonda', 'Pearlman', 'cprouty@gmail.com', '13125551212', None),
    ('William', 'Moreland', 'cprouty@gmail.com', '13125551212', None),
    ('Cedric', 'Daniels', 'cprouty@gmail.com', '13125551212', None),
    ('Reginald', 'Cousins', 'cprouty@gmail.com', '13125551212', None),
    ('Kima', 'Greggs', 'cprouty@gmail.com', '13125551212', None),
    ('Frank', 'Sobotka', 'cprouty@gmail.com', '13125551212', None),
    ('Spiros', 'Vondopoulos', 'cprouty@gmail.com', '13125551212', None),
    ('Lester', 'Freamon', 'cprouty@gmail.com', '13125551212', None),
    ('Beatrice', 'Russell', 'cprouty@gmail.com', '13125551212', None),
    ('Tommy', 'Carcetti', 'cprouty@gmail.com', '13125551212', None),
    ('Roland', 'Pryzbylewski', 'cprouty@gmail.com', '13125551212', None),
    ('Howard', 'Colvin', 'cprouty@gmail.com', '13125551212', None),
    ('Ellis', 'Carver', 'cprouty@gmail.com', '13125551212', None),
    ('Thomas', 'Hauk', 'cprouty@gmail.com', '13125551212', None),
    ('Preston', 'Broadus', 'cprouty@gmail.com', '13125551212', None),
    ('Omar', 'Little', 'cprouty@gmail.com', '13125551212', None),
    ('Leander', 'Sydnor', 'cprouty@gmail.com', '13125551212', None),
    ('Norman', 'Wilson', 'cprouty@gmail.com', '13125551212', None),
    ('Dennis', 'Wise', 'cprouty@gmail.com', '13125551212', None),
    ('Marlo', 'Stanfield', 'cprouty@gmail.com', '13125551212', None),
    ('Clarence', 'Royce', 'cprouty@gmail.com', '13125551212', None),
    ('Augustus', 'Haynes', 'cprouty@gmail.com', '13125551212', None),
    ('Chris', 'Partlow', 'cprouty@gmail.com', '13125551212', None),
    ('Homer', 'Simpson', 'cprouty@gmail.com', '13125551212', None),
    ('Scott', 'Galloway', 'cprouty@gmail.com', '13125551212', None),
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

