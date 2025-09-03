import os
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.utils import timezone
from django.utils.timezone import now
from django.utils.dateparse import parse_date
from GRPR.models import Crews, Courses, TeeTimesInd, Players, SubSwap, Log, LoginActivity, SMSResponse, Xdates, Games, GameInvites, CourseTees, ScorecardMeta, Scorecard, CourseHoles, Skins, AutomatedMessages, Forty, GasCupPair, GasCupScore, GameSetupDraft
from datetime import datetime, date
from django.conf import settings  # Import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login # for user activity tracking on Admin page
from django.contrib.auth.decorators import login_required # added to require certified login to view any page
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm # added for secure login page creation
from django.contrib.auth.models import User # for user activity tracking on Admin page
from django.contrib.auth.views import LoginView # added for secure login page creation
from django.contrib.auth.views import PasswordChangeView
from .forms import CustomPasswordChangeForm
from django.views.decorators.csrf import csrf_exempt # added to allow Twilio to send messages
from django.views.decorators.http import require_POST, require_http_methods # added for Gas Cup toggling & new game setup workflow
from django.template.loader import render_to_string  # used on hole_input_score_view
from django.db.models import Q, Count, F, Func, Subquery, OuterRef, Max, Min, IntegerField, ExpressionWrapper, Sum
from django.db.models.functions import Cast
from django.db import transaction, connection
from django.urls import reverse_lazy, reverse
from django.core.mail import send_mail
from django.core.management import call_command
from GRPR.utils import get_open_subswap_or_error, check_player_availability, get_tee_time_details, parse_date_any, get_toggles
from GRPR.services import gascup
from twilio.rest import Client # Import the Twilio client
from twilio.twiml.messaging_response import MessagingResponse
from decimal import Decimal
import math
from collections import Counter, defaultdict
import itertools
from itertools import chain
import re
from typing import Optional


# --- helper: normalize user-entered tee time strings to "H:MM" not sure this is needed long term---
_TIME_RE = re.compile(r'^\s*(\d{1,2})(?::?(\d{2}))?\s*(am|pm)?\s*$', re.I)

def _normalize_teetime_label(raw: str) -> Optional[str]:
    """
    '900'  -> '9:00'
    '9:00' -> '9:00'
    '900am'/'9:00 AM' -> '9:00'
    '12', '12pm'-> '12:00', '12am'-> '12:00' (we’re not storing am/pm; label only)
    Returns None if it can't parse.
    """
    if not raw:
        return None
    m = _TIME_RE.match(raw)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    # We ignore am/pm in the label because your DB uses strings like '8:04'
    if not (1 <= hour <= 12) or not (0 <= minute < 60):
        return None
    return f"{hour}:{minute:02d}"


# Function to round numbers to the nearest integer
def custom_round(value):
    if value >= 0:
        return math.floor(value + 0.5)  # Round up at .5 for positive numbers
    else:
        return math.ceil(value - 0.5)  # Round up at .5 for negative numbers

today = datetime.now().date()

def game_id_for_today():
    """
    Return the Skins game-id for **today** (or None if not found).
    Adjust the Status filter if your codes differ.
    """
    today = timezone.localdate()
    game = (
        Games.objects
        .filter(PlayDate=today, Type="Skins")
        .exclude(Status="Closed")      # keep only active / pending
        .first()
    )
    return game.id if game else None

# ------------------------------------------------------------------
# Handicap utility
# ------------------------------------------------------------------
def _net_hdcp_or_zero(game_id: int, pid: int) -> int:
    """
    Return a player's NetHDCP for this game, or 0 if missing/NULL.
    Safe for use in stroke & net calculations.
    """
    from GRPR.models import ScorecardMeta
    val = (
        ScorecardMeta.objects
        .filter(GameID=game_id, PID_id=pid)
        .values_list("NetHDCP", flat=True)
        .first()
    )
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


# for Twilio.  Creates a response to people who reply to outbound text messages
@csrf_exempt
def sms_reply(request):
    # Get the message body and sender's phone number from the request
    message_body = request.POST.get('Body', '').strip().lower()
    from_number = request.POST.get('From', '').lstrip('+')  # Remove the leading '+'

    # Create a new SMSResponse object and save it to the database
    SMSResponse.objects.create(
        from_number=from_number,
        message_body=message_body
    )

    # Create a TwiML response
    response = MessagingResponse()
    # IF you want to send a response, uncomment below.  Currently no response is sent
    # response.message("Thank you for your response!")
    return HttpResponse(str(response), content_type='text/xml')

# added for secure login page creation
class CustomLoginView(LoginView):
    template_name = 'GRPR/login.html'

    def form_valid(self, form):
        user = form.get_user()
        auth_login(self.request, user)
        print(f"User {user.username} authenticated")
        
        # Log the login event
        try:
            LoginActivity.objects.create(user=user)
            print(f"LoginActivity created for user: {user.username}")
        except Exception as e:
            print(f"Error creating LoginActivity: {e}")
        
        return redirect('home_page')

# added to allow users tp change their password
class CustomPasswordChangeView(PasswordChangeView):
    form_class = CustomPasswordChangeForm
    success_url = reverse_lazy('password_change_done')
    template_name = 'GRPR/password_change.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        # Set force_password_change to False after successful password change
        self.request.user.userprofile.force_password_change = False
        self.request.user.userprofile.save()
        return response


# login page
def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})


def login_view(request):
    print("login_view called")
    
    if request.method == 'POST':
        print("POST request received")
        
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            print("Form is valid")
            
            user = form.get_user()
            auth_login(request, user)
            print(f"User {user.username} authenticated")
            
            # Log the login event
            try:
                LoginActivity.objects.create(user=user)
                print(f"LoginActivity created for user: {user.username}")
            except Exception as e:
                print(f"Error creating LoginActivity: {e}")
            return redirect('home_page')
        else:
            print("Form is not valid")
    else:
        print("GET request received")
        
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})


# Home page
@login_required
def home_page(request):
    # Get today's date
    current_datetime = datetime.now()

    # Query the next closest future date in the TeeTimesInd table
    next_closest_date = TeeTimesInd.objects.filter(gDate__gte=current_datetime).order_by('gDate').values('gDate').first()
    # last_date will provide the last date in the TeeTimesInd table if the season is over and done.  Prevents the teesheet page from failing
    last_date = TeeTimesInd.objects.filter(gDate__lt=current_datetime).order_by('gDate').values('gDate').last()
    

    # Format the date to be in YYYY-MM-DD format
    if next_closest_date:
        next_closest_date = next_closest_date['gDate'].strftime('%Y-%m-%d')
    else:
        next_closest_date = last_date['gDate'].strftime('%Y-%m-%d')

    context = {
        'userid': request.user.id,
        'username': request.user.username,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'next_closest_date': next_closest_date,  
    }
    return render(request, 'GRPR/index.html', context)

# About page
@login_required
def about_view(request):

    context = {
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }

    return render(request, 'GRPR/about.html', context)


# Admin page
@login_required
def admin_view(request):
    if request.user.username not in ['cprouty', 'Christopher_Coogan@rush.edu']:
        return redirect('home_page')  # Redirect to home if unauthorized
    
    #checks to see if Gas Cup is enabled for users to pick, possibly other games in the future
    toggles = get_toggles()
    
    # Fetch user activity
    users = User.objects.all().values('username', 'date_joined', 'last_login').order_by('-last_login')
    login_activities = LoginActivity.objects.values('user__username').annotate(login_count=Count('id'))

    # Fetch the SMS Response Activity
    players_subquery = Players.objects.filter(
        Mobile=OuterRef('from_number')
    ).values(
        'FirstName', 'LastName'
    )

    responses = SMSResponse.objects.annotate(
        player_first_name=Subquery(players_subquery.values('FirstName')[:1]),
        player_last_name=Subquery(players_subquery.values('LastName')[:1])
    ).order_by('-received_at')[:30].values(
        'received_at',
        'from_number',
        'message_body',
        'player_first_name',
        'player_last_name'
    )
    
    context = {
        'users': users,
        "gascup_enabled": toggles.gascup_enabled,
        'login_activities': login_activities,
        'responses': responses,
    }
    return render(request, 'admin_view.html', context)

# added for Gas Cup toggling
@login_required
@require_POST
def toggle_gascup_view(request):
    toggles = get_toggles()
    # checkbox posts only when checked; treat absence as False
    new_value = request.POST.get('gascup_enabled') == 'on'
    if toggles.gascup_enabled != new_value:
        toggles.gascup_enabled = new_value
        toggles.save()
    return redirect('admin_page')


# automated msg admin page - aka Coogan's Corner
@login_required
def automated_msg_admin_view(request):
    # Check if the logged-in user is 'cprouty' or 'ccoogan'
    if request.user.username not in ['cprouty', 'Christopher_Coogan@rush.edu']:
        return redirect('home_page')  # Redirect to home if unauthorized

    if request.method == 'POST':
        # Get the logged-in user's name
        logged_in_user_name = f"{request.user.first_name} {request.user.last_name}"

        # Get the message from the form
        msg = request.POST.get('message', '').strip()

        # Validate the message length
        if len(msg) > 2048:
            error_message = "Message exceeds the 2048 character limit. Please shorten your message."
            return render(request, 'automated_msg_admin.html', {
                'error_message': error_message,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
            })

        # Store the message and user name in the session
        request.session['logged_in_user_name'] = logged_in_user_name
        request.session['msg'] = msg

        # Redirect to the confirmation page
        return redirect('automated_msg_confirm_view')

    # Render the initial page for GET requests
    return render(request, 'automated_msg_admin.html', {
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    })


# Coogan's Corner Confirm view
@login_required
def automated_msg_confirm_view(request):
    # Retrieve the message and user name from the session
    logged_in_user_name = request.session.get('logged_in_user_name')
    msg = request.session.get('msg')

    if not logged_in_user_name or not msg:
        return redirect('automated_msg_admin_view')  # Redirect back if data is missing

    # Render the confirmation page
    return render(request, 'automated_msg_confirm.html', {
        'logged_in_user_name': logged_in_user_name,
        'msg': msg,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    })


# Sets the DB msg and sends a test email to Coogan and Prouty
@login_required
def automated_msg_sent_view(request):
    # Retrieve the message and user name from the session
    logged_in_user_name = request.session.pop('logged_in_user_name', None)
    msg = request.session.pop('msg', None)
    print('logged_in_user_name', logged_in_user_name)
    print('msg', msg)

    # Ensure the required data is present
    if not logged_in_user_name or not msg:
        return redirect('automated_msg_admin_view')  # Redirect back if data is missing
    
    # 'closes' prior messages that have not been sent.
    AutomatedMessages.objects.filter(SentVia='Ready').update(SentVia='CXLD', AlterDate=now(), AlterPerson='Automated')

    # Insert the message into the AutomatedMessages table
    AutomatedMessages.objects.create(
        CreateDate=now(),
        CreatePerson=logged_in_user_name,
        SentVia='Ready',
        Msg=msg
    )

    # Run the weekly_email.py management command
    try:
        call_command('weekly_email') # This will execute the weekly_email.py code
        print('call was a success?')  
    except Exception as e:
        return render(request, 'admin_view.html', {
            'error_message': f"Message was logged, but the weekly email failed to send: {e}",
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        })

    # Redirect to the admin page
    return render(request, 'admin_view.html', {
        'success_message': "Message successfully sent and logged.",
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    })


# Email test page
@login_required
def email_test_view(request):
    if request.user.username != 'cprouty':
        return redirect('home_page')  # Redirect to home if the user is not cprouty

    if request.method == 'POST':
        email = request.POST.get('email')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        from_email = os.environ.get('EMAIL_HOST_USER')

        try:
            send_mail(subject, message, from_email, [email])
            success_message = 'Test email sent successfully.'
            return render(request, 'email_test.html', {'success_message': success_message})
        except Exception as e:
            error_message = f'Error sending test email: {e}'
            return render(request, 'email_test.html', {'error_message': error_message})

    return render(request, 'email_test.html')


@login_required
def text_test_view(request):
    if request.user.username != 'cprouty':
        return redirect('home_page')  # Redirect to home if the user is not cprouty

    if request.method == 'POST':
        player_ids = request.POST.getlist('players')
        message = request.POST.get('message')
        twilio_account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        twilio_auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        twilio_phone_number = '+18449472599'

        client = Client(twilio_account_sid, twilio_auth_token)
        user_id = request.user.id
        logged_in_user = Players.objects.get(user_id=user_id)

        try:
            for player_id in player_ids:
                player = Players.objects.get(id=player_id)
                cell_number = player.Mobile
                twilio_message = client.messages.create(
                    body=message,
                    from_=twilio_phone_number,
                    to=cell_number
                )
                mID = twilio_message.sid

                # Insert record into Log table
                Log.objects.create(
                    SentDate=timezone.now(),
                    Type="Admin Text Msg",
                    MessageID=mID,
                    OfferID=logged_in_user.id,
                    ReceiveID=player.id,
                    Msg=message,
                    To_number=cell_number
            )

            success_message = 'text message sent successfully.'
            return render(request, 'text_test.html', {'success_message': success_message, 'players': Players.objects.all().exclude(Member=0).order_by('LastName', 'FirstName')})

        except Exception as e:
            error_message = f'Error sending test text message: {e}'
            return render(request, 'text_test.html', {'error_message': error_message, 'players': Players.objects.all().exclude(Member=0).order_by('LastName', 'FirstName')})

    return render(request, 'text_test.html', {'players': Players.objects.all().exclude(Member=0).order_by('LastName', 'FirstName')})


@login_required
def error_message_view(request, error_msg):
    context = {
        'error_msg': error_msg,
    }
    return render(request, 'GRPR/error_msg.html', context)


@login_required
def teesheet_view(request):
    # get today's date
    current_datetime = datetime.now()

    # Query distinct dates from TeeTimesInd that are more recent than today's date
    distinct_dates = TeeTimesInd.objects.filter(gDate__gt='2025-01-01').values('gDate').distinct().order_by('gDate')

    # Format the dates to be in YYYY-MM-DD format
    distinct_dates = [{'gDate': date['gDate'].strftime('%Y-%m-%d')} for date in distinct_dates]

    # Check if the form was submitted
    if request.method == "GET" and "gDate" in request.GET:
        gDate = request.GET["gDate"]

        # Handle the case where the date is not provided
        if not gDate:
            return HttpResponseBadRequest("Date is required.")

        # Query the database for the tee sheet cards
        queryset = TeeTimesInd.objects.filter(gDate=gDate).select_related('PID', 'CourseID').order_by('CourseID')

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
        
        # Query the database for the schedule table
        schedule_queryset = TeeTimesInd.objects.filter(gDate__gt=current_datetime).select_related('PID', 'CourseID').order_by('gDate', 'CourseID')

        # Construct the schedule dictionary
        schedule_dict = {}
        for teetime in schedule_queryset:
            key = (teetime.gDate, teetime.CourseID.courseName, teetime.CourseID.courseTimeSlot)
            if key not in schedule_dict:
                schedule_dict[key] = {
                    "date": teetime.gDate,
                    "course": teetime.CourseID.courseName,
                    "time_slot": teetime.CourseID.courseTimeSlot,
                    "players": []
                }
            schedule_dict[key]["players"].append(f"{teetime.PID.FirstName} {teetime.PID.LastName}")

        # Convert the schedule dictionary to a list
        schedule = []
        for key, value in schedule_dict.items():
            value["players"] = ", ".join(value["players"])
            schedule.append(value)

        # Pass data to the template
        context = {
            "cards": cards,
            "gDate": gDate,  # Add the chosen date to the context
            "schedule": schedule,  # Add the schedule data to the context
            "distinct_dates": distinct_dates,  # Add the distinct dates to the context
            "first_name": request.user.first_name,  # Add the first name of the logged-in user
            "last_name": request.user.last_name, # Add the last name of the logged-in user
        }
        return render(request, "GRPR/teesheet.html", context)
    else:
        # Pass the distinct dates to the template even if the form is not submitted
        context = {
        "distinct_dates": distinct_dates,
            "first_name": request.user.first_name,  # Add the first name of the logged-in user
            "last_name": request.user.last_name,  # Add the last name of the logged-in user
        }
        return render(request, "GRPR/teesheet.html", context)

@login_required
def schedule_view(request):
    players = Players.objects.all().exclude(Member=0).order_by('LastName', 'FirstName')

    current_datetime = datetime.now()

    # Fetch the logged-in user's player ID
    logged_in_user_id = request.user.id
    logged_in_player = Players.objects.filter(user_id=logged_in_user_id).first()

    # If a player is selected, fetch their schedule
    selected_player = None
    schedule = []

    if request.method == "GET":
        player_id = request.GET.get("player_id", logged_in_player.id if logged_in_player else None)
        if player_id:
            selected_player = Players.objects.filter(id=player_id).exclude(Member=0).first()
            schedule_query = TeeTimesInd.objects.filter(PID=player_id, gDate__gte='2025-01-01').select_related('CourseID').order_by('gDate')
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

    current_datetime = datetime.now()

    # Fetch the Player ID associated with the logged-in user
    player = Players.objects.filter(user_id=user_id).first()
    if not player:
        return HttpResponseBadRequest("Player not found for the logged-in user.")
    player_id = player.id

    # Fetch the schedule for the player
    schedule = TeeTimesInd.objects.filter(PID=player_id, gDate__gte=current_datetime).select_related('CourseID').order_by('gDate')

    # Schedule Table - for player to offer Subs and Swaps from
    schedule_data = []
    for teetime in schedule:
        other_players = TeeTimesInd.objects.filter(
            CourseID=teetime.CourseID, gDate=teetime.gDate
        ).exclude(PID=player_id)

        schedule_data.append({
            'tt_id': teetime.id,
            'date': teetime.gDate,
            'course': teetime.CourseID.courseName,
            'time_slot': teetime.CourseID.courseTimeSlot,
            'other_players': ", ".join([
                f"{player.PID.FirstName} {player.PID.LastName}" for player in other_players
            ])
        })
    
    # Available Subs Table
    # Fetch available subs for the player
    available_subs = SubSwap.objects.filter(
        nType='Sub',
        SubType='Received',
        nStatus='Open',
        PID=player_id
    ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID').order_by('TeeTimeIndID__gDate')

    available_subs_data = []
    for sub in available_subs:
        teetime = sub.TeeTimeIndID
        other_players = TeeTimesInd.objects.filter(
            CourseID=teetime.CourseID, gDate=teetime.gDate
        ).exclude(PID=player_id)

        # Fetch the OfferID for the sub offer
        try:
            sub_offer = SubSwap.objects.get(SwapID=sub.SwapID, nType='Sub', SubType='Offer')
            offer_pid = sub_offer.PID.id
        except SubSwap.DoesNotExist:
            offer_pid = None
            print(f"No sub offer found for SwapID: {sub.SwapID}")

        available_subs_data.append({
            'date': teetime.gDate,
            'ymdDate': teetime.gDate.strftime("%Y-%m-%d"), #converts date to YYYY-MM-DD
            'course': teetime.CourseID.courseName,
            'time_slot': teetime.CourseID.courseTimeSlot,
            'swapID': sub.SwapID,
            'Msg': sub.Msg,
            'OfferID': offer_pid,
            'other_players': ", ".join([
                f"{player.PID.FirstName} {player.PID.LastName}" for player in other_players
            ])
        })

    # Available Swaps Table
    # Fetch available swaps for the player
    available_swaps = SubSwap.objects.filter(
        nType='Swap',
        SubType='Received',
        nStatus='Open',
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
            swap_offer = SubSwap.objects.get(SwapID=swap.SwapID, nType='Swap', SubType='Offer')
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
        nType='Swap',
        SubType='Offer',
        nStatus='Open'
    )

    counter_offers_data = []
    if offered_swaps.exists():
        for offer in offered_swaps:
            # Fetch the original offer details
            original_offer = SubSwap.objects.filter(
                nType='Swap',
                SubType='Offer',
                nStatus='Open',
                SwapID=offer.SwapID
            ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID').first()

            if original_offer:
                original_offer_date = f"{original_offer.TeeTimeIndID.gDate} at {original_offer.TeeTimeIndID.CourseID.courseName}  {original_offer.TeeTimeIndID.CourseID.courseTimeSlot}am"
                offer_other_players = original_offer.OtherPlayers

                # Fetch the proposed swaps
                proposed_swaps = SubSwap.objects.filter(
                    nType='Swap',
                    SubType='Counter',
                    nStatus='Open',
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
    
    #Subs Offered Table
    subs_proposed = SubSwap.objects.filter(
        nType='Sub',
        SubType='Offer',
        nStatus='Open',
        PID=player_id
    ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID')

    subs_proposed_data = []
    for sub in subs_proposed:
        subs_proposed_data.append({
            'request_date': sub.RequestDate,
            'playing_date': sub.TeeTimeIndID.gDate,
            'course': sub.TeeTimeIndID.CourseID.courseName,
            'tee_time': sub.TeeTimeIndID.CourseID.courseTimeSlot,
            'swap_id': sub.id
        })
    
    # Swaps Proposed Table
    swaps_proposed = SubSwap.objects.filter(
        nType='Swap',
        SubType='Offer',
        nStatus='Open',
        PID=player_id
    ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID')

    # Counter Offers Proposed Table
    counter_offers_proposed = SubSwap.objects.filter(
        nType='Swap',
        SubType='Counter',
        nStatus='Open',
        PID_id=player_id
    ).select_related('TeeTimeIndID__CourseID')

    counter_offers_proposed_data = []
    for offer in counter_offers_proposed:
        
        counter_offers_proposed_data.append({
            'request_date': offer.RequestDate.strftime('%Y-%m-%d'),
            'playing_date': offer.TeeTimeIndID.gDate.strftime('%Y-%m-%d'),
            'course': offer.TeeTimeIndID.CourseID.courseName,
            'tee_time': offer.TeeTimeIndID.CourseID.courseTimeSlot,
            'subswap_table_id': offer.id #gets the unique row id in the subswap table
        })

    swaps_proposed_data = []
    # used to check if the swap has already been proposed, if it has, the buttons will be disabled
    offered_tee_time_ids = set()
    for swap in swaps_proposed:
        swaps_proposed_data.append({
            'request_date': swap.RequestDate,
            'playing_date': swap.TeeTimeIndID.gDate,
            'course': swap.TeeTimeIndID.CourseID.courseName,
            'tee_time': swap.TeeTimeIndID.CourseID.courseTimeSlot,
            'swap_id': swap.id
        })
        offered_tee_time_ids.add(swap.TeeTimeIndID.id)
    
    # Query for Open Sub Offers - used to gray out Sub Swap buttons on subswap.html
    open_sub_offers = SubSwap.objects.filter(
        nType='Sub',
        SubType='Offer',
        nStatus='Open',
        PID=player_id
    ).select_related('TeeTimeIndID')

    for sub_offer in open_sub_offers:
        offered_tee_time_ids.add(sub_offer.TeeTimeIndID.id)
    
    # Calculate the count of rows in key tables
    available_swaps_data_count = len(available_swaps_data)
    available_subs_data_count = len(available_subs_data)
    counter_offers_data_count = len(counter_offers_data)

    context = {
        'user_name': user_name,  
        'user_id': user_id,  
        'player_id': player_id,  
        'schedule_data': schedule_data,
        'available_subs_data': available_subs_data,
        'available_swaps_data': available_swaps_data,
        'counter_offers_data': counter_offers_data,
        'subs_proposed_data': subs_proposed_data, 
        'swaps_proposed_data': swaps_proposed_data,
        'offered_tee_time_ids': offered_tee_time_ids,
        'counter_offers_proposed_data': counter_offers_proposed_data,
        'first_name': request.user.first_name,  
        'last_name': request.user.last_name, 
        'available_swaps_data_count': available_swaps_data_count,   
        'available_subs_data_count': available_subs_data_count,
        'counter_offers_data_count': counter_offers_data_count,
    }

    return render(request, 'GRPR/subswap.html', context)


@login_required
def store_sub_request_data_view(request):
    tt_id = request.GET.get('tt_id')

    request.session['tt_id'] = tt_id

    return redirect('subrequest_view')


@login_required
def subrequest_view(request):
    tt_id = request.session.pop('tt_id', None)

    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    first_name = request.user.first_name
    last_name = request.user.last_name

    player = get_object_or_404(Players, user_id=user_id)
    player_id = player.id

    # Fetch the TeeTimeInd instance and other players using the utility function (in utils.py)
    tee_time_details = get_tee_time_details(tt_id, player_id)
    gDate = tee_time_details['gDate']
    course_name = tee_time_details['course_name']
    course_time_slot = tee_time_details['course_time_slot']
    other_players = tee_time_details['other_players']

    # Get players already playing on the date
    playing_players = TeeTimesInd.objects.filter(gDate=gDate).values_list('PID_id', flat=True)

    # Get all players who are members and subtract playing players
    available_players = Players.objects.filter(Member=1).exclude(id__in=list(playing_players))

    ## GATE - make sure there are players available, send to error page if not.
    if not available_players.exists():
        return render(request, 'GRPR/error_msg.html', {'error_msg': 'No Players have available tee times on this date.'})
    
    # Get list of players available to sub
    available_subs = []
    for player in available_players:
        possible_sub = player.FirstName + " " + player.LastName
        available_subs.append({'possible_sub': possible_sub, 'id': player.id})
        

    # Pass data to the template
    context = {
        'first_name': first_name,
        'last_name': last_name,
        'gDate': gDate,
        'gDate_display': gDate,
        'course_name': course_name,
        'course_time_slot': course_time_slot,
        'other_players': other_players,
        'tt_id': tt_id, 
        'available_subs': available_subs,
    }
    return render(request, 'GRPR/subrequest.html', context)


@login_required
def store_sub_request_sent_data_view(request):
    if request.method == "POST":
        tt_id = request.POST.get('tt_id')
        player_ids = request.POST.getlist('player_ids')

        if not player_ids:
            return render(request, 'GRPR/error_msg.html', {'error_msg': 'No players selected for the sub request.'})

        # Store necessary data in the session
        request.session['tt_id'] = tt_id
        request.session['player_ids'] = player_ids

        return redirect('subrequestsent_view')
    else:
        return HttpResponseBadRequest("Invalid request.")

@login_required
def subrequestsent_view(request):
    tt_id = request.session.pop('tt_id', None)
    # changing the available players id list name to avoid confusion with player_id variable
    sub_ids = request.session.pop('player_ids', None)

    if not tt_id or not sub_ids:
        return HttpResponseBadRequest("Required data is missing. - subrequestsent_view")
    
    for s_id in sub_ids:
        print(f"Sub ID: {s_id}")
    

    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    first_name = request.user.first_name
    last_name = request.user.last_name

    offer_player = get_object_or_404(Players, user_id=user_id)
    offer_player_id = offer_player.id

    # Fetch the TeeTimeInd instance and other players using the utility function
    tee_time_details = get_tee_time_details(tt_id, offer_player_id)
    gDate = tee_time_details['gDate']
    tt_pid = tee_time_details['tt_pid']
    course_name = tee_time_details['course_name']
    course_time_slot = tee_time_details['course_time_slot']
    other_players = tee_time_details['other_players']

    # GATE: Verify the logged in user owns this tee time (abundance of caution here)
    if tt_pid != offer_player_id:
        error_msg = 'It appears you are not the owner of this tee time.  Please return to the Sub Swap page and try again.'
        return render(request, 'GRPR/error_msg.html', {'error_msg': error_msg})
    
    # GATE: Verify the user has not offered this tt_id already - prevents 'back' button abuse
    if SubSwap.objects.filter(TeeTimeIndID_id=tt_id, nType='Sub', SubType = 'Offer', nStatus = 'Open').exists():
        error_msg = 'It appears you have already offered this tee time and it is still available.  Please return to the Sub Swap page and try again.'
        return render(request, 'GRPR/error_msg.html', {'error_msg': error_msg})

    # Create the sub_offer message
    sub_offer = f"{first_name} {last_name} is offering his tee time on {gDate} at {course_name} {course_time_slot} to play with {other_players} to the first person who wants it."

    # Insert the initial Sub Offer into SubSwap
    initial_sub = SubSwap.objects.create(
        RequestDate=timezone.now(),
        PID_id=offer_player_id,
        TeeTimeIndID_id=tt_id,
        nType="Sub",
        SubType="Offer",
        nStatus="Open",
        Msg=sub_offer,
        OtherPlayers=other_players
    )

    # Update the SwapID of the initial Sub Offer
    initial_sub.SwapID = initial_sub.id
    initial_sub.save()
    swap_id = initial_sub.id
    
    available_players = []

    for s_id in sub_ids:
        player = Players.objects.get(id=s_id)
        to_number = player.Mobile
        avail_id = player.id
        avail_name = player.FirstName + " " + player.LastName
        available_players.append({'player': player, 'to_number': to_number, 'avail_id': avail_id, 'avail_name': avail_name})


    if settings.TWILIO_ENABLED:
        # Initialize the Twilio client
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        client = Client(account_sid, auth_token)

        # Generate text message and send to Sub Offering player
        msg = "This msg has been sent to all of the players available for your request date: '" + sub_offer + "'      you will be able to see this offer and status on the sub swap page."
        to_number = offer_player.Mobile
        message = client.messages.create(from_='+18449472599', body=msg, to=to_number)
        mID = message.sid

        # Insert initial Sub Offer into Log
        Log.objects.create(
            SentDate=timezone.now(),
            Type="Sub Offer",
            MessageID=mID,
            RequestDate=gDate,
            OfferID=offer_player_id,
            RefID=swap_id,
            Msg=sub_offer,
            To_number=to_number
        )

        # Create an insert in SubSwap table for every player in the Available Players list
        for player_data in available_players:
            player = player_data['player']
            to_number = player_data['to_number']
            avail_id = player_data['avail_id']

            SubSwap.objects.create(
                RequestDate=timezone.now(),
                PID=player,
                TeeTimeIndID_id=tt_id,
                nType="Sub",
                SubType="Received",
                nStatus="Open",
                Msg=sub_offer,
                OtherPlayers=other_players,
                SwapID=swap_id
            )

            # Create and send a text to every Available Player
            msg = f"{sub_offer} https://www.gasgolf.org/GRPR/store_subaccept_data/?swap_id={swap_id}"
            message = client.messages.create(from_='+18449472599', body=msg, to=to_number)
            mID = message.sid

            # Insert a row into Log table for every text sent
            Log.objects.create(
                SentDate=timezone.now(),
                Type="Sub Offer Sent",
                MessageID=mID,
                RequestDate=gDate,
                OfferID=offer_player_id,
                ReceiveID=avail_id,
                RefID=swap_id,
                Msg=sub_offer,
                To_number=to_number
            )
    else:

        # Insert initial Sub Offer into Log
        Log.objects.create(
            SentDate=timezone.now(),
            Type="Sub Offer",
            MessageID='fake mID',
            RequestDate=gDate,
            OfferID=offer_player_id,
            RefID=swap_id,
            Msg=sub_offer,
            To_number=to_number
        )

        # Create an insert in SubSwap table for every player in the Available Players list
        for player_data in available_players:
            player = player_data['player']
            to_number = player_data['to_number']
            avail_id = player_data['avail_id']

            SubSwap.objects.create(
                RequestDate=timezone.now(),
                PID=player,
                TeeTimeIndID_id=tt_id,
                nType="Sub",
                SubType="Received",
                nStatus="Open",
                Msg=sub_offer,
                OtherPlayers=other_players,
                SwapID=swap_id
            )

            # Insert a row into Log table for every text sent
            Log.objects.create(
                SentDate=timezone.now(),
                Type="Sub Offer Sent",
                MessageID='fake mID',
                RequestDate=gDate,
                OfferID=offer_player_id,
                ReceiveID=avail_id,
                RefID=swap_id,
                Msg=sub_offer,
                To_number=to_number
            )

    # Pass data to the template
    context = {
        'date': gDate,
        'sub_offer': sub_offer,
        'available_players': available_players,
    }
    return render(request, 'GRPR/subrequestsent.html', context)


@login_required
def store_subaccept_data_view(request):
    swap_id = request.GET.get('swap_id')

    # GATE: Fetch the SubSwap instance using the utility function (in utils.py)
    error_msg = 'The requested Sub is no longer available'
    sub_offer = get_open_subswap_or_error(swap_id, error_msg, request)
    if isinstance(sub_offer, HttpResponse):
        return sub_offer
    
    # Fetch the TeeTimeInd instance
    teetime = sub_offer.TeeTimeIndID
    gDate = teetime.gDate
    course = teetime.CourseID
    course_name = course.courseName 
    course_time_slot = course.courseTimeSlot

    user_id = request.user.id # gets the logged in user's ID
    player = get_object_or_404(Players, user_id=user_id) # turns the user ID into a player object, to get the player ID
    
    # GATE: Check if the logged-in user is still available to play the Sub gDate on offer
    availability_error = check_player_availability(player.id, gDate, request)
    if availability_error:
        return availability_error

    # Fetch the offer player details
    offer_player = sub_offer.PID
    offer_player_first_name = offer_player.FirstName
    offer_player_last_name = offer_player.LastName

    # Fetch other players
    other_players = sub_offer.OtherPlayers

    # Store necessary data in the session
    request.session['swap_id'] = swap_id
    request.session['gDate'] = gDate.strftime('%Y-%m-%d')
    request.session['course_name'] = course_name
    request.session['course_time_slot'] = course_time_slot
    request.session['offer_player_first_name'] = offer_player_first_name
    request.session['offer_player_last_name'] = offer_player_last_name
    request.session['other_players'] = other_players

    return redirect('subaccept_view')


@login_required
def subaccept_view(request):
    # Retrieve data from the session
    swap_id = request.session.pop('swap_id', None)
    gDate = request.session.pop('gDate', None)
    course_name = request.session.pop('course_name', None)
    course_time_slot = request.session.pop('course_time_slot', None)
    offer_player_first_name = request.session.pop('offer_player_first_name', None)
    offer_player_last_name = request.session.pop('offer_player_last_name', None)
    other_players = request.session.pop('other_players', None)

    if not swap_id or not gDate or not course_name or not course_time_slot or not offer_player_first_name or not offer_player_last_name or not other_players:
        return HttpResponseBadRequest("Required data is missing. - subaccept_view")

    # Format the date for display
    gDate_display = datetime.strptime(gDate, '%Y-%m-%d').strftime('%B %d, %Y')

    # Pass data to the template
    context = {
        'swap_id': swap_id,
        'gDate': gDate_display,
        'course_name': course_name,
        'course_time_slot': course_time_slot,
        'offer_player_first_name': offer_player_first_name,
        'offer_player_last_name': offer_player_last_name,
        'other_players': other_players,
        'first_name': request.user.first_name, # for nav bar
        'last_name': request.user.last_name, # for nav bar
    }
    return render(request, 'GRPR/subaccept.html', context)


@login_required
def store_subfinal_data_view(request):
    if request.method == "GET":
        swap_id = request.GET.get('swap_id')

        # GATE: Fetch the SubSwap instance using the utility function (in utils.py)
        error_msg = 'The requested Sub is no longer available'
        sub_offer = get_open_subswap_or_error(swap_id, error_msg, request)
        if isinstance(sub_offer, HttpResponse):
            return sub_offer
        
        # Fetch the TeeTimeInd instance
        teetime = sub_offer.TeeTimeIndID
        gDate = teetime.gDate
        course = teetime.CourseID
        course_name = course.courseName 
        course_time_slot = course.courseTimeSlot

        user_id = request.user.id # gets the logged in user's ID
        player = get_object_or_404(Players, user_id=user_id) # turns the user ID into a player object, to get the player ID
        player_id = player.id
        player_mobile = player.Mobile

        # GATE: Check if the logged-in user is still available to play the Sub gDate on offer
        availability_error = check_player_availability(player.id, gDate, request)
        if availability_error:
            return availability_error


        # Fetch the offer player details
        offer_player = sub_offer.PID
        offer_player_first_name = offer_player.FirstName
        offer_player_last_name = offer_player.LastName
        offer_player_mobile = offer_player.Mobile
        offer_player_id = offer_player.id

        # Fetch other players
        other_players = sub_offer.OtherPlayers

        # Fetch the Player name associated with the logged-in user
        first_name = request.user.first_name
        last_name = request.user.last_name

        # Store necessary data in the session
        request.session['swap_id'] = swap_id
        request.session['tt_id'] = teetime.id
        request.session['gDate'] = gDate.strftime('%Y-%m-%d')
        request.session['course_name'] = course_name
        request.session['course_time_slot'] = course_time_slot
        request.session['offer_player_first_name'] = offer_player_first_name
        request.session['offer_player_last_name'] = offer_player_last_name
        request.session['offer_player_mobile'] = offer_player_mobile
        request.session['offer_player_id'] = offer_player_id
        request.session['other_players'] = other_players
        request.session['first_name'] = first_name
        request.session['last_name'] = last_name
        request.session['player_id'] = player_id
        request.session['player_mobile'] = player_mobile

        return redirect('subfinal_view')
    else:
        return HttpResponseBadRequest("Invalid request.")
    

@login_required
def subfinal_view(request):
    # Retrieve data from the session
    swap_id = request.session.pop('swap_id', None)
    tt_id = request.session.pop('tt_id', None)
    gDate = request.session.pop('gDate', None)
    course_name = request.session.pop('course_name', None)
    course_time_slot = request.session.pop('course_time_slot', None)
    offer_player_first_name = request.session.pop('offer_player_first_name', None)
    offer_player_last_name = request.session.pop('offer_player_last_name', None)
    offer_player_mobile = request.session.pop('offer_player_mobile', None)
    offer_player_id = request.session.pop('offer_player_id', None)
    other_players = request.session.pop('other_players', None)
    first_name = request.session.pop('first_name', None)
    last_name = request.session.pop('last_name', None)
    player_id = request.session.pop('player_id', None)
    player_mobile = request.session.pop('player_mobile', None)

    if not swap_id or not tt_id or not gDate or not course_name or not course_time_slot or not offer_player_first_name or not offer_player_last_name or not offer_player_mobile or not offer_player_id or not other_players or not first_name or not last_name or not player_id or not player_mobile:
        return HttpResponseBadRequest("Required data is missing. - subfinal_view")

    # Update SubSwap table
    # updates the row for the user who took the sub
    SubSwap.objects.filter(
        SwapID=swap_id,
        nStatus='Open',
        nType='Sub',
        SubType='Received',
        PID=player_id
    ).update(nStatus = 'Closed', SubStatus='Accepted')

    # closes all the other sub offer rows that equal this swap_id
    SubSwap.objects.filter(
        SwapID=swap_id,
        nType='Sub',
        nStatus='Open'
    ).update(nStatus='Closed')

    # closes any swap counters that could be open and offered by the original owner of the offered Sub tee time
    SubSwap.objects.filter(
        TeeTimeIndID=tt_id,
        nType = 'Swap',
        nStatus='Open',
    ).update(nStatus='Closed', SubStatus='Owner Change')
    
    #finds any other sub or swap offers that are open for the accepting player for the same date they just took a sub for
    subswap_offers_same_date = SubSwap.objects.select_related('TeeTimeIndID').filter(
            Q(TeeTimeIndID__gDate=gDate) &
            Q(PID=player_id) &
            Q(nStatus='Open') 
    )
    
    #closes any other subs or swaps that were opened (when the accepting player was available) that, with this acceptance, are no longer available for
    for ss in subswap_offers_same_date:
        ss_id = ss.id
        ss_swap_id = ss.SwapID

        SubSwap.objects.filter(
            id=ss_id,
            ).update(nStatus='Closed', SubStatus='Superseded')
        
        # Insert row into Log for offer player
        Log.objects.create(
            SentDate=timezone.now(),
            Type="SubSwap Superseded",
            MessageID='none',
            RequestDate=gDate,
            ReceiveID=player_id,
            RefID=ss_swap_id,
            Msg="Sub Swap was superseded by another Sub Swap for the same date that was accepted by this player",
        )
    
    # Find all other players in SubSwap for this SwapID except the Offer Player and Sub Accept Player - allows us to send them a msg the Sub is closed
    other_subswap_players = SubSwap.objects.filter(
        SwapID=swap_id
    ).exclude(
        PID__in=[offer_player_id, player_id]
    ).select_related('PID')


    # Check if Twilio is enabled
    if settings.TWILIO_ENABLED:
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        client = Client(account_sid, auth_token)

        # Send text to the Sub Offer Player
        offer_msg = f"Sub Accepted: {first_name} {last_name} is taking your tee time on {gDate} at {course_name} {course_time_slot}."
        to_number = offer_player_mobile
        message = client.messages.create(from_='+18449472599', body=offer_msg, to=to_number)
        offer_mID = message.sid

        # Insert row into Log for offer player
        Log.objects.create(
            SentDate=timezone.now(),
            Type="Sub Given",
            MessageID=offer_mID,
            RequestDate=gDate,
            OfferID=offer_player_id,
            ReceiveID=player_id,
            RefID=swap_id,
            Msg=offer_msg,
            To_number=to_number
        )

        # Send text to the Sub Accept Player
        accept_msg = f"Sub Accepted: { first_name } { last_name } is taking {offer_player_first_name} {offer_player_last_name}'s tee time on {gDate} at {course_name} {course_time_slot}."
        to_number = player_mobile
        message = client.messages.create(from_='+18449472599', body=accept_msg, to=to_number)
        accept_mID = message.sid

        # Insert row into Log for Sub Accept Player
        Log.objects.create(
            SentDate=timezone.now(),
            Type="Sub Received",
            MessageID=accept_mID,
            RequestDate=gDate,
            OfferID=offer_player_id,
            ReceiveID=player_id,
            RefID=swap_id,
            Msg=accept_msg,
            To_number=to_number
        )

        # Send text to all other players
        for sub in other_subswap_players:
            sub_closed_msg = f"Sub Closed: {first_name} {last_name} has taken {offer_player_first_name} {offer_player_last_name}'s tee time on {gDate}."
            to_number = sub.PID.Mobile
            message = client.messages.create(from_='+18449472599', body=sub_closed_msg, to=to_number)

            # Insert row into Log for each player
            Log.objects.create(
                SentDate=timezone.now(),
                Type="Sub Closed Notification",
                MessageID=message.sid,
                RequestDate=gDate,
                OfferID=offer_player_id,
                ReceiveID=sub.PID.id,
                RefID=swap_id,
                Msg=sub_closed_msg,
                To_number=to_number
            )

    else:
        offer_msg = f"Sub Accepted: {first_name} {last_name} is taking your tee time on {gDate} at {course_name} {course_time_slot}."

        # Insert row into Log for offer player
        Log.objects.create(
            SentDate=timezone.now(),
            Type="Sub Given",
            MessageID='fake mID',
            RequestDate=gDate,
            OfferID=offer_player_id,
            ReceiveID=player_id,
            RefID=swap_id,
            Msg=offer_msg,
            To_number=offer_player_mobile
        )

        accept_msg = f"Sub Accepted: { first_name } { last_name } is taking {offer_player_first_name} {offer_player_last_name}'s tee time on {gDate} at {course_name} {course_time_slot}."

        # Insert row into Log for Sub Accept Player
        Log.objects.create(
            SentDate=timezone.now(),
            Type="Sub Received",
            MessageID='fake mID',
            RequestDate=gDate,
            OfferID=offer_player_id,
            ReceiveID=player_id,
            RefID=swap_id,
            Msg=accept_msg,
            To_number=player_mobile
        )

        for sub in other_subswap_players:
            sub_closed_msg = f"Sub Closed: {first_name} {last_name} has taken {offer_player_first_name} {offer_player_last_name}'s tee time on {gDate}."
            Log.objects.create(
                SentDate=timezone.now(),
                Type="Sub Closed Notification",
                MessageID='fake mID',
                RequestDate=gDate,
                OfferID=offer_player_id,
                ReceiveID=sub.PID.id,
                RefID=swap_id,
                Msg=sub_closed_msg,
                To_number=sub.PID.Mobile
            )

    # Update TeeTimesInd table
    TeeTimesInd.objects.filter(id=tt_id).update(PID=player_id)

    # Pass data to the template
    context = {
        'first_name': first_name,
        'last_name': last_name,
        'accept_msg': accept_msg,
    }
    return render(request, 'GRPR/subfinal.html', context)


@login_required
def store_subcancelconfirm_data_view(request):
    if request.method == "GET":
        swap_id = request.GET.get('swap_id')

        # Fetch the SubSwap instance
        sub_offer = get_object_or_404(SubSwap, SwapID=swap_id, nType='Sub', nStatus='Open', SubType='Offer')

        # GATE: Fetch the SubSwap instance using the utility function (in utils.py)
        error_msg = 'The requested Sub is no longer open and able to be cxld'
        sub_offer = get_open_subswap_or_error(swap_id, error_msg, request)
        if isinstance(sub_offer, HttpResponse):
            return sub_offer

        # Fetch the TeeTimeInd instance
        teetime = sub_offer.TeeTimeIndID
        gDate = teetime.gDate
        course = teetime.CourseID
        course_name = course.courseName
        course_time_slot = course.courseTimeSlot

        # Store necessary data in the session
        request.session['gDate'] = gDate.strftime('%Y-%m-%d')
        request.session['course_name'] = course_name
        request.session['course_time_slot'] = course_time_slot
        request.session['swap_id'] = swap_id

        return redirect('subcancelconfirm_view')
    else:
        return HttpResponseBadRequest("Invalid request.")
    

@login_required
def subcancelconfirm_view(request):
    # Retrieve data from the session
    gDate = request.session.pop('gDate', None)
    course_name = request.session.pop('course_name', None)
    course_time_slot = request.session.pop('course_time_slot', None)
    swap_id = request.session.pop('swap_id', None)

    if not gDate or not course_name or not course_time_slot or not swap_id:
        return HttpResponseBadRequest("Required data is missing. - SUBcancelconfirm_view")
    
    # GATE: Verify Sub is still open - prevents back button abuse
    error_msg = 'The requested Sub is no longer available.  Please review the available Subs on the Sub Swap page and try again.'
    sub_offer = get_open_subswap_or_error(swap_id, error_msg, request)
    if isinstance(sub_offer, HttpResponse):
        return sub_offer
    
    # Convert the date string back to a datetime object
    gDate = datetime.strptime(gDate, '%Y-%m-%d')

    # Format the date for display
    gDate_display = gDate.strftime('%B %d, %Y')
    
    # Fetch the offer player instance for nav bar
    first_name = request.user.first_name
    last_name = request.user.last_name

    context = {
        'gDate': gDate_display,
        'course_name': course_name,
        'course_time_slot': course_time_slot,
        'swap_id': swap_id,
        'first_name': first_name,
        'last_name': last_name,
    }
    return render(request, 'GRPR/subcancelconfirm.html', context)


@login_required
def store_subcancel_data_view(request):
    if request.method == "GET":
        swap_id = request.GET.get('swap_id')
        error_msg = 'The requested Sub is no longer Open and able to be cancelled' # used only if next step fails

        # GATE: Fetch the SubSwap instance using the utility function (in utils.py)
        sub_offer = get_open_subswap_or_error(swap_id, error_msg, request)
        if isinstance(sub_offer, HttpResponse):
            return sub_offer

        # Fetch the TeeTimeInd instance
        teetime = sub_offer.TeeTimeIndID
        gDate = teetime.gDate
        course = teetime.CourseID
        course_name = course.courseName
        course_time_slot = course.courseTimeSlot

        # Store necessary data in the session
        request.session['gDate'] = gDate.strftime('%Y-%m-%d')
        request.session['course_name'] = course_name
        request.session['course_time_slot'] = course_time_slot
        request.session['swap_id'] = swap_id

        return redirect('subcancel_view')
    else:
        return HttpResponseBadRequest("Invalid request.")


@login_required
def subcancel_view(request):
    # Retrieve data from the session
    swap_id = request.session.pop('swap_id', None)
    course_name = request.session.pop('course_name', None)
    course_time_slot = request.session.pop('course_time_slot', None)
    gDate = request.session.pop('gDate', None)

    if not swap_id or not course_name or not course_time_slot or not gDate:
        return HttpResponseBadRequest("Required data is missing. - SUBcancel_view")
    
    # Convert the date string back to a datetime object
    gDate = datetime.strptime(gDate, '%Y-%m-%d')

    # Format the date for display
    gDate_display = gDate.strftime('%B %d, %Y')
    
    # Fetch the offer player instance for nav bar
    first_name = request.user.first_name
    last_name = request.user.last_name
    user_id = request.user.id
    player = Players.objects.filter(user_id=user_id).first()
    if not player:
        return HttpResponseBadRequest("Player not found for the logged-in user.")
    player_id = player.id

    # Update SubSwap table
    SubSwap.objects.filter(SwapID=swap_id, nStatus='Open').update(nStatus='Closed', SubStatus='Cancelled')

    # Insert a row into Log table
    Log.objects.create(
        SentDate=timezone.now(),
        Type='Sub Cancelled',
        MessageID='No text sent',
        RequestDate=gDate,
        OfferID=player_id,
        RefID=swap_id,
        Msg=f'Sub Cancelled by {first_name} {last_name}'
    )

    context = {
        'gDate': gDate_display,
        'course_name': course_name,
        'course_time_slot': course_time_slot,
        'first_name': first_name,
        'last_name': last_name,
    }
    return render(request, 'GRPR/subcancel.html', context)


# this view is used to store session data for the swap request
@login_required
def store_swap_data_view(request):
    if request.method == "GET" and "tt_id" in request.GET:
        tt_id = request.GET["tt_id"]

        # Store necessary data in the session
        request.session['swap_tt_id'] = tt_id

        return redirect('swaprequest_view')
    else:
        return HttpResponseBadRequest("Invalid request.")
    
@login_required
def swaprequest_view(request):
    # Retrieve data from the session
    swap_tt_id = request.session.pop('swap_tt_id', None)

    if not swap_tt_id:
        return HttpResponseBadRequest("Required data is missing.")

    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    first_name = request.user.first_name
    last_name = request.user.last_name
    
    # Fetch the Player ID associated with the logged-in user
    player = Players.objects.filter(user_id=user_id).first()
    if not player:
        return HttpResponseBadRequest("Player not found for the logged-in user.")
    player_id = player.id

    # Fetch the TeeTimeInd instance and other players using the utility function
    tee_time_details = get_tee_time_details(swap_tt_id, player_id)
    gDate = tee_time_details['gDate']
    gDate_display = tee_time_details['gDate_display']
    course_name = tee_time_details['course_name']
    course_time_slot = tee_time_details['course_time_slot']
    other_players = tee_time_details['other_players']

    # Get players already playing on the date
    playing_players = TeeTimesInd.objects.filter(gDate=gDate).values_list('PID_id', flat=True)

    # Get all players who are members and subtract playing players
    available_players = Players.objects.filter(Member=1).exclude(id__in=list(playing_players))
    
    ## GATE - make sure there are players available, send to error page if not.
    if not available_players.exists():
        return render(request, 'GRPR/error_msg.html', {'error_msg': 'No Players have available tee times on this date.'})
    
    # Fetch the list of future dates for the offering player (player_id)
    offering_player_future_dates = TeeTimesInd.objects.filter(PID=player_id, gDate__gt=today).values_list('gDate', flat=True)
    print('offering_player_future_dates', offering_player_future_dates)

    available_players_with_swap_dates = []
    for player in available_players:
        # Fetch the list of future dates for the current player
        player_future_dates = TeeTimesInd.objects.filter(PID=player, gDate__gt=today).values_list('gDate', flat=True)
        print('player', player, 'player_future_dates', player_future_dates)
        
        # Check if all future dates for the current player are in the offering player's future dates
        if all(date in offering_player_future_dates for date in player_future_dates):
            print(f"Player {player.id} has all future dates in the offering player's schedule. Skipping.")
            continue
        
        # Check if the player has any available swap dates
        available_swap_dates = TeeTimesInd.objects.filter(PID=player, gDate__gt=today).exists()

        if available_swap_dates:
            available_players_with_swap_dates.append(player)

    if not available_players_with_swap_dates:
        return redirect('swapnoneavail_view')
    
    # Generate Available Swap Dates for each available player
    filtered_players = []
    for player in available_players:
        available_player_dates = TeeTimesInd.objects.filter(PID=player, gDate__gt=today).values_list('gDate', 'id')
        swap_request_player_dates = TeeTimesInd.objects.filter(PID=player_id, gDate__gt=today).values_list('gDate', flat=True)
        swap_dates = sorted([(d[0], d[1]) for d in available_player_dates if d[0] not in swap_request_player_dates])

        if swap_dates:
            formatted_swap_dates = [(d[0].strftime('%m/%d/%Y'), d[1]) for d in swap_dates]
            player.swap_dates = formatted_swap_dates
            filtered_players.append({
                'id': player.id,
                'FirstName': player.FirstName,
                'LastName': player.LastName,
                'Mobile': player.Mobile,
                'swap_dates': formatted_swap_dates,
            })


    context = {
        'tt_id': swap_tt_id,
        'gDate': gDate,
        'gDate_display': gDate_display,
        'course_name': course_name,
        'course_time_slot': course_time_slot,
        'other_players': other_players,
        'first_name': first_name,
        'last_name': last_name,
        'available_players': filtered_players, 
    }

    return render(request, 'GRPR/swaprequest.html', context)


@login_required
def store_swap_request_sent_data_view(request):
    if request.method == "POST":
        tt_id = request.POST.get('tt_id')
        player_ids = request.POST.getlist('player_ids')

        if not player_ids:
            return render(request, 'GRPR/error_msg.html', {'error_msg': 'No players selected for the swap request.'})

        # Store necessary data in the session
        request.session['tt_id'] = tt_id
        request.session['player_ids'] = player_ids

        return redirect('swaprequestsent_view')
    else:
        return HttpResponseBadRequest("Invalid request.")    

@login_required
def swaprequestsent_view(request):
    tt_id = request.session.pop('tt_id', None)
    player_ids = request.session.pop('player_ids', None)

    if not tt_id or not player_ids:
        return HttpResponseBadRequest("Required data is missing. - swaprequestsent_view")

    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    first_name = request.user.first_name
    last_name = request.user.last_name

    offer_player = get_object_or_404(Players, user_id=user_id)
    offer_player_id = offer_player.id

    # Fetch the TeeTimeInd instance and other players using the utility function
    tee_time_details = get_tee_time_details(tt_id, offer_player_id)
    gDate = tee_time_details['gDate']
    tt_pid = tee_time_details['tt_pid']
    course_name = tee_time_details['course_name']
    course_time_slot = tee_time_details['course_time_slot']
    other_players = tee_time_details['other_players']

    # GATE: Verify the logged in user owns this tee time (abundance of caution here)
    if tt_pid != offer_player_id:
        error_msg = 'It appears you are not the owner of this tee time.  Please return to the Sub Swap page and try again.'
        return render(request, 'GRPR/error_msg.html', {'error_msg': error_msg})
    
    # GATE: Verify the user has not offered this tt_id already - prevents 'back' button abuse
    if SubSwap.objects.filter(TeeTimeIndID_id=tt_id, nType='Swap', SubType = 'Offer', nStatus = 'Open').exists():
        error_msg = 'It appears you have already offered this tee time and it is still available.  Please return to the Sub Swap page and try again.'
        return render(request, 'GRPR/error_msg.html', {'error_msg': error_msg})

    # Create the swap_offer message
    swap_offer = f"{first_name} {last_name} is offering to trade his tee time on {gDate} at {course_name} {course_time_slot} playing with {other_players} for one of your tee times.  Please review the Sub Swap page for details."

    # Insert the initial Swap Offer into SubSwap
    initial_swap = SubSwap.objects.create(
        RequestDate=timezone.now(),
        PID_id=offer_player_id,
        TeeTimeIndID_id=tt_id,
        nType="Swap",
        SubType="Offer",
        nStatus="Open",
        Msg=swap_offer,
        OtherPlayers=other_players
    )

    # Update the SwapID of the initial Swap Offer
    initial_swap.SwapID = initial_swap.id
    initial_swap.save()
    swap_id = initial_swap.id

    available_players = []

    for s_id in player_ids:
        player = Players.objects.get(id=s_id)
        to_number = player.Mobile
        avail_id = player.id
        avail_name = player.FirstName + " " + player.LastName
        available_players.append({'player': player, 'to_number': to_number, 'avail_id': avail_id, 'avail_name': avail_name})

    if settings.TWILIO_ENABLED:
        # Initialize the Twilio client
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        client = Client(account_sid, auth_token)

        # Generate text message and send to Swap Offering player
        msg = "This msg has been sent to all of the players available for your request date: '" + swap_offer + "'      you will be able to see this offer and status on the sub swap page."
        to_number = offer_player.Mobile
        message = client.messages.create(from_='+18449472599', body=msg, to=to_number)
        mID = message.sid

        # Insert initial Swap Offer into Log
        Log.objects.create(
            SentDate=timezone.now(),
            Type="Swap Offer",
            MessageID=mID,
            RequestDate=gDate,
            OfferID=offer_player_id,
            RefID=swap_id,
            Msg=swap_offer,
            To_number=to_number
        )

        # Create an insert in SubSwap table for every player in the Available Players list
        for player_data in available_players:
            player = player_data['player']
            to_number = player_data['to_number']
            avail_id = player_data['avail_id']

            SubSwap.objects.create(
                RequestDate=timezone.now(),
                PID=player,
                TeeTimeIndID_id=tt_id,
                nType="Swap",
                SubType="Received",
                nStatus="Open",
                Msg=swap_offer,
                OtherPlayers=other_players,
                SwapID=swap_id
            )

            # Create and send a text to every Available Player
            msg = f"{swap_offer} https://www.gasgolf.org/GRPR/store_swapoffer_data/?swapID={swap_id}"
            message = client.messages.create(from_='+18449472599', body=msg, to=to_number)
            mID = message.sid

            # Insert a row into Log table for every text sent
            Log.objects.create(
                SentDate=timezone.now(),
                Type="Swap Offer Sent",
                MessageID=mID,
                RequestDate=gDate,
                OfferID=offer_player_id,
                ReceiveID=avail_id,
                RefID=swap_id,
                Msg=swap_offer,
                To_number=to_number
            )
    else:
        to_number = player.Mobile

        # Insert initial Swap Offer into Log
        Log.objects.create(
            SentDate=timezone.now(),
            Type="Swap Offer",
            MessageID='fake mID',
            RequestDate=gDate,
            OfferID=offer_player_id,
            RefID=swap_id,
            Msg=swap_offer,
            To_number=to_number
        )

        # Create an insert in SubSwap table for every player in the Available Players list
        for player_data in available_players:
            player = player_data['player']
            to_number = player_data['to_number']
            avail_id = player_data['avail_id']

            SubSwap.objects.create(
                RequestDate=timezone.now(),
                PID=player,
                TeeTimeIndID_id=tt_id,
                nType="Swap",
                SubType="Received",
                nStatus="Open",
                Msg=swap_offer,
                OtherPlayers=other_players,
                SwapID=swap_id
            )

            # Insert a row into Log table for every text sent
            Log.objects.create(
                SentDate=timezone.now(),
                Type="Swap Offer Sent",
                MessageID='fake mID',
                RequestDate=gDate,
                OfferID=offer_player_id,
                ReceiveID=avail_id,
                RefID=swap_id,
                Msg=swap_offer,
                To_number=to_number
            )

    # Pass data to the template
    context = {
        'date': gDate,
        'swap_offer': swap_offer,
        'available_players': available_players,
    }
    return render(request, 'GRPR/swaprequestsent.html', context)

@login_required
def store_swapoffer_data_view(request):
    if request.method == "GET":
        swap_id = request.GET.get('swapID')

        request.session['swap_id'] = swap_id

        return redirect('swapoffer_view')
    else:
        return HttpResponseBadRequest("Invalid request.")
    

@login_required
def swapoffer_view(request):
    # Retrieve data from the session
    swap_id = request.session.pop('swap_id', None)

    if not swap_id :
        return HttpResponseBadRequest("Required data is missing. - swapoffer_view")
    
    # Fetch the tt_id assoc with the swap_id
    subswap_row = get_object_or_404(SubSwap, id=swap_id, SubType='Offer')
    tt_id = subswap_row.TeeTimeIndID_id
    offer_id = subswap_row.PID_id

    # Fetch the offer player instance
    offer_player = get_object_or_404(Players, pk=offer_id)
    offer_player_first_name = offer_player.FirstName
    offer_player_last_name = offer_player.LastName
    
    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    first_name = request.user.first_name
    last_name = request.user.last_name

    player = get_object_or_404(Players, user_id=user_id)
    player_id = player.id

    # GATE: maybe not needed?
    if SubSwap.objects.filter(SwapID=swap_id, PID_id=player_id, SubType = 'Kountered', nStatus = 'Open').exists():
        error_msg = 'It appears you have already made a counter offer for this tee time.  Please return to the Sub Swap page and review.'
        return render(request, 'GRPR/error_msg.html', {'error_msg': error_msg})

    # Fetch the TeeTimeInd instance and other players using the utility function (in utils.py)
    tee_time_details = get_tee_time_details(tt_id, player_id)
    gDate = tee_time_details['gDate']
    gDate_display = tee_time_details['gDate_display']
    course_name = tee_time_details['course_name']
    course_time_slot = tee_time_details['course_time_slot']
    other_players = tee_time_details['other_players']

    msg = f"{offer_player_first_name} {offer_player_last_name} would like to swap his tee time on {gDate_display} at {course_name} {course_time_slot} (playing with {other_players}) with one of your tee times."

    # Fetch available dates for the user
    available_dates = TeeTimesInd.objects.filter(
        PID=player_id,
        gDate__gt=today
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
        'swap_id': swap_id,
        'first_name': first_name,
        'last_name': last_name,
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
        request.session['selected_dates'] = selected_dates
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
    
    # GATE: Verify Swap is still open
    error_msg = 'The requested Swap is no longer available.  Please review the available Swaps on the Sub Swap page and try again.'
    swap_offer = get_open_subswap_or_error(swap_id, error_msg, request)
    if isinstance(swap_offer, HttpResponse):
        return swap_offer

    # GATE: Check if the logged-in user is still available to play the Swap gDate on offer
    gDate = swap_offer.TeeTimeIndID.gDate
    print('gDate', gDate)
    availability_error = check_player_availability(player_id, gDate, request)
    if availability_error:
        return availability_error
    
    # GATE: prevents back button abuse
    if SubSwap.objects.filter(SwapID=swap_id, PID_id=player_id, SubType = 'Kountered', nStatus = 'Open').exists():
        error_msg = 'It appears you have already made a counter offer for this tee time.  Please return to the Sub Swap page and review.'
        return render(request, 'GRPR/error_msg.html', {'error_msg': error_msg})

    selected_dates = json.loads(selected_dates)

    # Fetch the player instance using player_id
    player = get_object_or_404(Players, pk=player_id)

    # Fetch the offer player instance
    swap_offer = get_object_or_404(SubSwap, pk=swap_id, nType='Swap', SubType='Offer')
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
    first_name = request.user.first_name
    last_name = request.user.last_name

    # Create message
    offer_msg = f"{ first_name } { last_name } have proposed dates to swap for {offer_player_first_name} {offer_player_last_name}'s tee time on {offer_date} at {offer_course} {offer_timeslot}am."

    # Send Twilio messages
    if settings.TWILIO_ENABLED:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # Insert into SubSwap table for each selected date
        for date in selected_dates:

            counter_date = date['date']
            counter_time_slot = date['time_slot']
            counter_course = date['course']
            counter_msg = f"{player.FirstName} {player.LastName} is willing to swap {counter_date} at {counter_course} at {counter_time_slot}am for your tee time on {offer_date}"
            print('counter_msg', counter_msg)

            SubSwap.objects.create(
                RequestDate=timezone.now(),
                PID=player,
                nType='Swap',
                nStatus='Open',
                SubType='Counter',
                Msg=counter_msg,
                OtherPlayers=date['other_players'],
                SwapID=swap_id,
                TeeTimeIndID_id=date['tt_id']
            )

            # Send message to offer player for each counter date
            message = client.messages.create(from_='+18449472599', body=counter_msg, to=offer_mobile)
            offer_mID = message.sid

        # Send message to counter player
        message = client.messages.create(from_='+18449472599', body=offer_msg, to=counter_mobile)
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

        # Insert into SubSwap table for each selected date
        for date in selected_dates:
            counter_date = date['date']
            counter_time_slot = date['time_slot']
            counter_course = date['course']
            counter_msg = f"{player.FirstName} {player.LastName} is willing to swap {counter_date} at {counter_course} at {counter_time_slot}am for your tee time on {offer_date}"
            print('counter_msg', counter_msg)

            SubSwap.objects.create(
                RequestDate=timezone.now(),
                PID=player,
                nType='Swap',
                nStatus='Open',
                SubType='Counter',
                Msg=counter_msg,
                OtherPlayers=date['other_players'],
                SwapID=swap_id,
                TeeTimeIndID_id=date['tt_id']
            )



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


    # Update SubSwap table.  Change status on the offer row to the counter player to 'Swap Kountered'.  
    # This prevents the same offer showing up in the Counter Players 'Available Swaps' list on subswap.html
    SubSwap.objects.filter(SwapID=swap_id, nType='Swap', SubType = 'Received', nStatus='Open', PID_id=player).update(SubType='Kountered')

    context = {
        'offer_msg': orig_offer_msg,
        'available_dates': selected_dates,
        'offer_player_first_name': offer_player_first_name,
        'offer_player_last_name': offer_player_last_name,
        'first_name': first_name,
        'last_name': last_name,
    }
    return render(request, 'GRPR/swapcounter.html', context)


@login_required
def store_swapcounteraccept_data_view(request):
    if request.method == "GET":
        swap_id = request.GET.get('swapid')
        counter_ttid = request.GET.get('swap_ttid')

        request.session['swap_id'] = swap_id
        request.session['counter_ttid'] = counter_ttid

        return redirect('swapcounteraccept_view')
    else:
        return HttpResponseBadRequest("Invalid request.")


@login_required
def swapcounteraccept_view(request):
    swap_id = request.session.pop('swap_id', None)
    counter_ttid = request.session.pop('counter_ttid', None)

    if not swap_id or not counter_ttid:
        return HttpResponseBadRequest("Required data is missing. - swapcounteraccept_view")

    # Fetch the tt_id assoc with the swap_id
    subswap_row = get_object_or_404(SubSwap, id=swap_id)
    offer_tt_id = subswap_row.TeeTimeIndID_id
    
    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    offer_first_name = request.user.first_name
    offer_last_name = request.user.last_name

    player = get_object_or_404(Players, user_id=user_id)
    player_id = player.id

    # Fetch the TeeTimeInd instance details for the offer date using the utility function (in utils.py)
    offer_tee_time_details = get_tee_time_details(offer_tt_id, player_id)
    offer_date = offer_tee_time_details['gDate']
    offer_course_name = offer_tee_time_details['course_name']
    offer_time_slot = offer_tee_time_details['course_time_slot']
    offer_other_players = offer_tee_time_details['other_players']

    # Fetch the TeeTimeInd instance details for the counter date using the utility function (in utils.py)
    counter_tti = get_object_or_404(TeeTimesInd, id=counter_ttid)
    counter_id = counter_tti.PID_id

    counter_tee_time_details = get_tee_time_details(counter_ttid, counter_id)
    counter_date = counter_tee_time_details['gDate']
    counter_course_name = counter_tee_time_details['course_name']
    counter_time_slot = counter_tee_time_details['course_time_slot']
    counter_other_players = counter_tee_time_details['other_players']

    # Fetch the first name and last name from the Players table using counter_player_id
    counter_player = Players.objects.filter(id=counter_id).first()
    counter_first_name = counter_player.FirstName
    counter_last_name = counter_player.LastName
    
    context = {
        'offer_date': offer_date,
        'offer_course_name': offer_course_name,
        'offer_time_slot': offer_time_slot,
        'offer_other_players': offer_other_players,
        'counter_date': counter_date,
        'counter_course_name': counter_course_name,
        'counter_time_slot': counter_time_slot,
        'counter_other_players': counter_other_players,
        'counter_ttid': counter_ttid,
        'swap_id': swap_id,
        'first_name' : offer_first_name,
        'last_name' : offer_last_name,
        'counter_first_name': counter_first_name,
        'counter_last_name': counter_last_name,
    }
    return render(request, 'GRPR/swapcounteraccept.html', context)


@login_required
def swapcounterreject_view(request):
    counter_ttid = request.GET.get('counter_ttid')
    swap_id = request.GET.get('swap_id')
    comments = request.GET.get('comments', '')

    if not counter_ttid or not swap_id:
        return HttpResponseBadRequest("Required data is missing. - swapfinal_view")
    
    # GATE: Verify Swap Offer is still open - prevents back button abuse
    error_msg = 'The requested Swap Offer is no longer available.  Please review the available Swaps on the Sub Swap page and try again.'
    swap_offer = get_open_subswap_or_error(swap_id, error_msg, request)
    if isinstance(swap_offer, HttpResponse):
        return swap_offer
    
    # GATE: Verify Counter Offer is still open
    counter_offer = SubSwap.objects.filter(SwapID=swap_id, SubType='Counter', nStatus='Open')
    if not counter_offer.exists():
        return render(request, 'GRPR/error_msg.html', {'error_msg': 'The Counter Offer is no longer available.  Please review the available Swaps on the Sub Swap page and try again.'})

    # Fetch the tt_id assoc with the swap_id
    subswap_row = get_object_or_404(SubSwap, id=swap_id)
    offer_tt_id = subswap_row.TeeTimeIndID_id
    
    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    offer_first_name = request.user.first_name
    offer_last_name = request.user.last_name

    player = get_object_or_404(Players, user_id=user_id)
    player_id = player.id

    # Fetch the TeeTimeInd instance details for the offer date using the utility function (in utils.py)
    offer_tee_time_details = get_tee_time_details(offer_tt_id, player_id)
    offer_date = offer_tee_time_details['gDate']
    offer_course_name = offer_tee_time_details['course_name']
    offer_time_slot = offer_tee_time_details['course_time_slot']

    # Fetch the TeeTimeInd instance details for the counter date using the utility function (in utils.py)
    counter_tti = get_object_or_404(TeeTimesInd, id=counter_ttid)
    counter_id = counter_tti.PID_id

    counter_tee_time_details = get_tee_time_details(counter_ttid, counter_id)
    counter_date = counter_tee_time_details['gDate']
    counter_course_name = counter_tee_time_details['course_name']
    counter_time_slot = counter_tee_time_details['course_time_slot']

    # Fetch the first name and last name from the Players table using counter_player_id
    counter_player = Players.objects.filter(id=counter_id).first()
    counter_first_name = counter_player.FirstName
    counter_last_name = counter_player.LastName
    counter_mobile = counter_player.Mobile
    counter_user_id = counter_player.id

    # Update SubSwap table for the Counter Offer, closes it as rejected
    SubSwap.objects.filter(
        SwapID=swap_id,
        nStatus='Open',
        nType='Swap',
        SubType='Counter',
        TeeTimeIndID=counter_ttid
    ).update(SubStatus='Rejected', nStatus='Closed')

    counter_msg = f"Tee Time Swap Proposal. {offer_first_name} {offer_last_name} has rejected your proposed { counter_date } at { counter_course_name } { counter_time_slot }am swap for his tee time on {offer_date} at {offer_course_name} {offer_time_slot}am.  Comments: {comments}"
    
    # Send texts via Twilio
    if settings.TWILIO_ENABLED:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # Send text to Counter Player
        message = client.messages.create(from_='+18449472599', body=counter_msg, to=counter_mobile)
        counter_mID = message.sid

        # Insert into Log table for counter player
        Log.objects.create(
            SentDate=timezone.now(),
            Type='Swap Offer Reject',
            MessageID=counter_mID,
            RequestDate=offer_date,
            OfferID=player_id,
            ReceiveID=counter_user_id,
            RefID=swap_id,
            Msg=counter_msg,
            To_number=counter_mobile
        )
    else:
        print('Twilio is not enabled')
        counter_mID = 'Fake Mib'

        # Insert into Log table for counter player
        Log.objects.create(
            SentDate=timezone.now(),
            Type='Swap Offer Accept',
            MessageID=counter_mID,
            RequestDate=offer_date,
            OfferID=player_id,
            ReceiveID=counter_user_id,
            RefID=swap_id,
            Msg=counter_msg,
            To_number=counter_mobile
        )

    context = {
        'original_player': offer_first_name + ' ' + offer_last_name,
        'original_teetime': offer_date,
        'original_course': offer_course_name,
        'original_time_slot' : offer_time_slot,
        'counter_player': counter_first_name + ' ' + counter_last_name, 
        'counter_teetime': counter_date,
        'counter_course': counter_course_name,
        'counter_course_time_slot': counter_time_slot,
        'counter_ttid': counter_ttid,
        'swap_id': swap_id,
        'comments': comments,
    }
    return render(request, 'GRPR/swapcounterreject.html', context)


@login_required
def store_swapfinal_data_view(request):
    if request.method == "GET":
        counter_ttid = request.GET.get('counter_ttid')
        swap_id = request.GET.get('swap_id')

        # Store necessary data in the session
        request.session['counter_ttid'] = counter_ttid
        request.session['swap_id'] = swap_id

        return redirect('swapfinal_view')
    else:
        return HttpResponseBadRequest("Invalid request.")
    

@login_required
def swapfinal_view(request):
    counter_ttid = request.session.pop('counter_ttid', None)
    swap_id = request.session.pop('swap_id', None)

    if not counter_ttid or not swap_id:
        return HttpResponseBadRequest("Required data is missing. - swapfinal_view")
    
    # GATE: Verify Swap Offer is still open - prevents back button abuse
    error_msg = 'The requested Swap Offer is no longer available.  Please review the available Swaps on the Sub Swap page and try again.'
    swap_offer = get_open_subswap_or_error(swap_id, error_msg, request)
    if isinstance(swap_offer, HttpResponse):
        return swap_offer
    
    # GATE: Verify Counter Offer is still open
    counter_offer = SubSwap.objects.filter(SwapID=swap_id, SubType='Counter', nStatus='Open')
    if not counter_offer.exists():
        return render(request, 'GRPR/error_msg.html', {'error_msg': 'The Counter Offer is no longer available.  Please review the available Swaps on the Sub Swap page and try again.'})

    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    first_name = request.user.first_name
    last_name = request.user.last_name

    # Fetch the offer player instance
    offer_player = get_object_or_404(Players, user_id=user_id)
    player_id = offer_player.id
    offer_mobile = offer_player.Mobile
    offer_name = f"{offer_player.FirstName} {offer_player.LastName}"

    # Fetch the counter offer details
    counter_offer = SubSwap.objects.filter(
        TeeTimeIndID=counter_ttid,
        SwapID=swap_id,
        nType='Swap',
        SubType='Counter',
        nStatus='Open'
    ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID', 'PID').first()

    counter_user_id = counter_offer.PID.id
    counter_gDate = counter_offer.TeeTimeIndID.gDate
    counter_Course = counter_offer.TeeTimeIndID.CourseID.courseName
    counter_TimeSlot = counter_offer.TeeTimeIndID.CourseID.courseTimeSlot
    counter_name = f"{counter_offer.PID.FirstName} {counter_offer.PID.LastName}"
    counter_mobile = counter_offer.PID.Mobile

    # GATE: Check if the logged-in user is still available to play the Swap gDate on offer
    offer_player_availability_error = check_player_availability(player_id, counter_gDate, request)
    if offer_player_availability_error:
        return offer_player_availability_error

    # Fetch the original offer details
    original_offer = SubSwap.objects.filter(
        SwapID=swap_id,
        nType='Swap',
        SubType='Offer',
        nStatus='Open'
    ).select_related('TeeTimeIndID', 'TeeTimeIndID__CourseID').first()

    offer_ttid = original_offer.TeeTimeIndID.id
    offer_gDate = original_offer.TeeTimeIndID.gDate
    offer_Course = original_offer.TeeTimeIndID.CourseID.courseName
    offer_TimeSlot = original_offer.TeeTimeIndID.CourseID.courseTimeSlot

    # GATE: Check if the Counter Player is still available to play the Swap gDate on offer
    counter_player_availability_error = check_player_availability(counter_user_id, offer_gDate, request)
    if counter_player_availability_error:
        return counter_player_availability_error

    # Update SubSwap table for the Counter Offer
    SubSwap.objects.filter(
        SwapID=swap_id,
        nStatus='Open',
        nType='Swap',
        SubType='Counter',
        TeeTimeIndID=counter_ttid
    ).update(SubStatus='Accepted', nStatus='Closed')

    # Update SubSwap table for all other open rows associated with the swap_id
    SubSwap.objects.filter(
        SwapID=swap_id,
        nStatus='Open'
    ).update(nStatus='Closed')

    # This bit closes any row in the SubSwap table related to the counter_tt_id that just changed ownership
    # For example, if the counter player currently had a Sub or Swap request live for this counter date, those would now be closed
    SubSwap.objects.filter(
        TeeTimeIndID=counter_ttid,
        nStatus='Open',
    ).update(nStatus='Closed', SubStatus='Owner Change')

    # Does the same for the offer_tt_id
    SubSwap.objects.filter(
        TeeTimeIndID=offer_ttid,
        nStatus='Open',
    ).update(nStatus='Closed', SubStatus='Owner Change')

    # Counter Player availability change - closes all sub swaps available to counter player for the offer date they just acquired
    counter_player_same_date = SubSwap.objects.select_related('TeeTimeIndID').filter(
            Q(TeeTimeIndID__gDate=offer_gDate) &
            Q(PID=counter_user_id) &
            Q(nStatus='Open')
    )

    for offers in counter_player_same_date:
        ss_id = offers.id
        ss_swap_id = offers.SwapID

        SubSwap.objects.filter(
            id=ss_id,
            ).update(nStatus='Closed', SubStatus='Superseded')
        
        # Insert row into Log for offer player
        Log.objects.create(
            SentDate=timezone.now(),
            Type="SubSwap Superseded",
            MessageID='none',
            RequestDate=offer_gDate,
            ReceiveID=counter_user_id,
            OfferID=player_id,
            RefID=ss_swap_id,
            Msg=f"{counter_name} has accepted a counter offer for this date.  SubSwap request has been superseded.",
        )

    # Offer Player availability change - closes all sub swaps available to offer player for the counter date they just acquired
    offer_player_same_date = SubSwap.objects.select_related('TeeTimeIndID').filter(
            Q(TeeTimeIndID__gDate=counter_gDate) &
            Q(PID=player_id) &
            Q(nStatus='Open')
    )

    for offers in offer_player_same_date:
        ss_id = offers.id
        ss_swap_id = offers.SwapID

        SubSwap.objects.filter(
            id=ss_id,
            ).update(nStatus='Closed', SubStatus='Superseded')
        
        # Insert row into Log for offer player
        Log.objects.create(
            SentDate=timezone.now(),
            Type="SubSwap Superseded",
            MessageID='none',
            RequestDate=offer_gDate,
            ReceiveID=counter_user_id,
            OfferID=player_id,
            RefID=ss_swap_id,
            Msg=f"{offer_name} has accepted a counter offer for this date.  SubSwap request has been superseded.",
        )

    # Update TeeTimesInd table
    TeeTimesInd.objects.filter(id=offer_ttid).update(PID=counter_user_id)
    TeeTimesInd.objects.filter(id=counter_ttid).update(PID=player_id)

    # create the msgs that will be sent via text to the players + be entered into the Log table
    offer_msg = f"Tee Time Swap Accepted. {offer_name} is now playing {counter_gDate} at {counter_Course} at {counter_TimeSlot}am. {counter_name} will play {offer_gDate} at {offer_Course} at {offer_TimeSlot}am."
    counter_msg = f"Tee Time Swap Accepted. {counter_name} is now playing {offer_gDate} at {offer_Course} at {offer_TimeSlot}am. {offer_name} will play {counter_gDate} at {counter_Course} at {counter_TimeSlot}am."
    
    # Send texts via Twilio
    if settings.TWILIO_ENABLED:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

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
            ReceiveID=player_id,
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
            OfferID=player_id,
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
            ReceiveID=player_id,
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
            OfferID=player_id,
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
        'first_name': first_name,
        'last_name': last_name,
    }
    return render(request, 'GRPR/swapfinal.html', context)


@login_required
def store_swapcancelconfirm_data_view(request):
    if request.method == "GET":
        swap_id = request.GET.get('swap_id')

        request.session['swap_id'] = swap_id

        return redirect('swapcancelconfirm_view')
    else:
        return HttpResponseBadRequest("Invalid request.")
    

@login_required
def swapcancelconfirm_view(request):
    swap_id = request.session.pop('swap_id', None)

    if not swap_id:
        return HttpResponseBadRequest("Required data is missing. - swapcancelconfirm_view")
    
    # Fetch the tt_id assoc with the swap_id
    subswap_row = get_object_or_404(SubSwap, id=swap_id)
    tt_id = subswap_row.TeeTimeIndID_id
    
    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    first_name = request.user.first_name
    last_name = request.user.last_name

    player = get_object_or_404(Players, user_id=user_id)
    player_id = player.id

    # Fetch the TeeTimeInd instance and other players using the utility function (in utils.py)
    tee_time_details = get_tee_time_details(tt_id, player_id)
    gDate = tee_time_details['gDate']
    course_name = tee_time_details['course_name']
    course_time_slot = tee_time_details['course_time_slot']

    context = {
        'gDate': gDate,
        'courseName': course_name,
        'courseTimeSlot': course_time_slot,
        'swap_id': swap_id,
        'first_name': first_name,
        'last_name': last_name,
    }
    return render(request, 'GRPR/swapcancelconfirm.html', context)


@login_required
def store_swapcancel_data_view(request):
    if request.method == "GET":
        swap_id = request.GET.get('swap_id')

        # Store necessary data in the session
        request.session['swap_id'] = swap_id

        return redirect('swapcancel_view')
    else:
        return HttpResponseBadRequest("Invalid request.")


@login_required
def swapcancel_view(request):
    # Retrieve data from the session
    swap_id = request.session.pop('swap_id', None)

    if not swap_id:
        return HttpResponseBadRequest("Required data is missing. - swapcancel_view")
    
    # GATE: Verify Swap is still open - prevents back button abuse
    error_msg = 'The requested Swap is no longer available.  Please review the available Swaps on the Sub Swap page and try again.'
    swap_offer = get_open_subswap_or_error(swap_id, error_msg, request)
    if isinstance(swap_offer, HttpResponse):
        return swap_offer
    

    # Fetch the tt_id assoc with the swap_id
    subswap_row = get_object_or_404(SubSwap, id=swap_id)
    tt_id = subswap_row.TeeTimeIndID_id
    
    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    first_name = request.user.first_name
    last_name = request.user.last_name

    player = get_object_or_404(Players, user_id=user_id)
    player_id = player.id

    # Fetch the TeeTimeInd instance and other players using the utility function (in utils.py)
    tee_time_details = get_tee_time_details(tt_id, player_id)
    gDate = tee_time_details['gDate']
    gDate_display = tee_time_details['gDate_display']
    course_name = tee_time_details['course_name']
    course_time_slot = tee_time_details['course_time_slot']
    other_players = tee_time_details['other_players']

    # Update SubSwap table
    SubSwap.objects.filter(SwapID=swap_id, nStatus='Open').update(nStatus='Closed', SubStatus='Cancelled')

    # Insert a row into Log table
    Log.objects.create(
        SentDate=timezone.now(),
        Type='Swap Cancelled',
        MessageID='No text sent',
        RequestDate=gDate,
        OfferID=player_id,
        RefID=swap_id,
        Msg=f'Swap Cancelled by {first_name} {last_name}'
    )

    context = {
        'gDate': gDate,
        'gDate_display': gDate_display,
        'course_name': course_name,
        'course_time_slot': course_time_slot,
        'first_name': first_name,
        'last_name': last_name,
    }
    return render(request, 'GRPR/swapcancel.html', context)


@login_required
def store_countercancelconfirm_data_view(request):
    if request.method == "GET":
        subswap_table_id = request.GET.get('subswap_table_id')

        request.session['subswap_table_id'] = subswap_table_id

        return redirect('countercancelconfirm_view')
    else:
        return HttpResponseBadRequest("Invalid request.")
    

@login_required
def countercancelconfirm_view(request):
    subswap_table_id = request.session.pop('subswap_table_id', None)

    if not subswap_table_id:
        return HttpResponseBadRequest("Required data is missing. - countercancelconfirm_view")
    
    # Fetch the tt_id assoc with the swap_id
    subswap_row = get_object_or_404(SubSwap, id=subswap_table_id)
    tt_id = subswap_row.TeeTimeIndID_id
    
    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    first_name = request.user.first_name
    last_name = request.user.last_name

    player = get_object_or_404(Players, user_id=user_id)
    player_id = player.id

    # Fetch the TeeTimeInd instance and other players using the utility function (in utils.py)
    tee_time_details = get_tee_time_details(tt_id, player_id)
    gDate = tee_time_details['gDate']
    course_name = tee_time_details['course_name']
    course_time_slot = tee_time_details['course_time_slot']

    context = {
        'gDate': gDate,
        'courseName': course_name,
        'courseTimeSlot': course_time_slot,
        'subswap_table_id': subswap_table_id,
        'first_name': first_name,
        'last_name': last_name,
    }
    return render(request, 'GRPR/countercancelconfirm.html', context)


@login_required
def store_countercancel_data_view(request):
    if request.method == "GET":
        subswap_table_id = request.GET.get('subswap_table_id')

        # Store necessary data in the session
        request.session['subswap_table_id'] = subswap_table_id

        return redirect('countercancel_view')
    else:
        return HttpResponseBadRequest("Invalid request.")


@login_required
def countercancel_view(request):
    # Retrieve data from the session
    subswap_table_id = request.session.pop('subswap_table_id', None)

    if not subswap_table_id:
        return HttpResponseBadRequest("Required data is missing. - countercancel_view")
    
    # GATE: Verify Counter is still open - prevents back button abuse
    error_msg = 'The requested Counter is no longer available. Please review the Sub Swap page and try again.'
    counter_offer = SubSwap.objects.filter(id=subswap_table_id, nStatus='Open', SubType='Counter')
    
    if not counter_offer.exists():
        return render(request, 'GRPR/error_msg.html', {'error_msg': error_msg})


    # Fetch the tt_id assoc with the swap_id
    subswap_row = get_object_or_404(SubSwap, id=subswap_table_id)
    tt_id = subswap_row.TeeTimeIndID_id
    swap_id = subswap_row.SwapID
    
    # Fetch the Player ID associated with the logged-in user
    user_id = request.user.id
    first_name = request.user.first_name
    last_name = request.user.last_name

    player = get_object_or_404(Players, user_id=user_id)
    player_id = player.id

    # Fetch the TeeTimeInd instance and other players using the utility function (in utils.py)
    tee_time_details = get_tee_time_details(tt_id, player_id)
    gDate = tee_time_details['gDate']
    gDate_display = tee_time_details['gDate_display']
    course_name = tee_time_details['course_name']
    course_time_slot = tee_time_details['course_time_slot']

    # Update SubSwap table
    SubSwap.objects.filter(id=subswap_table_id, nStatus='Open', SubType='Counter').update(nStatus='Closed', SubStatus='Cancelled')

    # Ack.  Thi is more complicated.  Since a user can have multiple counters out there, cancelling one of them but having the others still alive
    # could lead to a situation where the original offer is open and can be countered again.  Possibly with the same counter dates currently live
    # Update SubSwap table original received row and remove the 'Kountered' status so it can be countered again
    # SubSwap.objects.filter(id=swap_id, nStatus='Open', SubType='Kountered').update(SubStatus='Received')
    # print('Kounter Cancel:  Original Received swap offer has been changed from Kountered back to Received so it can be countered again')

    # Insert a row into Log table
    Log.objects.create(
        SentDate=timezone.now(),
        Type='Counter Cancelled',
        MessageID='No text sent',
        RequestDate=gDate,
        OfferID=player_id,
        RefID=swap_id,
        Msg=f'Counter Cancelled by {first_name} {last_name}'
    )

    context = {
        'gDate': gDate,
        'gDate_display': gDate_display,
        'course_name': course_name,
        'course_time_slot': course_time_slot,
        'first_name': first_name,
        'last_name': last_name,
    }
    return render(request, 'GRPR/countercancel.html', context)


@login_required
def swapnoneavail_view(request):
    # Retrieve data from the session
    first_name = request.session.get('first_name')
    last_name = request.session.get('last_name')
    swap_tt_id = request.session.get('swap_tt_id')

    context = {
        
        'first_name': first_name,
        'last_name': last_name,
        'tt_id': swap_tt_id,
    }
    return render(request, 'GRPR/swapnoneavail.html', context)


@login_required
def subswap_dashboard_view(request):

    # Total number of sub swaps that result in a tee time trade
    accepted_count = SubSwap.objects.filter(SubStatus='Accepted').count()

    # Open Subs & Swaps Table
    open_subswap_data = SubSwap.objects.filter(
        nStatus='Open',
        SubType='Offer',
    ).select_related(
        'TeeTimeIndID', 'TeeTimeIndID__CourseID', 'PID'
    ).annotate(
        gDate=F('TeeTimeIndID__gDate'),
        course_time_slot=F('TeeTimeIndID__CourseID__courseTimeSlot'),
        FirstName=F('PID__FirstName'),
        LastName=F('PID__LastName')
    ).values(
        'id',
        'SwapID',
        'RequestDate',
        'TeeTimeIndID_id',
        'FirstName',
        'LastName',
        'gDate',
        'course_time_slot',
        'nStatus',
        'SubStatus',
        'nType',
        'SubType'
    ).order_by('-RequestDate')
    
    # Closed Swaps Table
    closed_subswap_data = SubSwap.objects.filter(
        nStatus='Closed',
        SubType='Offer'
    ).select_related(
        'TeeTimeIndID', 'TeeTimeIndID__CourseID', 'PID'
    ).annotate(
        gDate=F('TeeTimeIndID__gDate'),
        course_time_slot=F('TeeTimeIndID__CourseID__courseTimeSlot'),
        FirstName=F('PID__FirstName'),
        LastName=F('PID__LastName')
    ).values(
        'id',
        'SwapID',
        'RequestDate',
        'TeeTimeIndID_id',
        'FirstName',
        'LastName',
        'gDate',
        'course_time_slot',
        'nStatus',
        'SubStatus',
        'nType',
        'SubType'
    ).order_by('-RequestDate')

    context = {
        'accepted_count': accepted_count,
        'open_subswap_data': open_subswap_data,
        'closed_subswap_data': closed_subswap_data,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name
    }

    # Render the template
    return render(request, 'GRPR/subswap_dashboard.html', context)


@login_required
def subswap_details_view(request):
    swap_id = request.GET.get('swap_id')

    # Get the status and type from the Offer row so we can print out the right buttons on the page.  This is not efficient
    subswap_specs = SubSwap.objects.filter(SwapID=swap_id, SubType='Offer').values('nStatus', 'nType').first()
    Status = subswap_specs['nStatus']
    Type = subswap_specs['nType']

    # Query for the specific SwapID
    swap_details = SubSwap.objects.filter(
        SwapID=swap_id
    ).select_related(
        'TeeTimeIndID', 'TeeTimeIndID__CourseID', 'PID'
    ).annotate(
        gDate=F('TeeTimeIndID__gDate'),
        course_time_slot=F('TeeTimeIndID__CourseID__courseTimeSlot'),
        FirstName=F('PID__FirstName'),
        LastName=F('PID__LastName')
    ).values(
        'id',
        'SwapID',
        'RequestDate',
        'TeeTimeIndID_id',
        'FirstName',
        'LastName',
        'gDate',
        'course_time_slot',
        'nStatus',
        'SubStatus',
        'nType',
        'SubType'
    ).order_by('RequestDate')
    
    # Query for the Log Messages table (without ReceiveID and related fields)
    log_messages = Log.objects.filter(
        RefID=swap_id
    ).values(
        'id',
        'RefID',
        'OfferID',
        'SentDate',
        'Type',
        'MessageID',
        'ReceiveID',
        'RequestDate',
        'Msg'
    ).order_by('SentDate')

    # if the sub Swap has been completed, this will allow us to print out a msg of the details
    accepted_offer = SubSwap.objects.filter(SwapID=swap_id).filter(SubStatus='Accepted').first()
    if accepted_offer:
        teetime_swap_details = Log.objects.filter(RefID=swap_id).first()
        acceptance_msg = teetime_swap_details.Msg
    else:
        acceptance_msg = None
    

    context = {
        'swap_details': swap_details,
        'log_messages': log_messages,
        'acceptance_msg': acceptance_msg,
        'swap_id': swap_id,
        'status': Status,
        'type': Type,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name
    }

    # Render the template
    return render(request, 'GRPR/subswap_details.html', context)


@login_required
def subswap_admin_change_view(request):
    # Query for tee times (future dates)
    tee_times = (
        TeeTimesInd.objects
        .filter(gDate__gt=date.today())
        .select_related('CourseID', 'PID')
        .order_by('gDate', 'CourseID__courseTimeSlot', 'PID__LastName')
        .values(
            'id',
            'gDate',
            'CourseID__courseTimeSlot',
            'PID__FirstName',
            'PID__LastName',
            'PID'
        )
    )

    # Query for all players
    players = (
        Players.objects
        .all()
        .order_by('LastName', 'FirstName')
        .values('id', 'FirstName', 'LastName')
    )

    context = {
        'tee_times': tee_times,
        'players': players,
        'first_name': request.user.first_name,  
        'last_name': request.user.last_name,
    }
    return render(request, 'GRPR/subswap_admin_change.html', context)



from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt


@login_required
def subswap_admin_update_view(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    tt_id = request.POST.get('tt_id')
    offer_player_id = request.POST.get('offer_player_id')
    accept_player_id = request.POST.get('accept_player_id')

    if not tt_id or not offer_player_id or not accept_player_id:
        return render(request, 'GRPR/subswap_admin_change.html', {
            'error_message': "Missing required data for sub execution."
        })

    # Get the tee time and playing date
    try:
        teetime = TeeTimesInd.objects.get(id=tt_id)
        playing_date = teetime.gDate
    except TeeTimesInd.DoesNotExist:
        return render(request, 'GRPR/subswap_admin_change.html', {
            'error_message': "Tee time not found."
        })

    logged_in_user_id = request.user.id
    accept_player = Players.objects.get(id=accept_player_id)

    # Check if accept_player is already playing that date
    already_playing = TeeTimesInd.objects.filter(PID=accept_player_id, gDate=playing_date).exists()
    if already_playing:
        return render(request, 'GRPR/subswap_admin_change.html', {
            'error_message': f"{accept_player.FirstName} {accept_player.LastName} is already playing {playing_date}, Sub NOT executed."
        })

    # Update the tee time to assign the new player
    TeeTimesInd.objects.filter(id=tt_id).update(PID=accept_player_id)

    logged_in_user = Players.objects.get(user_id=logged_in_user_id)
    offer_player = Players.objects.get(id=offer_player_id)
    exch_msg = f"{accept_player.FirstName} {accept_player.LastName} is now playing {playing_date} for {offer_player.FirstName} {offer_player.LastName}. Sub executed via Admin function"

    # Insert SubSwap Offer row
    sub_offer = SubSwap.objects.create(
        RequestDate=timezone.now(),
        PID_id=offer_player_id,
        TeeTimeIndID_id=tt_id,
        nType="Sub",
        SubType="Offer",
        nStatus="Closed",
        Msg=exch_msg,
    )
    swap_id = sub_offer.id
    SubSwap.objects.filter(id=swap_id).update(SwapID=swap_id)

    # Insert SubSwap Received row
    SubSwap.objects.create(
        RequestDate=timezone.now(),
        PID_id=accept_player_id,
        TeeTimeIndID_id=tt_id,
        nType="Sub",
        SubType="Received",
        nStatus="Closed",
        SubStatus="Received",
        SwapID=swap_id,
        Msg=exch_msg,
    )

    # Log entries
    from GRPR.models import Log
    now_time = timezone.now()
    Log.objects.create(
        SentDate=now_time,
        Type='Sub Given',
        RequestDate=playing_date,
        OfferID=offer_player_id,
        ReceiveID=accept_player_id,
        RefID=swap_id,
        Msg=exch_msg,
    )
    Log.objects.create(
        SentDate=now_time,
        Type='Sub Received',
        RequestDate=playing_date,
        OfferID=accept_player_id,
        ReceiveID=offer_player_id,
        RefID=swap_id,
        Msg=exch_msg,
    )

    # Close any open SubSwaps for this tee time
    SubSwap.objects.filter(TeeTimeIndID_id=tt_id, nStatus='Open').update(nStatus='Closed')
    # Close any open SubSwaps for accept_player on this date
    SubSwap.objects.filter(
        nStatus='Open',
        PID=accept_player_id,
        TeeTimeIndID__gDate=playing_date
    ).update(nStatus='Closed')

    # Re-render the admin page with a success message
    # (You may want to re-query tee_times and players here)
    tee_times = (
        TeeTimesInd.objects
        .filter(gDate__gt=date.today())
        .select_related('CourseID', 'PID')
        .order_by('gDate', 'CourseID__courseTimeSlot', 'PID__LastName')
        .values(
            'id',
            'gDate',
            'CourseID__courseTimeSlot',
            'PID__FirstName',
            'PID__LastName',
            'PID'
        )
    )
    players = (
        Players.objects
        .all()
        .order_by('LastName', 'FirstName')
        .values('id', 'FirstName', 'LastName')
    )
    return render(request, 'GRPR/subswap_admin_change.html', {
        'success_message': exch_msg,
        'tee_times': tee_times,
        'players': players,
    })


@login_required
def statistics_view(request):
    # for course distro chart:
    courses = Courses.objects.all().order_by('id')
    players = Players.objects.filter(Member=1).order_by('LastName')

    course_names= []
    for course in courses:
        name_slot = f"{course.courseName} {course.courseTimeSlot}am"
        course_names.append(name_slot)

    korse_chart_data = {}

    for player_a in players:
        korse_per = {}
        for korse in courses:
            korse_count = TeeTimesInd.objects.filter(PID=player_a.id, CourseID=korse.id, gDate__gt='2025-01-01').count()
            korse_per[korse.id] = korse_count
        total_count = sum(korse_per.values())
        korse_per['total'] = total_count
        korse_chart_data[player_a.id] = korse_per

    # for date distro chart:
    dates = TeeTimesInd.objects.filter(gDate__gt='2025-01-01').values('gDate').distinct().order_by('gDate')

    date_names = [date['gDate'].strftime('%Y-%m-%d') for date in dates]

    date_chart_data = {}
    
    for player_b in players:
        date_per = {}
        for date in dates:
            date_count = TeeTimesInd.objects.filter(PID=player_b.id, gDate=date['gDate']).count()
            # Replace zero values with blanks
            date_per[date['gDate'].strftime('%Y-%m-%d')] = date_count if date_count != 0 else ''
        total_count = sum(value for value in date_per.values() if value != '')
        date_per['total'] = total_count
        date_chart_data[player_b.id] = date_per

    # For the player heatmap chart:
    chart_data = {}
    max_count = 0

    for player_a in players:
        distinct_counts = {}
        for p_id in players:
            distinct_counts[p_id.id] = 0
        ttis = TeeTimesInd.objects.filter(PID=player_a.id, gDate__gt='2025-01-01')
        for tt in ttis:
            tDate = tt.gDate
            cID = tt.CourseID
            partners = TeeTimesInd.objects.filter(gDate=tDate, CourseID=cID).exclude(PID=player_a.id)
            for p in partners:
                pID = p.PID_id
                if pID in distinct_counts:
                    distinct_counts[pID] += 1
                # else:
                #     distinct_counts[pID] = 1
        chart_data[player_a.id] = distinct_counts

    # Find the maximum count for normalization
    max_count = max(max(distinct_counts.values()) for distinct_counts in chart_data.values())

    # Normalize the values
    normalized_chart_data = {}
    for player_a_id, counts in chart_data.items():
        normalized_counts = {player_id: count / max_count for player_id, count in counts.items()}
        normalized_chart_data[player_a_id] = normalized_counts

    # Zip the players, chart_data, and normalized_chart_data for easy iteration in the template
    zipped_data = [
        (player_a, [(player_b, chart_data[player_a.id].get(player_b.id, None), normalized_chart_data[player_a.id].get(player_b.id, None)) for player_b in players])
        for player_a in players
    ]

    # for the User Activity feed:
    actions = []

    statistics_query = Log.objects.filter(
    Q(Type='Swap Offer Accept') |
    Q(Type='Swap Counter Accept') |
    Q(Type='Sub Received') |
    Q(Type='Sub Given') |
    Q(Type='Sub Offer') |
    Q(Type='Swap Offer') |
    Q(Type='Sub Cancelled') |
    Q(Type='Swap Cancelled') |
    Q(Type='Swap Counter')
    ).order_by('-SentDate')[:25]

    for row in statistics_query:

        actions.append({
            "lDate": row.SentDate,  
            'type': row.Type,
            "rDate": row.RequestDate.strftime('%B %d, %Y'),
            "ref_id": row.RefID,
            "msg": row.Msg,
            'offer_id': row.OfferID,
        })
    
    # for Requested Off dates:
    xdates_query = Xdates.objects.select_related('PID').order_by('PID__LastName', 'PID__FirstName')
    xdates_data = {}
    for xdate in xdates_query:
        player_name = f"{xdate.PID.FirstName} {xdate.PID.LastName}"
        if player_name not in xdates_data:
            xdates_data[player_name] = []
        xdates_data[player_name].append(xdate.xDate.strftime('%Y-%m-%d'))

    # Convert the xdates_data dictionary to a list of dictionaries for easier iteration in the template
    xdates_list = [{'player': player, 'requested_off': ', '.join(dates)} for player, dates in xdates_data.items()]


    context = {
        'players': players,
        'korse_chart_data': korse_chart_data,
        'course_names': course_names,
        'date_names': date_names,
        'date_chart_data': date_chart_data,
        'zipped_data': zipped_data,
        "actions": actions,
        'xdates_list': xdates_list,  
        "first_name": request.user.first_name,  # Add the first name of the logged-in user
        "last_name": request.user.last_name, # Add the last name of the logged-in user
    }

    return render(request, 'GRPR/statistics.html', context)


@login_required
def players_view(request):
    # Get today's date
    current_datetime = datetime.now()

    # Query all players
    players = Players.objects.filter(Member=1).order_by('LastName', 'FirstName')

    # Prepare the data for the table
    players_data = []
    for player in players:
        rounds_played = TeeTimesInd.objects.filter(PID=player.id, gDate__lt=current_datetime).count()
        rounds_scheduled = TeeTimesInd.objects.filter(PID=player.id, gDate__gte=current_datetime).count()
        scores = list(
            ScorecardMeta.objects
            .filter(PID_id=player.id)
            .values_list('PlayDate', 'RawTotal')
            .order_by('-PlayDate')
        )
        players_data.append({
            'first_name': player.FirstName,
            'last_name': player.LastName,
            'mobile': player.Mobile,
            'email': player.Email,
            'index': player.Index,
            'rounds_played': rounds_played,
            'rounds_scheduled': rounds_scheduled,
            'scores': scores,
        })

    # Pass data to the template
    context = {
        'players_data': players_data,
        'first_name': request.user.first_name,  # Add the first name of the logged-in user
        'last_name': request.user.last_name,  # Add the last name of the logged-in user
    }
    return render(request, 'GRPR/players.html', context)


@login_required
def profile_view(request):
    player_first_name = request.GET.get('first_name')
    player_last_name = request.GET.get('last_name')
    player = Players.objects.get(FirstName=player_first_name, LastName=player_last_name)
    user = request.user
    first_name = user.first_name
    last_name = user.last_name
    username = user.username
    logged_in_user_id = user.id
    

    context = {
        'player_first_name': player_first_name,
        'player_last_name': player_last_name,
        'player_username': player.Email,
        'email_address': player.Email,
        'mobile': player.Mobile,
        'index': player.Index,
        'player_id': player.id,
        'first_name': first_name,
        'last_name': last_name,
        'username': username,
        'logged_in_user_id': logged_in_user_id,
    }
    return render(request, 'GRPR/profile.html', context)


## Allows Player data to be updated via the profile page.  only HDCP so far
@login_required
def player_update_view(request):
    if request.method == 'POST':
        # Retrieve form data
        player_id = request.POST.get('player_id')
        player_first_name = request.POST.get('player_first_name')
        player_last_name = request.POST.get('player_last_name')
        index = request.POST.get('index')
        new_index = request.POST.get('new_index')
        logged_in_user_id = request.user.id
        first_name = request.user.first_name
        last_name = request.user.last_name
        username = request.user.username

        # Update the Players table
        Players.objects.filter(id=player_id).update(Index=new_index)

        player = Players.objects.get(id=player_id)

        # Insert a new row into the Log table
        log_message = f"{first_name} {last_name} updated the Index for {player_first_name} {player_last_name} from {index} to {new_index}"
        Log.objects.create(
            SentDate=now(),
            Type='Player Update',
            OfferID=logged_in_user_id,
            ReceiveID=player_id,
            Msg=log_message
        )

        # Render profile.html with a success message
        success_message = f"Index for {player_first_name} {player_last_name} successfully updated from {index} to {new_index}."
        return render(request, 'GRPR/profile.html', {
            'player_first_name': player_first_name,
            'player_last_name': player_last_name,
            'email_address': player.Email,
            'mobile': player.Mobile,
            'index': new_index,
            'success_message': success_message,
            'player_id': player.id,
            'first_name': first_name,
            'last_name': last_name,
            'username': username,
            'logged_in_user_id': logged_in_user_id,
        })

    return redirect('profile_view')


# ------------------------------------------------------------------ #
#  This section is for the Best Rounds page                          #
#  Helpers: leaders + top-10 lists                                   #
# ------------------------------------------------------------------ #

STAT_LABELS = {
    # "gross"        : "Best Gross",
    "net"          : "Best Net Score",
    "skins"        : "Most Skins (Season)",
    "gross_member" : "Best Gross Score (Member)",
    "attendance"   : "Best Attendance",
    "skins_one"    : "Most Skins (1 Round)",
    "forty_season" : "Most Forty Holes (Season)",
    "forty_one"    : "Most Forty Holes (1 Round)",
    "trader"       : "Best Trader",
    "quick_draw"   : "Quickest Draw",
    "friends"      : "Most Frequent Partners",
}

YEAR_START = date(2025, 1, 1)
TODAY       = timezone.now().date() 


# def _top10_gross():
#     qs = (
#         ScorecardMeta.objects
#         .filter(PlayDate__gte=YEAR_START)
#         .values("PID_id", "PID__FirstName", "PID__LastName")
#         .annotate(value=Min("RawTotal"))
#         .order_by("value")[:10]
#     )
#     return [
#         {"name": f"{r['PID__FirstName']} {r['PID__LastName']}",
#          "value": r["value"]}
#         for r in qs
#     ]

# ----------  gross_member  (best score + date) -----------------
def _top10_gross_member():
    rows = (
        ScorecardMeta.objects
        .filter(
            PlayDate__gte=YEAR_START,
            PID__Member=1,
            RawTotal__isnull=False,
        )
        .annotate(hole_count=Count("scorecard"))
        .filter(hole_count__gte=18)
        .order_by("RawTotal", "-PlayDate")
        .values("PID__FirstName", "PID__LastName", "PlayDate", "RawTotal")[:10]
    )
    return [
        {"name": f"{r['PID__FirstName']} {r['PID__LastName']}",
         "value": r["RawTotal"],
         "date":  r["PlayDate"]}
        for r in rows
    ]


# ----------  net  (best net score + date) ----------------------
def _top10_net():
    rows = (
        ScorecardMeta.objects
        .filter(
            PlayDate__gte=YEAR_START,
            NetTotal__isnull=False,
        )
        .annotate(hole_count=Count("scorecard"))
        .filter(hole_count__gte=18)
        .order_by("NetTotal", "-PlayDate")
        .values("PID__FirstName", "PID__LastName", "PlayDate", "NetTotal")[:10]
    )
    return [
        {"name": f"{r['PID__FirstName']} {r['PID__LastName']}",
         "value": r["NetTotal"],
         "date":  r["PlayDate"]}
        for r in rows
    ]


# ----------  skins_one  (max skins in one round + date) --------
def _top10_skins_one():
    from collections import defaultdict

    per_round = (
        Skins.objects
        .filter(SkinDate__gte=YEAR_START)
        .values("PlayerID_id", "PlayerID__FirstName", "PlayerID__LastName",
                "GameID__PlayDate")
        .annotate(cnt=Count("id"))
    )

    best = defaultdict(lambda: {"value": 0})
    for r in per_round:
        pid, c = r["PlayerID_id"], r["cnt"]
        if c > best[pid]["value"]:
            best[pid] = {
                "name": f"{r['PlayerID__FirstName']} {r['PlayerID__LastName']}",
                "value": c,
                "date":  r["GameID__PlayDate"],
            }

    top = sorted(best.values(), key=lambda x: -x["value"])[:10]
    return top


# ----------  forty_one  (max forty rows in one round + date) ---
def _top10_forty_one():
    import itertools
    from collections import defaultdict

    per_round = (
        Forty.objects
        .filter(GameID__PlayDate__gte=YEAR_START)
        .values("PID_id", "PID__FirstName", "PID__LastName", "GameID__PlayDate")
        .annotate(cnt=Count("id"))
    )

    best = defaultdict(lambda: {"value": 0})
    for r in per_round:
        pid, c = r["PID_id"], r["cnt"]
        if c > best[pid]["value"]:
            best[pid] = {
                "name": f"{r['PID__FirstName']} {r['PID__LastName']}",
                "value": c,
                "date":  r["GameID__PlayDate"],
            }

    return sorted(best.values(), key=lambda x: -x["value"])[:10]

def _top10_skins():
    qs = (
        Skins.objects
        .filter(SkinDate__gte=YEAR_START)
        .values("PlayerID_id", "PlayerID__FirstName", "PlayerID__LastName")
        .annotate(value=Count("id"))
        .order_by("-value")[:10]
    )
    return [{"name": f"{r['PlayerID__FirstName']} {r['PlayerID__LastName']}", "value": r["value"]} for r in qs]


def _top10_attendance():
    qs = (
        TeeTimesInd.objects
        .filter(gDate__range=(YEAR_START, TODAY))
        .values("PID_id", "PID__FirstName", "PID__LastName")
        .annotate(value=Count("id"))
        .order_by("-value")[:10]
    )
    return [{"name": f"{r['PID__FirstName']} {r['PID__LastName']}", "value": r["value"]} for r in qs]

def _top10_forty_season():
    """Most Forty rows per player for the whole 2025 season."""
    qs = (
        Forty.objects
        .filter(GameID__PlayDate__gte=YEAR_START)            # join through FK
        .values("PID_id", "PID__FirstName", "PID__LastName")
        .annotate(value=Count("id"))
        .order_by("-value")[:10]
    )
    return [
        {"name": f"{r['PID__FirstName']} {r['PID__LastName']}",
         "value": r["value"]}
        for r in qs
    ]

def _top10_trader():
    """
    Counts BOTH players involved in every swap that ended
    Closed & Accepted between 1 Jan 2025 and today.
    """
    # 1) SwapIDs that actually closed/accepted in the window
    swaps = (
        SubSwap.objects
        .filter(nStatus="Closed",
                SubStatus="Accepted",
                RequestDate__range=(YEAR_START, TODAY))
        .values_list("SwapID", flat=True)
    )

    # 2) rows that earn credit
    offers   = SubSwap.objects.filter(SwapID__in=swaps, SubType="Offer")\
                              .values_list("PID_id", flat=True)
    counters = SubSwap.objects.filter(SwapID__in=swaps,
                                      SubType="Counter",
                                      SubStatus="Accepted")\
                              .values_list("PID_id", flat=True)

    freq     = Counter(chain(offers, counters))
    ranking  = freq.most_common(10)

    return [
        {
            "name":  f"{Players.objects.get(pk=pid).FirstName} "
                     f"{Players.objects.get(pk=pid).LastName}",
            "value": total,
        }
        for pid, total in ranking
    ]


def _top10_quick_draw():
    qs = (
        SubSwap.objects
        .filter(nStatus="Closed", SubStatus="Accepted", nType="Sub", RequestDate__gte=YEAR_START)
        .values("PID_id", "PID__FirstName", "PID__LastName")
        .annotate(value=Count("id"))
        .order_by("-value")[:10]
    )
    return [{"name": f"{r['PID__FirstName']} {r['PID__LastName']}", "value": r["value"]} for r in qs]

def _top10_friends():
    """
    Top 10 most-frequent playing partners in 2025 (same date & slot).
    """
    sql = """
        SELECT  LEAST(t1."PID_id", t2."PID_id")  AS p1,
                GREATEST(t1."PID_id", t2."PID_id") AS p2,
                COUNT(*)                          AS cnt
        FROM    "TeeTimesInd" t1
        JOIN    "TeeTimesInd" t2
          ON    t1."gDate"       = t2."gDate"
         AND    t1."CourseID_id" = t2."CourseID_id"
         AND    t1."PID_id"      < t2."PID_id"          -- avoid (A,B) / (B,A)
        WHERE   t1."gDate" BETWEEN %s AND %s
        GROUP BY p1, p2
        ORDER BY cnt DESC
        LIMIT 10;
    """

    with connection.cursor() as cur:
        cur.execute(sql, [YEAR_START, TODAY])
        rows = cur.fetchall()          # (p1, p2, cnt)

    result = []
    for pid1, pid2, cnt in rows:
        p1 = Players.objects.get(pk=pid1)
        p2 = Players.objects.get(pk=pid2)
        result.append({
            "name":  f"{p1.FirstName} {p1.LastName} & "
                     f"{p2.FirstName} {p2.LastName}",
            "value": cnt,
        })
    return result

TOP10_FUNC = {
    # "gross"        : _top10_gross,
    "net"          : _top10_net,
    "gross_member" : _top10_gross_member,
    "skins"        : _top10_skins,
    "attendance"   : _top10_attendance,
    "skins_one"    : _top10_skins_one,
    "forty_season" : _top10_forty_season,
    "forty_one"    : _top10_forty_one,
    "trader"       : _top10_trader,
    "quick_draw"   : _top10_quick_draw,
    "friends"      : _top10_friends,
}

def _get_round_leaders():
    """
    Build a dict keyed by stat name whose value is the first row
    of the corresponding _top10_… helper (or None if no data).
    This guarantees card == top-row of the Top-10 table.
    """
    leaders = {}
    for stat, func in TOP10_FUNC.items():
        rows = func()
        leaders[stat] = rows[0] if rows else None
    return leaders

@login_required
def rounds_leaderboard_view(request):
    chosen = request.GET.get("stat", "gross_member")     # default that exists
    if chosen not in TOP10_FUNC:
        chosen = "gross_member"

    label   = STAT_LABELS[chosen]
    topten  = TOP10_FUNC[chosen]()          # same helpers…
    leaders = _get_round_leaders()           # …and cards use them too

    return render(request, "GRPR/rounds_leaderboard.html", {
        "chosen":  chosen,
        "label":   label,
        "topten":  topten,
        "leaders": leaders,
    })


##########################
####  Games Section   ####
##########################

@login_required
def games_view(request):
    user = request.user
    # Discover if there is a current game in process
    game = Games.objects.exclude(Status='Closed').order_by('-CreateDate').first()
    gDate = game.PlayDate if game else None
    game_status = game.Status if game else None
    game_id = game.id if game else None
    game_type = game.Type if game else None
    assoc_game_id = game.AssocGame if game else None

    assoc_game = Games.objects.filter(id = assoc_game_id).first() if assoc_game_id else None

    if game_type == 'Skins':
        skins_game_id = game_id
        forty_game_id = assoc_game_id
    elif game_type == 'Forty':
        skins_game_id = assoc_game_id
        forty_game_id = game_id
    else:
        skins_game_id = None
        forty_game_id = None
    
    if skins_game_id:
        skins_players_num = ScorecardMeta.objects.filter(GameID=skins_game_id).count()
    else:
        skins_players_num = 0
    
    if forty_game_id:
        forty_players_num = ScorecardMeta.objects.filter(GameID=forty_game_id).count()
    else:
        forty_players_num = 0
    
    context = {
        'game_status': game_status,
        'gDate': gDate,
        'game_type': game_type,
        'skins_game_id': skins_game_id,
        'skins_players_num': skins_players_num,
        'forty_game_id': forty_game_id,
        'forty_players_num': forty_players_num if assoc_game else None,
        'first_name': user.first_name,
        'last_name': user.last_name,
    }

    return render(request, 'GRPR/games.html', context)


@login_required
def games_choice_view(request):
    if request.method == "POST":
        # ADDED: read the toggle and enforce on POST
        toggles = get_toggles()

        choices = request.POST.getlist("game")  # ['skins','forty','gascup']

        # ADDED: server-side defense — strip Gas Cup if disabled
        if not toggles.gascup_enabled and "gascup" in choices:
            choices = [c for c in choices if c != "gascup"]

        want_forty  = ("forty"  in choices)
        want_gascup = ("gascup" in choices)

        # ADDED: ensure session reflects enforced value (no stale True)
        request.session["want_gascup"] = want_gascup
        request.session.modified = True

        # Decide where to go next:
        # Always handle Skins already being the "base" game (created earlier).
        # If they picked Forty, go to Forty config (normal flow).
        if want_forty:
            return redirect("forty_config_view")

        # Else if Gas Cup only (no Forty), jump straight to Gas Cup assignment.
        if want_gascup:
            # We expect skins_game_id to be in session (set in skins_config_confirm_view).
            # If missing, we’ll try to locate a recent Skins game for today; soft fallback.
            if "skins_game_id" not in request.session:
                request.session["skins_game_id"] = game_id_for_today()
                request.session.modified = True
            return redirect("gascup_team_assign_view")

        # If neither Forty nor Gas Cup selected, just drop to leaderboard (same as “done”)
        return redirect("skins_leaderboard_view")

    # ---------- GET: show the game choice form ----------
    current_datetime = datetime.now()
    next_closest_date = (
        TeeTimesInd.objects
        .filter(gDate__gte=current_datetime)
        .order_by('gDate')
        .values('gDate')
        .first()
    )
    play_date = next_closest_date['gDate'] if next_closest_date else None

    # get the flag to determine if Gas Cup is available
    toggles = get_toggles()

    context = {
        'play_date'  : play_date,
        "gascup_enabled": toggles.gascup_enabled,
        'first_name' : request.user.first_name,
        'last_name'  : request.user.last_name,
    }
    return render(request, 'GRPR/games_choice.html', context)




##########################
#### Skins game views ####
##########################
@login_required
def skins_admin_view(request):
    user = request.user
    # Discover if there is a current game in process
    game = Games.objects.filter(Type='Skins').exclude(Status='Closed').order_by('-CreateDate').first()
    gDate = game.PlayDate if game else None
    game_creator = game.CreateID if game else None
    game_status = game.Status if game else None
    game_id = game.id if game else None

    context = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'game_creator': game_creator,
        'gDate': gDate, 
        'game_status': game_status,
        'game_id': game_id,
    }

    return render(request, 'GRPR/skins_admin.html', context)

# just for a game close button for skins
# ❶  Close button: mark Closed *and* lock so it can’t be deleted later
@login_required
def skins_game_close_view(request):
    game_id = request.GET.get("game_id")
    if not game_id:
        return HttpResponseBadRequest("Game ID is missing.")

    Games.objects.filter(id=game_id).update(
        Status="Closed", IsLocked=True, LockedAt=timezone.now()
    )

    game = Games.objects.filter(id=game_id).first()
    context = {
        "first_name": request.user.first_name,
        "last_name": request.user.last_name,
        "game_creator": game.CreateID if game else None,
        "gDate": game.PlayDate if game else None,
        "game_status": game.Status if game else None,
        "game_id": game_id,
    }
    return render(request, "GRPR/skins_admin.html", context)

# ---------------------------------------------------------------------
# ❷  Menu view (unchanged except we send IsLocked to template)
@login_required
def skins_delete_game_menu_view(request):
    if request.user.username != "cprouty":
        return redirect("skins_admin_view")

    games = (
        Games.objects.order_by("id")
        .annotate(
            invites_count=Subquery(
                GameInvites.objects.filter(GameID_id=OuterRef("id"))
                .values("GameID_id")
                .annotate(c=Count("id"))
                .values("c")[:1]
            ),
            players_count=Subquery(
                ScorecardMeta.objects.filter(GameID_id=OuterRef("id"))
                .values("GameID_id")
                .annotate(c=Count("id"))
                .values("c")[:1]
            ),
            holes_count=Subquery(
                Scorecard.objects.filter(GameID_id=OuterRef("id"))
                .values("GameID_id")
                .annotate(c=Count("id"))
                .values("c")[:1]
            ),
            skins_count=Subquery(
                Skins.objects.filter(GameID_id=OuterRef("id"))
                .values("GameID_id")
                .annotate(c=Count("id"))
                .values("c")[:1]
            ),
        )
    )
    return render(request, "GRPR/skins_delete_game_menu.html", {"games": games})

# ---------------------------------------------------------------------
# ❸  Delete view with lock-guard
@login_required
def skins_delete_game_view(request):
    if request.method != "POST" or request.user.username != "cprouty":
        return redirect("skins_admin_view")

    game_id = request.POST.get("game_id")
    if not game_id:
        messages.error(request, "No game_id supplied.")
        return redirect("skins_admin_view") 

    game = get_object_or_404(Games, id=game_id)
    if not game:
        messages.error(request, f"Game {game_id} not found.")
        return redirect("skins_admin_view")

    # ---------- LOCK CHECK ----------
    if game.IsLocked:
        messages.error(request, "That game is locked and can’t be deleted.")
        return redirect("skins_admin_view")
    # --------------------------------

    if game.Type == "Skins":
        with transaction.atomic():
            scorecard_count = Scorecard.objects.filter(GameID=game).delete()[0]
            scoremeta_count = ScorecardMeta.objects.filter(GameID=game).delete()[0]
            invites_count   = GameInvites.objects.filter(GameID=game).delete()[0]
            skins_count     = Skins.objects.filter(GameID=game).delete()[0]
            game.delete()
        msg = (
            f"Skins game {game_id} deleted. "
            f"Scorecard: {scorecard_count}, "
            f"ScMeta: {scoremeta_count}, "
            f"Invites: {invites_count}, "
            f"Skins: {skins_count}."
        )
    elif game.Type == "Forty":
        with transaction.atomic():
            forty_count = Forty.objects.filter(GameID=game).delete()[0]
            game.delete()
        msg = f"Forty game {game_id} deleted. Rows: {forty_count}."
    elif game.Type == "GasCup":
        with transaction.atomic():
            gascuppair_count = GasCupPair.objects.filter(Game=game).delete()[0]
            gascupscore_count = GasCupScore.objects.filter(Game=game).delete()[0]
            game.delete()
        msg = (
            f"Gas Cup game {game_id} deleted. "
            f"Scores: {gascupscore_count}, "
            f"Pairs: {gascuppair_count}, "
        )
    else:
        msg = f"Game {game_id} is not Skins, Forty, or Gas Cup. No action taken."

    messages.success(request, msg)
    return redirect("skins_admin_view")
    

@login_required
def skins_view(request):
    user = request.user
    # Discover if there is a current game in process
    game = Games.objects.filter(Type='Skins').exclude(Status='Closed').order_by('-CreateDate').first()
    gDate = game.PlayDate if game else None
    game_creator = game.CreateID if game else None
    game_status = game.Status if game else None
    game_id = game.id if game else None

    context = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'game_creator': game_creator,
        'gDate': gDate, 
        'game_status': game_status,
        'game_id': game_id, 
    }

    return render(request, 'GRPR/skins.html', context)


@login_required
def skins_choose_players_view(request):
    # Get today's date
    current_datetime = datetime.now()

    # Query the next closest future date in the TeeTimesInd table
    next_closest_date = TeeTimesInd.objects.filter(gDate__gte=current_datetime).order_by('gDate').values('gDate').first()
    print('next_closest_date', next_closest_date)
    # hard code a date:
    # next_closest_date = {'gDate': date(2025, 4, 26)}
    print('')

    # If no future date is found, return an empty context
    if not next_closest_date:
        context = {
            'tee_times': [],
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        }
        return render(request, 'GRPR/new_skins_game.html', context)

    # Get the next closest date
    next_closest_date = next_closest_date['gDate']

    # Query the database for tee times on the next closest date
    tee_times_queryset = TeeTimesInd.objects.filter(gDate=next_closest_date).select_related('PID', 'CourseID').order_by('CourseID__courseTimeSlot')
    print()
    print('tee_times_queryset"', tee_times_queryset)
    print()

    # Group players by tee time
    tee_times = []
    current_group = None
    for teetime in tee_times_queryset:
        if not current_group or current_group['time'] != teetime.CourseID.courseTimeSlot:
            current_group = {
                'date': teetime.gDate.strftime('%Y-%m-%d'),
                'time': teetime.CourseID.courseTimeSlot,
                'course': teetime.CourseID.courseName,
                'players': []
            }
            tee_times.append(current_group)
        current_group['players'].append({
            'name': f"{teetime.PID.FirstName} {teetime.PID.LastName}",
            'player_id': teetime.PID.id,
            'tt_id': teetime.id,
            'index': teetime.PID.Index,
        })
    
    # Count the number of players in all tee_times groups
    number_of_players = sum(len(group['players']) for group in tee_times)
    
    print('new_skins_game_view')
    print('tee_times', tee_times)
    print()

    context = {
        'playing_date': next_closest_date,
        'tee_times': tee_times,
        'number_of_players': number_of_players,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }

    return render(request, 'GRPR/skins_choose_players.html', context)


@login_required
def skins_remove_player_view(request):
    if request.method == 'POST':
        player_id = int(request.POST.get('player_id'))
        tt_id = int(request.POST.get('tt_id'))
        playing_date = request.POST.get('playing_date')
        tee_times_json = request.POST.get('tee_times_json')
        tee_times = json.loads(tee_times_json)

        # Remove the player from the tee_times structure
        for group in tee_times:
            group['players'] = [p for p in group['players'] if p['player_id'] != player_id]

        # Remove any groups with no players
        tee_times = [group for group in tee_times if group['players']]

        number_of_players = sum(len(group['players']) for group in tee_times)

        context = {
            'playing_date': playing_date,
            'tee_times': tee_times,
            'number_of_players': number_of_players,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        }

        return render(request, 'GRPR/skins_choose_players.html', context)
    else:
        return redirect('skins_choose_players_view')


@login_required
def skins_choose_replacement_player_view(request):
    playing_date = request.POST.get('playing_date')
    tee_times = json.loads(request.POST.get('tee_times_json'))
    number_of_players = int(request.POST.get('number_of_players'))
    first_name = request.POST.get('first_name')
    last_name = request.POST.get('last_name')

    # Get all player_ids already in tee_times
    existing_player_ids = [p['player_id'] for group in tee_times for p in group['players']]

    # Query available players
    available_players = Players.objects.filter(CrewID=1, Member=1).exclude(id__in=existing_player_ids).order_by('LastName', 'FirstName')
    print('available_players', available_players)

    # Find groups with less than 4 players
    available_groups = [group for group in tee_times if len(group['players']) < 4]

    context = {
        'playing_date': playing_date,
        'tee_times': tee_times,
        'number_of_players': number_of_players,
        'first_name': first_name,
        'last_name': last_name,
        'available_players': available_players,
        'available_groups': available_groups,
    }

    return render(request, 'GRPR/skins_choose_replacement_player.html', context)


@login_required
def skins_add_player_view(request):
    if request.method == 'POST':
        playing_date = request.POST.get('playing_date')
        # Convert to date object if not already in YYYY-MM-DD
        # try:
        #     # Try parsing as YYYY-MM-DD first
        #     playing_date_obj = datetime.strptime(playing_date, "%Y-%m-%d").date()
        # except ValueError:
        #     # If that fails, try parsing as "Month D, YYYY"
        #     playing_date_obj = datetime.strptime(playing_date, "%B %d, %Y").date()
        playing_date_obj = parse_date_any(playing_date)

        tee_times = json.loads(request.POST.get('tee_times_json'))
        number_of_players = int(request.POST.get('number_of_players'))
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        new_player_id = int(request.POST.get('player_id'))
        group_time = request.POST.get('group_time')

        # Find the group in tee_times
        group = next(g for g in tee_times if g['time'] == group_time)
        course_name = group['course']

        # Find available tt_id for this group
        course_obj = Courses.objects.get(courseTimeSlot=group_time, courseName=course_name)
        tts = TeeTimesInd.objects.filter(gDate=playing_date_obj, CourseID=course_obj)
        used_tt_ids = [p['tt_id'] for g in tee_times for p in g['players']]
        available_tt = tts.exclude(id__in=used_tt_ids).first()
        tt_id = available_tt.id

        # Get replaced player
        replaced_player_id = TeeTimesInd.objects.get(id=tt_id).PID_id

        # Update TeeTimesInd
        TeeTimesInd.objects.filter(id=tt_id).update(PID_id=new_player_id)

        # Log entry
        msg = f'Via the Skins process, {first_name} {last_name} has changed ttid: {tt_id} from player: {replaced_player_id} to player: {new_player_id}'
        Log.objects.create(
            SentDate=now(),
            Type='Sub Via Skins',
            RequestDate=playing_date_obj,
            OfferID=replaced_player_id,
            ReceiveID=new_player_id,
            RefID=tt_id,
            Msg=msg
        )

        # SubSwap entries
        sub1 = SubSwap.objects.create(
            RequestDate=now(),
            PID_id=replaced_player_id,
            TeeTimeIndID_id=tt_id,
            Msg=msg,
            SubStatus='Changed Via Skins',
            nStatus='Closed',
            nType='Sub'
        )
        swap_id = sub1.id
        sub1.SwapID = swap_id
        sub1.save()
        SubSwap.objects.create(
            RequestDate=now(),
            PID_id=new_player_id,
            TeeTimeIndID_id=tt_id,
            Msg=msg,
            SubStatus='Changed Via Skins',
            SwapID=swap_id,
            nStatus='Closed',
            nType='Sub'
        )

        # Add new player to tee_times group
        from .models import Players
        player_obj = Players.objects.get(id=new_player_id)
        group['players'].append({
            'name': f"{player_obj.FirstName} {player_obj.LastName}",
            'player_id': new_player_id,
            'tt_id': tt_id,
            'index': player_obj.Index,
        })

        number_of_players += 1

        context = {
            'playing_date': playing_date,
            'tee_times': tee_times,
            'number_of_players': number_of_players,
            'first_name': first_name,
            'last_name': last_name,
        }
        return render(request, 'GRPR/skins_choose_players.html', context)
    else:
        return redirect('skins_choose_players_view')
    

@login_required
def skins_config_view(request):
    if request.method == 'POST':
        user = request.user
        playing_date = request.POST.get('playing_date')
        tee_times = json.loads(request.POST.get('tee_times_json'))
        number_of_players = int(request.POST.get('number_of_players'))

        # Get logged_in_player_id
        logged_in_player = Players.objects.get(user_id=user.id)
        logged_in_player_id = logged_in_player.id

        print()
        print('ymd', playing_date)
        print()

        playing_date_ymd = parse_date_any(playing_date)

        print('ymd', playing_date_ymd )

        # Hard code ct_id for now
        ct_id = 1  # TODO: Make dynamic in future

        # --- Prevent duplicate game creation ---
        existing_game = Games.objects.filter(
            CrewID=1,
            PlayDate=playing_date_ymd,
            Status='Tees',
            Type='Skins',
        ).first()
        if existing_game:
            # Option 1: Redirect to config for existing game
            tee_options = CourseTees.objects.filter(CourseID=ct_id).order_by('TeeID')
            context = {
                'game_id': existing_game.id,
                'tee_options': tee_options,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'tee_times': tee_times,
                'playing_date': playing_date,
                'number_of_players': number_of_players,
                'message': 'A game for this date already exists. You are editing the existing game.',
            }
            return render(request, 'GRPR/skins_config.html', context)
        # --- End duplicate check ---

        # Insert new row into Games
        game = Games.objects.create(
            CrewID=1,
            CreateDate=now(),
            PlayDate=playing_date_ymd,
            Status='Tees',
            CreateID_id=logged_in_player_id,
            Type='Skins',
        )
        game_id = game.id

        # Remember the Skins game for downstream (Forty, Gas Cup) flows.
        request.session['skins_game_id'] = game.id
        request.session.modified = True   # defensive: ensure session is saved

        # Bulk insert GameInvites
        game_invites = []
        for group in tee_times:
            for player in group['players']:
                game_invites.append(GameInvites(
                    AlterDate=now(),
                    Status='Accepted',
                    GameID_id=game_id,
                    PID_id=player['player_id'],
                    TTID_id=player['tt_id']
                ))
        GameInvites.objects.bulk_create(game_invites)

        # Get tee options
        tee_options = CourseTees.objects.filter(CourseID=ct_id).order_by('TeeID')

        context = {
            'game_id': game_id,
            'tee_options': tee_options,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'tee_times': tee_times,
            'playing_date': playing_date,
            'number_of_players': number_of_players,
        }
        return render(request, 'GRPR/skins_config.html', context)
    else:
        return redirect('skins_choose_players_view')
    

# maybe an inefficent solution.  This allows the user to 'back button' from the skins config view to the choose players view
@login_required
def skins_undo_game_creation(request):
    if request.method == 'POST':
        game_id = request.POST.get('game_id')
        playing_date = request.POST.get('playing_date')
        tee_times = json.loads(request.POST.get('tee_times_json'))
        number_of_players = int(request.POST.get('number_of_players'))

        # Delete GameInvites and Games
        GameInvites.objects.filter(GameID_id=game_id).delete()
        Games.objects.filter(id=game_id).delete()

        context = {
            'playing_date': playing_date,
            'tee_times': tee_times,
            'number_of_players': number_of_players,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        }
        return render(request, 'GRPR/skins_choose_players.html', context)
    else:
        return redirect('skins_choose_players_view')
    

@login_required
def skins_config_confirm_view(request):
    if request.method == 'POST':
        game_id = request.POST.get('game_id')
        tee_id = int(request.POST.get('tee_id'))
        format_option = request.POST.get('format_option')
        game_format = request.POST.get('game_format')

        # Get game info
        game = get_object_or_404(Games, id=game_id)
        
        # --- Gas-Cup linkage: remember this Skins game for downstream flows ---
        request.session["skins_game_id"] = game.id
        request.session.modified = True   # (optional; forces session save)

        play_date = game.PlayDate
        ct_id = game.CourseTeesID_id

        # Get all invites for this game
        invites_qs = GameInvites.objects.filter(GameID=game_id, Status='Accepted').select_related('PID', 'TTID__CourseID')

        # Build player list
        player_list = []
        for invite in invites_qs:
            player = invite.PID
            tt = invite.TTID
            course = tt.CourseID
            player_list.append({
                'player_id': player.id,
                'first_name': player.FirstName,
                'last_name': player.LastName,
                'index': player.Index,
                'group_time': course.courseTimeSlot,
                'course_name': course.courseName,
            })

        # Tee options
        tee_options = CourseTees.objects.filter(CourseID=ct_id).order_by('TeeID')
        tee_options_list = []
        for tee in tee_options:
            tee_options_list.append({
                'tee_id': tee.id,
                'name': tee.TeeName,
                'rating': tee.CourseRating,
                'slope': tee.SlopeRating,
                'yards': tee.Yards,
            })

        
        # If format_option is not selected, re-render the config page with a message
        if not format_option:
            # You may want to also pass tee_times, playing_date, number_of_players if needed
            context = {
                'game_id': game_id,
                'ct_id': ct_id,
                'tee_id': tee_id,
                'player_list': player_list,
                'tee_options_list': tee_options_list,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'msg': "Please choose Format for Game",
                # Add any other context variables your template expects
            }
            return render(request, 'GRPR/skins_config.html', context)

        context = {
            'game_id': game_id,
            'ct_id': ct_id,
            'tee_id': tee_id,
            'player_list': player_list,
            'tee_options_list': tee_options_list,
            'game_format': game_format,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        }
        return render(request, 'GRPR/skins_config_confirm.html', context)
    else:
        return redirect('skins_config_view')



# deprecated once v2 of New Game process is done
@login_required
def skins_new_game_view(request):
    # Get today's date
    current_datetime = datetime.now()

    # Query the next closest future date in the TeeTimesInd table
    next_closest_date = TeeTimesInd.objects.filter(gDate__gte=current_datetime).order_by('gDate').values('gDate').first()
    print('next_closest_date', next_closest_date)
    # hard code a date:
    # next_closest_date = {'gDate': date(2025, 4, 26)}
    print('hard coded next_closest_date', next_closest_date)
    print('')

    # If no future date is found, return an empty context
    if not next_closest_date:
        context = {
            'tee_times': [],
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        }
        return render(request, 'GRPR/new_skins_game.html', context)

    # Get the next closest date
    next_closest_date = next_closest_date['gDate']

    # Query the database for tee times on the next closest date
    tee_times_queryset = TeeTimesInd.objects.filter(gDate=next_closest_date).select_related('PID', 'CourseID').order_by('CourseID__courseTimeSlot')
    print()
    print('tee_times_queryset"', tee_times_queryset)
    print()

    # Group players by tee time
    tee_times = []
    current_group = None
    for teetime in tee_times_queryset:
        if not current_group or current_group['time'] != teetime.CourseID.courseTimeSlot:
            current_group = {
                'date': teetime.gDate.strftime('%Y-%m-%d'),
                'time': teetime.CourseID.courseTimeSlot,
                'course': teetime.CourseID.courseName,
                'players': []
            }
            tee_times.append(current_group)
        current_group['players'].append({
            'name': f"{teetime.PID.FirstName} {teetime.PID.LastName}",
            'player_id': teetime.PID.id,
            'tt_id': teetime.id,
            'index': teetime.PID.Index,
        })
    
    # Count the number of players in all tee_times groups
    number_of_players = sum(len(group['players']) for group in tee_times)
    
    print('new_skins_game_view')
    print('tee_times', tee_times)
    print()

    context = {
        'playig_date': next_closest_date,
        'tee_times': tee_times,
        'number_of_players': number_of_players,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }
    return render(request, 'GRPR/skins_new_game.html', context)


@login_required
def skins_invite_view(request):
    if request.method == 'POST':
        game_creator = request.user
        gDate = request.POST.get('gDate')
        selected_players = request.POST.getlist('selected_players')
        print('skins_invite_view - selected_players', selected_players)
        print('skins_invite_view - gDate', gDate)
        print('skins_invite_view - game_creator', game_creator)
        print()

        # Filter out any empty values from selected_players
        selected_players = [player_id for player_id in selected_players if player_id]

        # Fetch the player instance for the logged-in user
        game_creator_player = get_object_or_404(Players, user=game_creator)

        # Create a new game
        game = Games.objects.create(
            CreateID=game_creator_player,
            CrewID=1,
            CreateDate=timezone.now().date(),
            PlayDate=gDate,
            Status='Invite',
            Type='Skins',
        )
        game_id = game.id

        # Get the first name and last name of the logged-in user
        invite_msg = f"{game_creator_player.FirstName} {game_creator_player.LastName} is inviting you to a Skins game for your tee time on {gDate}. Respond 'Accept' or 'Decline' to this message"

        # Check if Twilio is enabled
        twilio_enabled = os.getenv('TWILIO_ENABLED', 'False') == 'True'
        if twilio_enabled:
            client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))

        # Invite each selected player
        for player_data in selected_players:
            player_id, tt_id = player_data.split('|')
            player = get_object_or_404(Players, id=player_id)
            invitee_mobile = player.Mobile

            # Create a row in the GameInvites table
            GameInvites.objects.create(
                GameID=game,
                AlterDate=timezone.now().date(),
                PID=player,
                TTID_id=tt_id,
                Status='Invited',
            )

            # Send the invitation via Twilio if enabled
            # if twilio_enabled:
            #     message = client.messages.create(
            #         body=invite_msg,
            #         from_=os.getenv('TWILIO_PHONE_NUMBER'),
            #         to=invitee_mobile
            #     )
            #     mID = message.sid
            # else:
            #     mID = 'Fake'
            mID = 'Fake'

            # Create a row in the Log table
            Log.objects.create(
                SentDate=timezone.now(),
                Type='Game Invite',
                MessageID=mID,
                RequestDate=gDate,
                OfferID=game_creator_player.id,
                ReceiveID=player.id,
                RefID=game_id,
                Msg=invite_msg,
                To_number=invitee_mobile
            )

        # Set game creator row in the GameInvites table to Status = 1:
        GameInvites.objects.filter(
            GameID_id=game_id, 
            PID_id=game_creator_player, 
            Status='Invited',
        ).update(Status='Accepted')   

        # Store necessary data in the session
        print('game_id', game_id)
        request.session['game_id'] = game_id

        return redirect('skins_invite_status_view')
    else:
        return HttpResponseBadRequest("Invalid request.")  
    


@login_required
def skins_invite_status_view(request):
        game_id = request.GET.get('game_id') or request.session.pop('game_id', None)  # Retrieve from query params or session
        if not game_id:
            return HttpResponseBadRequest("Game ID is missing.")

        # Fetch the game invites to display on the skins_invite.html page
        invites_queryset = GameInvites.objects.filter(GameID=game_id).select_related('PID', 'TTID__CourseID')

        # Get distinct CourseID values
        distinct_course_ids = invites_queryset.values('TTID__CourseID').distinct()
        # Extract just the CourseID values
        distinct_course_ids_list = [course['TTID__CourseID'] for course in distinct_course_ids]

        # Group invites by date, course, and tee time
        invites = []
        for cid in distinct_course_ids_list:
            players = []
            for invite in invites_queryset:
                course_id = invite.TTID.CourseID_id
                if cid == course_id:
                    g_date = invite.TTID.gDate.strftime('%Y-%m-%d')
                    c_id = invite.TTID.CourseID
                    tee_time = invite.TTID.CourseID.courseTimeSlot
                    course_name = invite.TTID.CourseID.courseName
                    players.append({
                        'player_name': f"{invite.PID.FirstName} {invite.PID.LastName}",
                        'player_id': invite.PID_id,
                        'status': invite.Status,
                    })
            invites.append({
                'date': g_date, 
                'CID': c_id,
                'time': tee_time, 
                'course': course_name,
                'players': players,
            })

        context = {
            'game_id': game_id,
            'invites': invites,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        }
        return render(request, 'GRPR/skins_invite.html', context)
    

@login_required
def skins_accept_decline_view(request):
    game_id = request.GET.get('game_id')
    player_id = request.GET.get('player_id')
    gStatus = request.GET.get('gStatus')

    if not game_id or not player_id or not gStatus:
        return HttpResponseBadRequest("Missing parameters.")

    # Update the status in the GameInvites table
    GameInvites.objects.filter(GameID_id=game_id, PID_id=player_id).update(Status=gStatus)

    # Fetch the necessary data
    game_invite = GameInvites.objects.select_related('GameID', 'PID').get(GameID_id=game_id, PID_id=player_id)
    pDate = game_invite.GameID.PlayDate
    player = game_invite.PID
    mobile = player.Mobile
    
    # Get the player_id for the current logged-in user
    user = request.user
    owner = get_object_or_404(Players, user=user)
    owner_player_id = owner.id

    # Check if Twilio is enabled
    twilio_enabled = os.getenv('TWILIO_ENABLED', 'False') == 'True'
    # if twilio_enabled:
    #     client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
    #     message = client.messages.create(
    #         body=f"Your invite status has been changed to {gStatus}",
    #         from_=os.getenv('TWILIO_PHONE_NUMBER'),
    #         to=mobile
    #     )
    #     mID = message.sid
    # else:
    #     mID = 'Fake'
    #     mobile = 'None'

    mID = 'Fake'
    mobile = 'None'

    # Insert a new row into the Log table
    Log.objects.create(
        SentDate=timezone.now(),
        Type='Game Response',
        MessageID=mID,
        RequestDate=pDate,
        OfferID=owner_player_id,
        ReceiveID=player_id,
        RefID=game_id,
        Msg=f'Invite status changed to {gStatus}',
        To_number=mobile
    )

    # Store the game_id in the session
    request.session['game_id'] = game_id

    # Redirect to the skins_invite_status_view
    return redirect('skins_invite_status_view')


# this view picks the tees for the Skins game
@login_required
def skins_choose_tees_view(request):
    game_id = request.GET.get('game_id')

    if not game_id:
        return HttpResponseBadRequest("Missing game_id parameter.")

    # Update the Games table
    Games.objects.filter(id=game_id, CrewID=1).update(Status='Tees')

    # Fetch the necessary data
    game = get_object_or_404(Games, id=game_id)
    pDate = game.PlayDate
    ct_id = game.CourseTeesID_id

    print()
    print('skins_choose_tees_view - pDate', pDate)
    print()

    # Get the player_id for the current logged-in user
    user = request.user
    player = get_object_or_404(Players, user=user)
    player_id = player.id
    # player_name = f"{player.FirstName} {player.LastName}"

    # Fetch the game invites to display on the skins_invite.html page
    invites_queryset = GameInvites.objects.filter(GameID=game_id, Status='Accepted').select_related('PID', 'TTID__CourseID')
    print('skins_choose_tees_view - invites_queryset', invites_queryset)
    print()

    # Get distinct CourseID values
    distinct_course_ids = invites_queryset.values('TTID__CourseID').distinct()
    # Extract just the CourseID values
    distinct_course_ids_list = [course['TTID__CourseID'] for course in distinct_course_ids]

    # Group invites by date, course, and tee time
    invites = []
    for cid in distinct_course_ids_list:
        players = []
        for invite in invites_queryset:
            course_id = invite.TTID.CourseID_id
            if cid == course_id:
                g_date = invite.TTID.gDate.strftime('%Y-%m-%d')
                c_id = invite.TTID.CourseID
                tee_time = invite.TTID.CourseID.courseTimeSlot
                course_name = invite.TTID.CourseID.courseName
                players.append({
                    'player_name': f"{invite.PID.FirstName} {invite.PID.LastName}",
                    'player_id': invite.PID_id,
                    'player_index': invite.PID.Index,
                })
        invites.append({
            'date': g_date, 
            'CID': c_id,
            'time': tee_time, 
            'course': course_name,
            'players': players,
        })
    
    print('skins_choose_tees_view - invites', invites)
    print()
    
    tee_options = CourseTees.objects.filter(CourseID=ct_id).order_by('TeeID')
    print('ct_id', ct_id)
    print('tee_options', tee_options)
    
    tee_options_list = []
    for tee in tee_options:
        tee_options_list.append({
            'tee_id': tee.id,
            'name': tee.TeeName,
            'rating': tee.CourseRating,
            'slope': tee.SlopeRating,
            'yards': tee.Yards,
        })


    context = {
        'game_id': game_id,
        'invites': invites,
        'tee_options_list': tee_options_list,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }

    # Render the skins_tees.html page
    return render(request, 'GRPR/skins_tees.html', context)


@login_required
def skins_initiate_scorecard_meta_view(request):
    if request.method == "POST":
        game_id = request.POST.get("game_id")
        game_format = request.POST.get("game_format")
        player_ids = request.POST.getlist("player_ids")
        
        # Check if ScorecardMeta already exists for this game
        if ScorecardMeta.objects.filter(GameID=game_id).exists():
            # Already created, just redirect
            request.session['game_id'] = game_id
            return redirect('skins_leaderboard_view')

        # Update the Games table to set the status to 'Live'
        Games.objects.filter(id=game_id).update(Status="Live", Format = game_format)

        # Get logged-in user's player ID
        logged_in_user = get_object_or_404(Players, user_id=request.user.id)
        logged_in_user_player_id = logged_in_user.id

        # Get game details
        game = get_object_or_404(Games, id=game_id)
        play_date = game.PlayDate
        ct_id = game.CourseTeesID_id
        crew_id = game.CrewID
        crew = get_object_or_404(Crews, id=crew_id)
        print('player_ids', player_ids)

        # Process each player
        with transaction.atomic():
            for player_id in player_ids:
                tee_id = request.POST.get(f"tee_ids_{player_id}")  # Get the tee_id for this player
                print(f"Processing player_id: {player_id}, tee_id: {tee_id}")

                # Convert tee_id to a CourseTees object
                tee_object = get_object_or_404(CourseTees, id=int(tee_id))

                # Get player index and slope
                player = get_object_or_404(Players, id=player_id)
                index = player.Index
                slope = tee_object.SlopeRating  # Access the SlopeRating directly from the object

                # Calculate raw handicap
                if index == 0 or index is None:
                    # Avoid division by zero, if index is 0, set raw handicap to 0
                    raw_hcdp = 0
                else:
                    raw_hcdp = (slope / Decimal(113)) * Decimal(index)

                # Get group ID (courseTimeSlot)
                group_id = (
                    GameInvites.objects.filter(GameID=game_id, PID=player_id)
                    .select_related("TTID__CourseID")
                    .first()
                    .TTID.CourseID.courseTimeSlot
                )

                # Insert into ScorecardMeta
                ScorecardMeta.objects.create(
                    GameID=game,
                    CreateDate=timezone.now(),
                    CreateID=logged_in_user_player_id,
                    PlayDate=play_date,
                    PID=player,
                    CrewID=crew,
                    CourseID=ct_id,
                    TeeID=tee_object,  # Save the CourseTees object
                    Index=index,
                    RawHDCP=raw_hcdp,
                    GroupID=group_id,
                )
        
        # Calculate the NetHDCP for each player
        scm = ScorecardMeta.objects.filter(GameID=game_id)
        print('ScorecardMeta entries:', scm)

        if game_format == 'Low Man':
            # Find the lowest RawHDCP
            lowest_raw_hdcp = scm.order_by('RawHDCP').first().RawHDCP
            print('Lowest RawHDCP:', lowest_raw_hdcp)

            # Update NetHDCP for each player
            for hdcp in scm:
                pid = hdcp.PID
                raw_hdcp = hdcp.RawHDCP
                net_hdcp = custom_round(float(raw_hdcp - lowest_raw_hdcp))
                hdcp.NetHDCP = net_hdcp
                hdcp.save()
                print(f"Updated NetHDCP for PID {pid}: {net_hdcp}")
        elif game_format == 'Full Handicap':
            # Set NetHDCP to the rounded RawHDCP for each player
            for hdcp in scm:
                pid = hdcp.PID
                raw_hdcp = hdcp.RawHDCP
                net_hdcp = custom_round(float(raw_hdcp))
                hdcp.NetHDCP = net_hdcp
                hdcp.save()
                print(f"Updated NetHDCP for PID {pid}: {net_hdcp}")

        request.session['game_id'] = game_id

        # get flag for Gas Cup enablement
        toggles = get_toggles()

        context = {
        'game_id': game_id,
        'play_date': play_date,
        'game_format': game_format,
        'gascup_enabled': toggles.gascup_enabled,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }

    return render(request, 'GRPR/games_choice.html', context)


@login_required
def skins_leaderboard_view(request):
    # Retrieve game_id from session or query parameters
    game_id = request.GET.get('game_id') or request.session.pop('game_id', None)
    if not game_id:
        return HttpResponseBadRequest("Game ID is missing.")
    print('skins_leaderboard_view game_id', game_id)

    # Get the associated Forty game ID
    forty_game_id = Games.objects.filter(id=game_id).values_list('AssocGame', flat=True).first()

    # work for forty leaderboard table
    forty_leaderboard = []
    if forty_game_id:
        # Get all groups in the Forty table for this Forty game
        forty_groups = Forty.objects.filter(GameID_id=forty_game_id).values_list('GroupID', flat=True).distinct()
        for group_id in forty_groups:
            scores_used = Forty.objects.filter(GameID_id=forty_game_id, GroupID=group_id).count()
            scores_played = Scorecard.objects.filter(GameID_id=game_id, smID__GroupID=group_id).count()
            num_scores = Games.objects.filter(id=forty_game_id).values_list('NumScores', flat=True).first() or 0
            scores_needed = num_scores - scores_used
            scores_available = 72 - scores_played
            par = Forty.objects.filter(GameID_id=forty_game_id, GroupID=group_id).aggregate(total=Sum('Par'))['total'] or 0
            group_score = Forty.objects.filter(GameID_id=forty_game_id, GroupID=group_id).aggregate(total=Sum('NetScore'))['total'] or 0
            over_under = group_score - par

            forty_leaderboard.append({
                'group_id': group_id,
                'scores_used': scores_used,
                'scores_needed': scores_needed,
                'scores_available': scores_available,
                'over_under': over_under,
            })
    # -- end forty leaderboard table

    # =================== Gas Cup table ===========================
    gas_matches = []
    gas_totals  = None
    gas_rosters = None

    toggles = get_toggles()
    want_gascup = request.session.get("want_gascup", False)

    if toggles.gascup_enabled and want_gascup:
        from GRPR.services import gascup
        gas_game = gascup._get_gascup_game_for_skins(game_id)
        if gas_game:
            gas_matches, gas_totals = gascup.summary_for_game(gas_game.id)
            gas_rosters = gascup.rosters_for_game(gas_game.id)
    # =================== End Gas Cup table ===========================

    # Get the Status and PlayDate of the game in a single query
    game_data = Games.objects.filter(id=game_id).values('Status', 'PlayDate').first()
    if not game_data:
        return HttpResponseBadRequest("Game not found.")

    game_status = game_data['Status']
    play_date = game_data['PlayDate']
    print('skins_leaderboard_view game_status:', game_status)
    print('skins_leaderboard_view play_date:', play_date)

    # Query the ScorecardMeta table and join with related models
    scorecard_meta = ScorecardMeta.objects.filter(
        GameID_id=game_id
    ).select_related(
        'PID',  # Join with Players
        'TeeID'  # Join with CourseTees
    ).annotate(
        first_name=F('PID__FirstName'),  # Player's first name
        last_name=F('PID__LastName'),  # Player's last name
        tee_name=F('TeeID__TeeName'),  # Tee name
        skins=F('Skins'),
    )

    print()
    print('skins_leaderboard.html - scorecard_meta', scorecard_meta)

    # Build a list of dictionaries for the leaderboard
    leaderboard = []
    for entry in scorecard_meta:
        player_id = entry.PID.id

        # Get all holes where this player won a skin in this game
        won_holes = (
            Skins.objects
            .filter(GameID=game_id, PlayerID=player_id)
            .select_related('HoleNumber')
            .values_list('HoleNumber__HoleNumber', flat=True)
            .order_by('HoleNumber__HoleNumber')
        )
        won_holes_list = list(won_holes)

        # Query the Scorecard table to find the largest HoleNumber for the player
        current_hole = (
            Scorecard.objects.filter(GameID=game_id, smID__PID_id=player_id)
            .select_related('HoleID')
            .aggregate(max_hole=Max('HoleID__HoleNumber'))
        )['max_hole']

        # Add the player's data to the leaderboard
        leaderboard.append({
            'first_name': entry.first_name,
            'last_name': entry.last_name,
            'index': entry.Index,
            'raw_hdcp': entry.RawHDCP,
            'net_hdcp': entry.NetHDCP,
            'tee_name': entry.tee_name,
            'current_hole': current_hole if current_hole else 0,
            'skins': entry.skins if entry.skins else 0, 
            'won_holes': won_holes_list,
        })
    
    # Check if all players have completed their rounds
    scorecard_data = Scorecard.objects.filter(GameID_id=game_id).values(
        'smID__PID_id'
    ).annotate(
        hole_count=Count('id'),  # Count the number of rows per player
        max_hole=Max('HoleID__HoleNumber')  # Get the maximum HoleNumber per player
    )

    # Determine if all players have completed their rounds
    scorecard_complete = (
        scorecard_data.exists() and
        all(
        player['hole_count'] == 18 and player['max_hole'] == 18
        for player in scorecard_data
        )
    )

    print()
    print('scorecard_complete:', scorecard_complete)

    # Get all distinct group_ids for the game
    group_ids = ScorecardMeta.objects.filter(GameID_id=game_id).values_list('GroupID', flat=True).distinct().order_by('GroupID')

    # Determine if the logged-in user is a member of any group
    user_player = get_object_or_404(Players, user=request.user)
    user_group_id = ScorecardMeta.objects.filter(GameID_id=game_id, PID=user_player).values_list('GroupID', flat=True).first()

    # Build the list of group buttons
    group_buttons = []
    if user_group_id:
        # Add the user's group first, labeled as "My Scorecard"
        group_buttons.append({
            'group_id': user_group_id,
            'label': 'My Scorecard',
        })

    # Add the remaining groups
    for group_id in group_ids:
        if group_id != user_group_id:
            group_buttons.append({
                'group_id': group_id,
                'label': f"{group_id}a Scorecard",
            })
    
    #Get payout amount per skin if available
    payout = Skins.objects.filter(GameID_id=game_id).values('Payout').first()


    # Pass data to the template
    context = {
        "game_id": game_id,
        "leaderboard": leaderboard,
        "forty_game_id": forty_game_id,
        "forty_leaderboard": forty_leaderboard,
        "group_buttons": group_buttons,
        "scorecard_complete": scorecard_complete,
        "game_status": game_status,
        "play_date": play_date,
        "payout": payout['Payout'] if payout else None,
        "gas_matches" : gas_matches,
        "gas_totals"  : gas_totals,
        "gas_rosters": gas_rosters,
        "first_name": request.user.first_name,
        "last_name": request.user.last_name,
    }

    return render(request, "GRPR/skins_leaderboard.html", context)


# This process closes a completed Skins game and calculates the payouts
@login_required
def skins_close_view(request):
    # Retrieve game_id and wager from query parameters
    game_id = request.GET.get('game_id')
    wager = request.GET.get('wager')  # Optional

    if not game_id:
        return HttpResponseBadRequest("Game ID is missing.")
    
    # Convert wager to an integer if it exists (this already gate kept on the page, but good practice)
    try:
        wager = int(wager) if wager else None
    except ValueError:
        return HttpResponseBadRequest("Invalid wager value. Please enter a valid integer.")


    # Query ScorecardMeta to get player names
    players = ScorecardMeta.objects.filter(GameID_id=game_id).select_related('PID').values(
        'PID__FirstName', 'PID__LastName', 'PID_id'
    )

    # Initialize leaderboard data
    leaderboard = []

    # Calculate payouts and update Skins table if wager is provided
    if wager is not None:
        num_players = ScorecardMeta.objects.filter(GameID_id=game_id).count()
        num_skins = Skins.objects.filter(GameID_id=game_id).count()
        pot = wager * num_players
        skin_payout = round(pot / num_skins, 2) if num_skins > 0 else 0

        # Update all Skins records for this game with the payout per skin
        Skins.objects.filter(GameID_id=game_id).update(Payout=skin_payout)
    else:
        skin_payout = None

    # Query Skins table for each player
    for player in players:
        player_id = player['PID_id']
        first_name = player['PID__FirstName']
        last_name = player['PID__LastName']

        # Get the number of skins and the list of holes
        skins_data = Skins.objects.filter(GameID_id=game_id, PlayerID_id=player_id).select_related('HoleNumber').values(
            'HoleNumber__HoleNumber', 'Payout'
        )
        skins_count = skins_data.count()
        holes_list = [entry['HoleNumber__HoleNumber'] for entry in skins_data]

        # Default payout is blank unless wager is provided
        payout_value = ""

        # Calculate payout if wager is provided
        if wager is not None:
            if skins_count > 0:
                payout_value = round(skin_payout * skins_count - wager, 2)
            else:
                payout_value = -wager

            # Format payout as currency
            payout_value = f"${payout_value:.2f}"

        # Add player data to leaderboard
        leaderboard.append({
            'name': f"{first_name} {last_name}",
            'skins': skins_count,
            'holes': ', '.join(map(str, holes_list)) if holes_list else 'None',
            'payout': payout_value,
        })

    # Update the Games table to set the status to 'Closed' only if wager is provided
    if wager is not None:
        # Close the Skins game
        Games.objects.filter(id=game_id).update(Status='Closed')
        # Also close the associated Forty game
        Games.objects.filter(AssocGame=game_id, Type='Forty').update(Status='Closed')

    # Pass data to the template
    context = {
        'game_id': game_id,
        'leaderboard': leaderboard,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }

    return render(request, 'GRPR/skins_close.html', context)


@login_required
def skins_closed_games_view(request):
    # Query for completed games
    completed_games = Games.objects.filter(Status='Closed', Type='Skins').select_related('CourseTeesID').order_by('-PlayDate').values(
        'id',  # GameID
        'PlayDate',
        'CourseTeesID__CourseName'  # Course name
    )

    # Initialize data for the table
    games_data = []

    # Iterate through completed games to compile winners
    for game in completed_games:
        game_id = game['id']
        play_date = game['PlayDate']
        course_name = game['CourseTeesID__CourseName']

        # Query for winners and their skin counts
        winners_query = Skins.objects.filter(GameID_id=game_id).select_related('PlayerID').values(
            'PlayerID__LastName'
        ).annotate(
            skin_count=Count('id')
        ).order_by('-skin_count', 'PlayerID__LastName')

        # Compile winners into a single string
        winners = ', '.join([f"{winner['PlayerID__LastName']} {winner['skin_count']}" for winner in winners_query])

        # Add game data to the list
        games_data.append({
            'game_id': game_id,  
            'date': play_date,
            'course': course_name,
            'winners': winners if winners else 'No Skins Won'
        })

    # Pass data to the template
    context = {
        'games_data': games_data,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }

    return render(request, 'GRPR/skins_closed_games.html', context)


@login_required
def skins_reopen_game_view(request):
    # Retrieve game_id from query parameters
    game_id = request.GET.get('game_id')
    if not game_id:
        return HttpResponseBadRequest("Game ID is missing.")

    # Update the game status to 'Live'
    Games.objects.filter(id=game_id).update(Status='Live')

    # Get the logged-in user's details
    user = request.user
    player = Players.objects.filter(user=user).values('id', 'FirstName', 'LastName').first()
    if not player:
        return HttpResponseBadRequest("Player not found for the logged-in user.")

    # Insert a new row into the Log table
    Log.objects.create(
        SentDate=now(),
        Type='Skins game re-opened',
        RequestDate=Games.objects.filter(id=game_id).values_list('PlayDate', flat=True).first(),
        OfferID=player['id'],
        RefID=game_id,
        Msg=f"{player['FirstName']} {player['LastName']} re-opened Skins game id {game_id} for {player['RequestDate']}"
    )

    # Redirect to skins.html
    return redirect('skins_view')


##########################
####  Forty Section   ####
##########################

@login_required
def forty_view(request):
    user = request.user


    context = {
        'first_name': user.first_name,
        'last_name': user.last_name,
    }

    return render(request, 'GRPR/forty.html', context)


@login_required
def forty_config_view(request):
    # Find a live Skins game with a future PlayDate
    now = timezone.now().date()
    live_game = Games.objects.filter(Status='Live', Type='Skins', PlayDate__gte=now).order_by('PlayDate').first()
    game_format = live_game.Format

    live_skins_msg = None
    group_list = []

    if live_game:
        live_skins_msg = "There is a live Skins game, using those groups/tees for this game"
        # Get all ScorecardMeta rows for this game
        scm_qs = ScorecardMeta.objects.filter(GameID=live_game.id).select_related('PID')
        # Build a dict: {group_id: [LastName, ...]}
        groups = {}
        for scm in scm_qs:
            group_id = scm.GroupID
            last_name = scm.PID.LastName
            if group_id not in groups:
                groups[group_id] = []
            groups[group_id].append(last_name)
        # Prepare for template: list of (group_id, [LastName, ...])
        group_list = [
            {'group_id': group_id, 'last_names': sorted(names)}
            for group_id, names in groups.items()
        ]
        group_list.sort(key=lambda g: g['group_id'])
    else:
        live_skins_msg = "No live Skins game found. Please create one first."
    
    print("DEBUG config game_format = ", game_format)

    context = {
        'live_skins_msg': live_skins_msg,
        'group_list': group_list,
        'game_id': live_game.id if live_game else None,
        'game_format': game_format,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }
    return render(request, 'GRPR/forty_config.html', context)



@login_required
def forty_config_confirm_view(request):
    if request.method != "POST":
        return redirect("forty_config_view")

    # ------------------------------------------------------------------
    # pull the form fields we just POSTed
    # ------------------------------------------------------------------
    game_id     = request.POST.get("game_id")
    num_scores  = request.POST.get("num_scores")
    game_format = request.POST.get("game_format")
    min_1st     = request.POST.get("min_1st")
    min_18th    = request.POST.get("min_18th")

    group_list = []
    if game_id:
        scm_qs = (
            ScorecardMeta.objects
            .filter(GameID=game_id)
            .select_related("PID")
        )
        groups = {}
        for scm in scm_qs:
            groups.setdefault(scm.GroupID, []).append(scm.PID.LastName)

        group_list = [
            {"group_id": gid, "last_names": sorted(names)}
            for gid, names in groups.items()
        ]
        group_list.sort(key=lambda g: g["group_id"])
    
    print("DEBUG want_gascup =", request.session.get("want_gascup"))
    print("DEBUG skins_game_id =", request.session.get("skins_game_id"))
    print("DEBUG config confirm game_format = ", game_format)

    context = {
        "group_list":  group_list,
        "num_scores":  num_scores,
        "game_format": game_format,
        "min_1st":     min_1st,
        "min_18th":    min_18th,
        "game_id":     game_id,
        "first_name":  request.user.first_name,
        "last_name":   request.user.last_name,
    }
    return render(request, "GRPR/forty_config_confirm.html", context)
    

@login_required
def forty_game_creation_view(request):
    """
    Final step in Forty setup: create the Forty Game row and (optionally)
    hand off to Gas Cup team assignment if the user selected Gas Cup back
    on games_choice_view.
    """
    if request.method != "POST":
        return redirect("forty_config_view")

    # ------------------------------------------------------------------
    # Pull the posted Skins game id + Forty config fields
    # NOTE: game_id here is the *Skins* game we are associating to.
    # ------------------------------------------------------------------
    game_id     = request.POST.get('game_id')          # Skins id!
    game_format = request.POST.get('game_format')
    num_scores  = request.POST.get('num_scores')
    min_1st     = request.POST.get('min_1st')
    min_18th    = request.POST.get('min_18th')

    # Logged-in player (creator)
    logged_in_user = get_object_or_404(Players, user_id=request.user.id)
    logged_in_pid  = logged_in_user.id

    # Skins game info (PlayDate, tees, etc.)
    skins_game = get_object_or_404(Games, id=game_id)
    play_date  = skins_game.PlayDate
    ct_id      = skins_game.CourseTeesID_id

    # ------------------------------------------------------------------
    # Create the Forty game row
    # ------------------------------------------------------------------
    new_game = Games.objects.create(
        CreateID_id   = logged_in_pid,
        CrewID        = 1,
        CreateDate    = timezone.now(),
        PlayDate      = play_date,
        CourseTeesID_id = ct_id,
        Status        = 'Live',
        Type          = 'Forty',
        Format        = game_format,
        NumScores     = num_scores,
        Min1          = min_1st,
        Min18         = min_18th,
        AssocGame     = game_id,            # link back to Skins
    )
    forty_id = new_game.id

    # Update Skins row to cross-link back to the Forty row
    Games.objects.filter(id=game_id).update(AssocGame=forty_id)

    # Log
    Log.objects.create(
        SentDate    = timezone.now(),
        Type        = 'Forty Creation',
        RequestDate = play_date,
        OfferID     = logged_in_pid,
        Msg         = f'{logged_in_user.LastName} created Forty game {forty_id} from Skins {game_id}',
    )

    # ------------------------------------------------------------------
    # Gas Cup hand-off?
    #   We check/consume the flag *here* (final Forty step).
    #   Ensure we still have the Skins id in session so the GasCup
    #   team screen knows what to link to.
    # ------------------------------------------------------------------
    if request.session.pop("want_gascup", False):
        if "skins_game_id" not in request.session:
            request.session["skins_game_id"] = int(game_id)
            request.session.modified = True
        return redirect("gascup_team_assign_view")

    # ------------------------------------------------------------------
    # No Gas Cup → normal redirect back to Skins leaderboard
    # ------------------------------------------------------------------
    return redirect(f"{reverse('skins_leaderboard_view')}?game_id={game_id}")



@login_required
def forty_choose_score_view(request):
    hole_id = request.GET.get('hole_id') or request.POST.get('hole_id')
    game_id = request.GET.get('game_id') or request.POST.get('game_id')
    group_id = request.GET.get('group_id') or request.POST.get('group_id')


    hole = get_object_or_404(CourseHoles, id=hole_id)
    hole_number = hole.HoleNumber

    player_scores = Scorecard.objects.filter(
        GameID_id=game_id,
        HoleID_id=hole_id,
        smID__GroupID=group_id
    ).select_related('smID__PID').values(
        'smID__PID__id','smID__PID__FirstName', 'smID__PID__LastName', 'NetScore'
    )

    next_hole = CourseHoles.objects.filter(
        CourseTeesID=hole.CourseTeesID, HoleNumber__gt=hole.HoleNumber
    ).order_by('HoleNumber').first()
    next_hole_id = next_hole.id if next_hole else None

    # Get the AssocGame (Forty game id) for this Skins game
    forty_game_id = Games.objects.filter(id=game_id).values_list('AssocGame', flat=True).first()

    # Efficiently gather stats
    scores_used = Forty.objects.filter(GameID_id=forty_game_id, GroupID=group_id).count()
    scores_played = Scorecard.objects.filter(GameID_id=game_id, smID__GroupID=group_id).count()
    num_scores = Games.objects.filter(id=forty_game_id).values_list('NumScores', flat=True).first() or 0
    scores_needed = num_scores - scores_used
    scores_available = 76 - scores_played #ack.  this is 76 instead of 72 bc when the user sees this, the scores have been entered into scorecard (4 used) but can yet still be chosen for Forty
    scores_after_this_hole = scores_available - 4
    scores_min = scores_needed - scores_after_this_hole # minimum scores required to be used for this hole

    par = Forty.objects.filter(GameID_id=forty_game_id, GroupID=group_id).aggregate(total=Sum('Par'))['total'] or 0
    group_score = Forty.objects.filter(GameID_id=forty_game_id, GroupID=group_id).aggregate(total=Sum('NetScore'))['total'] or 0
    over_under = group_score - par

    error_msg = None
    print('hole #', hole_number)

    # Check if the user has already chosen players for this hole, but got sent back to this view bc they did not choose enough based on requirements (3 on 1, 3 on 18, etc)
    if request.method == "POST":
        selected_players = request.POST.getlist('selected_players')
        request.session['chosen_players'] = selected_players
        return redirect(f"{reverse('forty_confirm_score_view')}?hole_id={hole_id}&game_id={game_id}&group_id={group_id}&next_hole_id={next_hole_id}&forty_game_id={forty_game_id}")

    context = {
        'hole': hole,
        'player_scores': player_scores,
        'game_id': game_id,
        'group_id': group_id,
        'next_hole_id': next_hole_id,
        'forty_game_id': forty_game_id,
        'scores_used': scores_used,
        'scores_played': scores_played,
        'num_scores': num_scores,
        'scores_needed': scores_needed,
        'scores_available': scores_available,
        'scores_min': scores_min,
        'par': par,
        'group_score': group_score,
        'over_under': over_under,
        'error_msg': error_msg,
    }
    return render(request, 'GRPR/forty_choose_score.html', context)


@login_required
def forty_confirm_score_view(request):
    if request.method == "POST":
        hole_id = request.POST.get('hole_id')
        game_id = request.POST.get('game_id')
        group_id = request.POST.get('group_id')
        next_hole_id = request.POST.get('next_hole_id')
        forty_game_id = request.POST.get('forty_game_id')
        # get all selected player IDs (checkboxes)
        selected_players = request.POST.getlist('selected_players')

        # get Game info for variables
        game = get_object_or_404(Games, id=forty_game_id)
        min1 = game.Min1
        min18 = game.Min18
        
        # Get hole number
        hole = get_object_or_404(CourseHoles, id=hole_id)
        hole_number = hole.HoleNumber

        # Gather stats needed for validation
        scores_used = Forty.objects.filter(GameID_id=forty_game_id, GroupID=group_id).count()
        scores_played = Scorecard.objects.filter(GameID_id=game_id, smID__GroupID=group_id).count()
        num_scores = Games.objects.filter(id=forty_game_id).values_list('NumScores', flat=True).first() or 0
        scores_needed = num_scores - scores_used
        scores_available = 76 - scores_played
        scores_after_this_hole = scores_available - 4
        scores_min = scores_needed - scores_after_this_hole  # minimum scores required to be used for this hole

        # checks for number of scores that can be used prior to 18
        max_scores_usable_priot_to_18 = num_scores - min18

        error_msg = None

        # --- Begin Validation Logic ---
        # 1. If hole == 1, must select at least 3 scores
        if int(hole_number) == 1 and len(selected_players) < min1:
            error_msg = "On the 1st hole, you must use at least three scores."

        # 2. If scores_min > 0, must select at least scores_min scores
        elif scores_min > 0 and len(selected_players) < scores_min:
            error_msg = (
                f"Must use at least {scores_min} on this hole."
            )

        # 3. If scores_needed < 7 and not hole 18, limit max scores
        elif max_scores_usable_priot_to_18 - scores_used < 4 and int(hole_number) != 18:
            scores_max = max_scores_usable_priot_to_18 - scores_used
            if len(selected_players) > scores_max:
                error_msg = (
                    f"{scores_used} scores have been used, can only use {scores_max} more scores prior to 18 (where you must use at least {min18})."
                )

        # 4. If hole == 18, must use exactly scores_min scores
        elif int(hole_number) == 18:
            if len(selected_players) != scores_min:
                error_msg = f"Must use exactly {scores_min} scores on 18."

        # --- If any error, re-render choose page with error ---
        if error_msg:
            player_scores = Scorecard.objects.filter(
                GameID_id=game_id,
                HoleID_id=hole_id,
                smID__GroupID=group_id
            ).select_related('smID__PID').values(
                'smID__PID__id','smID__PID__FirstName', 'smID__PID__LastName', 'NetScore'
            )
            next_hole = CourseHoles.objects.filter(
                CourseTeesID=hole.CourseTeesID, HoleNumber__gt=hole.HoleNumber
            ).order_by('HoleNumber').first()
            next_hole_id = next_hole.id if next_hole else None
            par = Forty.objects.filter(GameID_id=forty_game_id, GroupID=group_id).aggregate(total=Sum('Par'))['total'] or 0
            group_score = Forty.objects.filter(GameID_id=forty_game_id, GroupID=group_id).aggregate(total=Sum('NetScore'))['total'] or 0
            over_under = group_score - par

            context = {
                'hole': hole,
                'player_scores': player_scores,
                'game_id': game_id,
                'group_id': group_id,
                'next_hole_id': next_hole_id,
                'forty_game_id': forty_game_id,
                'scores_used': scores_used,
                'scores_played': scores_played,
                'num_scores': num_scores,
                'scores_needed': scores_needed,
                'scores_available': scores_available,
                'scores_min': scores_min,
                'par': par,
                'group_score': group_score,
                'over_under': over_under,
                'error_msg': error_msg,
            }
            return render(request, 'GRPR/forty_choose_score.html', context)

        # --- If all checks pass, proceed as normal ---
        player_scores = Scorecard.objects.filter(
            GameID_id=game_id,
            HoleID_id=hole_id,
            smID__GroupID=group_id
        ).select_related('smID__PID', 'HoleID')

        chosen_scores = []
        for score in player_scores:
            pid = str(score.smID.PID.id)
            if pid in selected_players:
                chosen_scores.append({
                    'PlayerID': score.smID.PID.id,
                    'LastName': score.smID.PID.LastName,
                    'RawScore': score.RawScore,
                    'NetScore': score.NetScore,
                    'Par': score.HoleID.Par,
                })

        context = {
            'hole_id': hole_id,
            'game_id': game_id,
            'group_id': group_id,
            'next_hole_id': next_hole_id,
            'forty_game_id': forty_game_id,
            'chosen_scores': chosen_scores,
            'scores_used': scores_used,
            'scores_played': scores_played,
            'num_scores': num_scores,
            'scores_needed': scores_needed,
            'scores_available': scores_available,
            'scores_min': scores_min,
        }
        return render(request, 'GRPR/forty_confirm_score.html', context)
    else:
        return redirect('forty_choose_score_view')
    

@login_required
def forty_input_scores_view(request):
    if request.method == "POST":
        hole_id = request.POST.get('hole_id')
        game_id = request.POST.get('game_id')
        group_id = request.POST.get('group_id')
        next_hole_id = request.POST.get('next_hole_id')
        forty_game_id = request.POST.get('forty_game_id')

        # Check if Forty scores already exist for this hole/group/game
        forty_scores_already_entered = False
        if forty_game_id:
            if Forty.objects.filter(
                GameID_id=forty_game_id,
                GroupID=group_id,
                HoleNumber_id=hole_id
            ).exists():
                forty_scores_already_entered = True

        if forty_scores_already_entered:
            # Prepare the message
            msg = "Forty scores have already been entered for this hole and group. No changes were made."
            # Redirect with message to the appropriate page
            if next_hole_id and str(next_hole_id).lower() != "none":
                return redirect(f"{reverse('hole_score_data_view')}?hole_id={next_hole_id}&game_id={game_id}&group_id={group_id}&msg={msg}")
            else:
                return redirect(f"{reverse('scorecard_view')}?game_id={game_id}&group_id={group_id}&msg={msg}")
        # If no scores exist, proceed to input scores

        # Get logged-in user's player ID
        logged_in_user = get_object_or_404(Players, user_id=request.user.id)
        logged_in_user_player_id = logged_in_user.id

        # Get all chosen player data (multiple values per field)
        player_ids = request.POST.getlist('player_id')
        raw_scores = request.POST.getlist('raw_score')
        net_scores = request.POST.getlist('net_score')
        par = request.POST.getlist('par')

        for pid, raw, net, pr in zip(player_ids, raw_scores, net_scores, par):
            # Insert into Forty
            Forty.objects.create(
                CreateDate=now(),
                AlterDate=now(),
                CreateID=logged_in_user,
                AlterID=logged_in_user,
                CrewID=1,
                GameID_id=forty_game_id,
                HoleNumber_id=hole_id,
                PID_id=pid,
                GroupID=group_id,
                RawScore=raw,
                NetScore=net,
                Par=pr,
            )
            # Insert into Log
            Log.objects.create(
                SentDate=now(),
                Type='Forty Score',
                MessageID='None',
                OfferID=logged_in_user_player_id,
                ReceiveID=pid,
                Msg=f'Forty score inputted by {logged_in_user_player_id} for player {pid} on hole {hole_id}, raw {raw}, net {net}'
            )

        # Redirect based on next_hole_id
        if next_hole_id and str(next_hole_id).lower() != "none":
            print("Redirecting to hole_score_data_view with next_hole_id:", next_hole_id)
            return redirect(f"{reverse('hole_score_data_view')}?hole_id={next_hole_id}&game_id={game_id}&group_id={group_id}")
        else:
            print("Redirecting to scorecard_view (end of round)")
            return redirect(f"{reverse('scorecard_view')}?game_id={game_id}&group_id={group_id}")
    else:
        return redirect('home')
    

def _draft_for_user_or_redirect(request, need_date=True, need_course=True, need_assignments=True):
    """
    Fetch the most recent in-progress draft for the logged-in user.
    Optionally enforce that certain prior steps are completed.
    """
    draft = (GameSetupDraft.objects
             .filter(created_by=request.user, is_complete=False)
             .order_by("-updated_at", "-created_at")
             .first())
    if not draft:
        return None, redirect("game_setup_date")
    if need_date and not draft.event_date:
        return None, redirect("game_setup_date")
    if need_course and not draft.course_id:
        return None, redirect("game_setup_course")

    # assignments/players chosen on previous steps
    state = draft.state or {}
    if need_assignments and not state.get("assignments"):
        # if you split groups selection & assignment into two views,
        # redirect to assignment view; otherwise redirect to groups view
        return None, redirect("game_setup_assign")

    return draft, None

@login_required
@require_http_methods(["GET", "POST"])
def game_setup_config_view(request):
    """
    Step 5/6: General configuration (tees & handicap mode).
    - Shows a summary of chosen date, course, tee times, and assigned players.
    - Lets the user pick a tee set for the game and a handicap mode.
    - Saves choices back into GameSetupDraft.state (and tee_choice field).
    - Does not create Games / GameInvites (that will happen on the final step).
    """
    draft, redir = _draft_for_user_or_redirect(
        request, need_date=True, need_course=True, need_assignments=True
    )
    if redir:
        return redir

    # Resolve course & tee options
    course = Courses.objects.filter(id=draft.course_id).only("id", "courseName").first()

    tee_rows = (
        CourseTees.objects
        .filter(CourseID=draft.course_id)
        .order_by("TeeID", "id")
        .values("id", "TeeName", "CourseRating", "Yards")   # <-- dicts
    )

    tee_options = [
        {
            "id":     r["id"],
            "name":   r["TeeName"],
            "rating": r["CourseRating"],
            "yards":  r["Yards"],
        }
        for r in tee_rows
    ]

    # Pull assignment summary from draft.state
    state = draft.state or {}
    assignments = state.get("assignments") or {}   # {"9:04": [pid, pid, ...], ...}
    player_ids = {pid for plist in assignments.values() for pid in plist}
    players = {
        p.id: p
        for p in Players.objects.filter(id__in=player_ids).only("id", "FirstName", "LastName")
    }
    num_players = len(player_ids)

    # If coming here directly with forwarded JSON, accept it and persist
    if request.method == "POST" and request.POST.get("carry_forward_json"):
        try:
            forwarded = json.loads(request.POST.get("carry_forward_json") or "{}")
            if "assignments" in forwarded and isinstance(forwarded["assignments"], dict):
                state["assignments"] = forwarded["assignments"]
                draft.state = state
                draft.save(update_fields=["state", "updated_at"])
                assignments = forwarded["assignments"]
                player_ids = {pid for plist in assignments.values() for pid in plist}
                players = {
                    p.id: p
                    for p in Players.objects.filter(id__in=player_ids).only("id", "FirstName", "LastName")
                }
                num_players = len(player_ids)
        except Exception:
            # Ignore parse errors; fall back to what’s already in the draft
            pass

    # Handle configuration submit (tee + handicap)
    if request.method == "POST" and request.POST.get("action") == "save_config":
        tee_id_raw = (request.POST.get("tee_id") or "").strip()
        hc_mode    = (request.POST.get("handicap_mode") or "Low").strip()  # "Low" or "Full"

        chosen_tee = None
        if tee_id_raw.isdigit():
            chosen_tee = CourseTees.objects.filter(
                CourseID=draft.course_id, id=int(tee_id_raw)
            ).first()

        if not chosen_tee:
            messages.warning(request, "Please choose a tee set.")
        else:
            # Persist to draft
            state["handicap_mode"] = hc_mode
            state["tee_id"] = chosen_tee.id
            state["tee_label"] = chosen_tee.TeeName
            draft.state = state
            draft.tee_choice = chosen_tee.TeeName
            draft.save(update_fields=["state", "tee_choice", "updated_at"])

            messages.success(request, "Configuration saved.")
            # NEXT: route to your next step (games selection / review)
            return redirect("games_view")  # adjust when you add the next screen

    # Build display like skins_config: [{"label": "9:04", "players": [{"id":..., "name":...}, ...]}, ...]
    tee_times_for_display = []
    for tt in sorted(assignments.keys()):
        plist = []
        for pid in assignments.get(tt, []):
            p = players.get(pid)
            if p:
                plist.append({"id": pid, "name": f"{p.FirstName} {p.LastName}"})
        tee_times_for_display.append({"label": tt, "players": plist})

    context = {
        "first_name": request.user.first_name,
        "last_name":  request.user.last_name,
        "playing_date": draft.event_date,
        "number_of_players": num_players,
        "course_name": course.courseName if course else "—",
        "tee_options": tee_options,                    # list of {"id","label"}
        "tee_times": tee_times_for_display,
        "progress": {
            "current": 5, "total": 6,
            "labels": ["date", "course", "players", "tee times", "configuration", "review"],
        },
        "progress_pct": f"{int(5/6*100)}%",
        "selected_tee_id": state.get("tee_id"),
        "selected_handicap_mode": state.get("handicap_mode", "Low"),
    }
    return render(request, "GRPR/game_setup_config.html", context)

    

##########################
#### Gas Cup Section  ####
##########################

# ─── Team-assignment view  ────────────────────────────────────────────
@login_required
def gascup_team_assign_view(request):
    """
    Show ‘radio table’ version and, on POST, create Gas Cup + GasCupPair rows.

    Supports 4-ball (2 vs 2) and 3-ball (2 vs 1) group compositions.
    When a side has only one player, PID2 is stored as NULL in GasCupPair,
    and downstream best-ball logic will just use that one player's score.
    """
    skins_id = request.session.get("skins_game_id")
    skins_game = get_object_or_404(Games, pk=skins_id, Type="Skins")

    players = (
        GameInvites.objects
        .filter(GameID=skins_game)
        .select_related("PID", "TTID__CourseID")
        .order_by("TTID__CourseID__courseTimeSlot", "PID__LastName")
    )

    # ---------- POST: validate radio choices -------------------------
    if request.method == "POST":
        # pid -> "PGA"/"LIV"
        assignments = {
            int(k.split("_", 1)[1]): v
            for k, v in request.POST.items()
            if k.startswith("p_")
        }

        # ----- VALIDATE (allows 4-ball 2/2 OR 3-ball 2/1) --------------
        errors = _validate_gascup_teams(players, assignments)
        if errors:
            # Re-render with errors and the user's selections preserved
            for e in errors:
                messages.error(request, e)
            return render(request, "GRPR/gascup_team_assign.html", {
                "players":    players,
                "skins_game": skins_game,
                "teams":      ("PGA", "LIV"),
                "first_name": request.user.first_name,
                "last_name":  request.user.last_name,
                "assignments": assignments,   # pass selections back
            })

        # ---------- create rows in one transaction -------------------
        with transaction.atomic():
            gas_game = Games.objects.create(
                CrewID     = 1,
                CreateDate = timezone.now().date(),
                PlayDate   = skins_game.PlayDate,
                CreateID   = skins_game.CreateID,
                Status     = "Live",
                Type       = "GasCup",
                AssocGame  = skins_game.id,
            )

            for slot, group in itertools.groupby(
                    players,
                    key=lambda x: x.TTID.CourseID.courseTimeSlot):
                group = list(group)

                pga_ids = sorted([p.PID_id for p in group if assignments[p.PID_id] == "PGA"])
                liv_ids = sorted([p.PID_id for p in group if assignments[p.PID_id] == "LIV"])

                def _second(lst):
                    return lst[1] if len(lst) > 1 else None

                GasCupPair.objects.create(
                    Game=gas_game,
                    PID1_id=pga_ids[0],
                    PID2_id=_second(pga_ids),   # None OK for 2-v-1
                    Team="PGA",
                )
                GasCupPair.objects.create(
                    Game=gas_game,
                    PID1_id=liv_ids[0],
                    PID2_id=_second(liv_ids),
                    Team="LIV",
                )

        messages.success(request, "Gas Cup game created!")
        return redirect("skins_leaderboard_view")

    # ---------- GET: render radio-table form -------------------------
    return render(request, "GRPR/gascup_team_assign.html", {
        "players":    players,
        "skins_game": skins_game,
        "teams":      ("PGA", "LIV"), 
        "first_name": request.user.first_name,
        "last_name":  request.user.last_name,
    })


def _validate_gascup_teams(invites, assignments):
    """
    Acceptable per-foursome splits:
      • 4 players -> exactly 2 PGA / 2 LIV
      • 3 players -> 2/1 or 1/2

    `invites`     queryset of GameInvites (must be ordered but ordering
                  not required for correctness here).
    `assignments` dict {pid: "PGA"/"LIV"} parsed from POST.

    Return list of error strings (empty == OK).
    """
    by_slot = {}  # slot string -> counts dict
    for inv in invites:
        slot = inv.TTID.CourseID.courseTimeSlot  # shared tee time label
        d = by_slot.setdefault(slot, {"size": 0, "PGA": 0, "LIV": 0})
        d["size"] += 1
        team = assignments.get(inv.PID_id)
        if team in ("PGA", "LIV"):
            d[team] += 1

    errs = []
    for slot, d in by_slot.items():
        size = d["size"]
        pga  = d["PGA"]
        liv  = d["LIV"]

        if size == 4:
            if pga != 2 or liv != 2:
                errs.append(f"{slot}: need 2 PGA + 2 LIV (now {pga}/{liv})")
        elif size == 3:
            if not ((pga == 2 and liv == 1) or (pga == 1 and liv == 2)):
                errs.append(f"{slot}: for 3-ball use 2/1 split (now {pga}/{liv})")
        else:
            errs.append(f"{slot}: unsupported group size ({size})")

    return errs


####################################
#### New Game Creation Workflow ####
####################################

from django.db import connection

def _get_user_crew_id(user) -> int:
    """
    Resolve the user's CrewID from the legacy Players table.

    Strategy:
      1) Try the Django model `Players` if it exists, reading `.CrewID`.
      2) Fallback to raw SQL against the `Players` table, trying common
         column-name variants for both user and crew columns.
      3) Default to 1 if we can't resolve cleanly.
    """
    # 1) Try via ORM if the model is present
    try:
        # Common case: fields are user_id and CrewID on the model
        rec = Players.objects.filter(user_id=user.id).only("CrewID").first()
        if rec:
            crew = getattr(rec, "CrewID", None)
            if crew:
                return int(crew)
    except Exception:
        # Model might not be present or field names differ — fall through to SQL
        pass

    # 2) Fallback: raw SQL (tolerant to column-case variations)
    user_col_candidates = ("user_id", "UserID", "User_id", "userid")
    crew_col_candidates = ("CrewID", "crew_id", "CrewId", "crewid")

    with connection.cursor() as cur:
        for ucol in user_col_candidates:
            for ccol in crew_col_candidates:
                try:
                    # Quote identifiers to be safe with case-sensitive backends
                    cur.execute(
                        f'SELECT "{ccol}" FROM "Players" WHERE "{ucol}" = %s LIMIT 1',
                        [user.id],
                    )
                    row = cur.fetchone()
                except Exception:
                    # Column combo didn’t exist; try the next pair
                    continue

                if row and row[0] is not None:
                    try:
                        return int(row[0])
                    except (TypeError, ValueError):
                        pass

    # 3) Fallback so pages still render
    return 1


@login_required
def game_setup_date_view(request):
    """
    Step 1: choose a date (with a suggested 'next available' for the user's crew).
    Creates or resumes a GameSetupDraft and stores its id in session.
    """
    crew_id = _get_user_crew_id(request.user)

    # Create or resume draft
    draft_id = request.session.get("game_setup_id")
    draft = None
    if draft_id:
        draft = GameSetupDraft.objects.filter(
            pk=draft_id, created_by=request.user, is_complete=False
        ).first()
    if not draft:
        draft = GameSetupDraft.objects.create(created_by=request.user, crew_id=crew_id)
        request.session["game_setup_id"] = draft.pk

    # Try to compute a "suggested next date" card from your tee time tables.
    suggested = None
    try:
        # TODO: adjust these imports/field names to match your models.
        # These are written to *not* crash if you don't have these models/fields yet.
        from .models import TeeTimesInd, Courses  # adjust if your app models differ

        # Find earliest date with any rows for this crew
        # CHANGE fields if needed: e.g., TeeTimesInd has fields like: crew_id/CrewID, date/teeDate, CourseID_id, etc.
        bucket = (
            TeeTimesInd.objects
            .filter(CrewID=crew_id, teeDate__gte=today)        # <— adjust field names
            .values("teeDate")
            .annotate(num_players=Count("id"), any_course=Max("CourseID_id"))
            .order_by("teeDate")
            .first()
        )

        if bucket:
            course_name = ""
            tee_times = []

            if bucket["any_course"]:
                c = Courses.objects.filter(pk=bucket["any_course"]).first()
                # CHANGE property names if your Courses model differs
                course_name = getattr(c, "courseName", "") if c else ""

                # If you store time slots on the course model (as 'courseTimeSlot'), gather distinct ones
                # Otherwise, you might want distinct times from the tee times table for that date.
                if hasattr(Courses, "objects") and hasattr(c, "courseTimeSlot"):
                    tee_times = list(
                        Courses.objects
                        .filter(pk=bucket["any_course"])
                        .values_list("courseTimeSlot", flat=True)
                        .distinct()
                    )  # may be empty if you don't use this field
                else:
                    # As a fallback: distinct times from TeeTimesInd for that date:
                    tee_times = list(
                        TeeTimesInd.objects
                        .filter(CrewID=crew_id, teeDate=bucket["teeDate"])  # <— adjust
                        .values_list("teeTime", flat=True)                  # <— adjust
                        .distinct()
                    )

            suggested = {
                "date": bucket["teeDate"],
                "num_players": bucket["num_players"],
                "course_name": course_name,
                "tee_times": tee_times,
            }
    except Exception:
        # If models/fields don't line up, we still render the page w/o the suggested card.
        suggested = None

    if request.method == "POST":
        chosen = (request.POST.get("event_date") or "").strip()
        ev_date = parse_date(chosen)
        if not ev_date:
            messages.error(request, "Please choose a valid date.")
            return redirect("game_setup_date")

        draft.event_date = ev_date
        draft.save(update_fields=["event_date", "updated_at"])

        # NEXT: course selection step (we'll add that in the next chunk)
        # For now, go back to Games home so you can see the flow working.
        messages.success(request, f"Date saved: {ev_date}. Next step will be course selection.")
        return redirect("game_setup_course")  
    
    progress = {
        "current": 1,
        "total": 6,
        "labels": ["Date", "Course", "Players", "Tee times", "Games", "Config"],
    }
    progress_pct = int(progress["current"] * 100 / progress["total"])

    return render(request, "GRPR/game_setup_date.html", {
        "draft": draft,
        "suggested": suggested,
        "progress": progress,
        "progress_pct": progress_pct,
    })


from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .models import GameSetupDraft, Courses

@login_required
def game_setup_course_view(request):
    """
    Step 2/6: Course choice.
    - Requires an existing draft with event_date.
    - Presents a distinct list of course names pulled from Courses.
    - Saves the chosen CourseID to the draft, then goes to the next step.
    """

    # Get the user’s most recent open draft (created at step 1)
    draft = (
        GameSetupDraft.objects
        .filter(created_by=request.user, is_complete=False)
        .order_by("-updated_at", "-created_at")
        .first()
    )
    if not draft or not draft.event_date:
        return redirect("game_setup_date")

    # Resolve the user’s crew (legacy lookup helper you added earlier)
    crew_id = _get_user_crew_id(request.user)

    # Build a distinct list of course names with a representative id.
    # Prefer courses for this crew; if none, fall back to all courses.
    base_qs = Courses.objects.filter(crewID=crew_id)
    if not base_qs.exists():
        base_qs = Courses.objects.all()

    # DISTINCT by courseName, pick the smallest id for that name
    rows = (
        base_qs
        .values("courseName")
        .annotate(id_rep=Min("id"))
        .order_by("courseName")
    )
    course_options = [
        {"id": r["id_rep"], "name": (r["courseName"] or "").strip()}
        for r in rows
        if (r["courseName"] or "").strip()
    ]

    # Handle form submission
    if request.method == "POST":
        course_id = (request.POST.get("course_id") or "").strip()
        chosen = None
        if course_id.isdigit():
            chosen = Courses.objects.filter(pk=int(course_id)).only("id", "courseName").first()

        if not chosen:
            return render(request, "GRPR/game_setup_course.html", {
                "draft": draft,
                "courses": course_options,
                "progress": {
                    "current": 2, "total": 6,
                    "labels": ["date", "course", "players", "tee times", "games", "configuration"],
                },
                "progress_pct": f"{int(2/6*100)}%",
                "error": "Please choose a course.",
            })

        # Save selection to the draft (and stash readable name in state)
        draft.course_id = chosen.id
        state = dict(draft.state or {})
        state["courseName"] = chosen.courseName
        draft.state = state
        draft.save(update_fields=["course_id", "state", "updated_at"])

        # Next step (players) — adjust if your URL name differs
        return redirect("game_setup_players")

    # GET
    return render(request, "GRPR/game_setup_course.html", {
        "draft": draft,
        "courses": course_options,
        "progress": {
            "current": 2, "total": 6,
            "labels": ["date", "course", "players", "tee times", "games", "configuration"],
        },
        "progress_pct": f"{int(2/6*100)}%",
    })


@login_required
def game_setup_players_view(request):
    """
    Step 3/6: Choose players.
    - Requires a draft with event_date (step 1) and course_id (step 2).
    - Lists players in the user's crew (Members only by default, with an option
      to include non-members).
    - Stores selected player IDs in draft.state["player_ids"] (list of ints).
    """
    # Fetch the user's most-recent in-progress draft
    draft = (
        GameSetupDraft.objects
        .filter(created_by=request.user, is_complete=False)
        .order_by("-updated_at", "-created_at")
        .first()
    )
    if not draft:
        return redirect("game_setup_date")
    if not draft.event_date:
        return redirect("game_setup_date")
    if not draft.course_id:
        return redirect("game_setup_course")

    # Read current filter state (include non-members or not)
    # Keep it sticky across POST/GET via query param + local variable.
    show_all = request.GET.get("show_all") == "1"

    # Build player queryset for this crew
    qs = Players.objects.filter(CrewID=draft.crew_id).only("id", "FirstName", "LastName", "Member")
    if not show_all:
        qs = qs.filter(Member=1)
    else:
            # Include non-members = Member is 1 OR NULL
            qs = qs.filter(Q(Member=1) | Q(Member=0))

    # Order by last name, first name (case-insensitive-ish)
    qs = qs.order_by("LastName", "FirstName")

    # Pre-fill any existing selection (from state)
    state = draft.state or {}
    selected_ids = set(state.get("player_ids") or [])

    if request.method == "POST":
        # Gather selections; POST loses querystring, so preserve show_all via hidden input
        show_all = (request.POST.get("show_all") == "1")

        chosen = request.POST.getlist("player_ids")
        # Validate -> keep only ints that are in this crew
        valid_ids = set(
            qs.filter(id__in=[int(x) for x in chosen if x.isdigit()])
              .values_list("id", flat=True)
        )

        if not valid_ids:
            # Re-render with an error and keep whatever was already selected
            return render(request, "GRPR/game_setup_players.html", {
                "draft": draft,
                "players": qs,
                "selected_ids": selected_ids,
                "show_all": show_all,
                "error": "Please select at least one player.",
                "progress": {
                    "current": 3, "total": 6,
                    "labels": ["date", "course", "players", "tee times", "games", "configuration"],
                },
                "progress_pct": f"{int(3/6*100)}%",
            })

        # Persist selection to the draft.state JSON
        state["player_ids"] = sorted(list(valid_ids))
        draft.state = state
        draft.save(update_fields=["state", "updated_at"])

        # NEXT STEP (placeholder): send to the “Choose Groups / Tee Times” step.
        # Update this when you add the next page.
        return redirect("game_setup_groups")

    # GET: render
    return render(request, "GRPR/game_setup_players.html", {
        "draft": draft,
        "players": qs,
        "selected_ids": selected_ids,
        "show_all": show_all,
        "progress": {
            "current": 3, "total": 6,
            "labels": ["date", "course", "players", "tee times", "games", "configuration"],
        },
        "progress_pct": f"{int(3/6*100)}%",
    })


@login_required
def game_setup_groups_view(request):
    """
    Step 3/6: Choose tee times for the selected course.
    - Uses GameSetupDraft with event_date + course_id already chosen.
    - Shows distinct tee times for (crew_id, courseName).
    - Lets the user add a new tee time (deduped by normalization).
    - Persists list of selected tee times in draft.state["teetimes"] and
      on success redirects to Step 4 (assign players).
    """
    draft = (
        GameSetupDraft.objects
        .filter(created_by=request.user, is_complete=False)
        .order_by("-updated_at", "-created_at")
        .first()
    )
    if not draft:
        return redirect("game_setup_date")
    if not draft.event_date:
        return redirect("game_setup_date")
    if not draft.course_id:
        return redirect("game_setup_course")

    # Find the chosen courseName for this course_id
    course_row = Courses.objects.filter(id=draft.course_id).only("courseName", "crewID").first()
    if not course_row:
        messages.error(request, "Course not found. Please choose the course again.")
        return redirect("game_setup_course")

    course_name = course_row.courseName
    crew_id = draft.crew_id

    # Distinct tee times for this (courseName, crewID)
    existing_qs = (
        Courses.objects
        .filter(courseName=course_name, crewID=crew_id)
        .exclude(courseTimeSlot__isnull=True)
        .exclude(courseTimeSlot__exact="")
        .values_list("courseTimeSlot", flat=True)
        .distinct()
        .order_by("courseTimeSlot")
    )
    existing = list(existing_qs)

    # Use any previously selected set from state
    state = draft.state or {}
    selected = list(state.get("teetimes") or [])

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()  # 'continue' or 'add_and_continue'
        # Checkboxes: <input type="checkbox" name="teetimes" value="8:04">
        chosen = request.POST.getlist("teetimes")

        # Normalize + dedupe chosen
        norm_chosen = []
        seen = set()
        for raw in chosen:
            lab = _normalize_teetime_label(raw) or raw.strip()
            if not lab:
                continue
            key = lab.lower()
            if key not in seen:
                seen.add(key)
                norm_chosen.append(lab)

        # If an extra tee time is provided, process it
        new_tt_raw = (request.POST.get("new_teetime") or "").strip()
        if action == "add_and_continue" and new_tt_raw:
            new_norm = _normalize_teetime_label(new_tt_raw)
            if not new_norm:
                messages.warning(request, "That tee time format wasn’t recognized (try like 9:00).")
                # keep selections and fall through to render
            else:
                # Check duplicate against existing set (normalize those as well)
                existing_norm = set((_normalize_teetime_label(x) or x).lower() for x in existing)
                if new_norm.lower() in existing_norm:
                    messages.info(request, f"{new_norm} already exists for {course_name}.")
                else:
                    # Create new Courses row with same courseName + crewID
                    Courses.objects.create(
                        crewID=crew_id,
                        courseName=course_name,
                        courseTimeSlot=new_norm
                    )
                    existing.append(new_norm)
                    messages.success(request, f"Added tee time {new_norm}.")

                # Also mark it selected (if not already)
                if new_norm not in norm_chosen:
                    norm_chosen.append(new_norm)

        # Final validation: need at least one tee time before continuing
        if not norm_chosen:
            messages.error(request, "Please select at least one tee time (or add a new one).")
            return render(request, "GRPR/game_setup_groups.html", {
                "draft": draft,
                "course_name": course_name,
                "existing": existing,
                "selected": norm_chosen,  # empty -> nothing checked
                "progress": {
                    "current": 3, "total": 6,
                    "labels": ["date", "course", "players", "tee times", "games", "configuration"],
                },
                "progress_pct": f"{int(3/6*100)}%",
            })

        # Persist and move on
        state["teetimes"] = sorted(norm_chosen)
        draft.state = state
        draft.save(update_fields=["state", "updated_at"])
        return redirect("game_setup_assign")  # Step 4

    # GET
    return render(request, "GRPR/game_setup_groups.html", {
        "draft": draft,
        "course_name": course_name,
        "existing": existing,
        "selected": selected,
        "progress": {
            "current": 3, "total": 6,
            "labels": ["date", "course", "players", "tee times", "games", "configuration"],
        },
        "progress_pct": f"{int(3/6*100)}%",
    })



@login_required
def game_setup_assign_view(request):
    """
    Step 4/6: Assign players to selected tee times.
    Reads from the GameSetupDraft created by the earlier steps:
      - state["player_ids"] : list[int]
      - state["teetimes"]   : list[str]
    Writes:
      - state["assignments"]: { tee_label: [player_id, ...], ... }
    Constraints:
      - All selected players must be assigned.
      - Max 4 players per tee time.
      - No duplicates.
    """
    draft = (
        GameSetupDraft.objects
        .filter(created_by=request.user, is_complete=False)
        .order_by("-updated_at", "-created_at")
        .first()
    )
    if not draft:
        return redirect("game_setup_date")
    if not draft.event_date:
        return redirect("game_setup_date")
    if not draft.course_id:
        return redirect("game_setup_course")

    state = draft.state or {}
    player_ids = state.get("player_ids") or []
    teetimes   = state.get("teetimes") or []

    # Guard: need players & tee times selected earlier
    if not player_ids:
        messages.error(request, "Please choose players first.")
        return redirect("game_setup_players")
    if not teetimes:
        messages.error(request, "Please choose at least one tee time.")
        return redirect("game_setup_groups")  # previous step where tee times are chosen

    # Fetch player objects (limit to chosen ids)
    players_qs = (
        Players.objects
        .filter(id__in=player_ids)
        .only("id", "FirstName", "LastName")
        .order_by("LastName", "FirstName")
    )
    players = list(players_qs.values("id", "FirstName", "LastName"))

    # Existing assignments (if any)
    assignments = state.get("assignments") or {}
    # Make sure every selected tee time has a list
    for t in teetimes:
        assignments.setdefault(t, [])

    # Compute unassigned based on current assignments
    assigned_set = set()
    for vec in assignments.values():
        assigned_set.update(int(x) for x in vec if str(x).isdigit())
    unassigned = [p for p in players if p["id"] not in assigned_set]

    if request.method == "POST":
        raw = (request.POST.get("assignments_json") or "").strip()
        try:
            incoming = json.loads(raw)
        except Exception:
            incoming = None

        if not isinstance(incoming, dict):
            messages.error(request, "Could not read the assignments. Please try again.")
            return redirect("game_setup_assign")

        allowed_pids = set(int(pid) for pid in player_ids)
        cleaned = {}
        used    = set()
        valid   = True
        reason  = ""

        for tee in teetimes:
            ids = incoming.get(tee) or []
            vec = []
            for s in ids:
                try:
                    pid = int(s)
                except Exception:
                    continue
                if pid not in allowed_pids:
                    # ignore unknown ids
                    continue
                if pid in used:
                    # no duplicates
                    continue
                vec.append(pid)
                used.add(pid)
            if len(vec) > 4:
                valid = False
                reason = f"Tee time {tee} has more than 4 players."
                break
            cleaned[tee] = vec

        # Require all players assigned
        if valid and used != allowed_pids:
            valid = False
            missing = allowed_pids - used
            reason = f"Please assign all players. {len(missing)} unassigned."

        if not valid:
            # Re-render page with message and current UI state
            messages.error(request, reason or "Invalid assignment.")
            # Recalculate for page
            assigned_set = set(pid for lst in cleaned.values() for pid in lst)
            unassigned = [p for p in players if p["id"] not in assigned_set]
            return render(request, "GRPR/game_setup_assign.html", {
                "draft": draft,
                "players": players,
                "teetimes": teetimes,
                "assignments": cleaned,
                "unassigned": unassigned,
                "progress": {
                    "current": 4, "total": 6,
                    "labels": ["date", "course", "players", "tee times", "games", "configuration"],
                },
                "progress_pct": f"{int(4/6*100)}%",
                "total_players": len(players),
                "assigned_count": len(assigned_set),
            })

        # Persist to draft
        state["assignments"] = cleaned
        draft.state = state
        draft.save(update_fields=["state", "updated_at"])

        # NEXT STEP: tees & handicap config (placeholder name)
        return redirect("game_setup_config")

    # GET render
    return render(request, "GRPR/game_setup_assign.html", {
        "draft": draft,
        "players": players,
        "teetimes": teetimes,
        "assignments": assignments,
        "unassigned": unassigned,
        "progress": {
            "current": 4, "total": 6,
            "labels": ["date", "course", "players", "tee times", "games", "configuration"],
        },
        "progress_pct": f"{int(4/6*100)}%",
        "total_players": len(players),
        "assigned_count": len(assigned_set),
    })


##########################
#### Scorecard views ####
##########################

@login_required
def hole_select_view(request):
    # Get the CourseTees object with id = 4
    course_tees = get_object_or_404(CourseTees, id=4)

    # Query the CourseHoles table for the corresponding CourseTeesID
    holes = CourseHoles.objects.filter(CourseTeesID=course_tees).order_by('HoleNumber')

    # Pass the data to the template
    context = {
        'holes': holes,
        'course_name': course_tees.CourseName,  # Optional: Display the course name
    }
    return render(request, 'GRPR/hole_select.html', context)


@login_required
def hole_score_data_view(request):
    # Get the required parameters from the query string
    hole_id = request.GET.get('hole_id')
    game_id = request.GET.get('game_id')
    group_id = request.GET.get('group_id')

    # Validate that all required parameters are present
    if not hole_id or not game_id or not group_id:
        return HttpResponseBadRequest("Missing required parameters: hole_id, game_id, or group_id.")

    # Store the parameters in the session
    request.session['hole_id'] = hole_id
    request.session['game_id'] = game_id
    request.session['group_id'] = group_id

    # Redirect to hole_score_view
    return redirect('hole_score_view')


@login_required
def hole_score_view(request):
    # Retrieve the parameters from the session
    hole_id = request.session.pop('hole_id', None)
    game_id = request.session.pop('game_id', None)
    group_id = request.session.pop('group_id', None)
    msg = request.GET.get('msg', None)

    # Validate that all required parameters are present
    if not hole_id or not game_id or not group_id:
        return HttpResponseBadRequest("Missing required session data: hole_id, game_id, or group_id.")

    # Fetch the specific hole using the provided id
    hole = get_object_or_404(CourseHoles, id=hole_id)

    # Fetch the players in the specified group
    players = ScorecardMeta.objects.filter(GameID=game_id, GroupID=group_id).select_related('PID').values(
        first_name=F('PID__FirstName'),
        last_name=F('PID__LastName'),
        pid=F('PID__id'),
        scm_id=F('id'),  # Include ScorecardMeta ID
    )

    # Convert players queryset to a list of dictionaries
    player_list = list(players)

    # Fetch existing scores for the selected hole and players
    existing_scores = Scorecard.objects.filter(GameID_id=game_id, HoleID_id=hole_id).values(
        'id', 'RawScore', 'Putts', 'smID_id'
    )

    # Map existing scores by ScorecardMeta ID (scm_id)
    scores_map = {score['smID_id']: score for score in existing_scores}

    # Add existing scores and putts to the player list
    for player in player_list:
        scm_id = player['scm_id']
        if scm_id in scores_map:
            player['existing_score'] = scores_map[scm_id]['RawScore']
            player['existing_putts'] = scores_map[scm_id]['Putts']
            player['scorecard_id'] = scores_map[scm_id]['id']  # Include the Scorecard row ID
        else:
            player['existing_score'] = None
            player['existing_putts'] = None
            player['scorecard_id'] = None

    # Add a flag to check if any player has a scorecard_id
    has_existing_scores = any(player['scorecard_id'] for player in player_list)

    # Pass the data to the template
    context = {
        'hole_obj': hole,
        'HoleNumber': hole.HoleNumber,
        'Par': hole.Par,
        'Yardage': hole.Yardage,
        'Handicap': hole.Handicap,
        'player_list': player_list,  # Add players in the group to the context
        'game_id': game_id,
        'group_id': group_id,
        'score_range': range(1, 10),  # Add a range of scores (1 through 9)
        'putt_range': range(0, 10),  # Add a range of putts (0 through 9)
        'msg': msg,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'has_existing_scores': has_existing_scores,  # Add the flag to the context
    }
    return render(request, 'GRPR/hole_score.html', context)


@login_required
def hole_input_score_view(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        players = data.get('players', [])
        hole_id = data.get('hole_id')
        game_id = data.get('game_id')
        group_id = data.get('group_id')
        
        # Fetch the logged-in user's Player ID
        logged_in_user = get_object_or_404(Players, user_id=request.user.id)
        logged_in_user_id = logged_in_user.id

        for player in players:
            pid = player['pid']
            score = player['score']
            putts = player.get('putts', 0)  # Default to 0 if not present
            scorecard_id = player.get('scorecard_id')  # Get the Scorecard row ID if it exists

            # Fetch the Handicap for the hole
            hole = get_object_or_404(CourseHoles, id=hole_id)
            handicap = hole.Handicap

            # Fetch NetHDCP (fallback to 0 if missing)
            net_hdcp = _net_hdcp_or_zero(game_id, pid)

            # Calculate the stroke variable
            if handicap <= net_hdcp:
                stroke = 1
                if handicap + 18 <= net_hdcp:
                    stroke = 2
            else:
                stroke = 0

            # Calculate the NetScore
            net_score = score - stroke

            # Checks to see if the hole has already had a score saved
            # Fetch the ScorecardMeta object for the player
            scm = ScorecardMeta.objects.filter(GameID=game_id, PID=pid).first()
            if not scm:
                return JsonResponse({'success': False, 'error': 'ScorecardMeta not found for player, PID = '})

            # --- Prevent duplicate Scorecard rows ---
            # Always check for an existing Scorecard row for this player/hole/game
            existing_scorecard = Scorecard.objects.filter(
                GameID_id=game_id, HoleID_id=hole_id, smID_id=scm.id
            ).first()

            if existing_scorecard:
                # Update the existing row
                current_raw_score = existing_scorecard.RawScore
                current_net_score = existing_scorecard.NetScore
                current_putts = existing_scorecard.Putts

                existing_scorecard.AlterDate = timezone.now()
                existing_scorecard.RawScore = score
                existing_scorecard.NetScore = net_score
                existing_scorecard.AlterID_id = logged_in_user_id
                existing_scorecard.Putts = putts
                existing_scorecard.save()

                # Update ScorecardMeta based on the hole number
                if 1 <= hole.HoleNumber <= 9:
                    scm.RawOUT += score - current_raw_score
                    scm.NetOUT += net_score - current_net_score
                elif 10 <= hole.HoleNumber <= 18:
                    scm.RawIN += score - current_raw_score
                    scm.NetIN += net_score - current_net_score

                scm.RawTotal += score - current_raw_score
                scm.NetTotal += net_score - current_net_score
                scm.Putts += putts - current_putts
                scm.save()

                # Updates GasCup scores if exists
                gascup.update_for_score(existing_scorecard.id)
            # --- End duplicate prevention ---

            else:  # Otherwise, no scores have been previously entered for this hole, insert a new row
                # Insert a new row into the Scorecard table
                new_score = Scorecard.objects.create(
                    CreateDate=timezone.now(),
                    AlterDate=timezone.now(),
                    RawScore=score,
                    NetScore=net_score,
                    AlterID_id=logged_in_user_id,
                    smID_id=scm.id,
                    GameID_id=game_id,
                    HoleID_id=hole_id,
                    Putts=putts
                )

                # Update ScorecardMeta based on the hole number
                if 1 <= hole.HoleNumber <= 9:
                    scm.RawOUT += score
                    scm.NetOUT += net_score
                elif 10 <= hole.HoleNumber <= 18:
                    scm.RawIN += score
                    scm.NetIN += net_score

                scm.RawTotal += score
                scm.NetTotal += net_score
                scm.Putts += putts
                scm.save()

                # Updates GasCup scores if exists
                gascup.update_for_score(new_score.id)

        print('hole_input_score_view - players', players)
        print('hole_input_score_view - hole_id', hole_id)
        print('hole_input_score_view - game_id', game_id)
        print('hole_input_score_view - group_id', group_id)

        #### Skins Section Starts ####
        # Reset the Skins column for all players in the game since this process checks for all skins everywhere
        ScorecardMeta.objects.filter(GameID=game_id).update(Skins=0)
        Skins.objects.filter(GameID=game_id).delete()

        # Skins process done after all scores are updated - will find if there is a skin per hole and who won it
        skins_results = Scorecard.objects.filter(GameID_id=game_id).values('HoleID_id').annotate(
            min_net_score=Min('NetScore')
        )

        print()
        print('skins_results', skins_results)
        print()

        # Fetch the Games instance once
        game_obj = Games.objects.get(id=game_id)
        # Prefetch all Players and CourseHoles instances
        players_map = {player.id: player for player in Players.objects.filter(id__in=Scorecard.objects.filter(GameID_id=game_id).values_list('smID__PID_id', flat=True))}
        # holes_map = {hole.id: hole for hole in CourseHoles.objects.filter(id__in=Scorecard.objects.filter(GameID_id=game_id).values_list('HoleID_id', flat=True))}

        # Dictionary to track skins for each player
        player_skins = {}

        # Collect all Skins entries in a list
        skins_to_create = []

        for result in skins_results:
            skins_hole_id = result['HoleID_id']
            min_net_score = result['min_net_score']

            # Find all players with the lowest NetScore for this hole
            players_with_lowest_score = Scorecard.objects.filter(
                GameID_id=game_id,
                HoleID_id=skins_hole_id,
                NetScore=min_net_score
            ).values('smID__PID_id')

            if players_with_lowest_score.count() == 1:
                # Only one player has the lowest score, award a skin
                player_id = players_with_lowest_score.first()['smID__PID_id']
                player_obj = players_map[player_id]  # Use pre-fetched Players instance
                # hole_obj = holes_map[skins_hole_id]  # Use pre-fetched CourseHoles instance

                hole_obj = CourseHoles.objects.get(id=skins_hole_id)  # Fetch the CourseHoles instance
                skins_to_create.append(Skins(GameID=game_obj, PlayerID=player_obj, HoleNumber=hole_obj))
                print(f"For hole {skins_hole_id}, player {player_id} scored {min_net_score} and receives 1 skin.")
                player_skins[player_id] = player_skins.get(player_id, 0) + 1
            else:
                # Multiple players have the lowest score, no skins awarded
                print(f"For hole {skins_hole_id}, there are no skins.")

        # Perform bulk insert for all the Skins table data
        Skins.objects.bulk_create(skins_to_create)
        
        print()
        print('player_skins', player_skins)
        print()
        
        # Update the Skins column in the ScorecardMeta table
        for player_id, skins in player_skins.items():
            ScorecardMeta.objects.filter(GameID=game_id, PID_id=player_id).update(Skins=skins)
        
        #### Skins Section Done ####


        return JsonResponse({
            'success': True,
            'redirect_url': f"{reverse('hole_display_view')}?hole_id={hole_id}&game_id={game_id}&group_id={group_id}"
        })

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
def hole_display_view(request):
    # Get the required data from the request
    hole_id = request.GET.get('hole_id')
    game_id = request.GET.get('game_id')
    group_id = request.GET.get('group_id')
    print('hole_display_view - hole_id', hole_id)

    # Fetch the hole details
    hole = get_object_or_404(CourseHoles, id=hole_id)

    #Fetch the Forty GameID if it exists
    forty_game_id = Games.objects.filter(AssocGame=game_id, Type='Forty').first()

    # Check if Forty scores already entered for this hole/group/game
    forty_scores_already_entered = None
    if forty_game_id:
        if Forty.objects.filter(
            GameID_id=forty_game_id.id,
            GroupID=group_id,
            HoleNumber_id=hole_id
        ).exists():
            forty_scores_already_entered = 1

    # Fetch player scores for the hole
    player_scores = Scorecard.objects.filter(
        GameID_id=game_id,
        HoleID_id=hole_id,
        smID__GroupID=group_id  # Join with ScorecardMeta and filter by GroupID
    ).select_related('smID__PID').values(
        'smID__PID__FirstName', 'smID__PID__LastName', 'RawScore', 'NetScore', 'Putts'
    )

    # Calculate the next hole ID
    next_hole = CourseHoles.objects.filter(
        CourseTeesID=hole.CourseTeesID, HoleNumber__gt=hole.HoleNumber
    ).order_by('HoleNumber').first()

    next_hole_id = next_hole.id if next_hole else None
    print('hole_display_view - next_hole_id', next_hole_id)

    # ------------------- Gas Cup status (optional) -------------------
    gas_status = None
    try:
        pids = list(
            ScorecardMeta.objects
            .filter(GameID=game_id, GroupID=group_id)
            .values_list("PID_id", flat=True)
        )
        if pids:
            status = gascup.status_for_pids(game_id, pids, hole.HoleNumber)
            if status:
                pga_lbl, liv_lbl = gascup.pair_labels_for_pids(game_id, pids)
                gas_status = gascup.format_status_human_verbose(status, pga_lbl, liv_lbl)
    except Exception as e:
        print("GAS STATUS ERROR (hole_display_view):", e)
        gas_status = None
    # ------------------- End Gas Cup status -------------------

    context = {
        'hole': hole,
        'player_scores': player_scores,
        'game_id': game_id,
        'forty_game_id': forty_game_id.id if forty_game_id else None,  # Pass the Forty GameID if it exists
        'group_id': group_id, 
        'next_hole_id': next_hole_id,  # Pass the next hole ID to the template
        'gas_status': gas_status,
    }
    if forty_scores_already_entered:
        context['forty_scores_already_entered'] = forty_scores_already_entered

    return render(request, 'GRPR/hole_display.html', context)


@login_required
def scorecard_view(request):
    # ------------------------------------------------------------------
    # Params
    # ------------------------------------------------------------------
    game_id = request.GET.get('game_id')
    group_id = request.GET.get('group_id')  # may be blank → Big Scorecard
    msg = request.GET.get('msg')

    print()
    print('scorecard_view - game_id', game_id)
    print('scorecard_view - group_id', group_id)

    # ------------------------------------------------------------------
    # Linked Forty game (for red-border highlighting)
    # ------------------------------------------------------------------
    forty_game_id = (
        Games.objects
        .filter(id=game_id)
        .values_list('AssocGame', flat=True)
        .first()
    )

    forty_used_scores = set()
    if forty_game_id:
        for forty in Forty.objects.filter(GameID_id=forty_game_id):
            forty_used_scores.add(f"{forty.PID_id}:{forty.HoleNumber_id}")

    # ------------------------------------------------------------------
    # Player list (Skins ScorecardMeta -> players shown on card)
    # ------------------------------------------------------------------
    players_qs = (
        ScorecardMeta.objects
        .filter(GameID=game_id)
        .select_related('PID')
        .values(
            first_name=F('PID__FirstName'),
            last_name=F('PID__LastName'),
            pid=F('PID__id'),
            net_hdcp=F('NetHDCP'),
        )
    )
    if group_id:
        players_qs = players_qs.filter(GroupID=group_id)

    player_list = list(players_qs)
    print('player_list', player_list)

    # Normalize handicap now (int; fallback 0 if missing)
    for p in player_list:
        nh = p.get('net_hdcp')
        try:
            p['net_hdcp'] = int(nh) if nh is not None else 0
        except (TypeError, ValueError):
            p['net_hdcp'] = 0

    # ------------------------------------------------------------------
    # Tee context (we pick the most common tee in the game)
    # ------------------------------------------------------------------
    most_common_tee_id = (
        ScorecardMeta.objects
        .filter(GameID=game_id)
        .values('TeeID_id')
        .annotate(count=Count('TeeID_id'))
        .order_by('-count')
        .first()
    )
    print()
    print('most_common_tee_id', most_common_tee_id)

    course_holes = []
    course_name = None
    tee_pk = None
    if most_common_tee_id and most_common_tee_id['TeeID_id']:
        tee_pk = most_common_tee_id['TeeID_id']
        course_holes = (
            CourseHoles.objects
            .filter(CourseTeesID_id=tee_pk)
            .order_by('HoleNumber')
            .values('id', 'HoleNumber', 'Par', 'Yardage', 'Handicap')
        )
        course_name = (
            CourseTees.objects
            .filter(id=tee_pk)
            .values_list('CourseName', flat=True)
            .first()
        )

    print()
    print('course_holes', list(course_holes))

    # ------------------------------------------------------------------
    # Game date
    # ------------------------------------------------------------------
    play_date = (
        Games.objects
        .filter(id=game_id)
        .values_list('PlayDate', flat=True)
        .first()
    )
    print()
    print('play_date', play_date)

    # ------------------------------------------------------------------
    # Raw/Net per-hole scores
    # ------------------------------------------------------------------
    scores = (
        Scorecard.objects
        .filter(GameID_id=game_id)
        .select_related('HoleID', 'smID')
        .values('HoleID__HoleNumber', 'NetScore', 'RawScore', 'smID__PID_id')
    )
    if group_id:
        scores = scores.filter(smID__GroupID=group_id)

    player_scores = {p['pid']: {} for p in player_list}

    for s in scores:
        pid = s['smID__PID_id']
        hn = s['HoleID__HoleNumber']
        player_scores[pid][hn] = {
            'net': s['NetScore'] if s['NetScore'] is not None else '',
            'raw': s['RawScore'] if s['RawScore'] is not None else '',
            'skin': False,
        }

    # Ensure all holes + Out/In/Total keys exist
    for pid in player_scores:
        for h in course_holes:
            hn = h['HoleNumber']
            player_scores[pid].setdefault(hn, {'net': '', 'raw': ''})
        player_scores[pid]['Out']   = {'net': '', 'raw': '', 'skin': False}
        player_scores[pid]['In']    = {'net': '', 'raw': '', 'skin': False}
        player_scores[pid]['Total'] = {'net': '', 'raw': '', 'skin': False}

    # ------------------------------------------------------------------
    # Totals from ScorecardMeta
    # ------------------------------------------------------------------
    meta_qs = (
        ScorecardMeta.objects
        .filter(GameID=game_id)
        .values('PID_id', 'RawOUT', 'NetOUT', 'RawIN', 'NetIN', 'RawTotal', 'NetTotal')
    )
    if group_id:
        meta_qs = meta_qs.filter(GroupID=group_id)

    for m in meta_qs:
        pid = m['PID_id']
        if pid not in player_scores:
            continue
        player_scores[pid]['Out'] = {
            'net': m['NetOUT'] if m['NetOUT'] is not None else '',
            'raw': m['RawOUT'] if m['RawOUT'] is not None else '',
            'skin': False,
        }
        player_scores[pid]['In'] = {
            'net': m['NetIN'] if m['NetIN'] is not None else '',
            'raw': m['RawIN'] if m['RawIN'] is not None else '',
            'skin': False,
        }
        player_scores[pid]['Total'] = {
            'net': m['NetTotal'] if m['NetTotal'] is not None else '',
            'raw': m['RawTotal'] if m['RawTotal'] is not None else '',
            'skin': False,
        }

    # ------------------------------------------------------------------
    # Skins mark-up
    # ------------------------------------------------------------------
    skins = (
        Skins.objects
        .filter(GameID=game_id)
        .select_related('HoleNumber')
        .values('HoleNumber__HoleNumber', 'PlayerID_id')
    )
    for s in skins:
        hn = s['HoleNumber__HoleNumber']
        pid = s['PlayerID_id']
        if pid in player_scores and hn in player_scores[pid]:
            player_scores[pid][hn]['skin'] = True

    if not player_scores:
        player_scores = {}

    # ------------------------------------------------------------------
    # Stroke grids (uses normalized net_hdcp from player_list)
    # ------------------------------------------------------------------
    player_strokes = {}
    if tee_pk:  # we have a tee context
        # Preload the “extra stroke” hole set once for each player inside loop.
        # (Per-player anyway because addl_strokes differs by player.)
        for p in player_list:
            pid = p['pid']
            net_hdcp = p['net_hdcp']  # already int fallback 0

            base_strokes, addl_strokes = divmod(net_hdcp, 18)

            if addl_strokes > 0:
                stroke_holes = set(
                    CourseHoles.objects
                    .filter(CourseTeesID_id=tee_pk, Handicap__lte=addl_strokes)
                    .values_list('HoleNumber', flat=True)
                )
            else:
                stroke_holes = set()

            strokes = {}
            for h in course_holes:
                hn = h['HoleNumber']
                if hn in stroke_holes:
                    strokes[hn] = base_strokes + 1
                else:
                    strokes[hn] = base_strokes
            player_strokes[pid] = strokes
    else:
        # No tee context; give everyone 0 strokes so templates remain safe.
        for p in player_list:
            pid = p['pid']
            player_strokes[pid] = {}

    print("")
    print("forty_used_scores:", forty_used_scores)

    # ------------------------------------------------------------------
    # Gas Cup status banner (only for 4-player sub-card)
    # ------------------------------------------------------------------
    gas_status = None
    try:
        if group_id:
            pids = list(
                ScorecardMeta.objects
                .filter(GameID=game_id, GroupID=group_id)
                .values_list("PID_id", flat=True)
            )
            if pids:
                thru = (
                    Scorecard.objects
                    .filter(GameID=game_id, smID__PID_id__in=pids)
                    .aggregate(Max("HoleID__HoleNumber"))["HoleID__HoleNumber__max"]
                ) or 0
                status = gascup.status_for_pids(game_id, pids, thru)
                if status:
                    pga_lbl, liv_lbl = gascup.pair_labels_for_pids(game_id, pids)
                    gas_status = gascup.format_status_human_verbose(status, pga_lbl, liv_lbl)
    except Exception as e:
        print("GAS STATUS ERROR (scorecard_view):", e)
        gas_status = None

    # ------------------------------------------------------------------
    # Context & render
    # ------------------------------------------------------------------
    context = {
        'game_id': game_id,
        'group_id': group_id,
        'player_list': player_list,
        'course_holes': list(course_holes),
        'course_name': course_name,
        'play_date': play_date,
        'player_scores': player_scores,
        'player_strokes': player_strokes,
        'msg': msg,
        'gas_status': gas_status,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'forty_used_scores': list(forty_used_scores),
    }
    return render(request, 'GRPR/scorecard.html', context)
