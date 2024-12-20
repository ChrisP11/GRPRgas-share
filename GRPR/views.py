import os
import json
from django.shortcuts import render, get_object_or_404
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

# Import the Twilio client
from twilio.rest import Client


# Create your views here.
def home_page(request):
    # return HttpResponse("Hello, world! This is the GRPR app.")
    return render(request, 'GRPR/index.html')


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
            "gDate": gDate  # Add the chosen date to the context
        }
        return render(request, "GRPR/teesheet.html", context)
    else:
        return HttpResponseBadRequest("Invalid request.")


def schedule_view(request):
    players = Players.objects.all().order_by('LastName', 'FirstName')

    # If a player is selected, fetch their schedule
    selected_player = None
    schedule = []

    if request.method == "GET" and "player_id" in request.GET:
        player_id = request.GET.get("player_id")
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
    }
    return render(request, "GRPR/schedule.html", context)

def subswap_view(request):
    # Hardcoded user for now
    # user_name = "Chris Coogan"
    # user_id = "6"
    # user_name = "Chris Prouty"
    # user_id = "13"
    user_name = "Mike Ryan"
    user_id = "23"

    # Fetch the schedule for the user
    schedule = TeeTimesInd.objects.filter(PID=user_id).select_related('CourseID').order_by('gDate')

    # Prepare the data for the schedule table
    schedule_data = []
    for teetime in schedule:
        other_players = TeeTimesInd.objects.filter(
            CourseID=teetime.CourseID, gDate=teetime.gDate
        ).exclude(PID=user_id)

        schedule_data.append({
            'tt_id': teetime.id,  # Add the ID column here
            'date': teetime.gDate,
            'course': teetime.CourseID.courseName,
            'time_slot': teetime.CourseID.courseTimeSlot,
            'other_players': ", ".join([
                f"{player.PID.FirstName} {player.PID.LastName}" for player in other_players
            ])
        })
    
    # Fetch available swaps for the user
    available_swaps = SubSwap.objects.filter(
        Type='Swap Offer Sent',
        Status='Swap Open',
        PID=user_id
    ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID').order_by('TeeTimeIndID__gDate')

    # Prepare the data for the available swaps table
    available_swaps_data = []
    for swap in available_swaps:
        teetime = swap.TeeTimeIndID
        other_players = TeeTimesInd.objects.filter(
            CourseID=teetime.CourseID, gDate=teetime.gDate
        ).exclude(PID=user_id)

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

    context = {
        'user_name': user_name, # hard coded above
        'user_id': user_id,  # hard coded above
        'schedule_data': schedule_data,
        'available_swaps_data': available_swaps_data,
    }

    return render(request, 'GRPR/subswap.html', context)


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


def swaprequest_view(request):
    # Get the data passed via query parameters
    date = request.GET.get('date', 'Unknown date')  
    course = request.GET.get('course', 'Unknown course')
    time_slot = request.GET.get('time_slot', 'Unknown time slot')
    other_players = request.GET.get('other_players', 'No other players')
    user_name = request.GET.get('user_name', 'Unknown User')
    user_id = request.GET.get('user_id', 'Unknown User ID')
    tt_id = request.GET.get('tt_id', 'Unknown Tee Time ID')

    # Pass the data to the template
    context = {
        'date': date,
        'course': course,
        'time_slot': time_slot,
        'other_players': other_players,
        'user_name': user_name,
        'user_id': user_id,
        'tt_id': tt_id,
    }
    return render(request, 'GRPR/swaprequest.html', context)


def swaprequestsent_view(request):
    date_raw = request.GET.get('date')  # Raw date string from the request
    try:
        gDate = parser.parse(date_raw).strftime("%Y-%m-%d")  # Normalize the raw date and convert it to YYYY-MM-DD format
    except (ParserError, TypeError):
        return HttpResponse("Invalid date format.", status=400)
    
    course = request.GET.get('course', 'Unknown course')
    time_slot = request.GET.get('time_slot', 'Unknown time slot')
    user_name = request.GET.get('user_name', 'Unknown User')
    other_players = request.GET.get('other_players', 'No other players')
    tt_id = request.GET.get('tt_id', 'Unknown TT ID')

    # Validate tt_id
    if not tt_id or not tt_id.isdigit():
        return HttpResponse("Invalid Tee Time ID.", status=400)
    tt_id = int(tt_id)

    # Message to display at the top of the page
    swap_offer = f"{user_name} would like to swap his tee time on {date_raw} at {course} {time_slot} (playing with {other_players}) with one of your tee times."

    # Fetch the swap request player
    try:
        swap_request_player = Players.objects.get(FirstName=user_name.split()[0], LastName=user_name.split()[1])
    except (Players.DoesNotExist, AttributeError, IndexError):
        return HttpResponse("Swap request player not found or invalid user name format.", status=400)
    
     # Fetch the tee time instance (more foreign key crap)
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
        PID=swap_request_player, #this dumps the players 'instance' in instead of the ID bc this field in subswap is a foreign key to the Players table.
        TeeTimeIndID=tee_time_instance, #this assigns the whole instance of teetimesind not just a key
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
        # hard code to send sub offer to Chris Prouty
        to_number = '13122961817'
        # to_number=swap_request_player.Mobile
        message = client.messages.create(from_='+18449472599',body=msg,to= to_number )
        mID = message.sid
    else:
        # still be able to fill in appropriate fields in the tables
        mID = "Twilio turned off"
        msg = "This msg has been sent to all of the players available for your request date: '" + swap_offer + "'      you will be able to see this offer and status on the sub swap page."
        to_number=swap_request_player.Mobile

    # Insert the initial swap offer into Log
    Log.objects.create(
        SentDate=timezone.now()
        ,Type="Swap Offer"
        ,MessageID=mID
        ,RequestDate=gDate
        ,OfferID=swap_request_player.id
        ,RefID=initial_swap.id
        ,Msg=swap_offer
        ,To_number=to_number
    )

     # Check if Twilio is enabled
    if settings.TWILIO_ENABLED:
        # Initialize the Twilio client
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        client = Client(account_sid, auth_token)

        for player in available_players:
            SubSwap.objects.create(
            RequestDate=timezone.now(),
            PID=player, # foreign key thing , player instance not just the ID number
            TeeTimeIndID=tee_time_instance, #same foreign key thing as above
            Type="Swap Offer Sent",
            Status="Swap Open",
            Msg=swap_offer,
            OtherPlayers=other_players,
            SwapID=initial_swap.id
        )
        
            # Generate and send text to each available player
            msg = player.Mobile + " " + swap_offer + " Use this link to pick a date to swap."
            # hard code to send sub offer to Chris Prouty
            to_number = '13122961817'
            # to_number=player.Mobile
            message = client.messages.create(from_='+18449472599',body=msg,to=to_number )
            # mID = "fake Mib"
            mID = message.sid

            # Insert into Log table for tracking
            Log.objects.create(
            SentDate=timezone.now()
            ,Type="Swap Offer Sent"
            ,MessageID=mID
            ,RequestDate=gDate
            ,OfferID=swap_request_player.id
            ,ReceiveID=player.id
            ,RefID=initial_swap.id
            ,Msg=swap_offer
            ,To_number=to_number
        )
    else:
        for player in available_players:
            SubSwap.objects.create(
            RequestDate=timezone.now(),
            PID=player,
            TeeTimeIndID=tee_time_instance, #same foreign key thing as above
            Type="Swap Offer Sent",
            Status="Swap Open",
            Msg=swap_offer,
            OtherPlayers=other_players,
            SwapID=initial_swap.id
        )
            # fill out the needed variables with false data since Twilio is off
            mID = 'Twilio off'
            to_number=player.Mobile
            msg = player.Mobile + " " + swap_offer + " Use this link to pick a date to swap."
            
            # Insert into Log table for tracking
            Log.objects.create(
            SentDate=timezone.now()
            ,Type="Swap Offer Sent"
            ,MessageID=mID
            ,RequestDate=gDate
            ,OfferID=swap_request_player.id
            ,ReceiveID=player.id
            ,RefID=initial_swap.id
            ,Msg=swap_offer
            ,To_number=to_number
        )
                

    # Generate Available Swap Dates for each available player
    filtered_players = []  # List to store players with available swap dates
    for player in available_players:
        # Find dates the available player is playing in the future
        available_player_dates = TeeTimesInd.objects.filter(PID=player, gDate__gt=gDate).values_list('gDate', 'id')

        # Find dates the swap request player is playing in the future
        swap_request_player_dates = TeeTimesInd.objects.filter(PID=swap_request_player, gDate__gt=gDate).values_list('gDate', flat=True)

        # Find dates where the available player is playing, but the swap request player is not
        swap_dates = sorted([(d[0], d[1]) for d in available_player_dates if d[0] not in swap_request_player_dates])

        # Only add the player to the filtered list if they have available swap dates
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
        'available_players': filtered_players,  # Use filtered_players instead of available_players
    }
    return render(request, 'GRPR/swaprequestsent.html', context)


def swapoffer_view(request):
    user_id = request.GET.get('userid')
    swap_id = request.GET.get('swapID')
    msg = request.GET.get('Msg')
    request_date = request.GET.get('RequestDate')
    offer_id = request.GET.get('OfferID')

    # Fetch the user instance
    user = get_object_or_404(Players, pk=user_id)

    # Fetch the offer player instance
    offer_player = get_object_or_404(Players, pk=offer_id)

    # Fetch available dates for the user
    available_dates = TeeTimesInd.objects.filter(
        PID=user,
        gDate__gt=request_date
    ).exclude(
        gDate__in=TeeTimesInd.objects.filter(PID=offer_player).values_list('gDate', flat=True)
    ).select_related('CourseID').order_by('gDate')

    # Prepare the data for the table
    available_dates_data = []
    for teetime in available_dates:
        other_players = TeeTimesInd.objects.filter(
            CourseID=teetime.CourseID, gDate=teetime.gDate
        ).exclude(PID=user)

        available_dates_data.append({
            'tt_id': teetime.id,
            'date': teetime.gDate,
            'player': f"{user.FirstName} {user.LastName}",
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
    }
    return render(request, 'GRPR/swapoffer.html', context)

def swapcounter_view(request):
    user_id = request.POST.get('user_id')
    swap_id = request.POST.get('swap_id')
    offer_msg = request.POST.get('offer_msg')
    selected_dates = request.POST.get('selected_dates')

    selected_dates = json.loads(selected_dates)

    # Fetch the user instance
    user = get_object_or_404(Players, pk=user_id)

    # Fetch the offer player instance
    swap_offer = get_object_or_404(SubSwap, pk=swap_id, Type='Swap Offer')
    offer_player = swap_offer.PID

    # Fetch the mobile numbers
    # offer_mobile = offer_player.Mobile
    # counter_mobile = user.Mobile
    # hard code to Prouty for now
    offer_mobile = '13122961817'
    counter_mobile = '13122961817'

    # Fetch the original offer details
    offer_date = swap_offer.TeeTimeIndID.gDate
    offer_course = swap_offer.TeeTimeIndID.CourseID.courseName
    offer_timeslot = swap_offer.TeeTimeIndID.CourseID.courseTimeSlot

    # Create messages
    offer_msg = f"{user.FirstName} {user.LastName} has proposed dates to swap for your tee time on {offer_date} at {offer_course} {offer_timeslot}am."
    counter_msg = f"You have proposed dates to swap for {offer_player.FirstName} {offer_player.LastName}'s tee time on {offer_date} at {offer_course} {offer_timeslot}am."

    # Send Twilio messages
    if settings.TWILIO_ENABLED:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

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
            OfferID=user_id,
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
            OfferID=user_id,
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
            OfferID=user_id,
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
            OfferID=user_id,
            ReceiveID=offer_player.id,
            RefID=swap_id,
            To_number=counter_mobile,
            Msg=counter_msg
        )

    # Insert into SubSwap table for each selected date
    for date in selected_dates:
        SubSwap.objects.create(
            RequestDate=timezone.now(),
            PID=user,
            Type='Swap Counter',
            Status='Swap Open',
            Msg=counter_msg,
            OtherPlayers=date['other_players'],
            SwapID=swap_id,
            TeeTimeIndID_id=date['tt_id']
        )

    context = {
        'offer_msg': offer_msg,
        'available_dates': selected_dates,
    }
    return render(request, 'GRPR/swapcounter.html', context)