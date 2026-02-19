const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let backendProcess = null;

function resolveBackendExePath() {
  // PRODUKCJA (po instalacji)
  const prodPath = path.join(process.resourcesPath, 'backend', 'backend.exe');
  if (fs.existsSync(prodPath)) {
    console.log("✔ FOUND backend in production:", prodPath);
    return prodPath;
  }

  // DEV
  const devPath = path.join(__dirname, '..', 'dist', 'backend', 'backend.exe');
  if (fs.existsSync(devPath)) {
    console.log("✔ FOUND backend in dev:", devPath);
    return devPath;
  }

  console.error("❌ backend.exe NOT FOUND in any location.");
  return null;
}

function startBackend() {
  const backendPath = resolveBackendExePath();
  if (!backendPath) {
    console.error("❌ Backend could not be started (no path).");
    return;
  }

  const logPath = path.join(appDataDir(), "backend.log");
  const out = fs.openSync(logPath, 'a');
  const err = fs.openSync(logPath, 'a');

  console.log("🚀 Starting backend:", backendPath);
  console.log("📝 Writing logs to:", logPath);

  console.log("Electron backend PATH:", backendPath);

  backendProcess = spawn(backendPath, {
    detached: false,
    windowsHide: true,
    stdio: ['ignore', out, err]
  });

  backendProcess.on('exit', (code) => {
    console.error("❌ Backend exited with code:", code);
  });
}

function appDataDir() {
  const dir = path.join(process.env.APPDATA || ".", "ForVisDesktopLogs");
  if (!fs.existsSync(dir)) fs.mkdirSync(dir);
  return dir;
}

function stopBackend() {
  if (backendProcess) {
    console.log("🛑 Stopping backend");
    backendProcess.kill();
    backendProcess = null;
  }
}

module.exports = { startBackend, stopBackend };
