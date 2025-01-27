######################################################################################################################
### January 2025                                                                                                   ###
### see prior version for big revamp notes from last year                                                          ###
### This version utilizes grpr db in the djnago enviro to get players, ex dates, and course data                   ###
### still hard coded on dates and split partners                                                                   ###
### this version also checks for 2025 dates already existing and does not run if that is the case                  ###
######################################################################################################################

import math    # used to round up to integers
import random  # used to randomize the golfer order
import os
import django

# Set up the Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()
# import needdd tables
from GRPR.models import Players, Courses, TeeTimesInd, Xdates

def seed_process():
	# Randomize the order of the golfers - needed because some orders of golfers can result in some players not getting enough rounds
	golfers = preRandomGolfers.copy() # copy is necessary otherwise I randomize BOTH lists with the next command.
	random.shuffle(golfers)

	# Date Golfer Tracker - seed the dateGolferDict which tracks the golfers associated by date
	for i in range(0, len(teetimes)):
		date = teetimes[i]["date"]
		dateGolferDict[date] = []


	# Foursome Seed - For each date, create a date/course pair and populate that as the ‘seed’ for the foursomes
	for i in range (0,len(teetimes)):
		date = teetimes[i]["date"]
		for j in range(0, len(courses)):
			korse = courses[j]["name"]
			if date in foursomes:
				foursomes[date][korse] = []
			else:
				foursomes[date] = {korse:[]}

	# Dance Card- outer dict is every golfer, inner dict is every golfer with a tracking number
	for i in range (0, len(golfers)):
		player = golfers[i]
		for j in range (0, len(golfers)):
			# if player has already been added to the 'outer' dict, update the proper inner dict
			if player == golfers[j]:
				pass # print(f'{player} is the same as the current {golfers[j]} and will not be added to the Dance Card.')
			elif player in danceCard:
				danceCard[player][golfers[j]] = 0
			# if the player has not been added to the out dict, do so with the first golfer
			else:
				danceCard[player] = {golfers[j] : 0}

	# Slot Tracker - how many rounds each golfer has played
	for i in range (0, len(golfers)):
		golferSlotsDict[golfers[i]] = 0

	# Course Tracker - How many times each player has played a course
	for i in range (0, len(courses)):
		korse = courses[i]['name']
		for j in range (0, len(golfers)):
			# if course has already been added to the 'outer' dict, update the proper inner dict
			if korse in courseGolferDict:
				courseGolferDict[korse][golfers[j]] = 0
			# if the course has not been added to the out dict, do so with the first golfer
			else:
				courseGolferDict[korse] = {golfers[j] : 0}
	return golfers 



# creates the 4somes
def create_foursomes(maxRounds, maxPerCourse):
	# variable to track how many slots in each foursome have been used.  This allows for a while loop that fills the first slot in each foursome, then the second, etc.
	golfSlot = 1
	while golfSlot < 5:
		for date in foursomes:
			for korse in foursomes[date]:
				# create the basket to catch all available players
				basket = {}
				# check to see if a golfer is available for the date/course combo
				for i in range (0, len(golfers)):
					# check if that player is playing the current date (Hard)
					player = golfers[i]
					if date in dateGolferDict and player in dateGolferDict[date]:
						pass # print(f"{player} is already playing {date}, they cannot be chosen.")
					else:
						# check the players Requested Off dates
						if player in exDatesDict and date in exDatesDict[player]:
							pass # print(f'{player} has requested {date} off and is removed from consideration.')
						else:
							# check if the player has played the max number of plays allowed (Hard)
							slotsPlayed = golferSlotsDict[player]
							if slotsPlayed >= maxRounds:
								pass # print(f"{player} has played the maximum number of rounds available and can no longer be chosen")
							else:
						    	# see if the player has hit maximum number of plays on the course
								coursePlayed = courseGolferDict[korse][player]
								if coursePlayed >= maxPerCourse:
									pass # print(f"{player} has played this {korse} the max number ({courseGolferDict[korse][player]}) already.")
								else:
									# now we create the basket and fill it with the players who can play and give them a score.
									# slotsPlayed + coursePlayed + dcScore (times played with people already in the 4some)
									# the higher the score, the less likely they will be picked
									# the IF statements check the current size of the 4some
									if len(foursomes[date][korse]) == 0:
										dcScore = 0 # no other players in the 4some, dcScore is zero
									if len(foursomes[date][korse]) == 1:
										p1 = foursomes[date][korse][0]
										dcScore = danceCard[player][p1]
									if len(foursomes[date][korse]) == 2:
										p1 = foursomes[date][korse][0]
										p2 = foursomes[date][korse][1]
										dcScore = danceCard[player][p1] + danceCard[player][p2]
									if len(foursomes[date][korse]) == 3:
										p1 = foursomes[date][korse][0]
										p2 = foursomes[date][korse][1]
										p3 = foursomes[date][korse][2]
										dcScore = danceCard[player][p1] + danceCard[player][p2] + danceCard[player][p3]
									# player added to the basket here:
									basket[player] = slotsPlayed + coursePlayed + dcScore

				# print(date, korse, 'basket = ', basket)
				# get the player with the lowest (best) value from the basket
				minValue = min(basket.values())
				# reverse engineer to get the key (which is the player name) for the lowest value
				chosenPlayer = [key for key, value in basket.items() if value == minValue][0]
				# print('Player chosen', chosenPlayer)
				if len(foursomes[date][korse]) == 1:
					danceCard[p1][chosenPlayer] += 1
					danceCard[chosenPlayer][p1] += 1
				if len(foursomes[date][korse]) == 2:
					danceCard[p1][chosenPlayer] += 1
					danceCard[chosenPlayer][p1] += 1
					danceCard[p2][chosenPlayer] += 1
					danceCard[chosenPlayer][p2] += 1
				if len(foursomes[date][korse]) == 3:
					danceCard[p1][chosenPlayer] += 1
					danceCard[chosenPlayer][p1] += 1
					danceCard[p2][chosenPlayer] += 1
					danceCard[chosenPlayer][p2] += 1
					danceCard[p3][chosenPlayer] += 1
					danceCard[chosenPlayer][p3] += 1

				# add the player to the foursome
				foursomes[date][korse].append(chosenPlayer)
				# update the Chosen Player stats
				dateGolferDict[date].append(chosenPlayer)
				golferSlotsDict[chosenPlayer] += 1
				courseGolferDict[korse][chosenPlayer] += 1

		# variable to track how many slots in each foursome have been used.  
		# This allows for a while loop that fills the first slot in each foursome, then the second, etc.
		golfSlot += 1


# prints the foursomes
def results():
	print()
	print('Foursome Tracker')
	for i in range(0, len(teetimes)):
		date = teetimes[i]['date']
		for j in range(0, len(courses)):
			korse = courses[j]['name']
			print(date,",", korse, foursomes[date][korse][0], ",",foursomes[date][korse][1], ",",foursomes[date][korse][2], ",",foursomes[date][korse][3])
			plyr1 = Players.objects.get(id=foursomes[date][korse][0])
			plyr2 = Players.objects.get(id=foursomes[date][korse][1])
			plyr3 = Players.objects.get(id=foursomes[date][korse][2])
			plyr4 = Players.objects.get(id=foursomes[date][korse][3])
			korseObj = Courses.objects.get(id=korse)
			
			new_teetime_insert = TeeTimesInd(CrewID=1, gDate=date, CourseID=korseObj, PID=plyr1)
			new_teetime_insert.save()
			new_teetime_insert = TeeTimesInd(CrewID=1, gDate=date, CourseID=korseObj, PID=plyr2)
			new_teetime_insert.save()
			new_teetime_insert = TeeTimesInd(CrewID=1, gDate=date, CourseID=korseObj, PID=plyr3)
			new_teetime_insert.save()
			new_teetime_insert = TeeTimesInd(CrewID=1, gDate=date, CourseID=korseObj, PID=plyr4)
			new_teetime_insert.save()
	print()

def split_partners_distro():
	prds = [1,2,4,20] # hard coded list of players that need to be split
	for p in prds:
		print()
		splitPartnerTeeTimes = TeeTimesInd.objects.filter(PID_id=p, gDate__gt='2025-01-01').values('id')
		splitID = Players.objects.get(SplitPartner=p)
		trn = 0
		for tt in splitPartnerTeeTimes:
			tt_id = tt['id']
			print(tt_id)
			if trn == 0:
				trn = 1
				print(tt_id, 'stays with original player')
			else:
				# give this tee time to the split partner
				TeeTimesInd.objects.filter(id=tt_id).update(
					PID=splitID
				)
				print(tt_id, 'changed to', splitID)
				trn = 0


# Query the Players table and get PIDs
preRandomGolfers = []
# hard coded OUT the second split player - see below in the results() function where this needs to
players = Players.objects.exclude(id=25).exclude(SplitPartner__in=[1, 2, 4, 20])
for player in players:
	pID = player.id
	preRandomGolfers.append(pID)



courses = []
korses = Courses.objects.filter(crewID=1)
for korse in korses:
	cID = korse.id
	courses.append({'name': cID})


# 2025 dates, # Ryder Cup is 7/19 & 7/26
# will have to update later if we keep MM and it has a shortened season - not here but elsewhere
teetimes = [{'date': '2025-04-19'}, {'date': '2025-04-26'}, {'date': '2025-05-03'}, {'date': '2025-05-10'}
			, {'date': '2025-05-17'}, {'date': '2025-05-24'}, {'date': '2025-05-31'}, {'date': '2025-06-07'}
			, {'date': '2025-06-14'}, {'date': '2025-06-21'}, {'date': '2025-06-28'}, {'date': '2025-07-05'}
			, {'date': '2025-07-12'}, {'date': '2025-08-02'}, {'date': '2025-08-09'}, {'date': '2025-08-16'}
			, {'date': '2025-08-23'}, {'date': '2025-08-30'}]


exDatesDict = {
	1 : ['2025-06-28', '2025-07-05', '2025-08-16']
	,2 : ['2025-08-16', '2025-08-23', '2025-08-30']
	,4 : ['2025-04-26', '2025-06-14', '2025-08-16']
	,7 : ['2025-04-19', '2025-04-26', '2025-05-03', '2025-05-10', '2025-05-17', '2025-05-24', '2025-06-07', '2025-06-14', '2025-07-1', '2025-08-09']
	,6 : ['2025-05-10', '2025-05-17', '2025-05-24']
	,7 : ['2025-04-19', '2025-07-05', '2025-08-30']
	,8 : ['2025-07-19', '2025-08-16']
	,9 : ['2025-05-10', '2025-07-05', '2025-07-19']
	,10 : ['2025-05-10', '2025-06-28', '2025-07-12']
	,11 : ['2025-04-26', '2025-06-07', '2025-06-14']
	,12 : ['2025-05-03', '2025-05-24', '2025-06-28']
	,13 : ['2025-06-14', '2025-06-28']
	,14 : ['2025-05-10', '2025-06-21']
	,15 : ['2025-05-24', '2025-06-07']
	,16 : ['2025-06-14', '2025-07-05', '2025-08-30']
	,17 : ['2025-04-26', '2025-08-16']
	,18 : ['2025-04-19', '2025-05-10', '2025-05-17']
	,19 : ['2025-07-05']
	,20 : ['2025-05-17', '2025-06-07']
}


# create a variable to track if we need to run everything again
resultsGood = 0
# run IF loop based on the value of that variable
while resultsGood == 0:
	# dicts created to capture data - placed here to get wiped clean each re-run
	golfers = []          # used for the randomized list of golfers generated via the random module from the preRandomGolfers
	dateGolferDict = {}   # tracks date with associated golfers as a check for Already Played
	golferSlotsDict = {}  # tracks number of slots a player has used so far
	courseGolferDict = {} # tracks number of times golfer has played a course
	danceCard = {}        # This will track how often they have played with each other.
	foursomes = {}        # used to build the foursomes

	# set max variables
	maxRounds = math.ceil(len(courses)*len(teetimes)*4/len(preRandomGolfers))
	maxPerCourse = math.ceil(maxRounds/len(courses))

	# run the seed process - preps the data capture dicts
	seed_process()
	golfers = seed_process()
	print('golfers in randomized order:', golfers)

	# create the foursomes
	create_foursomes(maxRounds, maxPerCourse)

	# check to see if someone got shorted
	# special section to cover Mike Ewell and his short summer
	# del golferSlotsDict['Mike Ewell']
	del golferSlotsDict[7]
	minSlots = min(golferSlotsDict.values())
	print()
	if minSlots < maxRounds - 1:
		print('someone is being shorted - Max Rounds', maxRounds, 'Min Slot', minSlots, 'run it again!')
		# Clear out the data that was just entered into TeeTimesInd using gDate is more recent than 2025-01-01
		TeeTimesInd.objects.filter(gDate__gt='2025-01-01').delete()
	else:
		print('everyone gets to play enough Max Rounds', maxRounds, 'Min Slot', minSlots,)
		from GRPR.models import TeeTimesInd, Players
		resultsGood = 1

# get count for number of tee times are in 2025, this will prevent running for 2025 dates when it has already been done
post2025_teetimes=TeeTimesInd.objects.filter(gDate__gt='2025-01-01').count()

if post2025_teetimes == 0:
	# run the initial teetimes creation, will print results 
	results()
	# update teetimes to alternate teetimes bt split partners
	split_partners_distro()
	print()
	# this nugget is for the prima donna Brad Hunter - basically I re-ran the dmn thing until I knew he would not bitch
	print('Brad slots', golferSlotsDict[9])
	# print('me slots', golferSlotsDict['Chris Prouty'])
	print('Brad at MM', courseGolferDict[1][9])
	# print('Me at MM', courseGolferDict['Maple Meadows']['Chris Prouty'])
else:
	print('Tee Times already created for 2025')





