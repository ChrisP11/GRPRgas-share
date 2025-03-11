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
('Chris', 'Prouty', 'cprouty@gmail.com', '13122961817', None),
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


# then link the new players in the Players table to the User table
for first_name, last_name, email, mobile, split_partner in new_players:
    user = User.objects.get(username='cprouty')
    player = Players.objects.get(FirstName=first_name, LastName=last_name)
    player.user = user
    player.save()
    print(f"Linked user: {first_name} {last_name} {email} {mobile} {split_partner} {crew_id}")
