import os
from django.core.management.base import BaseCommand
from django.utils.timezone import now, localtime
from django.utils import timezone
from datetime import timedelta
from datetime import date
from GRPR.models import Players, TeeTimesInd
from django.core.mail import send_mail


class Command(BaseCommand):
    help = 'Send a weekly email to all members'

    def handle(self, *args, **kwargs):
        # Check if today is Tuesday
        if timezone.now().weekday() != 1:  # 0 = Monday, 1 = Tuesday, ..., 6 = Sunday
            self.stdout.write(self.style.WARNING('Today is not Tuesday. This job only runs on Tuesdays.'))
            return
        # Get the current date and calculate the upcoming weekend range (Saturday and Sunday)
        current_date = localtime(now()).date()
        # current_date = date(2025, 4, 15)
        print('current_date', current_date)
        
        saturday = current_date + timedelta((5 - current_date.weekday()) % 7)  # Next Saturday
        sunday = saturday + timedelta(days=1)  # Next Sunday
        print(f"Saturday: {saturday}, Sunday: {sunday}")

        # Query all players where Member = 1
        members = Players.objects.filter(Member=1).exclude(Email=None).values_list('Email', flat=True)

        if not members:
            self.stdout.write(self.style.WARNING('No members found to send the weekly email.'))
            return

        # Query tee times for the upcoming weekend
        tee_times = TeeTimesInd.objects.filter(
            gDate__range=[saturday, sunday]
        ).select_related('PID', 'CourseID').order_by('gDate', 'CourseID__courseTimeSlot')

        if not tee_times:
            self.stdout.write(self.style.WARNING('No tee times found to send the weekly email.'))
            return

        # Build the schedule for the email body
        schedule = {}
        for teetime in tee_times:
            formatted_date = teetime.gDate.strftime('%A, %B %d, %Y')  # Format: "Saturday, April 13, 2025"
            if formatted_date not in schedule:
                schedule[formatted_date] = []
            schedule[formatted_date].append({
                'course': teetime.CourseID.courseName,
                'time_slot': teetime.CourseID.courseTimeSlot,
                'player': f"{teetime.PID.FirstName} {teetime.PID.LastName}",
            })

        # Format the schedule into a readable string
        schedule_text = ""
        for formatted_date, times in schedule.items():
            schedule_text += f"\nSchedule for {formatted_date}:\n"
            grouped_times = {}
            for time in times:
                key = f"{time['course']} at {time['time_slot']}am"
                if key not in grouped_times:
                    grouped_times[key] = []
                grouped_times[key].append(time['player'])
            for key, players in grouped_times.items():
                schedule_text += f"  {key}: {', '.join(players)}\n"

        coogans_corner = (
            f"-- Coogan's Corner -- \n"
            f"Have a Great Opening Day!  Looking forward to a great season with everyone\n"
            f"Just FYI - if you have an outstanding Swap offered for this weekend, be aware that it will become a 'Sub' at 11:59p on Thursday.  "
            f"IE, it will become a tee time anyone can grab without giving you a future date in trade.  This makes it easier to use all spots.  "
            f"If you want to keep the tee time and play instead, just cancel your offer in the Sub / Swap section of gasgolf.org\n"
        )
        
        # Prepare the email details
        subject = f"GAS Weekly for {saturday.strftime('%B %d, %Y')}"
        from_email = os.environ.get('EMAIL_HOST_USER', 'gasgolf2025@gmail.com')
        recipient_list = list(members)  # Convert queryset to a list
        # recipient_list = ('cprouty@gmail.com',)

        # Email body
        email_body = (
            f"GAS Members-\n"
            f"{schedule_text}\n"
            f"{coogans_corner}\n"
            f"Hit 'em straight!"
        )

        recipient_list = ('cprouty@gmail.com',)

        # Send the email
        try:
            send_mail(
                subject=subject,
                message=email_body,
                from_email=from_email,
                recipient_list=recipient_list,
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(f"Weekly email sent successfully to {len(recipient_list)} members."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to send weekly email: {e}"))