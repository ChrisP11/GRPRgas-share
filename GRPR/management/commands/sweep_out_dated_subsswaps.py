import os
import django
from django.core.management.base import BaseCommand
from datetime import date
from django.utils import timezone
from django.db.models import Q
from GRPR.models import SubSwap, TeeTimesInd, Log
from django.core.mail import send_mail 

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

class Command(BaseCommand):
    help = 'Sweep out outdated SubSwaps and update their status'

    def handle(self, *args, **kwargs):

        # Define the date for filtering
        filter_date = date(2025, 5, 4)
        current_datetime = timezone.now()

        # Perform the query
        queryset = SubSwap.objects.select_related('TeeTimeIndID').filter(
            Q(TeeTimeIndID__gDate__lt=filter_date) &
            (Q(Status='Swap Open') | Q(Status='Sub Open'))
        )

        # Check if there are any records in the queryset
        if queryset.count() > 0:
            email_msg = "The Sub Swap Sweep has been run. The following have been expired:\n"

            # Iterate over the results and update the status
            for sub_swap in queryset:
                status = sub_swap.Status
                gDate = sub_swap.TeeTimeIndID.gDate
                ssID = sub_swap.id
                pID = sub_swap.PID_id

                if status == 'Swap Open':
                    msg = f"Swap: {ssID} on {gDate} has been closed due to expiration"
                    # Update the record
                    SubSwap.objects.filter(id=ssID).update(Status="Swap Expired")
                    new_status = "Swap Expired"
                    
                    self.stdout.write(self.style.SUCCESS(f'SubSwap id {sub_swap.id} gDate has passed, status has been set to Swap Expired'))
                elif status == 'Sub Open':
                    msg = f"Sub: {ssID} on {gDate} has been closed due to expiration"
                    # Update the record
                    SubSwap.objects.filter(id=ssID).update(Status="Sub Expired")
                    new_status = "Sub Expired"

                    self.stdout.write(self.style.SUCCESS(f'SubSwap id {sub_swap.id} gDate has passed, status has been set to Sub Expired'))
                else:
                    print(f"Unknown status for SubSwap ID: {sub_swap.id}, should have been Swap Open or Sub Open")
                    continue

                # Append the msg to the email_msg
                email_msg += f"{msg}\n"

                # Insert a new record into the Log table
                Log.objects.create(
                    SentDate=current_datetime,
                    Type="Sweep Expiration",
                    MessageID='none',
                    RequestDate=gDate,
                    OfferID=pID,
                    RefID=ssID,
                    Msg=msg,
                    To_number='none'
                )

            # Send an email to cprouty@gmail.com with the sweep report
            subject = 'SubSwap Sweep Report'
            from_email = os.environ.get('EMAIL_HOST_USER')
            recipient_list = ['cprouty@gmail.com']

            send_mail(subject, email_msg, from_email, recipient_list)
            
            self.stdout.write(self.style.SUCCESS('Successfully sent sweep report email to cprouty@gmail.com'))
        else:
            # Send an email indicating that the job has run but no records were in play
            subject = 'SubSwap Sweep Report'
            email_msg = "The Sub Swap Sweep has been run, but no records were in play."
            from_email = os.environ.get('EMAIL_HOST_USER')
            recipient_list = ['cprouty@gmail.com']

            send_mail(subject, email_msg, from_email, recipient_list)
            
            self.stdout.write(self.style.WARNING('No SubSwap records were in play.'))