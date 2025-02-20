import math    # used to round up to integers
import random  # used to randomize the golfer order
import os
import django

# Set up the Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()
# import needdd tables
from GRPR.models import Players, Courses, TeeTimesInd, Xdates




# Get all players
preRandomGolfers = []

players = Players.objects.exclude(id=25).exclude(SplitPartner__isnull=False)
for player in players:
    pID = player.id
    print(f"{pID} {player.FirstName} {player.LastName}")
    preRandomGolfers.append(pID)

print()

# Get all split players
s_golfers = []

splitPlayers = Players.objects.filter(SplitPartner__isnull=False)
for s_plyr in splitPlayers:
    pID = s_plyr.id
    split_pID = s_plyr.SplitPartner
    print(f"{pID} {s_plyr.FirstName} {s_plyr.LastName} {split_pID}")
    if split_pID not in s_golfers:
        s_golfers.append(pID)
        preRandomGolfers.append(pID)

for pID in s_golfers:
    print(pID)

print()
for pID in preRandomGolfers:
    print(pID)

# def split_partners_distro():
# 	prds = [1,2,4,20] # hard coded list of players that need to be split
# 	for p in prds:
# 		print()
# 		splitPartnerTeeTimes = TeeTimesInd.objects.filter(PID_id=p, gDate__gt='2025-01-01').values('id')
# 		splitID = Players.objects.get(SplitPartner=p)
# 		trn = 0
# 		for tt in splitPartnerTeeTimes:
# 			tt_id = tt['id']
# 			print(tt_id)
# 			if trn == 0:
# 				trn = 1
# 				print(tt_id, 'stays with original player')
# 			else:
# 				# give this tee time to the split partner
# 				TeeTimesInd.objects.filter(id=tt_id).update(
# 					PID=splitID
# 				)
# 				print(tt_id, 'changed to', splitID)
# 				trn = 0

