from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.db.models import Q
from GRPR.models import SubSwap, TeeTimesInd, Players, Log
from twilio.rest import Client
from django.conf import settings  # Import settings
import os

class Command(BaseCommand):
    help = 'Convert open Swaps for this weekend to Subs'

    def handle(self, *args, **kwargs):
        # Verify today is Friday
        today = timezone.now().date()
        self.stdout.write(f"Today's date: {today}")
        if today.weekday() != 4:  # 4 = Friday
            self.stdout.write("Today is not Thursday. Exiting.")
            return

        # Find the next playing date
        playing_date = TeeTimesInd.objects.filter(gDate__gte=today).order_by('gDate').values_list('gDate', flat=True).first()
        self.stdout.write(f"Next playing date: {playing_date}")
        if not playing_date:
            self.stdout.write("No future playing dates found. Exiting.")
            return

        # Find open Swaps for the playing date
        open_swaps = SubSwap.objects.filter(
            nStatus='Open',
            nType='Swap',
            SubType='Offer',
            TeeTimeIndID__gDate=playing_date
        ).select_related('TeeTimeIndID', 'PID')

        if not open_swaps.exists():
            self.stdout.write("No open Swaps found for the playing date. Exiting.")
            return

        # Twilio setup
        twilio_enabled = os.getenv('TWILIO_ENABLED', 'False') == 'True'
        self.stdout.write(f"Twilio enabled: {twilio_enabled}")
        if twilio_enabled:
            twilio_account_sid = settings.TWILIO_ACCOUNT_SID
            twilio_auth_token = settings.TWILIO_AUTH_TOKEN
            client = Client(twilio_account_sid, twilio_auth_token)

        self.stdout.write(f"Number of open swaps found: {open_swaps.count()}")
        open_swaps = list(open_swaps)

        # Process each open Swap
        for swap in open_swaps:
            self.stdout.write(f"Processing swap with ID: {swap.SwapID}")
            offer_player = swap.PID
            offer_player_name = f"{offer_player.FirstName} {offer_player.LastName}"
            offer_player_mobile = offer_player.Mobile
            swap_id = swap.SwapID
            tt_id = swap.TeeTimeIndID_id
            other_players = swap.OtherPlayers
            tee_time = swap.TeeTimeIndID.CourseID.courseTimeSlot
            sub_msg = f"Swap {swap_id} on {playing_date} for {offer_player_name} has been converted from a Swap to a Sub via automated job."

            # Close the open Swap rows
            SubSwap.objects.filter(SwapID=swap_id, nStatus='Open').update(nStatus='Closed', SubStatus='Changed to Sub')
            self.stdout.write(f"Closed swap with ID: {swap_id}")

            # Create a new Sub row
            new_sub = SubSwap.objects.create(
                RequestDate=timezone.now(),
                PID_id=offer_player.id,
                TeeTimeIndID_id=tt_id,
                nType="Sub",
                SubType="Offer",
                nStatus="Open",
                Msg=sub_msg,
                OtherPlayers=other_players
            )
            new_sub.SwapID = new_sub.id
            new_sub.save()
            sub_id = new_sub.id

            # Notify the offer player
            offer_player_msg = f"Your Swap request for {playing_date} has been converted to a Sub. Anyone available can claim your tee time without offering you a tee time in trade."
            if twilio_enabled:
                message = client.messages.create(from_='+18449472599', body=offer_player_msg, to=offer_player_mobile)
                mID = message.sid
            else:
                mID = 'Twilio disabled'
            self.stdout.write(f"Notified offer player: {offer_player_name} at {offer_player_mobile}")
            
            print(f"Sending message to {offer_player_mobile}: {offer_player_msg}")

            # Log the change
            Log.objects.create(
                SentDate=timezone.now(),
                Type="Swap to Sub",
                MessageID=mID,
                RequestDate=playing_date,
                OfferID=offer_player.id,
                RefID=swap_id,
                Msg=f"{offer_player_msg} SwapID {swap_id} became SubID {sub_id}",
                To_number=offer_player_mobile
            )

            # Find available players
            playing_players = TeeTimesInd.objects.filter(gDate=playing_date).values_list('PID_id', flat=True)
            available_players = Players.objects.filter(Member=1).exclude(id__in=list(playing_players))

            # Notify available players
            for player in available_players:
                avail_to_number = player.Mobile
                avail_players_msg = f"{offer_player_name}'s Swap has been converted to a Sub. {playing_date} {tee_time}am with {other_players} is immediately available to the first person who claims it."

                print(f"Sending message to {avail_to_number}: {avail_players_msg}")

                if twilio_enabled:
                    message = client.messages.create(from_='+18449472599', body=avail_players_msg, to=avail_to_number)
                    mID = message.sid
                else:
                    mID = 'Twilio disabled'

                # Log the notification
                Log.objects.create(
                    SentDate=timezone.now(),
                    Type="Swap to Sub",
                    MessageID=mID,
                    RequestDate=playing_date,
                    OfferID=offer_player.id,
                    ReceiveID=player.id,
                    RefID=sub_id,
                    Msg=avail_players_msg,
                    To_number=avail_to_number
                )

        # Notify the admin
        email = 'cprouty@gmail.com'
        subject = f"Swap-to-Sub Conversion Completed for {playing_date}"
        message = f"All open Swaps for {playing_date} have been converted to Subs.  Open Swaps list:  { open_swaps }"
        from_email = os.environ.get('EMAIL_HOST_USER')

        try:
            send_mail(subject, message, from_email, [email])
            self.stdout.write("Admin notification email sent successfully.")
        except Exception as e:
            self.stderr.write(f"Error sending admin notification email: {e}")

        self.stdout.write("Swap-to-Sub job completed successfully.")