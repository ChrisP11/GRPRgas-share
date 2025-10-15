import os
from pathlib import Path
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# static file settings
# Development: Static files are served from GRPR/GRPR/static/css/styles.css.
# Production: Static files are collected into GRPR/GRPR/staticfiles and served from there.
STATIC_URL = '/static/' 
STATICFILES_DIRS = [BASE_DIR / "GRPR/static"]
STATIC_ROOT = BASE_DIR / "staticfiles" # added as part of port to Postgres

# Security settings
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'your_secret_key')
# print(f"SECRET_KEY: {SECRET_KEY}")
# SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
print('Debug', DEBUG)

# Allow all host headers
ALLOWED_HOSTS = ['*'] if DEBUG else ['gasgolf.org', 'www.gasgolf.org', 'grpr.herokuapp.com']

# Database configuration. Always use production settings on Heroku
if 'DATABASE_URL' in os.environ:
    DATABASES = {'default': dj_database_url.config(conn_max_age=600, ssl_require=True)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'grpr_db',
            'USER': os.getenv('POSTGRES_USER', 'your_default_user'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'your_default_password'),
            'HOST': 'localhost',
            'PORT': '',
        }
    }


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # my apps
    'GRPR',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # added as part of port to Postgres
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'GRPR.middleware.SSLRedirectMiddleware',  # Add this line to force using https
    'GRPR.middleware.ForcePasswordChangeMiddleware',  # Add this line to force password change
]

ROOT_URLCONF = 'portfolio.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'GRPR/templates/GRPR'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'portfolio.context_processors.enviro',  # reads the ENVIRO env var
                'portfolio.context_processors.twilio_enabled',

            ],
        },
    },
]

WSGI_APPLICATION = 'portfolio.wsgi.application'

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# added this section as part of creating the secure login page for grpr
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# Redirect users to the home page after login
LOGIN_REDIRECT_URL = '/home/'

# Redirect users to the login page if not authenticated
LOGIN_URL = '/login/'

# Redirect users to the login page after logout
LOGOUT_REDIRECT_URL = '/login/'

# Session settings, recommended settings
SESSION_COOKIE_AGE = 86400  # Set session duration to 24 hour (1 hr = 3600 seconds), default is 2 weeks, comment out this line to revert to that timeframe
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # Expire session when the browser is closed
SESSION_COOKIE_SECURE = not DEBUG  # Ensure session cookies are only sent over HTTPS in production
SESSION_COOKIE_HTTPONLY = True  # Ensure session cookies are inaccessible to JavaScript
SESSION_COOKIE_SAMESITE = 'Lax'  # Set the SameSite attribute for session cookies
CSRF_COOKIE_SECURE = not DEBUG  # Ensure CSRF cookies are only sent over HTTPS in production
# Set the secure proxy header
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = ['https://gasgolf.org', 'https://www.gasgolf.org']

# Add Security Middleware
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/
LANGUAGE_CODE = 'en-us'

# Set the time zone to Central Standard Time (CST)
TIME_ZONE = 'America/Chicago'

USE_I18N = True

# Use timezone-aware datetimes
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Add this setting to control Twilio functionality, defualt is False if no environment variable is set
TWILIO_ENABLED = os.environ.get('TWILIO_ENABLED', 'False') == 'True'


# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')

# Email backend configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')

# Default from email address
DEFAULT_FROM_EMAIL = os.environ.get('EMAIL_HOST_USER')

# Environment setting
ENVIRO = os.environ.get('ENVIRO', 'Prod')
print(f"Environment: {ENVIRO}")  
print(f"ENVIRO: {os.environ.get('ENVIRO')}")
print(f"TWILIO_ENABLED: {os.environ.get('TWILIO_ENABLED')}")


### components to make Playwright testing work
# --- E2E/dev helpers (put after DEBUG) ---
IS_E2E = os.environ.get("E2E", "0") == "1"

# Point login redirect to your actual home route in this project
LOGIN_REDIRECT_URL = "/GRPR/home/"

# Security toggles for local / E2E runs
SECURE_SSL_REDIRECT   = not (DEBUG or IS_E2E)
SESSION_COOKIE_SECURE = not (DEBUG or IS_E2E)
CSRF_COOKIE_SECURE    = not (DEBUG or IS_E2E)

# Add local origins for CSRF when developing or running E2E
_local_csrf = [
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
    "http://localhost",
    "http://localhost:8000",
]
try:
    CSRF_TRUSTED_ORIGINS = list(CSRF_TRUSTED_ORIGINS)
except NameError:
    CSRF_TRUSTED_ORIGINS = []
if DEBUG or IS_E2E:
    for origin in _local_csrf:
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)

# In dev/E2E, drop the custom HTTPS redirect middleware so http://127.0.0.1 works
if DEBUG or IS_E2E:
    MIDDLEWARE = [mw for mw in MIDDLEWARE if mw != "GRPR.middleware.SSLRedirectMiddleware"]
