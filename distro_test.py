######################################################################################################################
### 18 January 2025 - testing improvements to tie into the GRPR app for 2025                                       ###  
### Notes from the 2024 final version:                                                                             ###
###                                                                                                                ###
### Big revamp from prior years                                                                                    ###
### version 1 had 3 major changes:                                                                                 ###
### 1. The first slot in every foursome was filled first, then the second slot etc.                                ###
### 2. For every slot, all available players put in a basket, then weighted according to plays, dance card, etc    ###
###   the result being the least weighted is chosen                                                                ###
### 3. Exception dates have been added - thus Golfers can be named and assigned in the code                        ###
### This worked much better than the prior version, but there is a condition for players later in the list         ###
### where they can get 'shorted' on total number of rounds (2 or more short of the max).                           ###
### This is caused by a combo of bad luck in terms of order and exception dates chosen for late in the year.       ###
### Version 1.1 resolved this by randomizing the golfer order AND checking to see if anyone gets shorted.          ###
### If some gets shorted (again, 2 or more less than max), the script gets run again until no one is shorted       ###
### (I did have to hard code in an exception for this rule for Mike Ewell)                                         ###
######################################################################################################################

import math    # used to round up to integers
import random  # used to randomize the golfer order
import os
import django

# Set up the Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from GRPR.models import Players

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
			print(date,",", korse, ", time, ",foursomes[date][korse][0], ",",foursomes[date][korse][1], ",",foursomes[date][korse][2], ",",foursomes[date][korse][3])
	print()

# prep the players list
preRandomGolfers = []

# Query the Players table and print FirstName and LastName
players = Players.objects.exclude(id=25)
for player in players:
    pName = (f"{player.FirstName} {player.LastName}")
    preRandomGolfers.append(pName)

# print(preRandomGolfers)


# lists/dicts with pre loaded data
# preRandomGolfers = [
# 	'Mark Brown'
# 	,'Chris English John Kane'
# 	,'Mike May Pete Birmingham'
# 	,'Chris Coogan'
# 	,'Mike Ewell'
# 	,'John Griffin'
# 	,'Brad Hunter'
# 	,'Mike Peterson'
# 	,'John Mcilwain'
# 	,'Chris Marzec'
# 	,'Chris Prouty'
# 	,'Jaime Santana'
# 	,'Ed Sloan'
# 	,'Mike Stutz'
# 	,'Kelly Taira'
# 	,'Paul Deutsch'
# 	,'Mike DeHaan'
# 	,'John Sullivan Chris Lynn'
# 	,'Keith Huizinga'
# 	,'Mike Ryan'
# 	,'Tom Canepa'
# ]
# Ryder Cup is 7/20 & 7/27
teetimes = [{'date': '2024-04-20'}, {'date': '2024-04-27'}, {'date': '2024-05-04'}, {'date': '2024-05-11'}
			, {'date': '2024-05-18'}, {'date': '2024-05-25'}, {'date': '2024-06-01'}, {'date': '2024-06-08'}
			, {'date': '2024-06-15'}, {'date': '2024-06-22'}, {'date': '2024-06-29'}, {'date': '2024-07-06'}
			, {'date': '2024-07-13'}, {'date': '2024-08-03'}, {'date': '2024-08-10'}, {'date': '2024-08-17'}
			, {'date': '2024-08-24'}, {'date': '2024-08-31'}]
			
courses = [{'name': 'Maple Meadows'}, {'name': 'The Preserve850'}, {'name': 'The Preserve900'}]

# dates requested off by the player
exDatesDict = {
	'Mark Brown': ['2024-06-29', '2024-07-06', '2024-08-17']
	,'Chris English John Kane': ['2024-08-17', '2024-08-24', '2024-08-31']
	,'Mike May Pete Birmingham': ['2024-05-18', '2024-06-08', '2024-08-31']
	,'Chris Coogan': ['2024-04-27', '2024-06-15', '2024-08-17']
	,'Mike Ewell': ['2024-04-20', '2024-04-27', '2024-05-04', '2024-05-11', '2024-05-18', '2024-05-25', '2024-06-01', '2024-06-08', '2024-06-15', '2024-07-13', '2024-08-10']
	,'John Griffin': ['2024-05-11', '2024-05-18', '2024-05-25']
	,'Brad Hunter': ['2024-04-20', '2024-07-06', '2024-08-31']
	,'Chris Marzec': ['2024-07-20', '2024-08-17']
	,'John Mcilwain': ['2024-05-11', '2024-07-06', '2024-07-20']
	,'Mike Peterson': ['2024-05-11', '2024-06-29', '2024-07-13']
	,'Chris Prouty': ['2024-04-27', '2024-06-08', '2024-06-15']
	,'Ed Sloan': ['2024-05-04', '2024-05-25', '2024-06-29']
	,'Mike Stutz': ['2024-06-01', '2024-06-15', '2024-06-29']
	,'Kelly Taira': ['2024-05-11', '2024-06-22']
	,'Paul Deutsch': ['2024-05-25', '2024-06-08']
	,'Mike DeHaan': ['2024-06-15', '2024-07-06', '2024-08-31']
	,'John Sullivan Chris Lynn': ['2024-04-27', '2024-08-17']
	,'Keith Huizinga': ['2024-04-20', '2024-05-11', '2024-05-18']
	,'Mike Ryan': ['2024-07-06']
	,'Tom Canepa': ['2024-05-18', '2024-06-01', '2024-06-08']
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
	print(golfers)

	# create the foursomes
	create_foursomes(maxRounds, maxPerCourse)

	# check to see if someone got shorted
	# special section to cover Mike Ewell and his short summer
	del golferSlotsDict['Mike Ewell']
	minSlots = min(golferSlotsDict.values())
	print()
	if minSlots < maxRounds - 1:
		print('someone is being shorted - Max Rounds', maxRounds, 'Min Slot', minSlots, 'run it again!')
	else:
		print('everyone gets to play enough Max Rounds', maxRounds, 'Min Slot', minSlots,)
		resultsGood = 1

# print the results 
results()
print()

# this nugget is for the prima donna Brad Hunter - basically I re-ran the dmn thing until I knew he would not bitch
print('Brad slots', golferSlotsDict['Brad Hunter'])
print('me slots', golferSlotsDict['Chris Prouty'])
print('Brad at MM', courseGolferDict['Maple Meadows']['Brad Hunter'])
print('Me at MM', courseGolferDict['Maple Meadows']['Chris Prouty'])











