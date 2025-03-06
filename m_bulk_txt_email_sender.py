# script to send out an email to everyone in the group

import os
import django
from datetime import datetime

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portfolio.settings')
django.setup()

from django.utils import timezone
from GRPR.models import Players, Log
from django.core.mail import send_mail
from twilio.rest import Client # Import the Twilio client

players = Players.objects.all().exclude(Member=0).order_by('LastName', 'FirstName')

for player in players:
    email = player.Email
    subject = 'The GAS schedule is posted'
    message = f'''{player.FirstName} -- \n\nThe schedule for the upcoming GAS season has been posted. Please log in to the GAS website, https://www.gasgolf.org/, to view your tee times.\n
    1. Your email address is your login : {email}\n
    2. Your temporary password is G4sgolf! (capital G, the number 4, lowercase s, golf!, exclamation point included)\n
    3. The site will prompt you to change your password when you log in for the first time.\n
    \n
    Key components of the site:\n
    Home - Your Home Page + Quick Links\n
    Tee Sheet - The next set of Tee Times + Future Schedule\n
    Schedule - Your full schedule + can search other's schedules \n
    Sub / Swap - Request Subs or Swaps for your Tee Times as well as accept offers by other players\n
    Players - List of everyone in the group with Cell & Email\n
    Data - Player, Course, & Date Distribution + an Activity Feed\n
    Your Name (Upper Right Hand Corner^^) - Clickable, Your Information + ability to change password\n
    
    \n\nThank you,\nCoogan and Prouty \n
    Any problems or concerns please contact Chris Prouty at 312-296-1817'''
    from_email = os.environ.get('EMAIL_HOST_USER')

    try:
        send_mail(subject, message, from_email, [email])
        email_success_message = f'Email sent {player.LastName} {email}.'
        print(email_success_message)
    except Exception as e:
        error_message = f'Error sending test email: {player.LastName} {email} {e}'
        print(error_message)    

    
    
    txt_msg = f'''
        {player.FirstName} -- The schedule for the upcoming GAS season has been posted. \n
          Please log in to the GAS website, https://www.gasgolf.org/ \n
          Your login is your email address: {email}
          Your temporary password is G4sgolf! \n
          You will be prompted to change your password on login.\n
          See your email for more instructions.
        '''
    twilio_account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    twilio_auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
    twilio_phone_number = '+18449472599'
    mobile = player.Mobile
    player_id = player.id

    client = Client(twilio_account_sid, twilio_auth_token)

    twilio_message = client.messages.create(
        body=txt_msg,
        from_=twilio_phone_number,
        to=mobile
    )
    mID = twilio_message.sid

    # Insert record into Log table
    Log.objects.create(
        SentDate=timezone.now(),
        Type="Admin Text Msg",
        MessageID=mID,
        OfferID=13,
        ReceiveID=player_id,
        Msg=txt_msg,
        To_number=mobile

    # print(f'{player.FirstName} {player.LastName} {player.Email} {player.Mobile} {player_id}')

    txt_success_message = f'text message sent {player.LastName} {mobile}.'
    print(txt_success_message)
