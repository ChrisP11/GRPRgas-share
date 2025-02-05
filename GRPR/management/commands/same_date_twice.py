import os
import django
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.db.models import Count
from GRPR.models import TeeTimesInd

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

class Command(BaseCommand):
    help = 'Checks to see if any player is playing same date twice'

    def handle(self, *args, **kwargs):
        queryset = TeeTimesInd.objects.values('gDate', 'PID_id') \
            .annotate(count=Count('id')) \
            .exclude(PID_id=25) \
            .filter(count__gt=1) \
            .order_by('-count')
    
        if queryset.count() > 0:
            email_msg = "The following players are playing the same date twice:\n"

            for player in queryset:
                email_msg += f"Player ID: {player['PID_id']} is playing on {player['gDate']} {player['count']} times\n"
                getTTIs = TeeTimesInd.objects.filter(PID_id=player['PID_id'], gDate=player['gDate'])
                for tti in getTTIs:
                    email_msg += f"  TeeTimeInd ID: {tti.id}\n"
                print(email_msg)
            
            # Send an email to cprouty@gmail.com
            subject = 'WARNING: Players playing same date twice'
            from_email = os.environ.get('EMAIL_HOST_USER')
            recipient_list = ['cprouty@gmail.com']

            send_mail(subject, email_msg, from_email, recipient_list)
