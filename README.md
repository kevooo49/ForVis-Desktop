# ForVis – Instrukcja deweloperska
Poniżej znajduje się instrukcja krok po kroku, jak uruchomić projekt w środowisku lokalnym.

1. **Wymagania wstępne**
Python: wersja 3.6.8

Node.js & npm

Środowisko wirtualne: venv

2. **Konfiguracja i uruchomienie**
# Krok 1: Backend (Python & Celery)
Upewnij się, że masz zainstalowane biblioteki z pliku requirements.txt wewnątrz swojego środowiska wirtualnego.

Otwórz terminal i aktywuj venv.

Uruchom skrypty startowe (na Windows użyj terminala typu Git Bash):

Bash
./run_desktop.sh
./run_celery_desktop.sh

# Krok 2: Redis
Projekt wymaga serwera Redis działającego na porcie 6379. Przejdź do folderu redis i wykonaj:

Linux/macOS/Git Bash:

Bash
redis-server --port 6379
Windows (CMD/PowerShell):

Bash
./redis-server.exe --port 6379

# Krok 3: Frontend (Angular)
Przejdź do katalogu forvis-frontend, zainstaluj zależności i uruchom frontend:

npm install   # Wykonaj tylko przy pierwszym uruchomieniu
npm start

3. **Podgląd projektu**
Po poprawnym uruchomieniu wszystkich komponentów, aplikacja powinna być dostępna pod adresem:
http://localhost:4200


# Jak stworzyć instalator? 

1. W katalogu głównym (na venv):
pyinstaller --clean --console backend.spec

2. Tworzy się wtedy nowy folder dist/backend w katalogu głównym. Folder backend skopiuj w całości do folderu forvis-frontend. 

3. Przejdź do folderu forvis-frontend:
npm run build:desktop

4. Następnie:
npm run dist

i w folderze release stworzy się plik .exe


Stare readme (do wersji mobilnej uruchamianej przez dockera)

# ForVis

# Wymagania wstępne:

1. **Zainstalowany Docker oraz Docker Compose**
   - Instrukcja instalacji Docker na Ubuntu 16.04: 
     [DigitalOcean Tutorial](https://www.digitalocean.com/community/tutorials/how-to-install-and-use-docker-on-ubuntu-16-04)
   - Instalacja Docker Compose:
     ```bash
     sudo apt install docker-compose
     ```
   - Instalacja Node.js i npm:
     ```bash
     sudo apt install nodejs
     sudo apt install npm
     ```

2. **Wyłączenie serwera Apache, jeśli działa:**
   ```bash
   sudo pkill apache
   ```

---

# Instrukcja uruchomienia systemu:

1. **Budowanie plików frontendowych:**
   Z katalogu `frontend/formulavis` wykonaj:
   ```bash
   npm install
   npm run build
   ```

2. **Uruchomienie systemu z folderu z plikiem `docker-compose.yml`:**
   - Standardowe uruchomienie:
     ```bash
     docker-compose up
     ```
   - Jeśli wymagane są uprawnienia administratora:
     ```bash
     sudo docker-compose up
     ```

3. **Uniknięcie błędów z plikami:**
   Wykonaj poniższą komendę:
   ```bash
   sudo chmod 777 _files
   ```

---

# Rozwiązywanie problemów:

### 1. **Błąd "Got permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock":**
   Ustaw odpowiednie uprawnienia:
   ```bash
   sudo chmod 666 /var/run/docker.sock
   ```

### 2. **Błąd związany z działającymi serwisami (np. nginx, postgres):**
   Wyłącz działające serwisy:
   ```bash
   sudo service nginx stop
   sudo service postgres stop
   ```

### 3. **Błąd "version in ... unsupported":**
   W pliku `docker-compose.yml` zmień wersję z `3` na `2`.

### 4. **Błąd związany z usługą nginx lub frontendem:**
   Postępuj zgodnie z poniższymi krokami:
   1. Zatrzymaj system:
      ```bash
      CTRL + C lub docker-compose stop
      ```

   2. W sekcji `frontend` pliku `docker-compose.yml` dodaj opcję:
      ```yml
      command: npm install --no-optional
      ```

   3. Uruchom system ponownie:
      ```bash
      docker-compose up
      ```

   4. Po ponownym wystąpieniu błędu frontend, zatrzymaj system:
      ```bash
      docker-compose stop
      ```

   5. Usuń wcześniej dodaną opcję w sekcji `frontend` w pliku `docker-compose.yml`.

   6. Uruchom system ponownie:
      ```bash
      docker-compose up
      ```

---

# Dane administratora:

- Login: `admin`
- Hasło: `admin`

---

# Dostęp do systemu:

1. **Strona główna projektu:**
   Wpisz w przeglądarce:
   ```txt
   localhost
   ```

2. **Panel administratora:**
   Wpisz w przeglądarce:
   ```txt
   localhost:8000/admin/
   ```

---

# **DEVELOPMENT**

   first terminal window:
   ```bash
   cd forvis-frontend
   ng serve --host 0.0.0.0 --port 4200
   ```

   second terminal window:
   ```bash
   docker-compose -f docker-compose.dev.yml up --build
   ```



**Uwagi dodatkowe:**
- System może wymagać kilku sekund na pełne uruchomienie.
- Powyższe instrukcje są zoptymalizowane dla Ubuntu 16.04, ale mogą działać również na nowszych wersjach systemu.