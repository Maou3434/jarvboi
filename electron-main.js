const { app, BrowserWindow, Tray, Menu, ipcMain, nativeImage } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let tray;
let pythonProcess;
let isQuitting = false;

// 1. Spawns the Python sidecar backend
function startPythonBackend() {
  const venvPython = path.join(__dirname, 'venv', 'Scripts', 'python.exe');
  const pythonPath = fs.existsSync(venvPython) ? venvPython : 'python';
  const apiScript = path.join(__dirname, 'api.py');

  console.log(`[Electron] Starting Python sidecar with: ${pythonPath} ${apiScript}`);

  pythonProcess = spawn(pythonPath, [apiScript], {
    cwd: __dirname,
    windowsHide: true, // Prevents cmd popup on Windows
    shell: false
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python Stdout]: ${data.toString().trim()}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python Stderr]: ${data.toString().trim()}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`[Electron] Python process exited with code ${code}`);
  });
}

// 2. Kills the Python process
function killPythonBackend() {
  if (pythonProcess) {
    console.log('[Electron] Terminating Python sidecar process...');
    pythonProcess.kill('SIGINT');
    pythonProcess = null;
  }
}

// 3. Creates the System Tray (Notification Area)
function createTray() {
  const iconPath = path.join(__dirname, 'icon.png');
  let trayImage;

  if (fs.existsSync(iconPath)) {
    // Resize for tray standard resolution (16x16 or 24x24)
    trayImage = nativeImage.createFromPath(iconPath).resize({ width: 20, height: 20 });
  } else {
    // Fallback if icon isn't present
    trayImage = nativeImage.createEmpty();
  }

  tray = new Tray(trayImage);
  tray.setToolTip('Jarvboi Assistant (Running in Background)');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Interface',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      }
    },
    {
      label: 'Restart Core Server',
      click: () => {
        killPythonBackend();
        setTimeout(startPythonBackend, 1000);
      }
    },
    { type: 'separator' },
    {
      label: 'Exit Entirely',
      click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]);

  tray.setContextMenu(contextMenu);

  // Toggle window on tray click
  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    }
  });
}

// 4. Creates the Main Window
function createWindow() {
  const iconPath = path.join(__dirname, 'icon.png');

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 750,
    frame: false, // Frameless for a sleek HUD look
    resizable: true,
    show: true,
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'electron-preload.js')
    }
  });

  // Decide whether to load Vite dev server or production built files
  const isDev = !app.isPackaged && process.argv.includes('--dev');
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    // Open DevTools if in dev mode
    mainWindow.webContents.openDevTools();
  } else {
    // Check if dist folder exists, otherwise load ui index.html
    const distPath = path.join(__dirname, 'ui', 'dist', 'index.html');
    if (fs.existsSync(distPath)) {
      mainWindow.loadFile(distPath);
    } else {
      mainWindow.loadFile(path.join(__dirname, 'ui', 'index.html'));
    }
  }

  // Intercept window close to hide to tray instead
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// IPC listeners for the custom titlebar buttons
ipcMain.on('window-minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window-close', () => {
  if (mainWindow) mainWindow.hide(); // Minimize/Close to tray
});

// 5. Electron Lifecycle Setup
app.whenReady().then(() => {
  startPythonBackend();
  createTray();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  // Respecting close-to-tray so we only quit when isQuitting is set from menu
  if (process.platform !== 'darwin' && isQuitting) {
    app.quit();
  }
});

app.on('will-quit', () => {
  killPythonBackend();
});
