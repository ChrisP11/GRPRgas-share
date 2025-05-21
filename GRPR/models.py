from django.db import models
from django.contrib.auth.models import User #Built-in Django User model, called to tie to the User model and the Player table

# Create your models here.
class Courses(models.Model):
    crewID = models.IntegerField()
    courseName = models.CharField(max_length=256)
    courseTimeSlot = models.CharField(max_length=256)

    class Meta:
        db_table = "Courses"

class Crews(models.Model):
    crewName = models.CharField(max_length=256)
    crewCaptain = models.IntegerField()
    email = models.CharField(max_length=256)
    mobile = models.CharField(max_length=256)

    class Meta:
        db_table = "Crews"


class TeeTimesInd(models.Model):
    CrewID = models.IntegerField()
    gDate = models.DateField()
    PID = models.ForeignKey('Players', on_delete=models.CASCADE)  # Links to Players table
    CourseID = models.ForeignKey('Courses', on_delete=models.CASCADE)  # Links to Courses table

    class Meta:
        db_table = "TeeTimesInd"


class Players(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True) # Links to the built-in Django User model, a foreign key
    CrewID = models.IntegerField()
    FirstName = models.CharField(max_length=30)
    LastName = models.CharField(max_length=30)
    Email = models.CharField(max_length=256)
    Mobile = models.CharField(max_length=256)
    SplitPartner = models.IntegerField(null=True)
    Member = models.IntegerField(null=True)
    GHIN = models.IntegerField(null=True)
    Index = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)  

    class Meta:
        db_table = "Players"


class SubSwap(models.Model):
    RequestDate = models.DateTimeField()
    PID = models.ForeignKey('Players', on_delete=models.CASCADE)
    TeeTimeIndID = models.ForeignKey('TeeTimesInd', on_delete=models.CASCADE)
    nStatus = models.CharField(max_length=32)
    SubStatus = models.CharField(max_length=32, null=True, blank=True)
    nType = models.CharField(max_length=32)
    SubType = models.CharField(max_length=32, null=True, blank=True)
    Msg = models.CharField(max_length=2048)
    OtherPlayers = models.CharField(max_length=1024)
    SwapID = models.IntegerField(null=True, blank=True) 

    class Meta:
        db_table = "SubSwap"


class Log(models.Model):
    SentDate = models.DateTimeField()
    Type = models.CharField(max_length=256)
    MessageID = models.CharField(max_length=256)
    RequestDate = models.DateTimeField(null=True, blank=True) 
    OfferID = models.IntegerField(null=True, blank=True) 
    ReceiveID = models.IntegerField(null=True, blank=True) 
    RefID = models.IntegerField(null=True, blank=True) 
    Msg = models.CharField(max_length=1024)
    Status = models.IntegerField(null=True, blank=True)
    To_number = models.CharField(max_length=16)

    class Meta:
        db_table = "Log"


class LoginActivity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    login_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} logged in at {self.login_time}"
    
    class Meta:
        db_table = "LoginActivity"


class Xdates(models.Model):
    CrewID = models.IntegerField()
    PID = models.ForeignKey('Players', on_delete=models.CASCADE)  # Links to Players table
    xDate = models.DateField() # date requested to be off
    rDate = models.DateField() # date request was made

    class Meta:
        db_table = "Xdates"


class SMSResponse(models.Model):
    from_number = models.CharField(max_length=15)
    message_body = models.TextField()
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"From: {self.from_number}, Message: {self.message_body}"
    
    class Meta:
        db_table = "SMSResponse"
    

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    force_password_change = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username
    

class AutomatedMessages(models.Model):
    CreateDate = models.DateTimeField(auto_now_add=True)
    CreatePerson = models.CharField(max_length=64)
    AlterDate = models.DateTimeField(null=True, blank=True)
    AlterPerson = models.CharField(max_length=64, null=True, blank=True)
    SentDate = models.DateTimeField(null=True, blank=True)
    SentPerson = models.CharField(max_length=64, null=True, blank=True)
    SentVia = models.CharField(max_length=64, null=True, blank=True)
    Msg = models.CharField(max_length=2048)

    class Meta:
        db_table = "AutomatedMessages"

    

### Scorecard Tables
class ScorecardMeta(models.Model):
    GameID = models.ForeignKey('Games', on_delete=models.CASCADE)  # Links to Games table, in future DO NOT delete on cascade
    CreateDate = models.DateField()
    CreateID = models.IntegerField()  # Links to Users table?
    PlayDate = models.DateField()
    PID = models.ForeignKey('Players', on_delete=models.CASCADE)  # Links to Players table
    CrewID = models.ForeignKey('Crews', on_delete=models.CASCADE)  # Links to Crews table
    CourseID = models.IntegerField() # will eventually link to Course Data table
    TeeID = models.ForeignKey('CourseTees', on_delete=models.CASCADE, null=True, blank=True)
    Index = models.DecimalField(max_digits=3, decimal_places=1,null=True, blank=True)
    RawHDCP = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True) 
    NetHDCP = models.IntegerField(null=True, blank=True)
    GroupID = models.CharField(max_length=16, null=True, blank=True)
    RawIN = models.IntegerField(null=True, blank=True, default=0)
    NetIN = models.IntegerField(null=True, blank=True, default=0)
    RawOUT = models.IntegerField(null=True, blank=True, default=0)
    NetOUT = models.IntegerField(null=True, blank=True, default=0)
    RawTotal = models.IntegerField(null=True, blank=True, default=0)
    NetTotal = models.IntegerField(null=True, blank=True, default=0)
    Putts = models.IntegerField(null=True, blank=True, default=0)
    Skins = models.IntegerField(null=True, blank=True, default=0)

    class Meta:
        db_table = "ScorecardMeta"


class Scorecard(models.Model):
    smID = models.ForeignKey('ScorecardMeta', on_delete=models.CASCADE)  # Links to ScorecardMeta table
    GameID = models.ForeignKey('Games', on_delete=models.CASCADE, null=True, blank=True)  
    CreateDate = models.DateTimeField()  # Changed to DateTimeField to include time
    AlterDate = models.DateTimeField()  # will be same as CreaetDate for now, but will be updated when a score is updated
    AlterID = models.ForeignKey('Players', on_delete=models.CASCADE)  # Links to Players table for last update
    HoleID = models.ForeignKey('CourseHoles', on_delete=models.CASCADE, null=True, blank=True)  
    RawScore = models.IntegerField()
    NetScore = models.IntegerField()
    Putts = models.IntegerField(null=True, blank=True) 

    class Meta:
        db_table = "Scorecard"


### Skins Game Tables

class Games(models.Model):
    CreateID = models.ForeignKey('Players', on_delete=models.CASCADE)  # Links to Players table, creator of the game
    CrewID = models.IntegerField()
    CreateDate = models.DateField()
    PlayDate = models.DateField()
    CourseTeesID = models.ForeignKey('CourseTees', on_delete=models.CASCADE, default=1)  # Links to CourseTees table
    Status = models.CharField(max_length=32, default='Pending')

    class Meta:
        db_table = "Games"


class GameInvites(models.Model):
    GameID = models.ForeignKey('Games', on_delete=models.CASCADE)  
    AlterDate = models.DateField()
    PID = models.ForeignKey('Players', on_delete=models.CASCADE)  
    TTID = models.ForeignKey('TeeTimesInd', on_delete=models.CASCADE)
    Status = models.CharField(max_length=32, default='Pending')

    class Meta:
        db_table = "GameInvites"


class CourseTees(models.Model):
    CourseID = models.IntegerField(null=True, blank=True)
    CourseName = models.CharField(max_length=128)
    TeeID = models.IntegerField()
    TeeName = models.CharField(max_length=128)
    CourseRating = models.DecimalField(max_digits=4, decimal_places=1)  
    SlopeRating = models.IntegerField()
    Par = models.IntegerField()
    Yards = models.IntegerField()

    class Meta:
        db_table = "CourseTees"


class CourseHoles(models.Model):
    CourseTeesID = models.ForeignKey('CourseTees', on_delete=models.CASCADE, default=1)  # Links to CourseTees table
    HoleNumber = models.IntegerField()
    Par = models.IntegerField()
    Yardage = models.IntegerField()
    Handicap = models.IntegerField()

    class Meta:
        db_table = "CourseHoles"


class Skins(models.Model):
    GameID = models.ForeignKey('Games', on_delete=models.CASCADE)  # Links to the Games table
    PlayerID = models.ForeignKey('Players', on_delete=models.CASCADE)  # Links to the Players table
    HoleNumber = models.ForeignKey('CourseHoles', on_delete=models.CASCADE)  # The hole number where the skin was won
    SkinDate = models.DateField(auto_now_add=True)  # Date when the skin was recorded
    Payout = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)  # New field

    class Meta:
        db_table = "Skins"
        unique_together = ('GameID', 'PlayerID', 'HoleNumber')  # Prevent duplicate entries