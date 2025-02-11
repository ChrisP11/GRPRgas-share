from django.shortcuts import render
from .models import SubSwap, TeeTimesInd, Players

# function to verify there is an open subswap offer for a given swap_id adn return it
def get_open_subswap_or_error(swap_id, error_msg, request):
    sub_offer = SubSwap.objects.filter(SwapID=swap_id, nType='Sub', SubType='Offer', nStatus='Open')
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