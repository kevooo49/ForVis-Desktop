import subprocess
import sys
import os
import time
import signal

if os.name == "nt":
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)

REDIS_DIR = os.path.join(BASE_DIR, "redis")
REDIS_PATH = os.path.join(REDIS_DIR, "redis-server.exe")
REDIS_CONF = os.path.join(REDIS_DIR, "redis.windows.conf")

env = os.environ.copy()
env["DJANGO_SETTINGS_MODULE"] = "formulavis.settings_desktop2"
env["PYTHONPATH"] = BASE_DIR

processes = []


def start_redis():
    print("[ForVis] Starting Redis...")

    p = subprocess.Popen(
        [REDIS_PATH, REDIS_CONF],
        cwd=REDIS_DIR,
        env=env,
        creationflags=CREATE_NO_WINDOW
    )

    processes.append(p)
    time.sleep(1)


def run_django():
    print("[ForVis] Django process started.")
    os.chdir(BASE_DIR)

    from django.core.management import execute_from_command_line
    execute_from_command_line(["manage.py", "migrate", "--noinput"])
    execute_from_command_line(["manage.py", "runserver", "127.0.0.1:8765", "--noreload"])


def run_celery():
    print("[ForVis] Celery process started.")
    os.chdir(BASE_DIR)

    from celery.bin.celery import main as celery_main
    sys.argv = ["celery", "-A", "formulavis", "worker", "--loglevel=INFO", "-P", "solo", "--concurrency=1"]
    celery_main()


def start_django_process():
    print("[ForVis] Starting Django backend...")
    p = subprocess.Popen(
        [sys.executable, sys.argv[0], "--django"],
        cwd=BASE_DIR,
        env=env,
        creationflags=CREATE_NO_WINDOW
    )
    processes.append(p)
    time.sleep(1)


def start_celery_process():
    print("[ForVis] Starting Celery worker...")
    p = subprocess.Popen(
        [sys.executable, sys.argv[0], "--celery"],
        cwd=BASE_DIR,
        env=env,
        creationflags=CREATE_NO_WINDOW
    )
    processes.append(p)


def shutdown():
    print("[ForVis] Shutting down all processes...")
    for p in processes:
        try:
            p.terminate()
        except:
            pass


def main_launcher():
    start_redis()
    start_django_process()
    start_celery_process()

    print("[ForVis] Backend started.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":

    exe_name = os.path.basename(sys.argv[0]).lower()
    if "backend" not in exe_name:
        sys.exit(0)

    if "--django" in sys.argv:
        run_django()
    elif "--celery" in sys.argv:
        run_celery()
    else:
        main_launcher()
