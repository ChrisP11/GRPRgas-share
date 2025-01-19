import os
import django

# Set up the Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from GRPR.models import Players

# Query the Players table and print FirstName and LastName
players = Players.objects.exclude(id=25)
for player in players:
    # print(f"{player.id} {player.FirstName} {player.LastName}")
    # pName = player.FirstName, " ", player.LastName
    pName = (f"{player.FirstName} {player.LastName}")
    print(pName)

    # preRandomGolfers.append({player.FirstName},{player.LastName})