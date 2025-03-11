# filepath: /Users/cprouty/Dropbox/Dev/Python/Apps/GRPR/demo_enviro_build.sh
#!/bin/bash

# Set variables
APP_NAME="demo-grpr"
GIT_REMOTE="preprod"

# Create a new Heroku app
heroku create $APP_NAME

# Check if the app was created successfully
if [ $? -ne 0 ]; then
    echo "Failed to create Heroku app. Exiting."
    exit 1
fi

# Set non-sensitive environment variables
heroku config:set ENVIRO=Demo --app $APP_NAME
heroku config:set DEBUG=True --app $APP_NAME
heroku config:set EMAIL_HOST_USER=gasgolf25@gmail.com --app $APP_NAME
heroku config:set TWILIO_ENABLED=False --app $APP_NAME

# creates the postgres db
heroku addons:create heroku-postgresql:essential-0 --app $APP_NAME

# Check if the addon was created successfully
if [ $? -ne 0 ]; then
    echo "Failed to create Heroku Postgres addon. Exiting."
    exit 1
fi

# Add Heroku remote
git remote add $GIT_REMOTE https://git.heroku.com/$APP_NAME.git

# Deploy code to Heroku
git push $GIT_REMOTE main

# Reminder to manually set sensitive environment variables
echo "Please set the following sensitive environment variables manually:"
echo "DJANGO_SECRET_KEY, EMAIL_HOST_PASSWORD, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN"

# Pause the script to allow manual setting of environment variables
read -p "Press [Enter] key after setting the environment variables..."

# Run migrations
heroku run python manage.py migrate --app $APP_NAME

# Create a superuser (optional)
heroku run python manage.py createsuperuser --app $APP_NAME

# Run Python scripts to insert data into the database
# heroku run python manage.py shell --app $APP_NAME < /Users/cprouty/Dropbox/Dev/Python/Apps/GRPR/demo_Players_Users_data.py
heroku run python /app/demo_Players_Users_data.py --app $APP_NAME
heroku run python /app/demo_Courses_insert_data.py --app $APP_NAME

echo "Environment setup complete."