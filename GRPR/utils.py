from django.shortcuts import render, get_object_or_404
from datetime import datetime, date
import re
from .models import SubSwap, TeeTimesInd, Players, GameToggles


# function to verify there is an open subswap offer for a given swap_id adn return it
def get_open_subswap_or_error(swap_id, error_msg, request):
    sub_offer = SubSwap.objects.filter(SwapID=swap_id, SubType='Offer', nStatus='Open')
    if not sub_offer.exists():
        return render(request, 'GRPR/error_msg.html', {'error_msg': error_msg})
    return sub_offer.first()

# function to verify a player is still available for a given gDate
def check_player_availability(player_id, gDate, request):
    playing_dates = TeeTimesInd.objects.filter(PID=player_id).values_list('gDate', flat=True)
    if gDate in playing_dates:
        player = get_object_or_404(Players, id=player_id)
        player_name = f'{player.FirstName} {player.LastName}'
        error_msg = f'{player_name} is not available to play on {gDate}. They are already scheduled to play on this date.'
        return render(request, 'GRPR/error_msg.html', {'error_msg': error_msg})
    return None

# gets Tee Time details for a given tee time id and player id
def get_tee_time_details(tt_id, player_id):
    teetime = get_object_or_404(TeeTimesInd, id=tt_id)
    gDate = teetime.gDate
    course = teetime.CourseID
    tt_pid = teetime.PID.id
    course_name = course.courseName
    course_time_slot = course.courseTimeSlot
    gDate_display = gDate.strftime('%B %d, %Y')

    other_players_qs = TeeTimesInd.objects.filter(
        CourseID=course,
        gDate=gDate,
        CourseID__courseTimeSlot=course_time_slot
    ).exclude(PID=player_id).select_related('PID')

    other_players = ', '.join([f"{entry.PID.FirstName} {entry.PID.LastName}" for entry in other_players_qs])

    return {
        'gDate': gDate,
        'gDate_display': gDate_display,
        'course': course,
        'tt_pid': tt_pid,
        'course_name': course_name,
        'course_time_slot': course_time_slot,
        'other_players': other_players
    }


### helper to parse dates properly and consistently

# Accepts strings like:
#   2025-08-02
#   August 2, 2025
#   Aug 2, 2025
#   Aug. 2, 2025     (note the dot)
#   08/02/2025       (one place emits this)
# Returns a datetime.date
def parse_date_any(date_value):
    if isinstance(date_value, (datetime, date)):
        return date_value.date() if isinstance(date_value, datetime) else date_value

    s = str(date_value).strip()

    # normalize: remove trailing dot after abbreviated months, e.g., "Aug." -> "Aug"
    s = re.sub(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.(?=\s)', r'\1', s)

    # try formats most common in your app
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass

    raise ValueError(f"Unrecognized date format: {date_value!r}")

def to_ymd(date_value) -> str:
    return parse_date_any(date_value).strftime("%Y-%m-%d")

def to_long(date_value) -> str:
    return parse_date_any(date_value).strftime("%B %d, %Y")


## helper for toggling games on and off - specifically for Gas Cup
def get_toggles():
    toggles, _ = GameToggles.objects.get_or_create(pk=1)
    return toggles