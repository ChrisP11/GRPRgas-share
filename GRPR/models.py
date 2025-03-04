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