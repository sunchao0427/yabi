# -*- coding: utf-8 -*-
# Django settings for project.
import os
from django.utils.webhelpers import url

# PROJECT_DIRECTORY isnt set when not under wsgi
if not os.environ.has_key('PROJECT_DIRECTORY'):
    os.environ['PROJECT_DIRECTORY']=os.path.dirname(__file__).split("/appsettings/")[0]

from appsettings.default_dev import *
from appsettings.yabife.dev import *

# subsitution done by fab, this will be your username or in the case of a snapshot, 'snapshot'
TARGET = '<CCG_TARGET_NAME>'

# Defaults
#LOGIN_REDIRECT_URL

# These are non standard
LOGIN_URL = url('/login/')
LOGOUT_URL = url('/logout/')

ROOT_URLCONF = 'yabife.urls'

INSTALLED_APPS.extend( [
    'django.contrib.messages',
    'yabife.registration',
    'yabife.yabifeapp',
] )

MIDDLEWARE_CLASSES.extend( [
    'django.contrib.messages.middleware.MessageMiddleware',
] )

MEMCACHE_KEYSPACE = "dev-yabife-"+TARGET

AUTHENTICATION_BACKENDS = [
 'django.contrib.auth.backends.LDAPBackend',
 'django.contrib.auth.backends.NoAuthModelBackend',
]

AUTH_PROFILE_MODULE = 'yabifeapp.User'

SESSION_COOKIE_PATH = url('/')
SESSION_SAVE_EVERY_REQUEST = True
CSRF_COOKIE_NAME = "csrftoken_yabife"

WRITABLE_DIRECTORY = os.path.join(PROJECT_DIRECTORY,"scratch")

#functions to evaluate for status checking
import status
STATUS_CHECKS = [
    status.check_database,
    status.check_disk,
]

APPEND_SLASH = True
SITE_NAME = 'yabife'


##
## Preview settings
##

# The truncate key controls whether the file may be previewed in truncated form
# (ie the first "size" bytes returned). If set to false, files beyond the size
# limit simply won't be available for preview.
#
# The override_mime_type key will set the content type that's sent in the
# response to the browser, replacing the content type received from Admin.
#
# MIME types not in this list will result in the preview being unavailable.
PREVIEW_SETTINGS = {
    # Text formats.
    "text/plain": { "truncate": True },

    # Structured markup formats.
    "text/html": { "truncate": False, "sanitise": True },
    "application/xhtml+xml": { "truncate": False, "sanitise": True },
    "text/svg+xml": { "truncate": True, "override_mime_type": "text/plain" },
    "text/xml": { "truncate": True, "override_mime_type": "text/plain" },
    "application/xml": { "truncate": True, "override_mime_type": "text/plain" },

    # Image formats.
    "image/gif": { "truncate": False },
    "image/jpeg": { "truncate": False },
    "image/png": { "truncate": False },
}

# The length of time preview metadata will be cached, in seconds.
PREVIEW_METADATA_EXPIRY = 60

# The maximum file size that can be previewed.
PREVIEW_SIZE_LIMIT = 1048576


##
## CAPTCHA settings
##
# the filesystem space to write the captchas into
CAPTCHA_ROOT = os.path.join(MEDIA_ROOT, 'captchas')

# the URL base that points to that directory served out
CAPTCHA_URL = os.path.join(MEDIA_URL, 'captchas')

# Captcha image directory
CAPTCHA_IMAGES = os.path.join(WRITABLE_DIRECTORY, "captcha")

FILE_UPLOAD_MAX_MEMORY_SIZE = 0


##
## LOGGING
##
import logging
LOG_DIRECTORY = os.path.join(PROJECT_DIRECTORY,"logs")
LOGGING_LEVEL = logging.DEBUG
LOGGING_FORMATTER = logging.Formatter('[%(name)s:%(levelname)s:%(filename)s:%(lineno)s:%(funcName)s] %(message)s')
LOGS = ['yabife']

# kick off mango initialisation of logging
from django.contrib import logging as mangologging

##
## SENTRY
##

# Use sentry if we can, otherwise use EmailExceptionMiddleware
# sentry_test is set to true by snapshot deploy, so we can use sentry
# even though debug=True
try:
    assert DEBUG == False
    SENTRY_REMOTE_URL = 'http://faramir.localdomain/sentryserver/%s/store/' % TARGET
    SENTRY_KEY = 'lrHEULXanJMB5zygOLUUcCRvCxYrcWVZJZ0fzsMzx'
    SENTRY_TESTING = False

    INSTALLED_APPS.extend(['sentry.client'])
    
    from sentry.client.handlers import SentryHandler
    logging.getLogger().addHandler(SentryHandler())

    # Add StreamHandler to sentry's default so you can catch missed exceptions
    logging.getLogger('sentry.errors').addHandler(logging.StreamHandler())

    # remove the EmailExceptionMiddleware so
    # exceptions are handled and mailed by sentry
    try:
        MIDDLEWARE_CLASSES.remove('django.middleware.email.EmailExceptionMiddleware')
    except ValueError,e:
        pass

except (ImportError, AssertionError), e:
    pass
