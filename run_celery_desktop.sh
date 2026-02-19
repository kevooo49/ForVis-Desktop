#!/bin/bash
# celery -A formulavis worker -l info -c 4 -Q visualization
export DJANGO_SETTINGS_MODULE=formulavis.settings_desktop2
celery -A formulavis.celeryconf worker --pool=solo -l info
