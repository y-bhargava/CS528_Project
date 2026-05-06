/* global window, document */

const formIds = [
  "mode",
  "platform",
  "live",
  "serialPort",
  "serialBaud",
  "inputFile",
  "cameraIndex",
  "cvHeadless",
  "smooth",
  "pinchThreshold",
  "dragHoldMs",
  "clickMoveThreshold",
  "hideLandmarks",
  "enableDictationHold",
  "dictationHoldMs",
  "disableContextRouting",
];

const browserPreviewLauncher = {
  getRuntime: async () => ({
    likelySerialPorts: ["/dev/cu.usbserial-10", "/dev/cu.usbmodemXXXX"],
  }),
  getConfig: async () => ({
    mode: "cv",
    platform: "auto",
    live: true,
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
  }),
  saveConfig: async () => ({ ok: true }),
  startRun: async () => ({ ok: true, pid: "preview" }),
  stopRun: async () => ({ ok: true, message: "Preview stopped." }),
  pickReplayFile: async () => ({ canceled: true }),
  getPermissions: async () => ({
    camera: "granted",
    accessibility: "denied",
  }),
  requestCameraPermission: async () => ({ ok: true, granted: true }),
  promptAccessibilityPermission: async () => ({ ok: true, trusted: false }),
  openPermissionSettings: async (kind) => ({
    ok: true,
    message: `Preview settings opened for ${kind}.`,
  }),
  onRunLog: () => () => {},
  onRunStatus: () => () => {},
};

const launcherApi = window.launcher || browserPreviewLauncher;

const fields = Object.fromEntries(formIds.map((id) => [id, document.getElementById(id)]));

const runStatus = document.getElementById("run-status");
const startButton = document.getElementById("btn-start");
const stopButton = document.getElementById("btn-stop");

const openSettingsButton = document.getElementById("btn-open-settings");
const closeSettingsButton = document.getElementById("btn-close-settings");
const settingsDrawer = document.getElementById("settings-drawer");
const drawerBackdrop = document.getElementById("drawer-backdrop");
const windowShell = document.querySelector(".window-shell");

const toggleLogsButton = document.getElementById("btn-toggle-logs");
const clearLogButton = document.getElementById("btn-clear-log");
const logPanel = document.getElementById("log-panel");
const logOutput = document.getElementById("log-output");

const pickFileButton = document.getElementById("btn-pick-file");
const refreshPortsButton = document.getElementById("btn-refresh-ports");
const refreshPermButton = document.getElementById("btn-refresh-perm");
const requestCameraButton = document.getElementById("btn-request-camera");
const requestAccessibilityButton = document.getElementById("btn-request-accessibility");
const openPermSettingsButton = document.getElementById("btn-open-perm-settings");
const permCamera = document.getElementById("perm-camera");
const permAccessibility = document.getElementById("perm-accessibility");
const permSummaryState = document.getElementById("perm-summary-state");
const permMessage = document.getElementById("perm-message");

let saveTimer = null;
let lineCount = 0;
let logsVisible = false;
let cachedPermissions = null;
let settingsVisible = true;
let cachedSerialPorts = [];

function isCheckedInput(id) {
  return [
    "live",
    "cvHeadless",
    "hideLandmarks",
    "enableDictationHold",
    "disableContextRouting",
  ].includes(id);
}

function getFormConfig() {
  const config = {};
  for (const [id, el] of Object.entries(fields)) {
    if (!el) {
      continue;
    }
    if (isCheckedInput(id)) {
      config[id] = Boolean(el.checked);
    } else {
      config[id] = el.value;
    }
  }
  return config;
}

function renderSerialPortOptions(ports, selectedValue = "") {
  const serialField = fields.serialPort;
  if (!serialField) {
    return;
  }

  const uniquePorts = [...new Set((ports || []).map((p) => String(p).trim()).filter(Boolean))];
  cachedSerialPorts = uniquePorts;
  serialField.innerHTML = "";

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = uniquePorts.length > 0 ? "Select a serial port" : "No serial ports found";
  serialField.appendChild(placeholder);

  for (const port of uniquePorts) {
    const option = document.createElement("option");
    option.value = port;
    option.textContent = port;
    serialField.appendChild(option);
  }

  if (selectedValue && uniquePorts.includes(selectedValue)) {
    serialField.value = selectedValue;
  } else {
    serialField.value = "";
  }
}

async function refreshSerialPorts() {
  const selectedBefore = String(fields.serialPort?.value || "");
  try {
    const runtime = await launcherApi.getRuntime();
    const detected = runtime?.likelySerialPorts || [];
    renderSerialPortOptions(detected, selectedBefore);
    if (selectedBefore && fields.serialPort.value !== selectedBefore) {
      appendLog(`serial port '${selectedBefore}' is not currently detected`, "err");
    }
  } catch (error) {
    appendLog(`serial port refresh failed: ${error}`, "err");
  }
}

function applyConfig(config) {
  const selectedPort = String(config.serialPort || "");
  if (selectedPort && !cachedSerialPorts.includes(selectedPort)) {
    cachedSerialPorts = [...cachedSerialPorts, selectedPort];
  }
  renderSerialPortOptions(cachedSerialPorts, selectedPort);

  for (const [id, el] of Object.entries(fields)) {
    if (!el || !(id in config)) {
      continue;
    }
    if (isCheckedInput(id)) {
      el.checked = Boolean(config[id]);
    } else {
      el.value = String(config[id]);
    }
  }
  refreshModeScopedFields();
}

function refreshModeScopedFields() {
  const mode = fields.mode.value;
  const espVisible = mode === "esp" || mode === "hybrid";
  const cvVisible = mode === "cv" || mode === "hybrid";

  for (const el of document.querySelectorAll(".esp-only")) {
    el.classList.toggle("hidden-mode-field", !espVisible);
  }
  for (const el of document.querySelectorAll(".cv-only")) {
    el.classList.toggle("hidden-mode-field", !cvVisible);
  }
}

function updateStatusPill(state, extra) {
  const map = {
    idle: { label: "Idle", bg: "rgba(255,255,255,0.05)", border: "rgba(210,224,245,0.22)" },
    running: { label: "Running", bg: "rgba(95,204,163,0.18)", border: "rgba(151,237,202,0.52)" },
    stopping: { label: "Stopping", bg: "rgba(255,196,112,0.18)", border: "rgba(255,218,156,0.5)" },
    stopped: { label: "Stopped", bg: "rgba(149,176,214,0.18)", border: "rgba(192,214,245,0.42)" },
    error: { label: "Error", bg: "rgba(255,126,135,0.2)", border: "rgba(255,168,174,0.52)" },
  };

  const chosen = map[state] || map.idle;
  runStatus.textContent = extra ? `${chosen.label} · ${extra}` : chosen.label;
  runStatus.style.background = chosen.bg;
  runStatus.style.borderColor = chosen.border;
}

function appendLog(text, kind) {
  const line = document.createElement("div");
  line.className = `log-line ${kind}`;
  line.textContent = text;
  logOutput.appendChild(line);

  lineCount += 1;
  const maxLines = 1200;
  while (lineCount > maxLines && logOutput.firstChild) {
    logOutput.removeChild(logOutput.firstChild);
    lineCount -= 1;
  }

  logOutput.scrollTop = logOutput.scrollHeight;
}

function permissionLooksValid(value) {
  const normalized = String(value || "").toLowerCase();
  return normalized === "granted" || normalized === "authorized";
}

function setPermissionMessage(message, kind = "info") {
  if (!permMessage) {
    return;
  }
  permMessage.textContent = message;
  if (kind === "error") {
    permMessage.style.color = "#ffb3b9";
  } else if (kind === "success") {
    permMessage.style.color = "#9be9c8";
  } else {
    permMessage.style.color = "";
  }
}

function renderPermissionBadge(el, value) {
  if (!el) {
    return;
  }
  const valid = permissionLooksValid(value);
  el.classList.remove("valid", "invalid");
  el.classList.add(valid ? "valid" : "invalid");
  el.textContent = valid ? "Valid" : "Invalid";
}

function renderPermissionSummary(status) {
  if (!permSummaryState) {
    return;
  }
  const cameraValid = permissionLooksValid(status.camera);
  const accessibilityValid = permissionLooksValid(status.accessibility);
  permSummaryState.classList.remove("valid", "invalid");
  permSummaryState.classList.add(cameraValid && accessibilityValid ? "valid" : "invalid");
  permSummaryState.textContent = cameraValid && accessibilityValid ? "Valid" : "Needs Setup";
}

function preferredPermissionSettingsKind() {
  if (!cachedPermissions) {
    return "camera";
  }
  if (!permissionLooksValid(cachedPermissions.camera)) {
    return "camera";
  }
  if (!permissionLooksValid(cachedPermissions.accessibility)) {
    return "accessibility";
  }
  return "automation";
}

async function refreshPermissions() {
  try {
    const status = await launcherApi.getPermissions();
    cachedPermissions = status;
    renderPermissionBadge(permCamera, status.camera);
    renderPermissionBadge(permAccessibility, status.accessibility);
    renderPermissionSummary(status);
    setPermissionMessage(
      `Camera: ${String(status.camera || "unknown")} · Accessibility: ${String(status.accessibility || "unknown")}`,
      "info",
    );
  } catch (error) {
    appendLog(`permission check failed: ${error}`, "err");
    setPermissionMessage(`Permission check failed: ${error}`, "error");
  }
}

function setLogsVisible(visible) {
  logsVisible = visible;
  logPanel.hidden = !visible;
  toggleLogsButton.textContent = visible ? "Hide logs" : "Show logs";
}

function setDrawerOpen(open) {
  settingsVisible = open;
  if (windowShell) {
    windowShell.classList.toggle("settings-collapsed", !open);
  }
  if (open) {
    settingsDrawer.classList.add("open");
    settingsDrawer.setAttribute("aria-hidden", "false");
    drawerBackdrop.hidden = false;
  } else {
    settingsDrawer.classList.remove("open");
    settingsDrawer.setAttribute("aria-hidden", "true");
    drawerBackdrop.hidden = true;
  }
}

function scheduleSave() {
  if (saveTimer) {
    clearTimeout(saveTimer);
  }
  saveTimer = setTimeout(async () => {
    try {
      await launcherApi.saveConfig(getFormConfig());
    } catch {
      // Non-blocking save.
    }
  }, 220);
}

async function startRun() {
  startButton.disabled = true;
  stopButton.disabled = true;
  try {
    const result = await launcherApi.startRun(getFormConfig());
    if (!result.ok) {
      appendLog(result.message || "failed to start run", "err");
      updateStatusPill("error");
      startButton.disabled = false;
      stopButton.disabled = true;
      return;
    }

    appendLog(`started pid=${result.pid}`, "sys");
    updateStatusPill("running", `PID ${result.pid}`);
    stopButton.disabled = false;
  } catch (error) {
    appendLog(`start error: ${error}`, "err");
    updateStatusPill("error");
    startButton.disabled = false;
    stopButton.disabled = true;
  }
}

async function stopRun() {
  try {
    const result = await launcherApi.stopRun();
    appendLog(result.message, result.ok ? "sys" : "err");
  } catch (error) {
    appendLog(`stop error: ${error}`, "err");
  }
}

function bindEvents() {
  fields.mode.addEventListener("change", () => {
    refreshModeScopedFields();
    scheduleSave();
  });

  for (const [id, el] of Object.entries(fields)) {
    if (!el || id === "mode") {
      continue;
    }
    const eventName = isCheckedInput(id) ? "change" : "input";
    el.addEventListener(eventName, scheduleSave);
  }

  startButton.addEventListener("click", startRun);
  stopButton.addEventListener("click", stopRun);

  openSettingsButton.addEventListener("click", () => setDrawerOpen(!settingsVisible));
  closeSettingsButton.addEventListener("click", () => setDrawerOpen(false));
  drawerBackdrop.addEventListener("click", () => setDrawerOpen(false));

  toggleLogsButton.addEventListener("click", () => setLogsVisible(!logsVisible));
  clearLogButton.addEventListener("click", () => {
    logOutput.innerHTML = "";
    lineCount = 0;
  });

  pickFileButton.addEventListener("click", async () => {
    const result = await launcherApi.pickReplayFile();
    if (!result.canceled && result.path) {
      fields.inputFile.value = result.path;
      scheduleSave();
    }
  });
  if (refreshPortsButton) {
    refreshPortsButton.addEventListener("click", async () => {
      await refreshSerialPorts();
      scheduleSave();
    });
  }

  refreshPermButton.addEventListener("click", refreshPermissions);

  requestCameraButton.addEventListener("click", async () => {
    try {
      setPermissionMessage("Checking camera permission…", "info");
      const before = await launcherApi.getPermissions();
      const status = String(before.camera || "").toLowerCase();

      if (status === "granted" || status === "authorized") {
        appendLog("camera permission already valid", "sys");
        setPermissionMessage("Camera already valid.", "success");
        await refreshPermissions();
        return;
      }

      if (status === "denied" || status === "restricted") {
        const openResult = await launcherApi.openPermissionSettings("camera");
        appendLog(
          "camera permission is denied; macOS will not re-prompt. Opened settings.",
          "err",
        );
        appendLog(
          `open settings (camera): ${openResult.message}`,
          openResult.ok ? "sys" : "err",
        );
        setPermissionMessage(
          openResult.ok
            ? "Camera denied. Opened System Settings; enable camera access there."
            : `Could not open settings: ${openResult.message}`,
          openResult.ok ? "info" : "error",
        );
        await refreshPermissions();
        return;
      }

      const result = await launcherApi.requestCameraPermission();
      appendLog(`camera permission prompt: ${JSON.stringify(result)}`, result.ok ? "sys" : "err");
      if (result.ok && result.granted) {
        setPermissionMessage("Camera permission granted.", "success");
      } else if (result.ok && result.granted === false) {
        const openResult = await launcherApi.openPermissionSettings("camera");
        setPermissionMessage(
          openResult.ok
            ? "Camera not granted. Opened System Settings for manual enable."
            : "Camera not granted. Please open System Settings > Privacy > Camera.",
          "error",
        );
      } else {
        setPermissionMessage(`Camera request failed: ${result.message || "unknown error"}`, "error");
      }
      await refreshPermissions();
    } catch (error) {
      appendLog(`camera request crashed: ${error}`, "err");
      setPermissionMessage(`Camera request failed: ${error}`, "error");
    }
  });

  requestAccessibilityButton.addEventListener("click", async () => {
    try {
      const result = await launcherApi.promptAccessibilityPermission();
      appendLog(
        `accessibility permission: ${JSON.stringify(result)}`,
        result.ok ? "sys" : "err",
      );
      if (result.ok && result.trusted) {
        setPermissionMessage("Accessibility permission granted.", "success");
      } else {
        setPermissionMessage("Accessibility not granted yet. Approve in System Settings.", "error");
      }
      await refreshPermissions();
    } catch (error) {
      setPermissionMessage(`Accessibility request failed: ${error}`, "error");
    }
  });

  openPermSettingsButton.addEventListener("click", async () => {
    const kind = preferredPermissionSettingsKind();
    const result = await launcherApi.openPermissionSettings(kind);
    appendLog(`open settings (${kind}): ${result.message}`, result.ok ? "sys" : "err");
    setPermissionMessage(
      result.ok ? `Opened settings for ${kind}.` : `Could not open settings: ${result.message}`,
      result.ok ? "info" : "error",
    );
  });

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setDrawerOpen(false);
    }
  });

  launcherApi.onRunLog((entry) => {
    const kind = entry.stream === "stderr" ? "err" : "out";
    appendLog(entry.text, kind);
  });

  launcherApi.onRunStatus((status) => {
    if (status.state === "running") {
      updateStatusPill("running", `PID ${status.pid || "-"}`);
      startButton.disabled = true;
      stopButton.disabled = false;
    } else if (status.state === "stopping") {
      updateStatusPill("stopping");
    } else if (status.state === "stopped") {
      updateStatusPill("stopped", `code ${status.code ?? "?"}`);
      startButton.disabled = false;
      stopButton.disabled = true;
      appendLog(
        `run exited code=${status.code ?? "?"} signal=${status.signal || "none"}`,
        "sys",
      );
    } else if (status.state === "error") {
      updateStatusPill("error");
      startButton.disabled = false;
      stopButton.disabled = true;
      appendLog(status.message || "runtime error", "err");
    }
  });
}

async function bootstrap() {
  bindEvents();

  stopButton.disabled = true;
  updateStatusPill("idle");
  setLogsVisible(false);
  setDrawerOpen(true);

  await refreshSerialPorts();
  const config = await launcherApi.getConfig();
  applyConfig(config);
  await refreshPermissions();
}

bootstrap().catch((error) => {
  appendLog(`launcher bootstrap failed: ${error}`, "err");
  updateStatusPill("error");
});
