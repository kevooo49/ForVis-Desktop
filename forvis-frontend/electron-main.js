const { app, BrowserWindow } = require('electron');
const path = require('path');

const { startBackend, stopBackend } = require('./electron-backend');

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 1000,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: false,
      nodeIntegration: true,
      sandbox: false
    }
  });

  const indexPath = path.join(
    __dirname,
    'dist',
    'formula-visualisation',
    'browser',
    'index.html'
  );

  console.log("📄 Loading index:", indexPath);
  mainWindow.loadFile(indexPath);

  mainWindow.on('closed', () => {
    console.log("🛑 Window closed → stopping backend");
    stopBackend();
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  console.log("🚀 App ready – starting backend...");
  startBackend();
  createWindow();
});

app.on('before-quit', () => {
  console.log("🛑 before-quit → stopping backend");
  stopBackend();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
