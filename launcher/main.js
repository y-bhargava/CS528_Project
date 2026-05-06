const { app, BrowserWindow, dialog, ipcMain, shell, systemPreferences } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const hostMainPath = path.join(repoRoot, "host", "main.py");
const launcherConfigPath = path.join(app.getPath("userData"), "hci-launcher-config.json");

let mainWindow = null;
let activeRun = null;
let nextRunId = 1;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 850,
    height: 700,
    minWidth: 850,
    minHeight: 700,
    backgroundColor: "#0B0E12",
    title: "Touchless HCI Launcher",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function sendToRenderer(channel, payload) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send(channel, payload);
}

function normalizeNumber(value, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return fallback;
  }
  return n;
}

function normalizeInt(value, fallback) {
  const n = Number.parseInt(String(value), 10);
  if (!Number.isFinite(n)) {
    return fallback;
  }
  return n;
}

function clamp(value, lo, hi) {
  return Math.max(lo, Math.min(hi, value));
}

function listLikelySerialPorts() {
  if (process.platform === "win32") {
    // Conservative guess list for quick-pick UX.
    return ["COM3", "COM4", "COM5", "COM6"];
  }

  try {
    const entries = fs.readdirSync("/dev");
    const patterns =
      process.platform === "darwin"
        ? [/^cu\./]
        : [/^ttyUSB/, /^ttyACM/, /^rfcomm/, /^ttyS/];
    return entries
      .filter((name) => patterns.some((re) => re.test(name)))
      .map((name) => path.join("/dev", name))
      .slice(0, 20);
  } catch {
    return [];
  }
}

function getPythonCandidates() {
  const candidates = [];
  if (process.platform === "win32") {
    candidates.push(path.join(repoRoot, ".venv", "Scripts", "python.exe"));
    candidates.push(path.join(repoRoot, ".venv", "Scripts", "python"));
    candidates.push("python");
    candidates.push("py");
  } else {
    candidates.push(path.join(repoRoot, ".venv", "bin", "python3"));
    candidates.push(path.join(repoRoot, ".venv", "bin", "python"));
    candidates.push("python3");
    candidates.push("python");
  }
  return candidates;
}

function pickPythonExecutable() {
  const candidates = getPythonCandidates();
  for (const candidate of candidates) {
    if (candidate.includes(path.sep) && fs.existsSync(candidate)) {
      return { selected: candidate, candidates };
    }
  }
  return { selected: candidates[0], candidates };
}

function defaultConfig() {
  return {
    mode: "hybrid",
    platform: "auto",
    live: false,
    serialPort: "",
    serialBaud: 115200,
    inputFile: "",
    cameraIndex: 1,
    cvHeadless: true,
    smooth: 0.22,
    pinchThreshold: 0.045,
    dragHoldMs: 350,
    clickMoveThreshold: 24,
    hideLandmarks: true,
    enableDictationHold: false,
    dictationHoldMs: 550,
    disableContextRouting: false,
  };
}

function normalizeConfig(raw) {
  const base = defaultConfig();
  const mode = String(raw.mode || base.mode).toLowerCase();
  const platform = String(raw.platform || base.platform).toLowerCase();

  return {
    mode: ["esp", "cv", "hybrid"].includes(mode) ? mode : base.mode,
    platform: ["auto", "mac", "windows"].includes(platform) ? platform : base.platform,
    live: Boolean(raw.live),
    serialPort: String(raw.serialPort || "").trim(),
    serialBaud: Math.max(1200, normalizeInt(raw.serialBaud, base.serialBaud)),
    inputFile: String(raw.inputFile || "").trim(),
    cameraIndex: Math.max(0, normalizeInt(raw.cameraIndex, base.cameraIndex)),
    cvHeadless: raw.cvHeadless === undefined ? base.cvHeadless : Boolean(raw.cvHeadless),
    smooth: clamp(normalizeNumber(raw.smooth, base.smooth), 0.01, 1),
    pinchThreshold: Math.max(0.005, normalizeNumber(raw.pinchThreshold, base.pinchThreshold)),
    dragHoldMs: Math.max(50, normalizeInt(raw.dragHoldMs, base.dragHoldMs)),
    clickMoveThreshold: Math.max(2, normalizeNumber(raw.clickMoveThreshold, base.clickMoveThreshold)),
    hideLandmarks: Boolean(raw.hideLandmarks),
    enableDictationHold: Boolean(raw.enableDictationHold),
    dictationHoldMs: Math.max(200, normalizeInt(raw.dictationHoldMs, base.dictationHoldMs)),
    disableContextRouting: Boolean(raw.disableContextRouting),
  };
}

function readSavedConfig() {
  try {
    const text = fs.readFileSync(launcherConfigPath, "utf8");
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function writeSavedConfig(config) {
  try {
    fs.mkdirSync(path.dirname(launcherConfigPath), { recursive: true });
    fs.writeFileSync(launcherConfigPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");
    return true;
  } catch {
    return false;
  }
}

function quoteArg(value) {
  if (/^[A-Za-z0-9_./:-]+$/.test(value)) {
    return value;
  }
  return JSON.stringify(value);
}

function buildHostCommand(config, pythonExecutable) {
  const args = ["-u", hostMainPath, "--mode", config.mode, "--platform", config.platform];

  if (config.mode === "esp" || config.mode === "hybrid") {
    if (config.serialPort) {
      args.push("--serial-port", config.serialPort);
      args.push("--serial-baud", String(config.serialBaud));
    }
    if (config.inputFile) {
      args.push("--input-file", config.inputFile);
    }
  }

  if (config.mode === "cv" || config.mode === "hybrid") {
    args.push("--camera-index", String(config.cameraIndex));
    args.push("--smooth", String(config.smooth));
    args.push("--pinch-threshold", String(config.pinchThreshold));
    args.push("--drag-hold-ms", String(config.dragHoldMs));
    args.push("--click-move-threshold", String(config.clickMoveThreshold));
    if (config.hideLandmarks) {
      args.push("--hide-landmarks");
    }
    if (config.cvHeadless) {
      args.push("--headless-cv");
    }
    if (config.enableDictationHold) {
      args.push("--enable-dictation-hold");
      args.push("--dictation-hold-ms", String(config.dictationHoldMs));
    }
  }

  if (config.disableContextRouting) {
    args.push("--disable-context-routing");
  }

  if (config.live) {
    args.push("--live");
  }

  const printable = [pythonExecutable, ...args].map(quoteArg).join(" ");
  return { command: pythonExecutable, args, printable };
}

function validateStart(config) {
  if (!fs.existsSync(hostMainPath)) {
    return { ok: false, message: `host/main.py not found at ${hostMainPath}` };
  }

  if ((config.mode === "esp" || config.mode === "hybrid") && !config.serialPort && !config.inputFile) {
    return {
      ok: false,
      message: "ESP or hybrid mode needs either Serial Port or Replay Input File.",
    };
  }
  if ((config.mode === "esp" || config.mode === "hybrid") && config.serialPort && config.inputFile) {
    return {
      ok: false,
      message: "Use Serial Port or Replay Input File, not both at the same time.",
    };
  }

  return { ok: true, message: "ok" };
}

function emitRunStatus(status) {
  sendToRenderer("run:status", {
    at: new Date().toISOString(),
    ...status,
  });
}

function emitRunLog(runId, stream, text) {
  sendToRenderer("run:log", {
    runId,
    stream,
    text,
    at: new Date().toISOString(),
  });
}

function attachLineEmitter(stream, runId, streamName) {
  let buffer = "";
  stream.on("data", (chunk) => {
    buffer += chunk.toString("utf8");
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || "";
    for (const line of lines) {
      emitRunLog(runId, streamName, line);
    }
  });

  stream.on("end", () => {
    if (buffer.length > 0) {
      emitRunLog(runId, streamName, buffer);
      buffer = "";
    }
  });
}

function stopActiveRun(reason = "user") {
  if (!activeRun) {
    return false;
  }

  const runSnapshot = activeRun;
  emitRunStatus({
    runId: runSnapshot.runId,
    state: "stopping",
    reason,
  });

  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(runSnapshot.child.pid), "/t", "/f"], {
      windowsHide: true,
    });
    return true;
  }

  try {
    runSnapshot.child.kill("SIGTERM");
  } catch {
    return true;
  }

  setTimeout(() => {
    if (!activeRun || activeRun.runId !== runSnapshot.runId) {
      return;
    }
    try {
      runSnapshot.child.kill("SIGKILL");
    } catch {
      // Ignore when process already exited.
    }
  }, 1600);

  return true;
}

function getPermissionStatus() {
  const status = {
    platform: process.platform,
    camera: "unknown",
    microphone: "unknown",
    screen: "unknown",
    accessibility: "unknown",
  };

  try {
    status.camera = systemPreferences.getMediaAccessStatus("camera");
  } catch {
    status.camera = "unknown";
  }

  try {
    status.microphone = systemPreferences.getMediaAccessStatus("microphone");
  } catch {
    status.microphone = "unknown";
  }

  try {
    status.screen = systemPreferences.getMediaAccessStatus("screen");
  } catch {
    status.screen = "unknown";
  }

  if (process.platform === "darwin") {
    try {
      status.accessibility = systemPreferences.isTrustedAccessibilityClient(false)
        ? "granted"
        : "denied";
    } catch {
      status.accessibility = "unknown";
    }
  }

  return status;
}

function getPermissionSettingsURL(kind) {
  if (process.platform === "darwin") {
    const macMap = {
      camera: "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
      microphone: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
      accessibility: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
      automation: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
      inputMonitoring: "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
      screen: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    };
    return macMap[kind] || "x-apple.systempreferences:com.apple.preference.security?Privacy";
  }

  if (process.platform === "win32") {
    const winMap = {
      camera: "ms-settings:privacy-webcam",
      microphone: "ms-settings:privacy-microphone",
      accessibility: "ms-settings:easeofaccess-display",
      automation: "ms-settings:privacy",
      inputMonitoring: "ms-settings:privacy",
      screen: "ms-settings:privacy",
    };
    return winMap[kind] || "ms-settings:privacy";
  }

  return "";
}

async function openPermissionSettings(kind) {
  const url = getPermissionSettingsURL(kind);
  if (!url) {
    return { ok: false, message: "Permission deep-link not available on this platform." };
  }
  try {
    if (process.platform === "darwin") {
      const result = await new Promise((resolve) => {
        const child = spawn("open", [url], { windowsHide: true });
        child.on("close", (code) => resolve(code));
        child.on("error", () => resolve(1));
      });
      if (result !== 0) {
        return { ok: false, message: `open returned exit code ${result}` };
      }
      return { ok: true, message: `Opened settings: ${url}` };
    }
    await shell.openExternal(url);
    return { ok: true, message: `Opened settings: ${url}` };
  } catch (error) {
    return { ok: false, message: String(error) };
  }
}

function getRuntimeInfo() {
  const python = pickPythonExecutable();
  return {
    repoRoot,
    hostMainPath,
    hostMainExists: fs.existsSync(hostMainPath),
    launcherConfigPath,
    selectedPython: python.selected,
    pythonCandidates: python.candidates,
    platform: process.platform,
    hostname: os.hostname(),
    likelySerialPorts: listLikelySerialPorts(),
    isRunning: Boolean(activeRun),
  };
}

ipcMain.handle("launcher:get-runtime", async () => {
  return getRuntimeInfo();
});

ipcMain.handle("launcher:get-config", async () => {
  const saved = readSavedConfig();
  return normalizeConfig(saved || defaultConfig());
});

ipcMain.handle("launcher:save-config", async (_event, rawConfig) => {
  const normalized = normalizeConfig(rawConfig || {});
  const ok = writeSavedConfig(normalized);
  return { ok, config: normalized };
});

ipcMain.handle("launcher:pick-file", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Select NDJSON Replay File",
    properties: ["openFile"],
    filters: [
      { name: "NDJSON", extensions: ["ndjson", "jsonl", "txt", "json"] },
      { name: "All Files", extensions: ["*"] },
    ],
  });
  if (result.canceled || !result.filePaths || result.filePaths.length === 0) {
    return { canceled: true };
  }
  return { canceled: false, path: result.filePaths[0] };
});

ipcMain.handle("launcher:preview-command", async (_event, rawConfig) => {
  const config = normalizeConfig(rawConfig || {});
  const python = pickPythonExecutable();
  const command = buildHostCommand(config, python.selected);
  return {
    printable: command.printable,
    config,
  };
});

ipcMain.handle("launcher:start", async (_event, rawConfig) => {
  if (activeRun) {
    return {
      ok: false,
      message: "A run is already active. Stop it before starting another.",
    };
  }

  const config = normalizeConfig(rawConfig || {});
  const validation = validateStart(config);
  if (!validation.ok) {
    return { ok: false, message: validation.message };
  }

  writeSavedConfig(config);

  const python = pickPythonExecutable();
  const command = buildHostCommand(config, python.selected);
  const runId = nextRunId++;

  let child;
  try {
    child = spawn(command.command, command.args, {
      cwd: repoRoot,
      env: { ...process.env },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
  } catch (error) {
    return { ok: false, message: `Failed to spawn process: ${error}` };
  }

  activeRun = { runId, child };

  emitRunStatus({
    runId,
    state: "running",
    pid: child.pid,
    printableCommand: command.printable,
    config,
  });

  attachLineEmitter(child.stdout, runId, "stdout");
  attachLineEmitter(child.stderr, runId, "stderr");

  child.on("error", (error) => {
    emitRunStatus({
      runId,
      state: "error",
      message: String(error),
    });
  });

  child.on("close", (code, signal) => {
    const wasActive = activeRun && activeRun.runId === runId;
    if (wasActive) {
      activeRun = null;
    }
    emitRunStatus({
      runId,
      state: "stopped",
      code,
      signal,
    });
  });

  return {
    ok: true,
    runId,
    pid: child.pid,
    printableCommand: command.printable,
  };
});

ipcMain.handle("launcher:stop", async () => {
  const ok = stopActiveRun("user");
  return {
    ok,
    message: ok ? "Stop signal sent." : "No active run.",
  };
});

ipcMain.handle("launcher:get-permissions", async () => {
  return getPermissionStatus();
});

ipcMain.handle("launcher:request-camera", async () => {
  if (process.platform !== "darwin") {
    return { ok: false, message: "Direct camera permission prompt is only supported on macOS." };
  }

  try {
    const granted = await systemPreferences.askForMediaAccess("camera");
    return { ok: true, granted };
  } catch (error) {
    return { ok: false, message: String(error) };
  }
});

ipcMain.handle("launcher:prompt-accessibility", async () => {
  if (process.platform !== "darwin") {
    return { ok: false, message: "Accessibility prompt API is only available on macOS." };
  }

  try {
    const trusted = systemPreferences.isTrustedAccessibilityClient(true);
    return { ok: true, trusted };
  } catch (error) {
    return { ok: false, message: String(error) };
  }
});

ipcMain.handle("launcher:open-permission-settings", async (_event, kind) => {
  return openPermissionSettings(String(kind || ""));
});

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("before-quit", () => {
  stopActiveRun("app-quit");
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
