# GRPR/management/commands/weekly_reminder.py
import os, django
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.core.management.base import BaseCommand
from django.utils import timezone
from twilio.rest import Client

from GRPR.models import Log, TeeTimesInd

CENTRAL = ZoneInfo("America/Chicago")
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token  = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)

class Command(BaseCommand):
    help = "Tuesday SMS reminder to players on this week’s tee sheet"

    def handle(self, *args, **kwargs):
        now_cst = timezone.now().astimezone(CENTRAL)

        # only Tuesday
        if now_cst.weekday() != 1:
            self.stdout.write(self.style.WARNING("Not Tuesday – aborting."))
            return

        # guard: already sent?
        monday = now_cst.date() - timedelta(days=now_cst.weekday())
        if Log.objects.filter(
                Type="Weekly Reminder",
                SentDate__date__gte=monday).exists():
            self.stdout.write(self.style.WARNING("SMS already sent."))
            return

        # next tee-date is the coming Saturday
        saturday = now_cst.date() + timedelta((5 - now_cst.weekday()) % 7)
        tee_times = TeeTimesInd.objects.filter(gDate=saturday) \
                                       .select_related('PID', 'CourseID')
        if not tee_times:
            self.stdout.write(self.style.WARNING("No tee times found."))
            return

        for tt in tee_times:
            group = [
                f"{p.PID.FirstName} {p.PID.LastName}"
                for p in tee_times
                if p.CourseID == tt.CourseID and p.PID != tt.PID
            ]
            if len(group) != 3:
                continue   # skip malformed foursomes

            msg_text = (f"Reminder: you play Saturday {saturday} at "
                        f"{tt.CourseID.courseTimeSlot}am "
                        f"{tt.CourseID.courseName} with {', '.join(group)}.")
            to_number = tt.PID.Mobile
            message = client.messages.create(
                from_='+18449472599', body=msg_text, to=to_number)

            Log.objects.create(
                SentDate=timezone.now(),
                Type="Weekly Reminder",
                MessageID=message.sid,
                RequestDate=saturday,
                OfferID=tt.PID_id,
                Msg=msg_text,
                To_number=to_number)

        self.stdout.write(self.style.SUCCESS("Weekly SMS reminder sent."))
