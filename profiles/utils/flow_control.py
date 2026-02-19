import redis
import json
import numpy as np
from django.conf import settings

# 1. Twój niestandardowy wyjątek. 
# Działa jak katapulta - wyrzuca nas z dowolnego miejsca w kodzie.
class PauseInterrupt(Exception):
    def __init__(self, state_data):
        self.state_data = state_data
        super().__init__("Process paused by user")

# 2. Encoder, żeby JSON nie wywalił się na macierzach Numpy
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        return super(NumpyEncoder, self).default(obj)

# 3. Funkcja-strażnik. Wstawiasz ją w pętle.
def check_interruption(task_id, context_data):
    """
    Sprawdza w Redis, czy ustawiono flagę PAUSE dla danego task_id.
    Jeśli tak - rzuca wyjątek PauseInterrupt z danymi context_data.
    """
    # Połączenie do Redisa (dostosuj host/port jeśli masz inne w settings)
    r = redis.Redis(host='localhost', port=6379, db=0)
    
    # Klucz w Redis, np. "pause_task_12345"
    pause_key = f"pause_task_{task_id}"
    
    if r.exists(pause_key):
        print(f"[DEBUG WORKER] PAUSE DETECTED for task {task_id}! Stopping...")
        # Usuwamy klucz, żeby po wznowieniu nie zapauzowało się od razu ponownie
        r.delete(pause_key)
        
        # RZUCAMY WYJĄTEK - to jest ten moment "Eject"
        raise PauseInterrupt(context_data)
        

# 4. Funkcja do wywołania z widoku (Django View), gdy user klika przycisk
def trigger_pause_signal(task_id):
    r = redis.Redis(host='localhost', port=6379, db=0)
    # Ustawiamy klucz z krótkim czasem życia (np. 1 godzina), żeby nie śmiecić
    r.setex(f"pause_task_{task_id}", 3600, "1")