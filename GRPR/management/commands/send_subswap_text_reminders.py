import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from GRPR.models import SubSwap, TeeTimesInd, Players, Log
from django.core.mail import send_mail
from django.conf import settings
from twilio.rest import Client


class Command(BaseCommand):
    help = 'Send reminder texts for open subs/swaps for the upcoming weekend'

    def handle(self, *args, **kwargs):
        # Check if today is Tuesday
        if timezone.now().weekday() != 3:  # 0 = Monday, 1 = Tuesday, ..., 6 = Sunday
            self.stdout.write(self.style.WARNING('Today is not Tuesday. This job only runs on Tuesdays.'))
            return

        # Get the next available tee time date
        current_datetime = timezone.now()
        next_tee_time = TeeTimesInd.objects.filter(gDate__gte=current_datetime).order_by('gDate').values('gDate').first()

        if not next_tee_time:
            self.stdout.write(self.style.WARNING('No upcoming tee times found.'))
            return

        next_tee_time = next_tee_time['gDate']

        # Query for open subs/swaps for the next tee time
        subswaps = SubSwap.objects.select_related('TeeTimeIndID__CourseID').filter(
            TeeTimeIndID__gDate=next_tee_time,
            nStatus='Open',
            SubType='Offer'
        )

        if not subswaps.exists():
            self.stdout.write(self.style.WARNING('No open subs/swaps found for the next tee time.'))
            return

        # Prepare to send reminders
        email_msg = "Sub Swap reminders have been sent for the upcoming weekend:\n\n"
        from_email = os.environ.get('EMAIL_HOST_USER', 'gasgolf2025@gmail.com')
        recipient_list = ['cprouty@gmail.com']

        # Check if Twilio is enabled
        twilio_enabled = getattr(settings, 'TWILIO_ENABLED', False)
        if twilio_enabled:
            # Initialize the Twilio client
            account_sid = settings.TWILIO_ACCOUNT_SID
            auth_token = settings.TWILIO_AUTH_TOKEN
            twilio_number = settings.TWILIO_PHONE_NUMBER
            client = Client(account_sid, auth_token)
        else:
            email_msg += "Note: Twilio is not enabled. These messages were not actually sent.\n\n"

        for subswap in subswaps:
            # Get the offering player's name
            offering_player = Players.objects.filter(id=subswap.PID_id).first()
            offering_player_name = f"{offering_player.FirstName} {offering_player.LastName}" if offering_player else "Unknown Player"

            # Get the tee time details
            gDate = subswap.TeeTimeIndID.gDate
            course_name = subswap.TeeTimeIndID.CourseID.courseName  # Access via CourseID relationship
            course_time_slot = subswap.TeeTimeIndID.CourseID.courseTimeSlot  # Access via CourseID relationship

            # Prepare the message
            message = (
                f"Reminder, there is a {subswap.nType} available for this weekend. "
                f"{offering_player_name} is offering {gDate}, {course_name}, at {course_time_slot}am. "
                f"Go to gasgolf.org, choose Sub / Swap to review."
            )

            # Get the list of PID_id from SubSwap where SwapID = swap_id and SubType = 'Received'
            swap_id = subswap.SwapID
            received_pids = SubSwap.objects.filter(SwapID=swap_id, SubType='Received', nStatus='Open').values_list('PID_id', flat=True)

            # Get the Mobile values from the Players table for the retrieved PID_id values
            available_players = Players.objects.filter(id__in=received_pids).exclude(Mobile=None).values('Mobile')

            # Iterate through the Mobile values and send a text message
            for player in available_players:
                if twilio_enabled:
                    try:
                        twilio_message = client.messages.create(
                            from_=twilio_number,
                            body=message,
                            to=player['Mobile']
                        )
                        mID = twilio_message.sid  # Collect the message SID
                        self.stdout.write(self.style.SUCCESS(f"Text sent to {player['Mobile']}: SID {mID}"))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Failed to send text to {player['Mobile']}: {e}"))
                        mID = 'Failed'  # Assign a fallback value for failed messages
                else:
                    mID = 'Twilio Disabled'  # Assign a fallback value if Twilio is disabled

                # Append the message to the email summary
                email_msg += f"Message to {player['Mobile']}: {message}\n"

                # Log the reminder in the Log table
                Log.objects.create(
                    SentDate=current_datetime,
                    Type="SubSwap Reminder",
                    MessageID=mID,
                    RequestDate=gDate,
                    OfferID=subswap.PID_id,
                    RefID=subswap.id,
                    Msg=message,
                    To_number=player['Mobile']
                )

        # Send the summary email
        send_mail(
            subject='Sub Swap Reminder Summary',
            message=email_msg,
            from_email=from_email,
            recipient_list=recipient_list
        )

        self.stdout.write(self.style.SUCCESS('Sub Swap reminders sent successfully.'))

    def send_text_message(self, client, twilio_number, mobile, message):
        """
        Send a text message using Twilio.
        """
        twilio_message = client.messages.create(
            from_=twilio_number,
            body=message,
            to=mobile
        )
        mID = twilio_message.sid

        self.stdout.write(self.style.SUCCESS(f"Text sent to {mobile}: SID {twilio_message.sid}"))