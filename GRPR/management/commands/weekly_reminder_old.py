# Sends weekly reminder via Twilio to everyone on the schedule for this week

import os
import django
from django.core.management.base import BaseCommand
from twilio.rest import Client
from GRPR.models import Log, TeeTimesInd
from django.utils import timezone 
from django.core.mail import send_mail 

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

# Initialize the Twilio client
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)

class Command(BaseCommand):
    help = 'Send a text message via Twilio as a weekly reminder of scheduled tee times'

    def handle(self, *args, **kwargs):
        # Check if today is Tuesday (or any other day you prefer)
        if timezone.now().weekday() != 1:  # 0 = Monday, 1 = Tuesday, 2 = Wednesday, 3 = Thursday, 4 = Friday, 5 = Saturday, 6 = Sunday
            self.stdout.write(self.style.WARNING('Today is not the scheduled day for sending reminders.'))
            return

        current_datetime = timezone.now()
        # gets the date for the next tee time. This script will run on Tuesday mornings.
        teeTime = TeeTimesInd.objects.filter(gDate__gte=current_datetime).order_by('gDate').values('gDate').first()
        email_msg = "The Weekly Reminder text has been sent out. See below for msgs sent and to which mobile:"
        if teeTime:
            teeTime = teeTime['gDate']  # Extract the gDate value

            # select the Mobile for all players with a tee time this week
            plyrs_this_week = TeeTimesInd.objects.filter(gDate=teeTime).select_related('PID').values('gDate', 'CourseID', 'PID','PID__Mobile')

            for player in plyrs_this_week:
                cID = player['CourseID']
                gDate = player['gDate']
                pID = player['PID']
                mobile = player['PID__Mobile']

                korse = TeeTimesInd.objects.filter(gDate=gDate, CourseID=cID).values('CourseID__courseName', 'CourseID__courseTimeSlot').first()
                time_slot = korse['CourseID__courseTimeSlot']
                course_name = korse['CourseID__courseName']

                other_players = TeeTimesInd.objects.filter(gDate=teeTime, CourseID=cID).exclude(PID=pID).select_related('PID').values('PID','PID__FirstName', 'PID__LastName')

                group = []

                for partner in other_players:
                    p = partner['PID__FirstName'] + " " + partner['PID__LastName']
                    group.append(p)
                
                if len(group) == 3:
                    msg = f'Reminder, you are playing golf Saturday, {gDate}, at {time_slot}am at {course_name}, with {group[0]}, {group[1]}, and {group[2]}..'
                    email_msg += f'\n{mobile} {msg}'
                    
                    # Generate text message and send 
                    # to_number = '13122961817'  # Hardcoded for now
                    to_number = mobile
                    message = client.messages.create(from_='+18449472599', body=msg, to=to_number)
                    mID = message.sid

                    self.stdout.write(self.style.SUCCESS(f'Successfully sent message: {message.sid}'))
                
                    # Insert reminder into Log for tracking
                    Log.objects.create(
                        SentDate=current_datetime,
                        Type="Weekly Reminder",
                        MessageID=mID,
                        RequestDate=teeTime,
                        OfferID=pID,
                        Msg=msg,
                        To_number=to_number
                    )
                else:
                    print(f'something is wrong, the foursome has the wrong number of players, PID: {pID} {gDate} / {time_slot} / {course_name} / {group})')

        else:
            self.stdout.write(self.style.WARNING('No upcoming tee times found.'))
        
        # Send an email to cprouty@gmail.com
        subject = 'Email verification for Weekly Reminder'
        email_message = email_msg
        from_email = os.environ.get('EMAIL_HOST_USER')
        recipient_list = ['cprouty@gmail.com']

        send_mail(subject, email_message, from_email, recipient_list)
        
        self.stdout.write(self.style.SUCCESS('Successfully sent weekyl reminder email to cprouty@gmail.com'))