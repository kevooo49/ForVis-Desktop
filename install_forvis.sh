#!/bin/bash
set -e

# Gdzie instalujemy aplikację (możesz zmienić, jak chcesz)
APP_DIR="$HOME/.local/forvis-desktop"
DESKTOP_FILE="$HOME/.local/share/applications/forvis-desktop.desktop"

echo "==> Installing ForVis Desktop to: $APP_DIR"

# Tworzymy katalog instalacyjny
mkdir -p "$APP_DIR"

echo "==> Copying project files..."
# Kopiujemy CAŁY projekt (bez .git, node_modules itp. żeby nie było syfu)
rsync -a --exclude='.git' --exclude='node_modules' --exclude='dist' ./ "$APP_DIR/"

cd "$APP_DIR"

echo "==> Creating Python virtualenv (.venv)"
python3.6 -m venv .venv

echo "==> Activating venv and installing Python dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Installing frontend dependencies (npm install)..."
cd forvis-frontend
npm install

echo "==> Building Angular app for desktop..."
npm run build:desktop

cd "$APP_DIR"

echo "==> Creating launch script for ForVis Desktop..."

cat > forvis-launch.sh << 'EOF'
#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$APP_DIR"

# Aktywujemy venv
source .venv/bin/activate

# Upewniamy się, że Redis działa – jeśli masz go jako usługę systemową, możesz ten fragment pominąć
if ! pgrep -x "redis-server" > /dev/null; then
  echo "Starting redis-server..."
  redis-server --daemonize yes
fi

echo "Starting Celery..."
# Jeśli masz osobny skrypt do Celery, użyj go tu:
./run_celery_desktop.sh &

sleep 2

echo "Starting Django backend..."
./run_desktop.sh &

sleep 3

echo "Starting Electron frontend..."
cd forvis-frontend
npm run electron
EOF

chmod +x forvis-launch.sh

echo "==> Creating desktop entry: $DESKTOP_FILE"

mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=ForVis Desktop
Comment=SAT / MaxSAT formula visualizer
Exec=$APP_DIR/forvis-launch.sh
Icon=$APP_DIR/forvis-frontend/src/assets/images/tree.png
Terminal=false
Categories=Education;Science;Development;
EOF

echo "==> Updating desktop database (might be optional)..."
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "==> Installation finished."
echo "You should now see 'ForVis Desktop' in your applications menu."
echo "You can also run: $APP_DIR/forvis-launch.sh"
