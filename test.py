import os
import django

# Set up the Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from GRPR.models import Players

# Query the Players table and print FirstName and LastName
players = Players.objects.exclude(id=25).exclude(SplitPartner__in=[2, 4, 20])
for player in players:
	pID = player.id
	print(pID)


