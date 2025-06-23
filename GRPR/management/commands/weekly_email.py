# GRPR/management/commands/weekly_email.py
import os
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.core.mail import send_mail

from GRPR.models import Players, TeeTimesInd, AutomatedMessages

CENTRAL = ZoneInfo("America/Chicago")        # CST/CDT, DST-aware


class Command(BaseCommand):
    help = "GAS weekly: verification (any day) and Tuesday blast"

    @transaction.atomic
    def handle(self, *args, **kwargs):
        now_cst = timezone.now().astimezone(CENTRAL)

        # ------------------------------------------------------------------
        # 0 ·  Verification path — runs whenever a 'Ready' row exists
        # ------------------------------------------------------------------
        ready = (AutomatedMessages.objects
                 .select_for_update()
                 .filter(SentVia="Ready")
                 .order_by("-CreateDate")
                 .first())
        if ready:
            saturday  = next_saturday(now_cst)
            schedule  = render_schedule(saturday)
            send_preview(ready, schedule, saturday)

            ready.SentVia      = "Verified"
            ready.AlterDate    = timezone.now()
            ready.AlterPerson  = "Automated"
            ready.save(update_fields=["SentVia", "AlterDate", "AlterPerson"])

            self.stdout.write(self.style.SUCCESS("Verification e-mail sent."))
            return

        # ------------------------------------------------------------------
        # 1 ·  Scheduled path — only act on Tuesday
        # ------------------------------------------------------------------
        if now_cst.weekday() != 1:             # 0=Mon, 1=Tue …
            self.stdout.write(self.style.WARNING("Not Tuesday — nothing to do."))
            return

        # ------------------------------------------------------------------
        # 2 ·  Abort if this week already sent
        # ------------------------------------------------------------------
        monday = now_cst.date() - timedelta(days=now_cst.weekday())
        if AutomatedMessages.objects.filter(
                SentVia="Email",
                SentDate__date__gte=monday).exists():
            self.stdout.write(self.style.WARNING("Weekly blast already sent."))
            return

        # ------------------------------------------------------------------
        # 3 ·  Need a Verified row to include Coogan's Corner
        # ------------------------------------------------------------------
        verified = (AutomatedMessages.objects
                    .select_for_update()
                    .filter(SentVia="Verified")
                    .order_by("-CreateDate")
                    .first())

        saturday  = next_saturday(now_cst)
        schedule  = render_schedule(saturday)

        # If no verified note, we'll still send the schedule-only e-mail
        corner_text = verified.Msg if verified else ""

        recipients = list(
            Players.objects.filter(Member=1)
            .exclude(Email=None)
            .values_list("Email", flat=True))

        if not recipients:
            self.stdout.write(self.style.WARNING("No member e-mails found."))
            return

        body_parts = [
            "GAS Members-",
            "",
            schedule,
            "",
            f"Coogan's Corner--\n{corner_text}" if corner_text else "",
            "Hit 'em straight!"
        ]
        email_body = "\n".join(part for part in body_parts if part != "")

        send_mail(
            subject=f"GAS Weekly for {saturday:%B %d, %Y}",
            message=email_body,
            from_email=os.environ.get("EMAIL_HOST_USER",
                                      "gasgolf2025@gmail.com"),
            recipient_list=recipients,
            fail_silently=False,
        )

        # mark sent if we had a Verified row
        if verified:
            verified.SentVia   = "Email"
            verified.SentDate  = timezone.now()
            verified.SentPerson = "Automated"
            verified.save(update_fields=["SentVia", "SentDate", "SentPerson"])

        self.stdout.write(
            self.style.SUCCESS(f"Weekly blast sent to {len(recipients)} golfers."))


# ----------------------------------------------------------------------
def next_saturday(now_cst):
    """Return the date of the coming Saturday relative to now_cst."""
    return now_cst.date() + timedelta((5 - now_cst.weekday()) % 7)


def render_schedule(saturday):
    """Build the schedule text block for the e-mail body."""
    sunday = saturday + timedelta(days=1)
    qs = (TeeTimesInd.objects
          .filter(gDate__range=[saturday, sunday])
          .select_related("PID", "CourseID")
          .order_by("gDate", "CourseID__courseTimeSlot"))

    schedule = {}
    for tt in qs:
        fd = tt.gDate.strftime("%A, %B %d, %Y")
        schedule.setdefault(fd, []).append({
            "course": tt.CourseID.courseName,
            "time":   tt.CourseID.courseTimeSlot,
            "player": f"{tt.PID.FirstName} {tt.PID.LastName}",
        })

    lines = []
    for fd, times in schedule.items():
        lines.append(f"Schedule for {fd}:")
        grouped = {}
        for t in times:
            key = f"{t['course']} at {t['time']}am"
            grouped.setdefault(key, []).append(t["player"])
        for key, players in grouped.items():
            lines.append(f"  {key}: {', '.join(players)}")
    return "\n".join(lines)


def send_preview(msg_row, schedule_text, saturday):
    """Email preview to Coogan & Prouty."""
    body = (
        "GAS Members-\n\n"
        f"{schedule_text}\n\n"
        f"Coogan's Corner--\n{msg_row.Msg}\n\n"
        "Hit 'em straight!"
    )
    send_mail(
        subject=("VERIFICATION – this is what the GAS Weekly for "
                 f"{saturday:%B %d, %Y} will look like"),
        message=body,
        from_email=os.environ.get("EMAIL_HOST_USER",
                                  "gasgolf2025@gmail.com"),
        recipient_list=["cprouty@gmail.com",
                        "Christopher_Coogan@rush.edu"],
        fail_silently=False,
    )
