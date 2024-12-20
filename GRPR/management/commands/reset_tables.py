from django.core.management.base import BaseCommand
from django.db import connection
from GRPR.models import Log, SubSwap

class Command(BaseCommand):
    help = 'Delete all data from the Log and SubSwap tables and reset the primary key counters'

    def handle(self, *args, **kwargs):
        # Delete all data from the Log table
        Log.objects.all().delete()

        # Delete all data from the SubSwap table
        SubSwap.objects.all().delete()

        # Reset the primary key counters
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='Log';")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='SubSwap';")

        self.stdout.write(self.style.SUCCESS('Successfully reset the Log and SubSwap tables'))