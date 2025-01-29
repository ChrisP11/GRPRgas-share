from django.core.management.base import BaseCommand
from django.db import connection
from GRPR.models import Log, SubSwap, LoginActivity

class Command(BaseCommand):
    help = 'Delete all data from the Log, SubSwap, and LoginActivity tables and reset the primary key counters'

    def handle(self, *args, **kwargs):
        # Delete all data from the Log table
        Log.objects.all().delete()

        # Delete all data from the SubSwap table
        SubSwap.objects.all().delete()

        # Delete all data from the LoginActivity table
        LoginActivity.objects.all().delete()

        # Reset the primary key counters for PostgreSQL
        with connection.cursor() as cursor:
            cursor.execute('ALTER SEQUENCE "Log_id_seq" RESTART WITH 1;')
            cursor.execute('ALTER SEQUENCE "SubSwap_id_seq" RESTART WITH 1;')
            cursor.execute('ALTER SEQUENCE "LoginActivity_id_seq" RESTART WITH 1;')

        self.stdout.write(self.style.SUCCESS('Successfully reset the Log, SubSwap, and LoginActivity tables'))
