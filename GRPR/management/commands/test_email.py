import os
import django
from django.core.management.base import BaseCommand
from django.core.mail import send_mail

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

class Command(BaseCommand):
    help = 'Send a test email to verify email settings'

    def handle(self, *args, **kwargs):
        subject = 'Email Test'
        email_message = 'Test msg'
        from_email = os.environ.get('EMAIL_HOST_USER')
        recipient_list = ['cprouty@gmail.com']

        print('from_email', from_email)

        try:
            send_mail(subject, email_message, from_email, recipient_list)
            self.stdout.write(self.style.SUCCESS('Test email sent successfully.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error sending test email: {e}'))