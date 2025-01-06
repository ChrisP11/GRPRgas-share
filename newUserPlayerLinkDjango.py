### IMPORTANT, CHANGE FLASTNAMES TO BE ALL LOWER CAPS IN NEXT GO ROUND

# Link an existing user in the User table to a player in the Players table
# via the django shell:  python manage.py shell
# run this:
players_with_users = Players.objects.filter(user__isnull=False)
# to get a list of all the players who already have a FK to Users in Players
for player in players_with_users:
    print(f"Player: {player.FirstName} {player.LastName}, User: {player.user.username}")
# this gets you a count:
count = players_with_users.count()
print(count)

# then add a link for the remaining players
# import first....
from django.contrib.auth.models import User
from GRPR.models import Players

# then the linking.  Again, slim up all the caps....
user = User.objects.get(username='cCoogan')
player = Players.objects.get(FirstName='Chris', LastName='Coogan')
player.user = user
player.save()

user = User.objects.get(username='bHunter')
player = Players.objects.get(FirstName='Brad', LastName='Hunter')
player.user = user
player.save()

user = User.objects.get(username='mBrown') 
player = Players.objects.get(FirstName='Mark', LastName='Brown') 
player.user = user 
player.save()

user = User.objects.get(username='cEnglish') 
player = Players.objects.get(FirstName='Chris', LastName='English') 
player.user = user 
player.save()

user = User.objects.get(username='jKane') 
player = Players.objects.get(FirstName='John', LastName='Kane') 
player.user = user 
player.save()

user = User.objects.get(username='mMay') 
player = Players.objects.get(FirstName='Mike', LastName='May') 
player.user = user 
player.save()

user = User.objects.get(username='pBirmingham') 
player = Players.objects.get(FirstName='Pete', LastName='Birmingham') 
player.user = user 
player.save()

user = User.objects.get(username='mEwell') 
player = Players.objects.get(FirstName='Mike', LastName='Ewell') 
player.user = user 
player.save()

user = User.objects.get(username='jGriffin') 
player = Players.objects.get(FirstName='John', LastName='Griffin') 
player.user = user 
player.save()

user = User.objects.get(username='cMarzec') 
player = Players.objects.get(FirstName='Chris', LastName='Marzec') 
player.user = user 
player.save()

user = User.objects.get(username='jMcilwain') 
player = Players.objects.get(FirstName='John', LastName='Mcilwain') 
player.user = user 
player.save()

user = User.objects.get(username='mPeterson') 
player = Players.objects.get(FirstName='Mike', LastName='Peterson') 
player.user = user 
player.save()

user = User.objects.get(username='cprouty') 
player = Players.objects.get(FirstName='Chris', LastName='Prouty') 
player.user = user 
player.save()

user = User.objects.get(username='jSantana') 
player = Players.objects.get(FirstName='Jaime', LastName='Santana') 
player.user = user 
player.save()

user = User.objects.get(username='eSloan') 
player = Players.objects.get(FirstName='Ed', LastName='Sloan') 
player.user = user 
player.save()

user = User.objects.get(username='mStutz') 
player = Players.objects.get(FirstName='Mike', LastName='Stutz') 
player.user = user 
player.save()

user = User.objects.get(username='kTaira') 
player = Players.objects.get(FirstName='Kelly', LastName='Taira') 
player.user = user 
player.save()

user = User.objects.get(username='pDeutsch') 
player = Players.objects.get(FirstName='Paul', LastName='Deutsch') 
player.user = user 
player.save()

user = User.objects.get(username='mDeHaan') 
player = Players.objects.get(FirstName='Mike', LastName='DeHaan') 
player.user = user 
player.save()

user = User.objects.get(username='jSullivan') 
player = Players.objects.get(FirstName='John', LastName='Sullivan') 
player.user = user 
player.save()

user = User.objects.get(username='cLynn') 
player = Players.objects.get(FirstName='Chris', LastName='Lynn') 
player.user = user 
player.save()

user = User.objects.get(username='kHuizinga') 
player = Players.objects.get(FirstName='Keith', LastName='Huizinga') 
player.user = user 
player.save()

user = User.objects.get(username='mRyan') 
player = Players.objects.get(FirstName='Mike', LastName='Ryan') 
player.user = user 
player.save()

user = User.objects.get(username='tCanepa') 
player = Players.objects.get(FirstName='Tom', LastName='Canepa') 
player.user = user 
player.save()

user = User.objects.get(username='ccourse') 
player = Players.objects.get(FirstName='Course', LastName='Credit') 
player.user = user 
player.save()
