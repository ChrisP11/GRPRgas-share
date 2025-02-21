import math    # used to round up to integers
import random  # used to randomize the golfer order
import os
import django
from datetime import datetime, date

# Set up the Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()
# import needdd tables
from GRPR.models import Players, Courses, TeeTimesInd, Xdates


teetimes = [{'date': '2025-04-19'}, {'date': '2025-04-26'}, {'date': '2025-05-03'}, {'date': '2025-05-10'}
			, {'date': '2025-05-17'}, {'date': '2025-05-24'}, {'date': '2025-05-31'}, {'date': '2025-06-07'}
			, {'date': '2025-06-14'}, {'date': '2025-06-21'}, {'date': '2025-06-28'}, {'date': '2025-07-05'}
			, {'date': '2025-07-12'}, {'date': '2025-08-02'}, {'date': '2025-08-09'}, {'date': '2025-08-16'}
			, {'date': '2025-08-23'}, {'date': '2025-08-30'}]

# get a list of disctinct PIDs in Xdates
distinct_pid_ids = Xdates.objects.filter(CrewID=1).values_list('PID_id', flat=True).distinct()

# Dictionary to store xDates for each PID
exDatesDict = {}

# Iterate through each distinct PID and get the xDates
for pid in distinct_pid_ids:
    xdates = Xdates.objects.filter(PID_id=pid).values_list('xDate', flat=True)
    exDatesDict[pid] = list(xdates)

players = Players.objects.exclude(id=25)


# Convert the dates in exDatesDict to strings in the same format as the dates in teetimes
# for pid, xdates in exDatesDict.items():
#     exDatesDict[pid] = [xdate.strftime('%Y-%m-%d') if isinstance(xdate, datetime) else xdate for xdate in xdates]

# date = '2025-05-10'

# Print each date associated with a PID in exDatesDict
# for pid, xdates in exDatesDict.items():
#     for xdate in xdates:
#         print(xdate.strftime('%Y-%m-%d'), date)
#         if xdate.strftime('%Y-%m-%d') == date:
#             print('finally???')
#         print(f"PID: {pid}, xDate: {xdate}")


# for tt in teetimes:
#     date = tt['date']
#     for player in players:
#         if player.id in exDatesDict and date in exDatesDict[player.id]:
#             print(f"Player {player} has an xDate on {date}")


# Convert the dates in exDatesDict to strings in the same format as the dates in teetimes
for pid, xdates in exDatesDict.items():
    exDatesDict[pid] = [xdate.strftime('%Y-%m-%d') if isinstance(xdate, (datetime, date)) else xdate for xdate in xdates]

# Print each date associated with a PID in exDatesDict
# for pid, xdates in exDatesDict.items():
#     for xdate in xdates:
#         print(f"PID: {pid}, xDate: {xdate}")

# Iterate through the teetimes and players
for tt in teetimes:
    date = tt['date']
    for player in players:
        if player.id in exDatesDict and date in exDatesDict[player.id]:
            print(f"Player {player.FirstName} {player.LastName} (ID: {player.id}) has an xDate on {date}")
        # else:
        #     print(f"Player {player.FirstName} {player.LastName} (ID: {player.id}) does not have an xDate on {date}")


# if player in exDatesDict and date in exDatesDict[player]: