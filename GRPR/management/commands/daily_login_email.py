from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils.timezone import now, localtime
from django.contrib.auth.models import User
from datetime import timedelta
import os

class Command(BaseCommand):
    help = 'Send a daily email with login activity for the last 24 hours'

    def handle(self, *args, **kwargs):
        # Calculate the time range for "yesterday" in CST
        end_time = localtime(now()).replace(hour=0, minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(days=1)

        # Fetch users who logged in during the time range
        logins = User.objects.filter(last_login__range=(start_time, end_time)).values('username', 'last_login')

        # Prepare the email content
        if logins.exists():
            email_body = "Daily Login Report (CST):\n\n"
            for login in logins:
                email_body += f"Username: {login['username']}, Last Login: {localtime(login['last_login']).strftime('%Y-%m-%d %H:%M:%S')}\n"
        else:
            email_body = "No logins were recorded in the last 24 hours."

        # Send the email
        subject = "Daily Login Report"
        from_email = os.environ.get('EMAIL_HOST_USER', 'gasgolf2025@gmail.com')
        to_email = ['cprouty@gmail.com']

        try:
            send_mail(subject, email_body, from_email, to_email)
            self.stdout.write(self.style.SUCCESS('Daily login email sent successfully.'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error sending daily login email: {e}"))