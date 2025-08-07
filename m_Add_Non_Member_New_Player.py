### This code allows for manual input of a new player, non member

import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from django.contrib.auth.models import User
from GRPR.models import Players



# new players to add
new_players = [
    ('Ed', 'Kemper', 'edward.kemper5@gmail.com', '17087046284', None),
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
        SplitPartner=split_partner,
        Member = 0,
    )

    print(f"Added player: {first_name} {last_name} {email} {mobile} {split_partner} {crew_id} as a non member")



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

