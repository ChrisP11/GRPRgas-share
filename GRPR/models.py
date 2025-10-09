from django.db import models
from django.contrib.auth.models import User #Built-in Django User model, called to tie to the User model and the Player table

# ▸▸▸  Gas-Cup data models  ◂◂◂
from django.db.models import UniqueConstraint, Q
from decimal import Decimal

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
    
    class Meta:
        db_table = "UserProfile" 
    

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


### Games Tables

# --- Wizard draft state for new game setup ---
class GameSetupDraft(models.Model):
    """
    Holds partial choices while a user steps through the new game setup wizard.
    We keep it very generic so we don't collide with legacy tables yet.
    """
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)
    created_by   = models.ForeignKey(User, on_delete=models.CASCADE, related_name="game_setup_drafts")
    crew_id      = models.IntegerField(db_index=True)               # keeping it simple/agnostic to your crew model name
    event_date   = models.DateField(null=True, blank=True)          # chosen date (step 1)
    course_id    = models.IntegerField(null=True, blank=True)       # optional: stash the course PK later (step 2)
    anchor_game_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    tee_choice   = models.CharField(max_length=64, blank=True)      # later: “Blue/White”, “White”, etc.
    state        = models.JSONField(default=dict, blank=True)       # anything else we want to cache per step
    is_complete  = models.BooleanField(default=False)

    class Meta:
        db_table = "GameSetupDraft" 
        indexes = [models.Index(fields=["created_by", "is_complete"])]
        ordering = ["-updated_at"]

    def __str__(self):
        status = "complete" if self.is_complete else "draft"
        return f"SetupDraft #{self.pk} by {self.created_by} ({status})"


class Games(models.Model):
    CreateID = models.ForeignKey('Players', on_delete=models.CASCADE)  # Links to Players table, creator of the game
    CrewID = models.IntegerField()
    CreateDate = models.DateField()
    PlayDate = models.DateField()
    CourseTeesID = models.ForeignKey('CourseTees', on_delete=models.CASCADE, default=1)  # Links to CourseTees table
    Status = models.CharField(max_length=32, default='Pending')
    IsLocked = models.BooleanField(default=False)        # ← NEW
    LockedAt = models.DateTimeField(null=True, blank=True)
    Type = models.CharField(max_length=32)  # Type of game, e.g., Skins, Forty
    Format = models.CharField(max_length=32, null=True, blank=True) # Full Handicap or Low Man
    NumScores = models.IntegerField(null=True, blank=True)
    Min1 = models.IntegerField(null=True, blank=True)
    Min18 = models.IntegerField(null=True, blank=True)
    AssocGame = models.IntegerField(null=True, blank=True) # id for associated game, if any

    class Meta:
        db_table = "Games"

    @property
    def is_skins_complete(self):
        # scorecardmeta rows per game × holes should exceed threshold
        return Scorecard.objects.filter(GameID=self).count() >= 100

    @property
    def is_forty_complete(self):
        return Forty.objects.filter(GameID=self).count() >= 15
    
    @property
    def is_complete(self):
        """Return True only when the game’s own type meets its threshold."""
        if self.Type == "Skins":
            return self.is_skins_complete
        elif self.Type == "Forty":
            return self.is_forty_complete
        return False   # fallback for any future type


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


class Forty(models.Model):
    CreateDate = models.DateTimeField(auto_now_add=True)
    AlterDate = models.DateTimeField(auto_now_add=True)
    CreateID = models.ForeignKey('Players', on_delete=models.CASCADE, related_name='created_records')
    AlterID = models.ForeignKey('Players', on_delete=models.CASCADE, related_name='altered_records', null=True, blank=True)
    CrewID = models.IntegerField()
    GameID = models.ForeignKey('Games', on_delete=models.CASCADE)  # Links to the Games table
    HoleNumber = models.ForeignKey('CourseHoles', on_delete=models.CASCADE)
    PID  = models.ForeignKey('Players', on_delete=models.CASCADE, related_name='player_scoring')
    GroupID = models.CharField(max_length=16, null=True, blank=True)
    RawScore = models.IntegerField()
    NetScore = models.IntegerField()
    Par = models.IntegerField()

    class Meta:
        db_table = "Forty"


class GasCupPair(models.Model):
    """
    Two partners that form ONE side in a Gas-Cup match.
    Exactly three rows per Gas-Cup Game (one per foursome).
    """
    TEAM_CHOICES = [("PGA", "PGA"), ("LIV", "LIV")]

    Game   = models.ForeignKey("Games", on_delete=models.CASCADE)
    PID1   = models.ForeignKey("Players",
                               related_name="gascup_partner1",
                               on_delete=models.CASCADE)
    PID2   = models.ForeignKey("Players",
                               related_name="gascup_partner2",
                               on_delete=models.CASCADE,
                               null=True, blank=True,)  # <-- allow singleton team
    Team   = models.CharField(max_length=12, choices=TEAM_CHOICES)

    class Meta:
        db_table = "GasCupPair"
        constraints = [
            models.UniqueConstraint(
                fields=["Game", "PID1"],
                name="gascuppair_unique_pid1",
            ),
            # NOTE: PID2 & ordered uniqueness removed to allow singleton teams.
        ]

    def __str__(self):
        return f"{self.Game_id}: {self.PID1_id}&{self.PID2_id} ({self.Team})"


class GasCupScore(models.Model):
    """
    One row = the BEST-BALL net score of a pair on a single hole.
    Always overwritten when a Scorecard edit occurs → idempotent.
    """
    Game      = models.ForeignKey("Games",      on_delete=models.CASCADE)
    Pair      = models.ForeignKey("GasCupPair", on_delete=models.CASCADE)
    Hole      = models.ForeignKey("CourseHoles", on_delete=models.CASCADE)
    NetScore  = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "GasCupScore"
        unique_together = ("Pair", "Hole")   # one result per hole

    def __str__(self):
        return f"{self.Game_id} {self.Pair_id} H{self.Hole_id}: {self.NetScore}"


class GasCupOverride(models.Model):
    """
    Manual override for a single Gas‑Cup match (one tee‑time slot).

    • Front/Back/Overall text fields replace the strings shown in the
      leaderboard row. (Leave blank to default to “All Square”.)
    • PGA_pts / LIV_pts are **the exact points to award** once the
      override is in effect (use Decimal so .5 works cleanly).
    • Slot must match the courseTimeSlot string in GameInvites.
    """
    Game        = models.ForeignKey("Games", on_delete=models.CASCADE)   # the Gas‑Cup game
    Slot        = models.CharField(max_length=16)                        # e.g. "9:00"
    PGA_pts     = models.DecimalField(max_digits=3, decimal_places=1, default=Decimal("0"))
    LIV_pts     = models.DecimalField(max_digits=3, decimal_places=1, default=Decimal("0"))
    Front_txt   = models.CharField(max_length=32, blank=True, null=True)
    Back_txt    = models.CharField(max_length=32, blank=True, null=True)
    Overall_txt = models.CharField(max_length=32, blank=True, null=True)
    Note        = models.CharField(max_length=128, blank=True, null=True)

    class Meta:
        db_table = "GasCupOverride"
        unique_together = ("Game", "Slot")

    def __str__(self):
        return f"{self.Game_id} • {self.Slot} override"
    

class StblTeam(models.Model):
    created_at   = models.DateTimeField(auto_now_add=True)
    Game         = models.ForeignKey(Games, on_delete=models.CASCADE, db_index=True)
    PID          = models.ForeignKey(Players, on_delete=models.CASCADE, db_index=True)
    TeamID       = models.PositiveSmallIntegerField()  # 1,2,3,...
    TeamName     = models.CharField(max_length=128, blank=True, null=True)

    class Meta:
        unique_together = (("Game", "PID"),)  # a player appears once per Stableford game
        indexes = [models.Index(fields=["Game", "TeamID"])]
        db_table = "StblTeam"

class StblScore(models.Model):
    AlterDate    = models.DateTimeField(auto_now=True)
    Game         = models.ForeignKey(Games, on_delete=models.CASCADE, db_index=True)
    PID          = models.ForeignKey(Players, on_delete=models.CASCADE, db_index=True)
    Hole         = models.ForeignKey(CourseHoles, on_delete=models.CASCADE, db_index=True)

    # Optional denorms for easier human debug/exports
    RawScore     = models.PositiveSmallIntegerField(null=True, blank=True)
    NetScore     = models.PositiveSmallIntegerField(null=True, blank=True)

    # The Stableford points for this player on this hole (0..5 in your rule)
    Points       = models.SmallIntegerField(default=0)

    class Meta:
        unique_together = (("Game", "PID", "Hole"),)
        indexes = [models.Index(fields=["Game", "PID"]), models.Index(fields=["Game"])]
        db_table = "StblScore"


class GameToggles(models.Model):
    # keep this as a single-row table; we’ll always get_or_create(pk=1)
    id = models.SmallAutoField(primary_key=True)
    gascup_enabled = models.BooleanField(default=False)  # off post-season
    fallclassic_enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"GameToggles(gascup_enabled={self.gascup_enabled})"
    
    class Meta:
        db_table = "GameToggles" 