import os
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.utils import timezone
from GRPR.models import Courses, TeeTimesInd, Players, SubSwap, Log, LoginActivity, SMSResponse, Xdates, Games, GameInvites
from datetime import datetime
from django.conf import settings  # Import settings
from django.contrib.auth.views import LoginView # added for secure login page creation
from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm # added for secure login page creation
from .forms import CustomPasswordChangeForm
from django.contrib.auth.decorators import login_required # added to require certified login to view any page
from django.views.decorators.csrf import csrf_exempt # added to allow Twilio to send messages
from django.contrib.auth.models import User # for user activity tracking on Admin page
from django.contrib.auth import login as auth_login # for user activity tracking on Admin page
from django.db.models import Q, Count, F, Func, Subquery, OuterRef, Value
from django.urls import reverse_lazy
from django.core.mail import send_mail
from GRPR.utils import get_open_subswap_or_error, check_player_availability, get_tee_time_details
from twilio.rest import Client # Import the Twilio client
from twilio.twiml.messaging_response import MessagingResponse

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
    if request.user.username != 'cprouty':
        return redirect('home_page')  # Redirect to home if the user is not cprouty
    
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
        'login_activities': login_activities,
        'responses': responses,
    }
    return render(request, 'admin_view.html', context)

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
    distinct_dates = TeeTimesInd.objects.filter(gDate__gt=current_datetime).values('gDate').distinct().order_by('gDate')

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
            schedule_query = TeeTimesInd.objects.filter(PID=player_id, gDate__gte=current_datetime).select_related('CourseID').order_by('gDate')
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

    player = get_object_or_404(Players, user_id=user_id)
    player_id = player.id

    # Fetch the TeeTimeInd instance and other players using the utility function
    tee_time_details = get_tee_time_details(tt_id, player_id)
    gDate = tee_time_details['gDate']
    tt_pid = tee_time_details['tt_pid']
    course_name = tee_time_details['course_name']
    course_time_slot = tee_time_details['course_time_slot']
    other_players = tee_time_details['other_players']

    # GATE: Verify the logged in user owns this tee time (abundance of caution here)
    if tt_pid != player_id:
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
        PID_id=player_id,
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
        to_number = player.Mobile
        message = client.messages.create(from_='+18449472599', body=msg, to=to_number)
        mID = message.sid

        # Insert initial Sub Offer into Log
        Log.objects.create(
            SentDate=timezone.now(),
            Type="Sub Offer",
            MessageID=mID,
            RequestDate=gDate,
            OfferID=player_id,
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
                OfferID=player_id,
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
            OfferID=player_id,
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
                OfferID=player_id,
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
    else:
        offer_msg = f"Sub Accepted: {first_name} {last_name} is taking your tee time on {gDate} at {course_name} {course_time_slot}."
        to_number = offer_player_mobile

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
            To_number=to_number
        )

        accept_msg = f"Sub Accepted: { first_name } { last_name } is taking {offer_player_first_name} {offer_player_last_name}'s tee time on {gDate} at {course_name} {course_time_slot}."
        to_number = player_mobile

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
            To_number=to_number
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
    
    # # Fetch the list of future dates for the offering player (player_id)
    offering_player_future_dates = TeeTimesInd.objects.filter(PID=player_id, gDate__gt=gDate).values_list('gDate', flat=True)

    available_players_with_swap_dates = []
    for player in available_players:
        # Fetch the list of future dates for the current player
        player_future_dates = TeeTimesInd.objects.filter(PID=player, gDate__gt=gDate).values_list('gDate', flat=True)
        
        # Check if all future dates for the current player are in the offering player's future dates
        if all(date in offering_player_future_dates for date in player_future_dates):
            print(f"Player {player.id} has all future dates in the offering player's schedule. Skipping.")
            continue
        
        # Check if the player has any available swap dates
        available_swap_dates = TeeTimesInd.objects.filter(PID=player, gDate__gt=gDate).exists()

        if available_swap_dates:
            available_players_with_swap_dates.append(player)

    if not available_players_with_swap_dates:
        return redirect('swapnoneavail_view')
    
    # Generate Available Swap Dates for each available player
    filtered_players = []
    for player in available_players:
        available_player_dates = TeeTimesInd.objects.filter(PID=player, gDate__gt=gDate).values_list('gDate', 'id')
        swap_request_player_dates = TeeTimesInd.objects.filter(PID=player_id, gDate__gt=gDate).values_list('gDate', flat=True)
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

    player = get_object_or_404(Players, user_id=user_id)
    player_id = player.id

    # Fetch the TeeTimeInd instance and other players using the utility function
    tee_time_details = get_tee_time_details(tt_id, player_id)
    gDate = tee_time_details['gDate']
    tt_pid = tee_time_details['tt_pid']
    course_name = tee_time_details['course_name']
    course_time_slot = tee_time_details['course_time_slot']
    other_players = tee_time_details['other_players']

    # GATE: Verify the logged in user owns this tee time (abundance of caution here)
    if tt_pid != player_id:
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
        PID_id=player_id,
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
        to_number = player.Mobile
        message = client.messages.create(from_='+18449472599', body=msg, to=to_number)
        mID = message.sid

        # Insert initial Swap Offer into Log
        Log.objects.create(
            SentDate=timezone.now(),
            Type="Swap Offer",
            MessageID=mID,
            RequestDate=gDate,
            OfferID=player_id,
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
            msg = f"{swap_offer} https://www.gasgolf.org/GRPR/store_swapaccept_data/?swap_id={swap_id}"
            message = client.messages.create(from_='+18449472599', body=msg, to=to_number)
            mID = message.sid

            # Insert a row into Log table for every text sent
            Log.objects.create(
                SentDate=timezone.now(),
                Type="Swap Offer Sent",
                MessageID=mID,
                RequestDate=gDate,
                OfferID=player_id,
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
            OfferID=player_id,
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
                OfferID=player_id,
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
        gDate__gt=gDate
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
        players_data.append({
            'first_name': player.FirstName,
            'last_name': player.LastName,
            'mobile': player.Mobile,
            'email': player.Email,
            'rounds_played': rounds_played,
            'rounds_scheduled': rounds_scheduled,
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
    user = request.user
    player = Players.objects.get(user_id=user.id)

    context = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'user_name': user.username,
        'email_address': player.Email,
        'mobile': player.Mobile,
    }
    return render(request, 'GRPR/profile.html', context)


##########################
#### Skins game views ####
##########################
@login_required
def skins_view(request):
    user = request.user

    context = {
        'first_name': user.first_name,
        'last_name': user.last_name,
    }

    return render(request, 'GRPR/skins.html', context)


@login_required
def scorecard_view(request):
    # Fetch distinct tee times
    teetimes = TeeTimesInd.objects.values('gDate', 'CourseID__courseName', 'CourseID__courseTimeSlot').distinct().order_by('gDate', 'CourseID__courseTimeSlot')

    # Fetch players for each distinct tee time
    for teetime in teetimes:
        teetime['players'] = list(TeeTimesInd.objects.filter(
            gDate=teetime['gDate'],
            CourseID__courseName=teetime['CourseID__courseName'],
            CourseID__courseTimeSlot=teetime['CourseID__courseTimeSlot']
        ).select_related('PID').values('PID__FirstName', 'PID__LastName'))
    print('teetime', teetimes)

    return render(request, 'GRPR/scorecard.html', {'teetimes': teetimes})

@login_required
def new_skins_game_view(request):
    # Get today's date
    current_datetime = datetime.now()

    # Query the next closest future date in the TeeTimesInd table
    next_closest_date = TeeTimesInd.objects.filter(gDate__gte=current_datetime).order_by('gDate').values('gDate').first()

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
    print('tee_times_queryset"', tee_times_queryset)

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
        })
    
    print('new_skins_game_view')
    print('tee_times', tee_times)


    context = {
        'tee_times': tee_times,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
    }
    return render(request, 'GRPR/new_skins_game.html', context)


@login_required
def skins_invite_view(request):
    if request.method == 'POST':
        game_creator = request.user
        gDate = request.POST.get('gDate')
        selected_players = request.POST.getlist('selected_players')

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
            Status='New',
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
            if twilio_enabled:
                message = client.messages.create(
                    body=invite_msg,
                    from_=os.getenv('TWILIO_PHONE_NUMBER'),
                    to=invitee_mobile
                )
                mID = message.sid
            else:
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
        request.session['game_id'] = game_id

        return redirect('skins_invite_status_view')   
    else:
        return HttpResponseBadRequest("Invalid request.")  
    

@login_required
def skins_game_current_view(request):
    # Fetch the most recent game with status 'New' or 'Live'
    game = Games.objects.filter(Status__in=['New', 'Live']).order_by('-CreateDate').first()

    if game:
        # Store the game_id in the session
        request.session['game_id'] = game.id
        return redirect('skins_invite_status_view')
    else:
        return HttpResponseBadRequest("No current game found.")


@login_required
def skins_invite_status_view(request):
        game_id = request.session.pop('game_id', None)

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
    if twilio_enabled:
        client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
        message = client.messages.create(
            body=f"Your invite status has been changed to {gStatus}",
            from_=os.getenv('TWILIO_PHONE_NUMBER'),
            to=mobile
        )
        mID = message.sid
    else:
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


@login_required
def skins_game_start_view(request):
    game_id = request.GET.get('game_id')

    if not game_id:
        return HttpResponseBadRequest("Missing game_id parameter.")

    # Update the Games table
    Games.objects.filter(id=game_id, CrewID=1).update(Status='Tees')

    # Fetch the necessary data
    game = get_object_or_404(Games, id=game_id)
    pDate = game.PlayDate

    # Get the player_id for the current logged-in user
    user = request.user
    player = get_object_or_404(Players, user=user)
    player_id = player.id

    # Insert a new row into the Log table
    Log.objects.create(
        SentDate=timezone.now(),
        Type='Game Config',
        MessageID='None',
        RequestDate=pDate,
        OfferID=player_id,
        RefID=game_id,
        Msg=f'{game_id} is choosing tees'
    )

    # Render the skins_tees.html page
    return render(request, 'GRPR/skins_tees.html')