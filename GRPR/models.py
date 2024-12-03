from django.db import models

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

class TeeTimes(models.Model):
    CrewID = models.IntegerField()
    gDate = models.DateField()
    CourseID = models.IntegerField()
    P1ID = models.IntegerField()
    P2ID = models.IntegerField()
    P3ID = models.IntegerField()
    P4ID = models.IntegerField()

    class Meta:
        db_table = "TeeTimes"


class TeeTimesInd(models.Model):
    CrewID = models.IntegerField()
    gDate = models.DateField()
    PID = models.ForeignKey('Players', on_delete=models.CASCADE)  # Links to Players table
    CourseID = models.ForeignKey('Courses', on_delete=models.CASCADE)  # Links to Courses table

    class Meta:
        db_table = "TeeTimesInd"


class Players(models.Model):
    CrewID = models.IntegerField()
    FirstName = models.CharField(max_length=256)
    LastName = models.CharField(max_length=256)
    Email = models.CharField(max_length=256)
    Mobile = models.CharField(max_length=256)
    SplitPartner = models.IntegerField(null=True)

    class Meta:
        db_table = "Players"