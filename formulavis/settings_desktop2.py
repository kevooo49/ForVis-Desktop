from .settings import *
import os
import sys

try:
    INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'django_extensions']
except NameError:
    pass

# ===========================
# DATABASE – SQLite
# ===========================

# BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.join(os.path.dirname(sys.executable), 'formulavis')
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'forvis_desktop.sqlite3'),
    }
}

# ===========================
# CELERY – SOLO MODE, NO BROKER
# ===========================

# CELERY_BROKER_URL = 'memory://'
# CELERY_RESULT_BACKEND = 'cache+memory://'
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/1'
CELERY_TASK_ALWAYS_EAGER = False   # ważne – chcemy async, ale solo
CELERY_TASK_EAGER_PROPAGATES = True

# Celery zawsze w trybie "solo"
CELERYD_POOL = "solo"

# BROKER_URL = 'memory://'
# CELERY_RESULT_BACKEND = 'cache+memory://'
BROKER_URL = CELERY_BROKER_URL
CELERY_RESULT_BACKEND = CELERY_RESULT_BACKEND

# ===========================
# ALLOWED HOSTS
# ===========================

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# ===========================
# MEDIA PATHS FOR DESKTOP
# ===========================

MEDIA_ROOT = os.path.join(BASE_DIR, '_files')
MEDIA_URL = '_files/'


if not os.path.exists(MEDIA_ROOT):
    os.makedirs(MEDIA_ROOT)

# ===========================
# EMAIL – OFF
# ===========================

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ===========================
# REST FRAMEWORK – tylko JSON (bez HTML / browsable API)
# ===========================
try:
    REST_FRAMEWORK  # czy istnieje w bazowych settings
except NameError:
    REST_FRAMEWORK = {}

REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = (
    'rest_framework.renderers.JSONRenderer',
)


# ===========================
# DEBUG
# ===========================

DEBUG = False
