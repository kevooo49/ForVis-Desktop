# formulavis/settings_desktop.py

from .settings import *

# 1. Baza – ten sam user/hasło, ale host = localhost
DATABASES['default']['HOST'] = 'localhost'
DATABASES['default']['PORT'] = '5433'

# 2. Redis – używamy lokalnego Redisa
REDIS_HOST = 'localhost'
CELERY_RESULT_BACKEND = 'redis://%s:%d/%d' % (REDIS_HOST, REDIS_PORT, REDIS_DB)

# 3. RabbitMQ – lokalny
RABBIT_HOSTNAME = 'localhost'
BROKER_URL = 'amqp://{user}:{password}@{hostname}/{vhost}/'.format(
    user='admin',
    password='mypass',
    hostname=RABBIT_HOSTNAME,
    vhost=''
)

# heartbeat nadal działa, korzystamy z BROKER_HEARTBEAT z bazowych settings
if not BROKER_URL.endswith(BROKER_HEARTBEAT):
    BROKER_URL += BROKER_HEARTBEAT

# 4. ALLOWED_HOSTS – na wszelki wypadek zostawiamy localhost/127.0.0.1
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]


EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
