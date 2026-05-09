const { app, BrowserWindow, dialog, ipcMain, shell, systemPreferences } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const launcherRoot = __dirname;
const workspaceRoot = path.resolve(launcherRoot, "..");
const devResourcesRoot = path.join(launcherRoot, "resources");
const launcherConfigPath = path.join(app.getPath("userData"), "hci-launcher-config.json");
const appIconPath = path.join(__dirname, "assets", "icons", "app-icon-transparent.png");

app.setName("Touchless Launcher");

let mainWindow = null;
let activeRun = null;
let activeVerify = null;
let activeFlash = null;
let nextRunId = 1;
const ACTION_COOLDOWNS_MS = {
  PREV_TAB: 350,
  NEXT_TAB: 350,
  NEW_TAB: 350,
  CLOSE_TAB: 350,
  PLAY_PAUSE: 1000,
  PREV_SLIDE: 300,
  NEXT_SLIDE: 300,
  START_PRESENTATION: 800,
  EXIT_PRESENTATION: 800,
  PREV_TRACK: 400,
  NEXT_TRACK: 400,
  VOLUME_UP: 200,
  VOLUME_DOWN: 200,
  SWITCH_SPACE_LEFT: 850,
  SWITCH_SPACE_RIGHT: 850,
  MISSION_CONTROL: 850,
  TRIGGER_SEARCH: 850,
  PAGE_UP: 350,
  PAGE_DOWN: 350,
  PRESS_ENTER: 200,
  TOGGLE_PAUSE: 350,
};
const lastExternalActionAt = new Map();
const externalRunState = new Map();

function getExternalState(runId) {
  let state = externalRunState.get(runId);
  if (!state) {
    state = {
      cursorX: 0,
      cursorY: 0,
      hasCursor: false,
      isDragging: false,
      dictationHeld: false,
      lastMoveAtMs: 0,
      lastScrollAtMs: 0,
    };
    externalRunState.set(runId, state);
  }
  return state;
}

function getResourcesRoot() {
  return app.isPackaged ? process.resourcesPath : devResourcesRoot;
}

function getHostMainPath() {
  return path.join(workspaceRoot, "host", "main.py");
}

function getBundledExecutableName(baseName) {
  return process.platform === "win32" ? `${baseName}.exe` : baseName;
}

function getBundledExecutablePath(baseName) {
  const exe = getBundledExecutableName(baseName);
  const runtimeRoot = path.join(getResourcesRoot(), "runtime");
  const direct = path.join(runtimeRoot, exe);
  const bundledDir = path.join(runtimeRoot, baseName, exe);
  if (fs.existsSync(bundledDir)) {
    return bundledDir;
  }
  return direct;
}

function getBundledHostPath() {
  return getBundledExecutablePath("touchless-host");
}

function getBundledEspToolPath() {
  return getBundledExecutablePath("touchless-esp-tool");
}

function getBundledFirmwareManifestPath() {
  return path.join(getResourcesRoot(), "firmware", "flasher_args.json");
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 850,
    height: 765,
    minWidth: 850,
    minHeight: 765,
    icon: appIconPath,
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
    candidates.push(path.join(workspaceRoot, ".venv", "Scripts", "python.exe"));
    candidates.push(path.join(workspaceRoot, ".venv", "Scripts", "python"));
    candidates.push("python");
    candidates.push("py");
  } else {
    candidates.push(path.join(workspaceRoot, ".venv", "bin", "python3"));
    candidates.push(path.join(workspaceRoot, ".venv", "bin", "python"));
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
    desktopUpEnter: false,
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
    desktopUpEnter: Boolean(raw.desktopUpEnter),
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

function buildHostArgs(config) {
  const args = ["--mode", config.mode, "--platform", config.platform];

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
  if (config.desktopUpEnter) {
    args.push("--desktop-up-enter");
  }

  if (config.live) {
    args.push("--live");
  }

  return args;
}

function resolveHostInvoker() {
  const bundledHostPath = getBundledHostPath();
  if (fs.existsSync(bundledHostPath)) {
    return {
      kind: "bundled",
      command: bundledHostPath,
      preArgs: [],
      printablePrefix: bundledHostPath,
    };
  }

  if (app.isPackaged) {
    return {
      kind: "missing",
      command: null,
      preArgs: [],
      printablePrefix: bundledHostPath,
      error:
        "Packaged host runtime is missing. Rebuild installer resources to include runtime/touchless-host.",
    };
  }

  const hostMainPath = getHostMainPath();
  const python = pickPythonExecutable();
  return {
    kind: "python",
    command: python.selected,
    preArgs: ["-u", hostMainPath],
    printablePrefix: python.selected,
  };
}

function buildHostCommand(config) {
  const hostArgs = buildHostArgs(config);
  const invoker = resolveHostInvoker();
  if (!invoker.command) {
    return {
      command: null,
      args: [],
      printable: invoker.printablePrefix,
      runtimeKind: invoker.kind,
      error: invoker.error || "Host runtime unavailable.",
    };
  }
  const args = [...invoker.preArgs, ...hostArgs];
  const printable = [invoker.printablePrefix, ...args].map(quoteArg).join(" ");
  return {
    command: invoker.command,
    args,
    printable,
    runtimeKind: invoker.kind,
  };
}

function buildHostEnv(config = null) {
  const env = { ...process.env };
  // Keep matplotlib cache in a stable writable location so font-cache build
  // is one-time and does not repeat every run.
  const mplConfigDir = path.join(app.getPath("userData"), "mplconfig");
  const xdgCacheHome = path.join(app.getPath("userData"), "cache");
  const homeDir = app.getPath("home");
  try {
    fs.mkdirSync(mplConfigDir, { recursive: true });
    fs.mkdirSync(xdgCacheHome, { recursive: true });
    env.MPLCONFIGDIR = mplConfigDir;
    env.XDG_CACHE_HOME = xdgCacheHome;
    if (homeDir) {
      env.HOME = homeDir;
    }
  } catch {
    // Best effort only; host can still run with default environment.
  }
  if (config && config.live) {
    // Route all live OS injection through launcher so Accessibility is tied
    // to Touchless Launcher.app instead of embedded runtime binaries.
    env.TOUCHLESS_EXTERNAL_EXECUTOR = "1";
  }
  return env;
}

function resolveEspToolInvoker() {
  const bundledEspToolPath = getBundledEspToolPath();
  if (fs.existsSync(bundledEspToolPath)) {
    return {
      kind: "bundled",
      command: bundledEspToolPath,
      preArgs: [],
      printablePrefix: bundledEspToolPath,
    };
  }

  if (app.isPackaged) {
    return {
      kind: "missing",
      command: null,
      preArgs: [],
      printablePrefix: bundledEspToolPath,
      error:
        "Packaged ESP tool is missing. Rebuild installer resources to include runtime/touchless-esp-tool.",
    };
  }

  const python = pickPythonExecutable();
  const espToolScriptPath = path.join(workspaceRoot, "launcher", "runtime_src", "esp_tool.py");
  return {
    kind: "python",
    command: python.selected,
    preArgs: [espToolScriptPath],
    printablePrefix: python.selected,
  };
}

function buildEspToolCommand(extraArgs) {
  const invoker = resolveEspToolInvoker();
  if (!invoker.command) {
    return {
      command: null,
      args: [],
      printable: invoker.printablePrefix,
      runtimeKind: invoker.kind,
      error: invoker.error || "ESP runtime unavailable.",
    };
  }
  const args = [...invoker.preArgs, ...extraArgs];
  const printable = [invoker.printablePrefix, ...args].map(quoteArg).join(" ");
  return {
    command: invoker.command,
    args,
    printable,
    runtimeKind: invoker.kind,
  };
}

function validateStart(config) {
  const hostInvoker = resolveHostInvoker();
  if (!hostInvoker.command) {
    return {
      ok: false,
      message: hostInvoker.error || "Host runtime is unavailable.",
    };
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

function attachLineEmitter(stream, runId, streamName, onLine) {
  let buffer = "";
  stream.on("data", (chunk) => {
    buffer += chunk.toString("utf8");
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || "";
    for (const line of lines) {
      emitRunLog(runId, streamName, line);
      if (onLine) {
        onLine(line, streamName);
      }
    }
  });

  stream.on("end", () => {
    if (buffer.length > 0) {
      emitRunLog(runId, streamName, buffer);
      if (onLine) {
        onLine(buffer, streamName);
      }
      buffer = "";
    }
  });
}

function shouldRunExternalAction(action) {
  const now = Date.now();
  const cooldown = Number(ACTION_COOLDOWNS_MS[action] || 0);
  const last = lastExternalActionAt.get(action);
  if (last && cooldown > 0 && now - last < cooldown) {
    return false;
  }
  lastExternalActionAt.set(action, now);
  return true;
}

function spawnOsaScript(lines) {
  const args = [];
  for (const line of lines) {
    args.push("-e", line);
  }
  return spawn("osascript", args, {
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function spawnOsaJavaScript(source) {
  return spawn("osascript", ["-l", "JavaScript", "-e", source], {
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function runJXABridge(runId, label, source, onSuccess = null) {
  let child;
  try {
    child = spawnOsaJavaScript(source);
  } catch (error) {
    emitRunLog(runId, "stderr", `[bridge-error] ${label} spawn failed: ${error}`);
    return;
  }
  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString("utf8");
  });
  child.on("close", (code) => {
    if (code !== 0) {
      emitRunLog(
        runId,
        "stderr",
        `[bridge-error] ${label} rc=${code}${stderr ? ` stderr=${stderr.trim()}` : ""}`,
      );
      return;
    }
    if (onSuccess) {
      onSuccess();
    }
  });
}

function parseKV(tailText) {
  const out = {};
  const text = String(tailText || "").trim();
  if (!text) {
    return out;
  }
  const parts = text.split(/\s+/);
  for (const part of parts) {
    const idx = part.indexOf("=");
    if (idx <= 0) {
      continue;
    }
    const key = part.slice(0, idx);
    const value = part.slice(idx + 1);
    out[key] = value;
  }
  return out;
}

function _mouseEventScript(eventConstant, x, y) {
  const nx = Math.round(Number(x));
  const ny = Math.round(Number(y));
  return [
    'ObjC.import("ApplicationServices");',
    `var p = $.CGPointMake(${nx}, ${ny});`,
    `var e = $.CGEventCreateMouseEvent(null, $.${eventConstant}, p, $.kCGMouseButtonLeft);`,
    "$.CGEventPost($.kCGHIDEventTap, e);",
  ].join(" ");
}

function _scrollEventScript(steps) {
  const n = Math.trunc(Number(steps));
  return [
    'ObjC.import("ApplicationServices");',
    `var e = $.CGEventCreateScrollWheelEvent(null, $.kCGScrollEventUnitLine, 1, ${n});`,
    "$.CGEventPost($.kCGHIDEventTap, e);",
  ].join(" ");
}

function _keyboardEventScript(keyCode, keyDown) {
  const code = Math.trunc(Number(keyCode));
  const down = keyDown ? "true" : "false";
  return [
    'ObjC.import("ApplicationServices");',
    `var e = $.CGEventCreateKeyboardEvent(null, ${code}, ${down});`,
    "$.CGEventPost($.kCGHIDEventTap, e);",
  ].join(" ");
}

function executeExternalAction(action, runId) {
  if (!shouldRunExternalAction(action)) {
    return;
  }
  if (process.platform !== "darwin") {
    emitRunLog(runId, "stderr", `[bridge-error] external executor unsupported on ${process.platform}`);
    return;
  }

  const scripts = {
    PREV_TAB: ['tell application "System Events" to key code 33 using {command down, shift down}'],
    NEXT_TAB: ['tell application "System Events" to key code 30 using {command down, shift down}'],
    NEW_TAB: ['tell application "System Events" to keystroke "t" using {command down}'],
    CLOSE_TAB: ['tell application "System Events" to keystroke "w" using {command down}'],
    PLAY_PAUSE: ['tell application "System Events" to key code 100'],
    PREV_SLIDE: ['tell application "System Events" to key code 126'],
    NEXT_SLIDE: ['tell application "System Events" to key code 125'],
    START_PRESENTATION: ['tell application "System Events" to keystroke "p" using {command down, option down}'],
    EXIT_PRESENTATION: ['tell application "System Events" to key code 53'],
    PREV_TRACK: ['tell application "Spotify" to previous track'],
    NEXT_TRACK: ['tell application "Spotify" to next track'],
    VOLUME_UP: [
      'tell application "Spotify" to set v to sound volume',
      "set v to v + 20",
      "if v > 100 then set v to 100",
      'tell application "Spotify" to set sound volume to v',
    ],
    VOLUME_DOWN: [
      'tell application "Spotify" to set v to sound volume',
      "set v to v - 20",
      "if v < 0 then set v to 0",
      'tell application "Spotify" to set sound volume to v',
    ],
    SWITCH_SPACE_LEFT: ['tell application "System Events" to key code 123 using {control down}'],
    SWITCH_SPACE_RIGHT: ['tell application "System Events" to key code 124 using {control down}'],
    MISSION_CONTROL: ['tell application "System Events" to key code 126 using {control down}'],
    TRIGGER_SEARCH: ['tell application "System Events" to keystroke space using {command down, option down}'],
    PAGE_UP: ['tell application "System Events" to key code 116'],
    PAGE_DOWN: ['tell application "System Events" to key code 121'],
    PRESS_ENTER: ['tell application "System Events" to key code 36'],
  };
  const lines = scripts[action];
  if (!lines) {
    return;
  }

  let child;
  try {
    child = spawnOsaScript(lines);
  } catch (error) {
    emitRunLog(runId, "stderr", `[bridge-error] action=${action} spawn failed: ${error}`);
    return;
  }
  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString("utf8");
  });
  child.on("close", (code) => {
    if (code !== 0) {
      emitRunLog(
        runId,
        "stderr",
        `[bridge-error] action=${action} rc=${code}${stderr ? ` stderr=${stderr.trim()}` : ""}`,
      );
    }
  });
}

function executeExternalCvEvent(eventType, fields, runId) {
  if (process.platform !== "darwin") {
    emitRunLog(runId, "stderr", `[bridge-error] cv_event unsupported on ${process.platform}`);
    return;
  }
  const state = getExternalState(runId);
  const now = Date.now();

  if (eventType === "move") {
    const x = Number.parseInt(fields.x || "", 10);
    const y = Number.parseInt(fields.y || "", 10);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return;
    }
    // CV can emit very frequently; cap launcher-side bridge rate.
    if (now - state.lastMoveAtMs < 18) {
      return;
    }
    const eventTypeConstant = state.isDragging
      ? "kCGEventLeftMouseDragged"
      : "kCGEventMouseMoved";
    runJXABridge(runId, `cv:${eventType}`, _mouseEventScript(eventTypeConstant, x, y), () => {
      state.cursorX = x;
      state.cursorY = y;
      state.hasCursor = true;
      state.lastMoveAtMs = Date.now();
    });
    return;
  }

  if (eventType === "dragDown") {
    if (state.isDragging) {
      return;
    }
    if (!state.hasCursor) {
      return;
    }
    const x = state.hasCursor ? state.cursorX : 0;
    const y = state.hasCursor ? state.cursorY : 0;
    runJXABridge(runId, "cv:dragDown", _mouseEventScript("kCGEventLeftMouseDown", x, y), () => {
      state.isDragging = true;
    });
    return;
  }

  if (eventType === "dragUp") {
    if (!state.isDragging) {
      return;
    }
    const x = state.hasCursor ? state.cursorX : 0;
    const y = state.hasCursor ? state.cursorY : 0;
    runJXABridge(runId, "cv:dragUp", _mouseEventScript("kCGEventLeftMouseUp", x, y), () => {
      state.isDragging = false;
    });
    return;
  }

  if (eventType === "click") {
    if (!state.hasCursor) {
      return;
    }
    const x = state.hasCursor ? state.cursorX : 0;
    const y = state.hasCursor ? state.cursorY : 0;
    const script = [
      _mouseEventScript("kCGEventLeftMouseDown", x, y),
      _mouseEventScript("kCGEventLeftMouseUp", x, y),
    ].join(" ");
    runJXABridge(runId, "cv:click", script);
    return;
  }

  if (eventType === "scroll") {
    const steps = Number.parseInt(fields.steps || "", 10);
    if (!Number.isFinite(steps) || steps === 0) {
      return;
    }
    if (now - state.lastScrollAtMs < 16) {
      return;
    }
    runJXABridge(runId, "cv:scroll", _scrollEventScript(steps), () => {
      state.lastScrollAtMs = Date.now();
    });
    return;
  }

  if (eventType === "dictationDown") {
    if (state.dictationHeld) {
      return;
    }
    runJXABridge(runId, "cv:dictationDown", _keyboardEventScript(63, true), () => {
      state.dictationHeld = true;
    });
    return;
  }

  if (eventType === "dictationUp") {
    if (!state.dictationHeld) {
      return;
    }
    runJXABridge(runId, "cv:dictationUp", _keyboardEventScript(63, false), () => {
      state.dictationHeld = false;
    });
  }
}

function releaseExternalRunState(runId) {
  if (process.platform === "darwin") {
    const state = externalRunState.get(runId);
    if (state) {
      const x = state.hasCursor ? state.cursorX : 0;
      const y = state.hasCursor ? state.cursorY : 0;
      if (state.isDragging) {
        runJXABridge(runId, "cv:cleanupDragUp", _mouseEventScript("kCGEventLeftMouseUp", x, y));
      }
      if (state.dictationHeld) {
        runJXABridge(runId, "cv:cleanupDictationUp", _keyboardEventScript(63, false));
      }
    }
  }
  externalRunState.delete(runId);
}

function maybeHandleExternalActionLine(line, runId) {
  const text = String(line || "").trim();
  if (!text) {
    return;
  }
  const actionMatch = text.match(/^execute action=([A-Z0-9_]+) mode=external$/);
  if (actionMatch) {
    executeExternalAction(actionMatch[1], runId);
    return;
  }
  const cvMatch = text.match(/^cv_event type=([A-Za-z0-9_]+)(?:\s+(.*))?$/);
  if (cvMatch) {
    const eventType = cvMatch[1];
    const fields = parseKV(cvMatch[2] || "");
    executeExternalCvEvent(eventType, fields, runId);
  }
}

function stopActiveRun(reason = "user") {
  if (!activeRun) {
    return false;
  }

  const runSnapshot = activeRun;
  releaseExternalRunState(runSnapshot.runId);
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

async function getPermissionStatus() {
  const status = {
    platform: process.platform,
    camera: "unknown",
    microphone: "unknown",
    screen: "unknown",
    accessibility: "unknown",
    accessibilitySource: "launcher",
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
      status.accessibilitySource = "unknown";
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
  const hostMainPath = getHostMainPath();
  const python = pickPythonExecutable();
  const bundledHostPath = getBundledHostPath();
  const bundledEspToolPath = getBundledEspToolPath();
  const firmwareManifestPath = getBundledFirmwareManifestPath();
  const resolvedHost = resolveHostInvoker();
  const resolvedEspTool = resolveEspToolInvoker();
  return {
    repoRoot: workspaceRoot,
    resourcesRoot: getResourcesRoot(),
    appPath: app.getAppPath(),
    executablePath: app.getPath("exe"),
    isPackaged: app.isPackaged,
    hostMainPath,
    hostMainExists: fs.existsSync(hostMainPath),
    bundledHostPath,
    bundledHostExists: fs.existsSync(bundledHostPath),
    bundledEspToolPath,
    bundledEspToolExists: fs.existsSync(bundledEspToolPath),
    firmwareManifestPath,
    firmwareManifestExists: fs.existsSync(firmwareManifestPath),
    selectedHostRuntime: resolvedHost.kind,
    selectedEspToolRuntime: resolvedEspTool.kind,
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
  const command = buildHostCommand(config);
  return {
    printable: command.printable,
    error: command.error || null,
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

  const command = buildHostCommand(config);
  if (!command.command) {
    return { ok: false, message: command.error || "Host runtime is unavailable." };
  }
  const runId = nextRunId++;

  let child;
  try {
    child = spawn(command.command, command.args, {
      cwd: workspaceRoot,
      env: buildHostEnv(config),
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

  attachLineEmitter(child.stdout, runId, "stdout", (line) => maybeHandleExternalActionLine(line, runId));
  attachLineEmitter(child.stderr, runId, "stderr");

  child.on("error", (error) => {
    emitRunStatus({
      runId,
      state: "error",
      message: String(error),
    });
  });

  child.on("close", (code, signal) => {
    releaseExternalRunState(runId);
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
    const before = systemPreferences.getMediaAccessStatus("camera");
    const granted = await systemPreferences.askForMediaAccess("camera");
    const after = systemPreferences.getMediaAccessStatus("camera");
    return { ok: true, granted, before, after };
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
    const settings = await openPermissionSettings("accessibility");
    return {
      ok: true,
      trusted,
      settingsOpened: settings.ok,
    };
  } catch (error) {
    return { ok: false, message: String(error) };
  }
});

ipcMain.handle("launcher:open-permission-settings", async (_event, kind) => {
  return openPermissionSettings(String(kind || ""));
});

ipcMain.handle("launcher:flash-esp", async (_event, serialPort) => {
  const port = String(serialPort || "").trim();
  if (!port) {
    return { ok: false, message: "Serial port is required." };
  }
  if (activeFlash) {
    return { ok: false, message: "Flash is already running." };
  }
  const firmwareManifest = getBundledFirmwareManifestPath();
  if (!fs.existsSync(firmwareManifest)) {
    return {
      ok: false,
      message:
        "Bundled firmware manifest is missing. Run launcher/scripts/sync_firmware.py before packaging.",
    };
  }
  const command = buildEspToolCommand([
    "flash",
    "--port",
    port,
    "--manifest",
    firmwareManifest,
  ]);
  if (!command.command) {
    return { ok: false, message: command.error || "ESP tool is unavailable." };
  }

  let child;
  try {
    child = spawn(command.command, command.args, {
      cwd: workspaceRoot,
      env: { ...process.env },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    return { ok: false, message: `Failed to start flash: ${error}` };
  }

  activeFlash = { child, port };
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => {
    stdout += chunk.toString("utf8");
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString("utf8");
  });

  const result = await new Promise((resolve) => {
    child.on("close", (code) => resolve({ code }));
    child.on("error", (error) =>
      resolve({
        code: 1,
        error: String(error),
      }),
    );
  });
  activeFlash = null;

  if (result.code !== 0) {
    return {
      ok: false,
      message: "ESP flash failed.",
      stdout,
      stderr: `${stderr}${result.error ? `\n${result.error}` : ""}\n[command] ${command.printable}`,
    };
  }
  return {
    ok: true,
    message: "ESP flashed successfully (bundled flasher).",
    stdout,
    stderr,
  };
});

ipcMain.handle("launcher:stop-flash-esp", async () => {
  if (!activeFlash) {
    return { ok: true, message: "Flash is not running." };
  }
  try {
    activeFlash.child.kill("SIGTERM");
  } catch {
    // Ignore if already closed.
  }
  return { ok: true, message: "Flash stop requested." };
});

ipcMain.handle("launcher:verify-esp-stream", async (_event, serialPort) => {
  const port = String(serialPort || "").trim();
  if (!port) {
    return { ok: false, message: "Serial port is required." };
  }
  const command = buildEspToolCommand([
    "verify-once",
    "--port",
    port,
    "--baud",
    "115200",
    "--timeout",
    "6.0",
  ]);
  if (!command.command) {
    return { ok: false, message: command.error || "ESP tool is unavailable." };
  }

  const result = await new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let spawned = null;
    try {
      spawned = spawn(command.command, command.args, {
        cwd: workspaceRoot,
        env: { ...process.env },
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (error) {
      resolve({ code: 1, stdout: "", stderr: String(error) });
      return;
    }
    spawned.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });
    spawned.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    spawned.on("close", (code) => resolve({ code, stdout, stderr }));
    spawned.on("error", (error) => resolve({ code: 1, stdout, stderr: `${stderr}\n${error}` }));
  });

  const hitsLine = String(result.stdout || "")
    .trim()
    .split(/\r?\n/)
    .filter(Boolean)
    .pop();
  const hits = Number.parseInt(String(hitsLine || ""), 10);
  if (result.code !== 0 || !Number.isFinite(hits) || hits < 1) {
    return {
      ok: false,
      message: "No gesture stream detected. Move ESP and retry.",
      stdout: result.stdout,
      stderr: `${result.stderr || ""}\n[command] ${command.printable}`,
    };
  }
  return {
    ok: true,
    message: `ESP stream verified (${hits} gesture event detected).`,
    stdout: result.stdout,
    stderr: result.stderr,
  };
});

ipcMain.handle("launcher:start-verify-esp-stream", async (_event, serialPort) => {
  const port = String(serialPort || "").trim();
  if (!port) {
    return { ok: false, message: "Serial port is required." };
  }
  if (activeVerify) {
    return { ok: false, message: "Verify stream is already running." };
  }
  const command = buildEspToolCommand(["verify-stream", "--port", port, "--baud", "115200"]);
  if (!command.command) {
    return { ok: false, message: command.error || "ESP tool is unavailable." };
  }
  let child;
  try {
    child = spawn(command.command, command.args, {
      cwd: workspaceRoot,
      env: { ...process.env },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
  } catch (error) {
    return { ok: false, message: `Failed to start verify stream: ${error}` };
  }

  activeVerify = { child, port };
  let ready = false;
  let startupFailureDetail = "";
  let readyResolver = null;
  const readyPromise = new Promise((resolve) => {
    readyResolver = resolve;
  });

  const pipeOut = (stream, kind) => {
    let buffer = "";
    stream.on("data", (chunk) => {
      buffer += chunk.toString("utf8");
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (kind === "stdout" && line === "__VERIFY_READY__") {
          ready = true;
          sendToRenderer("onboarding:verify-status", { state: "running", port });
          if (readyResolver) {
            readyResolver(true);
            readyResolver = null;
          }
          continue;
        }
        if (!ready && kind === "stderr") {
          startupFailureDetail = line;
        }
        sendToRenderer("onboarding:verify-log", { stream: kind, text: line });
      }
    });
    stream.on("end", () => {
      if (buffer.length > 0) {
        sendToRenderer("onboarding:verify-log", { stream: kind, text: buffer });
      }
    });
  };

  pipeOut(child.stdout, "stdout");
  pipeOut(child.stderr, "stderr");

  child.on("close", (code, signal) => {
    if (!ready && readyResolver) {
      readyResolver(false);
      readyResolver = null;
    }
    activeVerify = null;
    sendToRenderer("onboarding:verify-status", {
      state: "stopped",
      code,
      signal,
    });
  });

  child.on("error", (error) => {
    sendToRenderer("onboarding:verify-log", {
      stream: "stderr",
      text: String(error),
    });
  });

  const startupOk = await Promise.race([
    readyPromise,
    new Promise((resolve) => setTimeout(() => resolve(false), 2500)),
  ]);
  if (!startupOk) {
    const reason = startupFailureDetail || "Verify stream failed to start.";
    return {
      ok: false,
      message: `Verify startup failed: ${reason}`,
    };
  }
  return { ok: true, message: "Verify stream started." };
});

ipcMain.handle("launcher:stop-verify-esp-stream", async () => {
  if (!activeVerify) {
    return { ok: true, message: "Verify stream is not running." };
  }
  try {
    activeVerify.child.kill("SIGTERM");
  } catch {
    // Ignore already-closed process.
  }
  return { ok: true, message: "Verify stream stop requested." };
});

app.whenReady().then(() => {
  if (process.platform === "darwin" && app.dock && appIconPath) {
    try {
      app.dock.setIcon(appIconPath);
    } catch {
      // Ignore if icon cannot be set at runtime.
    }
  }
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("before-quit", () => {
  stopActiveRun("app-quit");
  if (activeFlash) {
    try {
      activeFlash.child.kill("SIGTERM");
    } catch {
      // Ignore if already exited.
    }
  }
  if (activeVerify) {
    try {
      activeVerify.child.kill("SIGTERM");
    } catch {
      // Ignore if already exited.
    }
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
