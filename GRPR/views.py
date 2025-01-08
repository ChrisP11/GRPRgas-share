import os
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.utils import timezone
from GRPR.models import Courses, TeeTimesInd, Players, SubSwap, Log
from django.db import connection
from GRPR.forms import DateForm
from datetime import datetime
from dateutil import parser
from dateutil.parser import ParserError
from django.conf import settings  # Import settings
from django.contrib.auth.views import LoginView # added for secure login page creation
from django.contrib.auth.forms import UserCreationForm # added for secure login page creation
from django.contrib.auth.decorators import login_required # added to require certified login to view any page

# Import the Twilio client
from twilio.rest import Client

# added for secure login page creation
class CustomLoginView(LoginView):
    template_name = 'GRPR/login.html'


# Create your views here.
# login page?
def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})

# Initial home page
@login_required
def home_page(request):
    context = {
        'userid': request.user.id,
        'username': request.user.username,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }
    return render(request, 'GRPR/index.html', context)


@login_required
def teesheet_view(request):
    # Check if the form was submitted
    if request.method == "GET" and "gDate" in request.GET:
        gDate = request.GET["gDate"]

        # Handle the case where the date is not provided
        if not gDate:
            return HttpResponseBadRequest("Date is required.")

        # Query the database
        queryset = TeeTimesInd.objects.filter(gDate=gDate).select_related('PID', 'CourseID')

        # Construct the cards dictionary
        cards = {}
        for teetime in queryset:
            courseName = teetime.CourseID.courseName
            courseTimeSlot = teetime.CourseID.courseTimeSlot
            key = (courseName, courseTimeSlot)
            
            if key not in cards:
                cards[key] = {
                    "courseName": courseName,
                    "courseTimeSlot": courseTimeSlot,
                    "gDate": gDate,
                    "players": []
                }
            
            player = teetime.PID
            cards[key]["players"].append({
                "firstName": player.FirstName,
                "lastName": player.LastName
            })

        # Pass data to the template
        context = {
            "cards": cards,
            "gDate": gDate,  # Add the chosen date to the context
            "first_name": request.user.first_name,  # Add the first name of the logged-in user
            "last_name": request.user.last_name, # Add the last name of the logged-in user
        }
        return render(request, "GRPR/teesheet.html", context)
    else:
        return HttpResponseBadRequest("Invalid request.")

@login_required
def schedule_view(request):
    players = Players.objects.all().order_by('LastName', 'FirstName')

    # Fetch the logged-in user's player ID
    logged_in_user_id = request.user.id
    logged_in_player = Players.objects.filter(user_id=logged_in_user_id).first()

    # If a player is selected, fetch their schedule
    selected_player = None
    schedule = []

    if request.method == "GET":
        player_id = request.GET.get("player_id", logged_in_player.id if logged_in_player else None)
        if player_id:
            selected_player = Players.objects.filter(id=player_id).first()
            schedule_query = TeeTimesInd.objects.filter(PID=player_id).select_related('CourseID').order_by('gDate')
            for teetime in schedule_query:
                # Collect the names of other players in the group
                group_players = TeeTimesInd.objects.filter(
                    gDate=teetime.gDate,
                    CourseID=teetime.CourseID
                ).exclude(PID=player_id).select_related('PID')

                other_players = [f"{gp.PID.FirstName} {gp.PID.LastName}" for gp in group_players]
                schedule.append({
                    "id": teetime.id,  # Add the ID column here
                    "gDate": teetime.gDate,
                    "courseName": teetime.CourseID.courseName,
                    "courseTimeSlot": teetime.CourseID.courseTimeSlot,
                    "otherPlayers": ", ".join(other_players),
                })

    context = {
        "players": players,
        "selected_player": selected_player,
        "schedule": schedule,
        "first_name": request.user.first_name,  # Add the first name of the logged-in user
        "last_name": request.user.last_name, # Add the last name of the logged-in user
    }
    return render(request, "GRPR/schedule.html", context)

@login_required
def subswap_view(request):
    # Fetch the logged-in user's information
    user_id = request.user.id
    user_name = f"{request.user.first_name} {request.user.last_name}"

    # Fetch the Player ID associated with the logged-in user
    player = Players.objects.filter(user_id=user_id).first()
    if not player:
        return HttpResponseBadRequest("Player not found for the logged-in user.")
    player_id = player.id

    # Fetch the schedule for the player
    schedule = TeeTimesInd.objects.filter(PID=player_id).select_related('CourseID').order_by('gDate')

    # Prepare the data for the schedule table
    schedule_data = []
    for teetime in schedule:
        other_players = TeeTimesInd.objects.filter(
            CourseID=teetime.CourseID, gDate=teetime.gDate
        ).exclude(PID=player_id)

        schedule_data.append({
            'tt_id': teetime.id,  # Add the ID column here
            'date': teetime.gDate,
            'course': teetime.CourseID.courseName,
            'time_slot': teetime.CourseID.courseTimeSlot,
            'other_players': ", ".join([
                f"{player.PID.FirstName} {player.PID.LastName}" for player in other_players
            ])
        })
    
    # Fetch available swaps for the player
    available_swaps = SubSwap.objects.filter(
        Type='Swap Offer Sent',
        Status='Swap Open',
        PID=player_id
    ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID').order_by('TeeTimeIndID__gDate')

    # Prepare the data for the available swaps table
    available_swaps_data = []
    for swap in available_swaps:
        teetime = swap.TeeTimeIndID
        other_players = TeeTimesInd.objects.filter(
            CourseID=teetime.CourseID, gDate=teetime.gDate
        ).exclude(PID=player_id)

        # Fetch the OfferID for the swap offer
        try:
            swap_offer = SubSwap.objects.get(SwapID=swap.SwapID, Type='Swap Offer')
            offer_pid = swap_offer.PID.id
        except SubSwap.DoesNotExist:
            offer_pid = None
            print(f"No swap offer found for SwapID: {swap.SwapID}")

        available_swaps_data.append({
            'date': teetime.gDate,
            'ymdDate': teetime.gDate.strftime("%Y-%m-%d"), #converts date to YYYY-MM-DD
            'course': teetime.CourseID.courseName,
            'time_slot': teetime.CourseID.courseTimeSlot,
            'swapID': swap.SwapID,
            'Msg': swap.Msg,
            'OfferID': offer_pid,
            'other_players': ", ".join([
                f"{player.PID.FirstName} {player.PID.LastName}" for player in other_players
            ])
        })
    
    # Counter Offers table - Fetch counter offers for the player
    offered_swaps = SubSwap.objects.filter(
        PID=player_id,
        Type='Swap Offer',
        Status='Swap Open'
    )

    counter_offers_data = []
    if offered_swaps.exists():
        for offer in offered_swaps:
            # Fetch the original offer details
            original_offer = SubSwap.objects.filter(
                Type='Swap Offer',
                Status='Swap Open',
                SwapID=offer.SwapID
            ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID').first()

            if original_offer:
                original_offer_date = f"{original_offer.TeeTimeIndID.gDate} at {original_offer.TeeTimeIndID.CourseID.courseName}  {original_offer.TeeTimeIndID.CourseID.courseTimeSlot}am"
                offer_other_players = original_offer.OtherPlayers

                # Fetch the proposed swaps
                proposed_swaps = SubSwap.objects.filter(
                    Type='Swap Counter',
                    Status='Swap Open',
                    SwapID=offer.SwapID
                ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID', 'PID')

                for proposed_swap in proposed_swaps:
                    proposed_swap_date = f"{proposed_swap.TeeTimeIndID.gDate} at {proposed_swap.TeeTimeIndID.CourseID.courseName}  {proposed_swap.TeeTimeIndID.CourseID.courseTimeSlot}am"
                    proposed_by = f"{proposed_swap.PID.FirstName} {proposed_swap.PID.LastName}"
                    swap_other_players = proposed_swap.OtherPlayers

                    counter_offers_data.append({
                        'original_offer_date': original_offer_date,
                        'offer_other_players': offer_other_players,
                        'proposed_swap_date': proposed_swap_date,
                        'proposed_by': proposed_by,
                        'swap_other_players': swap_other_players,
                        'swapID': proposed_swap.SwapID,
                        'swap_ttid': proposed_swap.TeeTimeIndID.id,
                    })

    context = {
        'user_name': user_name,  # Use the logged-in user's name
        'user_id': user_id,  # Use the logged-in user's ID
        'player_id': player_id,  # Use the logged-in user's Player ID
        'schedule_data': schedule_data,
        'available_swaps_data': available_swaps_data,
        'counter_offers_data': counter_offers_data,
        "first_name": request.user.first_name,  # Add the first name of the logged-in user
        "last_name": request.user.last_name, # Add the last name of the logged-in user
    }

    return render(request, 'GRPR/subswap.html', context)

@login_required
def subrequest_view(request):
    # Get data passed via query parameters
    user_name = request.GET.get('user_name', 'User')
    date = request.GET.get('date', 'Unknown date')
    course = request.GET.get('course', 'Unknown course')
    time_slot = request.GET.get('time_slot', 'Unknown time slot')
    other_players = request.GET.get('other_players', 'No other players')

    # Pass data to the template
    context = {
        'user_name': user_name,
        'date': date,
        'course': course,
        'time_slot': time_slot,
        'other_players': other_players,
    }
    return render(request, 'GRPR/subrequest.html', context)

@login_required
def subrequestsent_view(request):
    # Get data passed via query parameters
    date_raw = request.GET.get('date', 'Unknown date')
    gDate = parser.parse(date_raw).strftime("%Y-%m-%d") #this normalizes the raw date and converts it to YYYY-MM-DD format
    sub_offer = request.GET.get('sub_offer', '')
    tt_id = request.GET.get('tt_id', 'Unknown Tee Time ID')

    # Get players already playing on the date
    playing_players = TeeTimesInd.objects.filter(gDate=gDate).values_list('PID_id', flat=True)

    # Get all players and subtract playing players and Course Credit (ID 25)
    available_players = Players.objects.exclude(id__in=list(playing_players) + [25])

    if settings.TWILIO_ENABLED:
        # Initialize the Twilio client
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        client = Client(account_sid, auth_token)
        
        for player in available_players:
            msg = sub_offer
            # to_number=player.Mobile
            to_number='13122961817'
            message = client.messages.create(from_='+18449472599',body=msg,to=to_number )
            mID = message.sid
    else:
        print("Twilio is off")
    
    twilio_messages= "blank for now"
       
    # Pass data to the template
    context = {
        'date': date_raw,
        'sub_offer': sub_offer,
        'available_players': available_players,
        'twilio_messages': twilio_messages,
    }
    return render(request, 'GRPR/subrequestsent.html', context)

# this view is used to store session data for the swap request
@login_required
def store_swap_data_view(request):
    if request.method == "GET" and "tt_id" in request.GET:
        tt_id = request.GET["tt_id"]

        # Store necessary data in the session
        request.session['swap_tt_id'] = tt_id
        request.session['user_id'] = request.user.id
        print('store_swap_data_view')
        print('tt_id', tt_id)

        return redirect('swaprequest_view')
    else:
        return HttpResponseBadRequest("Invalid request.")
    
@login_required
def swaprequest_view(request):
    # Retrieve data from the session
    swap_tt_id = request.session.pop('swap_tt_id', None)
    user_id = request.session.pop('user_id', None)
    print('swaprequeset_view')
    print('swap_tt_id', swap_tt_id)
    print('user_id', user_id)

    if not swap_tt_id or not user_id:
        return HttpResponseBadRequest("Required data is missing.")
    
        # Fetch the Player ID associated with the logged-in user
    player = Players.objects.filter(user_id=user_id).first()
    if not player:
        return HttpResponseBadRequest("Player not found for the logged-in user.")
    player_id = player.id
    print('player_id', player_id)

    # Fetch the tee time entry
    teetime = TeeTimesInd.objects.get(id=swap_tt_id)

    # Fetch other necessary data from the database
    date = teetime.gDate
    course = teetime.CourseID.courseName
    time_slot = teetime.CourseID.courseTimeSlot
    other_players = ", ".join([
        f"{player.PID.FirstName} {player.PID.LastName}" for player in TeeTimesInd.objects.filter(
            CourseID=teetime.CourseID, gDate=teetime.gDate
        ).exclude(PID=player_id)
    ])

    print('swaprequest_view post data collection')
    print('swap_tt_id',swap_tt_id)
    print('user_id', user_id)
    print('date', date)
    print('course', course)
    print('time_slot', time_slot)
    print('other_players', other_players)


    context = {
        'swap_tt_id': swap_tt_id,
        'user_id': user_id,
        'date': date,
        'course': course,
        'time_slot': time_slot,
        'other_players': other_players,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'user_name': request.user.username,
    }

    return render(request, 'GRPR/swaprequest.html', context)


@login_required
def store_swaprequestsent_data_view(request):
    if request.method == "GET":
        date_raw = request.GET.get('date')
        course = request.GET.get('course')
        time_slot = request.GET.get('time_slot')
        user_name = request.GET.get('user_name')
        other_players = request.GET.get('other_players')
        swap_tt_id = request.GET.get('swap_tt_id')
        user_id = request.GET.get('user_id')

        print('store_swaprequestsent_data_view')
        print('date_raw:', date_raw)
        print('course', course)
        print('time_slot', time_slot)
        print('user_name', user_name)
        print('other_players', other_players)
        print('swap_tt_id', swap_tt_id)
        print('user_id', user_id)


        # Store necessary data in the session
        request.session['date_raw'] = date_raw
        request.session['course'] = course
        request.session['time_slot'] = time_slot
        request.session['user_name'] = user_name
        request.session['other_players'] = other_players
        request.session['tt_id'] = swap_tt_id

        return redirect('swaprequestsent_view')
    else:
        return HttpResponseBadRequest("Invalid request.")
    

@login_required
def swaprequestsent_view(request):
    # Retrieve data from the session
    date_raw = request.session.pop('date_raw', None)
    course = request.session.pop('course', None)
    time_slot = request.session.pop('time_slot', None)
    user_name = request.session.pop('user_name', None)
    other_players = request.session.pop('other_players', None)
    tt_id = request.session.pop('tt_id', None)

    if not date_raw or not course or not time_slot or not user_name or not other_players or not tt_id:
        return HttpResponseBadRequest("Required data is missing. - swaprequestsent_view")

    try:
        gDate = parser.parse(date_raw).strftime("%Y-%m-%d")
    except (ParserError, TypeError):
        return HttpResponse("Invalid date format.", status=400)

    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    player = Players.objects.filter(user_id=user_id).first()
    if not player:
        return HttpResponseBadRequest("Player not found for the logged-in user.")
    player_id = player.id
    first_name = player.FirstName
    last_name = player.LastName

    # Message to display at the top of the page
    swap_offer = f"{first_name} {last_name} would like to swap his tee time on {date_raw} at {course} {time_slot} (playing with {other_players}) with one of your tee times."

    # Fetch the swap request player
    try:
        swap_request_player = Players.objects.get(id=player_id)
    except (Players.DoesNotExist, AttributeError, IndexError):
        return HttpResponse("Swap request player not found or invalid user name format.", status=400)

    # Fetch the tee time instance
    tee_time_instance = get_object_or_404(TeeTimesInd, pk=tt_id)

    # Find all players playing on the requested date
    players_on_requested_date = TeeTimesInd.objects.filter(gDate=gDate).values_list('PID_id', flat=True)

    # Get all available players (excluding those playing on the requested date and "Course Credit")
    available_players = Players.objects.exclude(
        pk__in=players_on_requested_date
    ).exclude(pk=25)  # Exclude Course Credit

    # Insert the initial swap offer into SubSwap
    initial_swap = SubSwap.objects.create(
        RequestDate=timezone.now(),
        PID=swap_request_player,
        TeeTimeIndID=tee_time_instance,
        Type="Swap Offer",
        Status="Swap Open",
        Msg=swap_offer,
        OtherPlayers=other_players
    )

    # Update the SwapID of the initial swap offer
    initial_swap.SwapID = initial_swap.id
    initial_swap.save()

    # Check if Twilio is enabled
    if settings.TWILIO_ENABLED:
        # Initialize the Twilio client
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        client = Client(account_sid, auth_token)

        # Generate text message and send to Offering Player
        msg = "This msg has been sent to all of the players available for your request date: '" + swap_offer + "'      you will be able to see this offer and status on the sub swap page."
        to_number = '13122961817'  # Hardcoded for now
        # to_number = player.Mobile
        message = client.messages.create(from_='+18449472599', body=msg, to=to_number)
        mID = message.sid
    else:
        mID = "Twilio turned off"
        msg = "This msg has been sent to all of the players available for your request date: '" + swap_offer + "'      you will be able to see this offer and status on the sub swap page."
        to_number = swap_request_player.Mobile

    # Insert the initial swap offer into Log
    Log.objects.create(
        SentDate=timezone.now(),
        Type="Swap Offer",
        MessageID=mID,
        RequestDate=gDate,
        OfferID=swap_request_player.id,
        RefID=initial_swap.id,
        Msg=swap_offer,
        To_number=to_number
    )

    # Check if Twilio is enabled
    if settings.TWILIO_ENABLED:

        # Initialize the Twilio client
        # COMMENTED OUT BC I THINK I DO NOT NEED IT SINCE THIS WAS ENABLED ABOVE IN A PRIOR IF ENABLED SECTION
        # account_sid = settings.TWILIO_ACCOUNT_SID
        # auth_token = settings.TWILIO_AUTH_TOKEN
        # client = Client(account_sid, auth_token)

        for player in available_players:
            SubSwap.objects.create(
                RequestDate=timezone.now(),
                PID=player,
                TeeTimeIndID=tee_time_instance,
                Type="Swap Offer Sent",
                Status="Swap Open",
                Msg=swap_offer,
                OtherPlayers=other_players,
                SwapID=initial_swap.id
            )

            # Generate and send text to each available player
            msg = player.Mobile + " " + swap_offer + " Use this link to pick a date to swap."
            to_number = '13122961817'  # Hardcoded for now
            # to_number = swap_request_player.Mobile
            message = client.messages.create(from_= '+18449472599', body=msg, to=to_number)
            mID = message.sid

            # Insert into Log table for tracking
            Log.objects.create(
                SentDate=timezone.now(),
                Type="Swap Offer Sent",
                MessageID=mID,
                RequestDate=gDate,
                OfferID=swap_request_player.id,
                ReceiveID=player.id,
                RefID=initial_swap.id,
                Msg=swap_offer,
                To_number=to_number
            )
    else:
        for player in available_players:
            SubSwap.objects.create(
                RequestDate=timezone.now(),
                PID=player,
                TeeTimeIndID=tee_time_instance,
                Type="Swap Offer Sent",
                Status="Swap Open",
                Msg=swap_offer,
                OtherPlayers=other_players,
                SwapID=initial_swap.id
            )
            mID = 'Twilio off'
            to_number = player.Mobile
            msg = player.Mobile + " " + swap_offer + " Use this link to pick a date to swap."

            # Insert into Log table for tracking
            Log.objects.create(
                SentDate=timezone.now(),
                Type="Swap Offer Sent",
                MessageID=mID,
                RequestDate=gDate,
                OfferID=swap_request_player.id,
                ReceiveID=player.id,
                RefID=initial_swap.id,
                Msg=swap_offer,
                To_number=to_number
            )

    # Generate Available Swap Dates for each available player
    filtered_players = []
    for player in available_players:
        available_player_dates = TeeTimesInd.objects.filter(PID=player, gDate__gt=gDate).values_list('gDate', 'id')
        swap_request_player_dates = TeeTimesInd.objects.filter(PID=swap_request_player, gDate__gt=gDate).values_list('gDate', flat=True)
        swap_dates = sorted([(d[0], d[1]) for d in available_player_dates if d[0] not in swap_request_player_dates])

        if swap_dates:
            player.swap_dates = swap_dates
            filtered_players.append({
                'id': player.id,
                'FirstName': player.FirstName,
                'LastName': player.LastName,
                'Mobile': player.Mobile,
                'swap_dates': swap_dates,
            })

    context = {
        'swap_offer': swap_offer,
        'available_players': filtered_players,
    }
    return render(request, 'GRPR/swaprequestsent.html', context)


@login_required
def store_swapoffer_data_view(request):
    if request.method == "GET":
        user_id = request.GET.get('userid')
        swap_id = request.GET.get('swapID')
        msg = request.GET.get('Msg')
        request_date = request.GET.get('RequestDate')
        offer_id = request.GET.get('OfferID')

        # Debugging: Print the retrieved values
        print('store_swapoffer_data_view')
        print('user_id:', user_id)
        print('swap_id:', swap_id)
        print('msg:', msg)
        print('request_date:', request_date)
        print('offer_id:', offer_id)

        # Store necessary data in the session
        request.session['user_id'] = user_id
        request.session['swap_id'] = swap_id
        request.session['msg'] = msg
        request.session['request_date'] = request_date
        request.session['offer_id'] = offer_id

        return redirect('swapoffer_view')
    else:
        return HttpResponseBadRequest("Invalid request.")
    

@login_required
def swapoffer_view(request):
    # Retrieve data from the session
    user_id = request.session.pop('user_id', None)
    swap_id = request.session.pop('swap_id', None)
    msg = request.session.pop('msg', None)
    request_date = request.session.pop('request_date', None)
    offer_id = request.session.pop('offer_id', None)

    if not user_id or not swap_id or not msg or not request_date or not offer_id:
        return HttpResponseBadRequest("Required data is missing. - swapoffer_view")

    # Fetch the Player ID associated with the logged-in user 
    player = Players.objects.filter(user_id=user_id).first()
    if not player:
        return HttpResponseBadRequest("Player not found for the logged-in user. - swapoffer_view")
    player_id = player.id  # Get the player_id from the player object
    
    # Fetch the offer player instance
    offer_player = get_object_or_404(Players, pk=offer_id)

    # Fetch available dates for the user
    available_dates = TeeTimesInd.objects.filter(
        PID=player_id,
        gDate__gt=request_date
    ).exclude(
        gDate__in=TeeTimesInd.objects.filter(PID=offer_player).values_list('gDate', flat=True)
    ).select_related('CourseID').order_by('gDate')

    # Prepare the data for the table
    available_dates_data = []
    for teetime in available_dates:
        other_players = TeeTimesInd.objects.filter(
            CourseID=teetime.CourseID, gDate=teetime.gDate
        ).exclude(PID=player_id)

        available_dates_data.append({
            'tt_id': teetime.id,
            'date': teetime.gDate,
            'player': f"{player.FirstName} {player.LastName}",
            'course': teetime.CourseID.courseName,
            'time_slot': teetime.CourseID.courseTimeSlot,
            'other_players': ", ".join([
                f"{player.PID.FirstName} {player.PID.LastName}" for player in other_players
            ])
        })

    context = {
        'msg': msg,
        'available_dates': available_dates_data,
        'user_id': user_id,
        'swap_id': swap_id,
        'player_id': player_id,  # Include player_id in the context if needed
    }
    return render(request, 'GRPR/swapoffer.html', context)


@login_required
def store_swapcounter_data_view(request):
    if request.method == "POST":
        selected_dates = request.POST.get('selected_dates')
        swap_id = request.POST.get('swap_id')
        offer_msg = request.POST.get('offer_msg')
        user_id = request.user.id

        # Fetch the Player ID associated with the logged-in user
        player = Players.objects.filter(user_id=user_id).first()
        if not player:
            return HttpResponseBadRequest("Player not found for the logged-in user.")
        player_id = player.id

        # Store necessary data in the session
        request.session['selected_dates'] = selected_dates  # Convert to JSON string
        request.session['swap_id'] = swap_id
        request.session['offer_msg'] = offer_msg
        request.session['player_id'] = player_id

        return redirect('swapcounter_view')
    else:
        return HttpResponseBadRequest("Invalid request.")


@login_required
def swapcounter_view(request):
    # Retrieve data from the session
    selected_dates = request.session.pop('selected_dates', None)
    swap_id = request.session.pop('swap_id', None)
    orig_offer_msg = request.session.pop('offer_msg', None)
    player_id = request.session.pop('player_id', None)

    if not selected_dates or not swap_id or not orig_offer_msg or not player_id:
        return HttpResponseBadRequest("Required data is missing. - swapcounter_view")

    selected_dates = json.loads(selected_dates)

    # Fetch the player instance using player_id
    player = get_object_or_404(Players, pk=player_id)

    # Fetch the offer player instance
    swap_offer = get_object_or_404(SubSwap, pk=swap_id, Type='Swap Offer')
    offer_player = swap_offer.PID

    # Fetch the mobile numbers
    offer_mobile = offer_player.Mobile
    counter_mobile = player.Mobile
    print('offer_mobile', offer_mobile)
    print('counter_mobile', counter_mobile)

    # Fetch the original offer details
    offer_date = swap_offer.TeeTimeIndID.gDate
    offer_course = swap_offer.TeeTimeIndID.CourseID.courseName
    offer_timeslot = swap_offer.TeeTimeIndID.CourseID.courseTimeSlot
    offer_player_first_name = offer_player.FirstName
    offer_player_last_name = offer_player.LastName

    # Create messages
    offer_msg = f"{player.FirstName} {player.LastName} has proposed dates to swap for your tee time on {offer_date} at {offer_course} {offer_timeslot}am."
    counter_msg = f"You have proposed dates to swap for {offer_player_first_name} {offer_player_last_name}'s tee time on {offer_date} at {offer_course} {offer_timeslot}am."

    # Send Twilio messages
    if settings.TWILIO_ENABLED:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        ##############################
        # hard code to prouty mobile
        offer_mobile = '13122961817'
        counter_mobile = '13122961817'
        ##############################

        # Send message to offer player
        message = client.messages.create(from_='+18449472599', body=offer_msg, to=offer_mobile)
        offer_mID = message.sid

        # Send message to counter player
        message = client.messages.create(from_='+18449472599', body=counter_msg, to=counter_mobile)
        counter_mID = message.sid

        # Insert into Log table for offer player
        Log.objects.create(
            SentDate=timezone.now(),
            Type='Swap Counter',
            MessageID=offer_mID,
            RequestDate=offer_date,
            OfferID=player_id,
            ReceiveID=offer_player.id,
            RefID=swap_id,
            To_number=offer_mobile,
            Msg=offer_msg
        )

        # Insert into Log table for counter player
        Log.objects.create(
            SentDate=timezone.now(),
            Type='Swap Counter',
            MessageID=counter_mID,
            RequestDate=offer_date,
            OfferID=player_id,
            ReceiveID=offer_player.id,
            RefID=swap_id,
            To_number=counter_mobile,
            Msg=counter_msg
        )
    else:
        print('Twilio is not enabled')
        # Insert into Log table for offer player
        Log.objects.create(
            SentDate=timezone.now(),
            Type='Swap Counter',
            MessageID='fake Mib',
            RequestDate=offer_date,
            OfferID=player_id,
            ReceiveID=offer_player.id,
            RefID=swap_id,
            To_number=offer_mobile,
            Msg=offer_msg
        )

        # Insert into Log table for counter player
        Log.objects.create(
            SentDate=timezone.now(),
            Type='Swap Counter',
            MessageID='fake Mib',
            RequestDate=offer_date,
            OfferID=player_id,
            ReceiveID=offer_player.id,
            RefID=swap_id,
            To_number=counter_mobile,
            Msg=counter_msg
        )

    # Insert into SubSwap table for each selected date
    for date in selected_dates:
        SubSwap.objects.create(
            RequestDate=timezone.now(),
            PID=player,
            Type='Swap Counter',
            Status='Swap Open',
            Msg=counter_msg,
            OtherPlayers=date['other_players'],
            SwapID=swap_id,
            TeeTimeIndID_id=date['tt_id']
        )

    context = {
        'offer_msg': orig_offer_msg,
        'available_dates': selected_dates,
        'offer_player_first_name': offer_player_first_name,
        'offer_player_last_name': offer_player_last_name,
    }
    return render(request, 'GRPR/swapcounter.html', context)


@login_required
def swapcounteraccept_view(request):
    user_id = request.GET.get('userID')
    original_offer_date = request.GET.get('original_offer_date')
    offer_other_players = request.GET.get('offer_other_players')
    proposed_swap_date = request.GET.get('proposed_swap_date')
    swap_other_players = request.GET.get('swap_other_players')
    swap_id = request.GET.get('swapid')
    counter_ttid = request.GET.get('swap_ttid')

    # Fetch the counter player instance
    counter_player = get_object_or_404(Players, pk=user_id)

    context = {
        'original_offer_date': original_offer_date,
        'offer_other_players': offer_other_players,
        'proposed_swap_date': proposed_swap_date,
        'swap_other_players': swap_other_players,
        'counter_player': f"{counter_player.FirstName} {counter_player.LastName}",
        'user_id': user_id,
        'counter_ttid': counter_ttid,
        'swap_id': swap_id,
    }
    return render(request, 'GRPR/swapcounteraccept.html', context)

@login_required
def swapfinal_view(request):
    user_id = request.GET.get('user_id')
    counter_ttid = request.GET.get('counter_ttid')
    swap_id = request.GET.get('swap_id')

    # Fetch the offer player instance
    offer_player = get_object_or_404(Players, pk=user_id)
    offer_mobile = offer_player.Mobile
    offer_name = f"{offer_player.FirstName} {offer_player.LastName}"

    # Fetch the counter offer details
    counter_offer = SubSwap.objects.filter(
        TeeTimeIndID=counter_ttid,
        SwapID=swap_id,
        Type='Swap Counter',
        Status='Swap Open'
    ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID', 'PID').first()

    counter_user_id = counter_offer.PID.id
    counter_gDate = counter_offer.TeeTimeIndID.gDate
    counter_Course = counter_offer.TeeTimeIndID.CourseID.courseName
    counter_TimeSlot = counter_offer.TeeTimeIndID.CourseID.courseTimeSlot
    counter_name = f"{counter_offer.PID.FirstName} {counter_offer.PID.LastName}"
    counter_mobile = counter_offer.PID.Mobile

    # Fetch the original offer details
    original_offer = SubSwap.objects.filter(
        SwapID=swap_id,
        Type='Swap Offer',
        Status='Swap Open'
    ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID').first()

    offer_ttid = original_offer.TeeTimeIndID.id
    offer_gDate = original_offer.TeeTimeIndID.gDate
    offer_Course = original_offer.TeeTimeIndID.CourseID.courseName
    offer_TimeSlot = original_offer.TeeTimeIndID.CourseID.courseTimeSlot

    # Update SubSwap table
    SubSwap.objects.filter(
        SwapID=swap_id,
        Status='Swap Open',
        Type='Swap Counter',
        TeeTimeIndID=counter_ttid
    ).update(Type='Swap Accepted')

    SubSwap.objects.filter(
        SwapID=swap_id,
        Status='Swap Open'
    ).update(Status='Swap Closed')

    # Update TeeTimesInd table
    TeeTimesInd.objects.filter(id=offer_ttid).update(PID=counter_user_id)
    TeeTimesInd.objects.filter(id=counter_ttid).update(PID=user_id)

    # create the msgs that will be sent via text to the players + be entered into the Log table
    offer_msg = f"Tee Time Swap Accepted. You are now playing {counter_gDate} at {counter_Course} at {counter_TimeSlot}am. {counter_name} will play {offer_gDate} at {offer_Course} at {offer_TimeSlot}am."
    counter_msg = f"Tee Time Swap Accepted. You are now playing {offer_gDate} at {offer_Course} at {offer_TimeSlot}am. {offer_name} will play {counter_gDate} at {counter_Course} at {counter_TimeSlot}am."
    

    # Send texts via Twilio
    if settings.TWILIO_ENABLED:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # hard code mobiles to Chris Prouty
        print("currently hard coded to Prouty Mobile, but offer_mobile would be ", offer_mobile)
        offer_mobile='13122961817'
        print("currently hard coded to Prouty Mobile, but counter_mobile would be ", counter_mobile)
        counter_mobile='13122961817'

        # Send text to Offer Player
        message = client.messages.create(from_='+18449472599', body=offer_msg, to=offer_mobile)
        offer_mID = message.sid

        # Send text to Counter Player
        message = client.messages.create(from_='+18449472599', body=counter_msg, to=counter_mobile)
        counter_mID = message.sid

        # Insert into Log table for offer player
        Log.objects.create(
            SentDate=timezone.now(),
            Type='Swap Counter Accept',
            MessageID=offer_mID,
            RequestDate=counter_gDate,
            OfferID=counter_user_id,
            ReceiveID=user_id,
            RefID=swap_id,
            Msg=offer_msg,
            To_number=offer_mobile
        )

        # Insert into Log table for counter player
        Log.objects.create(
            SentDate=timezone.now(),
            Type='Swap Offer Accept',
            MessageID=counter_mID,
            RequestDate=offer_gDate,
            OfferID=user_id,
            ReceiveID=counter_user_id,
            RefID=swap_id,
            Msg=counter_msg,
            To_number=counter_mobile
        )
    else:
        print('Twilio is not enabled')
        offer_mID = 'Fake Mib'
        counter_mID = 'Fake Mib'

         # Insert into Log table for offer player
        Log.objects.create(
            SentDate=timezone.now(),
            Type='Swap Counter Accept',
            MessageID=offer_mID,
            RequestDate=counter_gDate,
            OfferID=counter_user_id,
            ReceiveID=user_id,
            RefID=swap_id,
            Msg=offer_msg,
            To_number=offer_mobile
        )

        # Insert into Log table for counter player
        Log.objects.create(
            SentDate=timezone.now(),
            Type='Swap Offer Accept',
            MessageID=counter_mID,
            RequestDate=offer_gDate,
            OfferID=user_id,
            ReceiveID=counter_user_id,
            RefID=swap_id,
            Msg=counter_msg,
            To_number=counter_mobile
        )

    context = {
        'counter_gDate': counter_gDate,
        'counter_Course': counter_Course,
        'counter_TimeSlot': counter_TimeSlot,
        'counter_Player': counter_name,
        'offer_gDate': offer_gDate,
        'offer_Course': offer_Course,
        'offer_TimeSlot': offer_TimeSlot,
    }
    return render(request, 'GRPR/swapfinal.html', context)