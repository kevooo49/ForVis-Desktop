from __future__ import absolute_import, unicode_literals

from .celery import app as celery_app

# Celery CLI oczekuje atrybutu `app`, Celery internals często patrzą na `celery_app`
app = celery_app

__all__ = ('celery_app', 'app')
