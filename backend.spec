# -*- mode: python -*-

import os
import glob

block_cipher = None
project_dir = os.path.abspath('.')

datas = []

# formulavis – kopiujemy z zachowaniem struktury
for f in glob.glob('formulavis/**/*', recursive=True):
    if os.path.isfile(f):
        relative_path = os.path.relpath(f, '.')
        dest_dir = os.path.dirname(relative_path)
        datas.append((f, dest_dir))

# profiles – MUSI być skopiowane
for f in glob.glob('profiles/**/*', recursive=True):
    if os.path.isfile(f):
        relative_path = os.path.relpath(f, '.')
        dest_dir = os.path.dirname(relative_path)
        datas.append((f, dest_dir))

# redis – cały katalog
for f in glob.glob('redis/**/*', recursive=True):
    if os.path.isfile(f):
        relative_path = os.path.relpath(f, '.')
        dest_dir = os.path.dirname(relative_path)
        datas.append((f, dest_dir))

# manage.py w katalogu głównym
datas.append(("manage.py", "."))

a = Analysis(
    ['backend_launcher.py'],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'django',
        'celery',
        'formulavis',
        'formulavis.celery',
        'profiles',

        # Celery + Kombu
        'celery.fixups',
        'celery.fixups.django',
        'celery.backends.redis',
        'celery.backends.cache',
        'celery.app.amqp',
        'celery.app.events',
        'celery.app.control',
        'celery.worker.autoscale',
        'celery.loaders.app',
        'celery.apps',
        'celery.apps.worker',
        'celery.app.log',
        'celery.worker.strategy',
        'celery.concurrency',
        'celery.concurrency.prefork',
        'celery.events.state',
        'celery.worker.consumer',
        'celery.concurrency.solo',

        'rest_framework_jwt',
        'rest_framework_jwt.authentication',
        'rest_framework_jwt.views',
        'rest_framework_jwt.utils',

        'rest_framework.negotiation',
        'rest_framework.metadata',

        'corsheaders.middleware',

    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # STANDARDOWA konfiguracja onedir
    name='backend',
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='backend'
)
