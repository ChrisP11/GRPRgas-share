from django.shortcuts import render, get_object_or_404
from .models import SubSwap, TeeTimesInd, Players

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
        error_msg = f'You are not available to play on {gDate}. You are already playing on this date.'
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