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
  "desktopUpEnter",
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
    desktopUpEnter: false,
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
  flashEsp: async (serialPort) => ({ ok: true, message: `Preview flashed ${serialPort}.` }),
  stopFlashEsp: async () => ({ ok: true, message: "Preview flash stop requested." }),
  startVerifyEspStream: async (serialPort) => ({ ok: true, message: `Preview verify started on ${serialPort}.` }),
  stopVerifyEspStream: async () => ({ ok: true, message: "Preview verify stopped." }),
  onRunLog: () => () => {},
  onRunStatus: () => () => {},
  onVerifyLog: () => () => {},
  onVerifyStatus: () => () => {},
};

const launcherApi = window.launcher || browserPreviewLauncher;

const fields = Object.fromEntries(formIds.map((id) => [id, document.getElementById(id)]));

const runStatus = document.getElementById("run-status");
const liveCountdown = document.getElementById("live-countdown");
const startupOverlay = document.getElementById("startup-overlay");
const startupOverlayTitle = document.getElementById("startup-overlay-title");
const startupOverlayMessage = document.getElementById("startup-overlay-message");
const startButton = document.getElementById("btn-start");
const stopButton = document.getElementById("btn-stop");

const openSettingsButton = document.getElementById("btn-open-settings");
const closeSettingsButton = document.getElementById("btn-close-settings");
const openOnboardingButton = document.getElementById("btn-open-onboarding");
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
const permRuntimeInfo = document.getElementById("perm-runtime-info");
const onboarding = document.getElementById("onboarding");
const onbSystemStatus = document.getElementById("onb-system-status");
const onbPortStatus = document.getElementById("onb-port-status");
const onbFlashStatus = document.getElementById("onb-flash-status");
const onbVerifyStatus = document.getElementById("onb-verify-status");
const onbSerialPort = document.getElementById("onb-serial-port");
const onbCompleteButton = document.getElementById("onb-complete");
const onbStepSystem = document.getElementById("onb-step-system");
const onbStepPort = document.getElementById("onb-step-port");
const onbStepFlash = document.getElementById("onb-step-flash");
const onbStepVerify = document.getElementById("onb-step-verify");
const onbLogOutput = document.getElementById("onb-log-output");
const onbClearLogs = document.getElementById("onb-clear-logs");
const wiringModal = document.getElementById("wiring-modal");
const onbOpenWiring = document.getElementById("onb-open-wiring");
const wiringClose = document.getElementById("wiring-close");

let saveTimer = null;
let lineCount = 0;
let onbLogLineCount = 0;
let logsVisible = false;
let cachedPermissions = null;
let cachedRuntime = null;
let settingsVisible = true;
let cachedSerialPorts = [];
let onboardingState = {
  systemOk: false,
  portOk: false,
  flashOk: false,
  verifyOk: false,
};
let verifyStreaming = false;
let flashInProgress = false;
let liveCountdownTimer = null;
let startupOverlayTimer = null;
let startupWarmupActive = false;

function onboardingDone() {
  return window.localStorage.getItem("hciOnboardingDone") === "1";
}

function markOnboardingDone() {
  window.localStorage.setItem("hciOnboardingDone", "1");
}

function renderStepHighlights() {
  onbStepSystem.classList.toggle("active", !onboardingState.systemOk && !onboardingState.portOk);
  onbStepPort.classList.toggle("active", !onboardingState.portOk);
  onbStepFlash.classList.toggle(
    "active",
    onboardingState.portOk && !onboardingState.flashOk,
  );
  onbStepVerify.classList.toggle(
    "active",
    onboardingState.portOk && onboardingState.flashOk && !onboardingState.verifyOk,
  );
  onbCompleteButton.disabled = !(onboardingState.portOk && onboardingState.flashOk && onboardingState.verifyOk);
}

function appendOnboardingLog(text, kind = "info") {
  if (!onbLogOutput) {
    return;
  }
  const line = document.createElement("div");
  line.className = `onb-log-line ${kind}`;
  line.textContent = `[${kind}] ${text}`;
  onbLogOutput.appendChild(line);
  onbLogLineCount += 1;
  const maxLines = 1200;
  while (onbLogLineCount > maxLines && onbLogOutput.firstChild) {
    onbLogOutput.removeChild(onbLogOutput.firstChild);
    onbLogLineCount -= 1;
  }
  onbLogOutput.scrollTop = onbLogOutput.scrollHeight;
}

function isCheckedInput(id) {
  return [
    "live",
    "cvHeadless",
    "hideLandmarks",
    "enableDictationHold",
    "disableContextRouting",
    "desktopUpEnter",
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

function renderOnboardingSerialOptions(ports, selectedValue = "") {
  if (!onbSerialPort) {
    return;
  }
  const uniquePorts = [...new Set((ports || []).map((p) => String(p).trim()).filter(Boolean))];
  onbSerialPort.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = uniquePorts.length > 0 ? "Select a serial port" : "No serial ports found";
  onbSerialPort.appendChild(placeholder);
  for (const port of uniquePorts) {
    const option = document.createElement("option");
    option.value = port;
    option.textContent = port;
    onbSerialPort.appendChild(option);
  }
  if (selectedValue && uniquePorts.includes(selectedValue)) {
    onbSerialPort.value = selectedValue;
  }
}

async function refreshSerialPorts() {
  const selectedBefore = String(fields.serialPort?.value || "");
  try {
    const runtime = await launcherApi.getRuntime();
    cachedRuntime = runtime || null;
    renderRuntimeInfo();
    const detected = runtime?.likelySerialPorts || [];
    renderSerialPortOptions(detected, selectedBefore);
    if (selectedBefore && fields.serialPort.value !== selectedBefore) {
      appendLog(`serial port '${selectedBefore}' is not currently detected`, "err");
    }
  } catch (error) {
    appendLog(`serial port refresh failed: ${error}`, "err");
  }
  renderOnboardingSerialOptions(cachedSerialPorts, onbSerialPort.value || "");
}

function renderRuntimeInfo() {
  if (!permRuntimeInfo || !cachedRuntime) {
    return;
  }
  const hostBackend = String(cachedRuntime.selectedHostRuntime || "unknown");
  const espBackend = String(cachedRuntime.selectedEspToolRuntime || "unknown");
  const packaged = Boolean(cachedRuntime.isPackaged);
  const appPath = String(cachedRuntime.appPath || "");
  const fromDmgVolume = packaged && appPath.includes("/Volumes/");

  const modeText = packaged ? "packaged" : "dev";
  let suffix = "";
  if (fromDmgVolume) {
    suffix = " (running from DMG volume; install to /Applications)";
  }
  permRuntimeInfo.textContent = `Runtime: ${modeText} · host=${hostBackend} · esp=${espBackend}${suffix}`;
  permRuntimeInfo.style.color = fromDmgVolume ? "#ffd7a8" : "";
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

function clearLiveCountdownTimer() {
  if (liveCountdownTimer) {
    clearTimeout(liveCountdownTimer);
    liveCountdownTimer = null;
  }
}

function clearStartupOverlayTimer() {
  if (startupOverlayTimer) {
    clearTimeout(startupOverlayTimer);
    startupOverlayTimer = null;
  }
}

function setStartupOverlay(visible, title = "", message = "", autoHideMs = 0) {
  if (!startupOverlay || !startupOverlayTitle || !startupOverlayMessage) {
    return;
  }
  clearStartupOverlayTimer();
  startupOverlay.hidden = !visible;
  if (visible) {
    if (title) {
      startupOverlayTitle.textContent = title;
    }
    if (message) {
      startupOverlayMessage.textContent = message;
    }
    if (autoHideMs > 0) {
      startupOverlayTimer = setTimeout(() => {
        startupOverlay.hidden = true;
        startupOverlayTimer = null;
      }, autoHideMs);
    }
  }
}

function setLiveCountdownMessage(message, { autoHideMs = 0 } = {}) {
  if (!liveCountdown) {
    return;
  }
  clearLiveCountdownTimer();
  if (!message) {
    liveCountdown.textContent = "";
    liveCountdown.hidden = true;
    return;
  }
  liveCountdown.textContent = message;
  liveCountdown.hidden = false;
  if (autoHideMs > 0) {
    liveCountdownTimer = setTimeout(() => {
      if (liveCountdown) {
        liveCountdown.textContent = "";
        liveCountdown.hidden = true;
      }
      liveCountdownTimer = null;
    }, autoHideMs);
  }
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
    const source =
      status.accessibilitySource && status.accessibilitySource !== "unknown"
        ? ` (${status.accessibilitySource})`
        : "";
    setPermissionMessage(
      `Camera: ${String(status.camera || "unknown")} · Accessibility: ${String(status.accessibility || "unknown")}${source}`,
      "info",
    );
    if (status.accessibilityDetail) {
      appendLog(`accessibility probe detail: ${status.accessibilityDetail}`, "warn");
    }
  } catch (error) {
    appendLog(`permission check failed: ${error}`, "err");
    setPermissionMessage(`Permission check failed: ${error}`, "error");
  }
}

async function refreshOnboardingSystemCheck() {
  try {
    const status = await launcherApi.getPermissions();
    const cameraValid = permissionLooksValid(status.camera);
    const accessibilityValid = permissionLooksValid(status.accessibility);
    onboardingState.systemOk = cameraValid && accessibilityValid;
    if (onboardingState.systemOk) {
      onbSystemStatus.textContent = "System check passed (recommended for CV/hybrid).";
      appendOnboardingLog("System check passed (camera + accessibility).", "ok");
    } else {
      onbSystemStatus.textContent = `Camera: ${status.camera}, Accessibility: ${status.accessibility}`;
      appendOnboardingLog(
        `System check pending (non-blocking for ESP setup): camera=${status.camera}, accessibility=${status.accessibility}`,
        "warn",
      );
    }
    renderStepHighlights();
  } catch (error) {
    onbSystemStatus.textContent = `System check failed: ${error}`;
    onboardingState.systemOk = false;
    appendOnboardingLog(`System check failed: ${error}`, "err");
    renderStepHighlights();
  }
}

function refreshOnboardingPortState() {
  onboardingState.portOk = Boolean(onbSerialPort.value);
  if (onboardingState.portOk) {
    onbPortStatus.textContent = `Selected: ${onbSerialPort.value}`;
  } else {
    onbPortStatus.textContent = "Select a serial port.";
  }
  if (!onboardingState.portOk) {
    onboardingState.flashOk = false;
    onboardingState.verifyOk = false;
    onbFlashStatus.textContent = "Not started.";
    onbVerifyStatus.textContent = "Not started.";
  }
  renderStepHighlights();
}

async function flashOnboardingEsp() {
  if (!onbSerialPort.value) {
    onbFlashStatus.textContent = "Choose a serial port first.";
    return;
  }
  onbFlashStatus.textContent = "Flashing ESP... this may take a minute.";
  appendOnboardingLog(`Starting flash on ${onbSerialPort.value}...`);
  flashInProgress = true;
  onboardingState.flashOk = false;
  onboardingState.verifyOk = false;
  onbVerifyStatus.textContent = "Not started.";
  renderStepHighlights();
  const result = await launcherApi.flashEsp(onbSerialPort.value);
  flashInProgress = false;
  if (!result.ok) {
    onbFlashStatus.textContent = `Flash failed. ${result.message}`;
    appendOnboardingLog(result.message, "err");
    if (result.stdout) {
      appendOnboardingLog(result.stdout.trim(), "stdout");
    }
    if (result.stderr) {
      appendOnboardingLog(result.stderr.trim(), "stderr");
    }
    appendLog(result.stderr || result.stdout || result.message, "err");
    renderStepHighlights();
    return;
  }
  onboardingState.flashOk = true;
  onbFlashStatus.textContent = "Flash complete.";
  appendOnboardingLog("Flash complete.", "ok");
  if (result.stdout) {
    appendOnboardingLog(result.stdout.trim(), "stdout");
  }
  renderStepHighlights();
}

async function verifyOnboardingEspStream() {
  if (!onbSerialPort.value) {
    onbVerifyStatus.textContent = "Choose a serial port first.";
    return;
  }
  const onbVerifyButton = document.getElementById("onb-verify");
  if (!verifyStreaming) {
    onbVerifyStatus.textContent = "Starting live verify stream...";
    appendOnboardingLog(`Starting verify stream on ${onbSerialPort.value}...`);
    const result = await launcherApi.startVerifyEspStream(onbSerialPort.value);
    if (!result.ok) {
      onbVerifyStatus.textContent = result.message;
      appendOnboardingLog(result.message, "err");
      return;
    }
    verifyStreaming = true;
    onboardingState.verifyOk = true;
    onbVerifyStatus.textContent = "Verify stream running. Move ESP to test.";
    if (onbVerifyButton) {
      onbVerifyButton.textContent = "Stop";
    }
    renderStepHighlights();
    return;
  }
  const stopResult = await launcherApi.stopVerifyEspStream();
  verifyStreaming = false;
  if (onbVerifyButton) {
    onbVerifyButton.textContent = "Verify";
  }
  onbVerifyStatus.textContent = stopResult.message || "Verify stream stopped.";
  appendOnboardingLog(stopResult.message || "Verify stream stopped.", "info");
}

function completeOnboarding() {
  Promise.allSettled([stopVerifyIfRunning(), stopFlashIfRunning()]).finally(() => {
    fields.serialPort.value = onbSerialPort.value || fields.serialPort.value;
    scheduleSave();
    markOnboardingDone();
    onboarding.hidden = true;
  });
}

async function stopVerifyIfRunning() {
  if (!verifyStreaming) {
    return;
  }
  const onbVerifyButton = document.getElementById("onb-verify");
  const result = await launcherApi.stopVerifyEspStream();
  verifyStreaming = false;
  if (onbVerifyButton) {
    onbVerifyButton.textContent = "Verify";
  }
  onbVerifyStatus.textContent = result.message || "Verify stream stopped.";
  appendOnboardingLog(result.message || "Verify stream stopped.", "info");
}

async function stopFlashIfRunning() {
  if (!flashInProgress) {
    return;
  }
  const result = await launcherApi.stopFlashEsp();
  onbFlashStatus.textContent = result.message || "Flash stop requested.";
  appendOnboardingLog(result.message || "Flash stop requested.", "info");
  flashInProgress = false;
}

function resetOnboardingSessionUi() {
  const onbVerifyButton = document.getElementById("onb-verify");
  if (onbVerifyButton) {
    onbVerifyButton.textContent = "Verify";
  }
  if (onbLogOutput) {
    onbLogOutput.innerHTML = "";
    onbLogLineCount = 0;
  }
  onboardingState.flashOk = false;
  onboardingState.verifyOk = false;
  onbFlashStatus.textContent = "Not started.";
  onbVerifyStatus.textContent = "Not started.";
  renderStepHighlights();
}

function setLogsVisible(visible) {
  logsVisible = visible;
  logPanel.hidden = !visible;
  toggleLogsButton.textContent = visible ? "Hide logs" : "Show logs";
  if (visible && startupWarmupActive) {
    setStartupOverlay(false);
  }
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

function setWiringModalOpen(open) {
  if (!wiringModal) {
    return;
  }
  wiringModal.hidden = !open;
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
    startupWarmupActive = true;
    if (!logsVisible) {
      setStartupOverlay(
        true,
        "Preparing Runtime",
        "Starting touchless runtime. First launch may take a few seconds. Open logs to monitor progress.",
      );
    }
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
  if (fields.live) {
    fields.live.addEventListener("change", () => {
      if (!fields.live.checked) {
        setLiveCountdownMessage("");
      }
    });
  }

  startButton.addEventListener("click", startRun);
  stopButton.addEventListener("click", stopRun);

  openSettingsButton.addEventListener("click", () => setDrawerOpen(!settingsVisible));
  closeSettingsButton.addEventListener("click", () => setDrawerOpen(false));
  if (openOnboardingButton) {
    openOnboardingButton.addEventListener("click", async () => {
      resetOnboardingSessionUi();
      onboarding.hidden = false;
      await refreshOnboardingSystemCheck();
    });
  }
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
  const onbRefreshPorts = document.getElementById("onb-refresh-ports");
  const onbRefreshSystem = document.getElementById("onb-refresh-system");
  const onbOpenSettings = document.getElementById("onb-open-settings");
  const onbFlash = document.getElementById("onb-flash");
  const onbVerify = document.getElementById("onb-verify");
  const onbSkip = document.getElementById("onb-skip");

  if (onbRefreshPorts) {
    onbRefreshPorts.addEventListener("click", async () => {
      await refreshSerialPorts();
      refreshOnboardingPortState();
    });
  }
  if (onbSerialPort) {
    onbSerialPort.addEventListener("change", refreshOnboardingPortState);
  }
  if (onbRefreshSystem) {
    onbRefreshSystem.addEventListener("click", refreshOnboardingSystemCheck);
  }
  if (onbOpenWiring) {
    onbOpenWiring.addEventListener("click", () => setWiringModalOpen(true));
  }
  if (wiringClose) {
    wiringClose.addEventListener("click", () => setWiringModalOpen(false));
  }
  if (wiringModal) {
    wiringModal.addEventListener("click", (event) => {
      if (event.target === wiringModal) {
        setWiringModalOpen(false);
      }
    });
  }
  if (onbOpenSettings) {
    onbOpenSettings.addEventListener("click", async () => {
      const result = await launcherApi.openPermissionSettings("privacy");
      appendLog(result.message || "Opened settings", result.ok ? "sys" : "err");
    });
  }
  if (onbFlash) {
    onbFlash.addEventListener("click", flashOnboardingEsp);
  }
  if (onbVerify) {
    onbVerify.addEventListener("click", verifyOnboardingEspStream);
  }
  if (onbCompleteButton) {
    onbCompleteButton.addEventListener("click", completeOnboarding);
  }
  if (onbSkip) {
    onbSkip.addEventListener("click", async () => {
      await Promise.allSettled([stopVerifyIfRunning(), stopFlashIfRunning()]);
      onboarding.hidden = true;
    });
  }
  if (onbClearLogs) {
    onbClearLogs.addEventListener("click", () => {
      if (onbLogOutput) {
        onbLogOutput.innerHTML = "";
        onbLogLineCount = 0;
      }
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
        await refreshOnboardingSystemCheck();
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
            ? "Camera denied. Opened System Settings; enable camera access, then restart Touchless Launcher."
            : `Could not open settings: ${openResult.message}`,
          openResult.ok ? "info" : "error",
        );
        await refreshPermissions();
        await refreshOnboardingSystemCheck();
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
            ? "Camera not granted. Opened System Settings for manual enable. Restart app after enabling."
            : "Camera not granted. Please open System Settings > Privacy > Camera.",
          "error",
        );
      } else {
        setPermissionMessage(`Camera request failed: ${result.message || "unknown error"}`, "error");
      }
      await refreshPermissions();
      await refreshOnboardingSystemCheck();
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
        setPermissionMessage(
          "Accessibility not granted yet. Enable Touchless Launcher in System Settings.",
          "error",
        );
      }
      await refreshPermissions();
      await refreshOnboardingSystemCheck();
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
      setWiringModalOpen(false);
      setDrawerOpen(false);
    }
  });

  launcherApi.onRunLog((entry) => {
    const text = String(entry.text || "");
    const trimmed = text.trim();
    if (trimmed.startsWith("cv_event type=move ")) {
      // Skip high-frequency cursor telemetry to keep logs readable.
      return;
    }
    const kind = entry.stream === "stderr" ? "err" : "out";
    appendLog(entry.text, kind);
    if (trimmed.includes("Matplotlib is building the font cache")) {
      startupWarmupActive = true;
      if (!logsVisible) {
        setStartupOverlay(
          true,
          "Preparing Runtime",
          "Building font cache for first-time startup. This usually happens once. Check logs for progress.",
        );
      }
      return;
    }
    if (
      trimmed.startsWith("[cv] ready") ||
      trimmed.startsWith("type=gesture") ||
      trimmed.startsWith("[live] live execution active")
    ) {
      if (startupWarmupActive) {
        startupWarmupActive = false;
        setStartupOverlay(false);
      }
    }
    if (trimmed.startsWith("[live] LIVE MODE ENABLED")) {
      setLiveCountdownMessage("Live actions armed. Starting countdown…");
      return;
    }
    const match = trimmed.match(/^\[live\] starting in (\d+)\.\.\.$/);
    if (match) {
      setLiveCountdownMessage(`Live actions start in ${match[1]}…`);
      return;
    }
    if (trimmed.startsWith("[live] live execution active")) {
      setLiveCountdownMessage("Live actions active.", { autoHideMs: 2000 });
    }
  });

  launcherApi.onRunStatus((status) => {
    if (status.state === "running") {
      updateStatusPill("running", `PID ${status.pid || "-"}`);
      startButton.disabled = true;
      stopButton.disabled = false;
    } else if (status.state === "stopping") {
      updateStatusPill("stopping");
      startupWarmupActive = false;
      setStartupOverlay(false);
    } else if (status.state === "stopped") {
      updateStatusPill("stopped", `code ${status.code ?? "?"}`);
      startButton.disabled = false;
      stopButton.disabled = true;
      setLiveCountdownMessage("");
      startupWarmupActive = false;
      setStartupOverlay(false);
      appendLog(
        `run exited code=${status.code ?? "?"} signal=${status.signal || "none"}`,
        "sys",
      );
    } else if (status.state === "error") {
      updateStatusPill("error");
      startButton.disabled = false;
      stopButton.disabled = true;
      setLiveCountdownMessage("");
      startupWarmupActive = false;
      setStartupOverlay(false);
      appendLog(status.message || "runtime error", "err");
    }
  });

  if (launcherApi.onVerifyLog) {
    launcherApi.onVerifyLog((entry) => {
      if (!entry || !entry.text) {
        return;
      }
      const text = String(entry.text);
      if (text === "__VERIFY_READY__") {
        appendOnboardingLog("Verify stream connected.", "ok");
        return;
      }
      appendOnboardingLog(text, entry.stream === "stderr" ? "stderr" : "stdout");
    });
  }

  if (launcherApi.onVerifyStatus) {
    launcherApi.onVerifyStatus((status) => {
      const onbVerifyButton = document.getElementById("onb-verify");
      if (status.state === "running") {
        verifyStreaming = true;
        onboardingState.verifyOk = true;
        onbVerifyStatus.textContent = `Verify stream running on ${status.port}.`;
        if (onbVerifyButton) {
          onbVerifyButton.textContent = "Stop";
        }
      } else if (status.state === "stopped") {
        verifyStreaming = false;
        onbVerifyStatus.textContent = "Verify stream stopped.";
        if (onbVerifyButton) {
          onbVerifyButton.textContent = "Verify";
        }
      }
      renderStepHighlights();
    });
  }
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
  renderRuntimeInfo();
  await refreshPermissions();
  onboarding.hidden = onboardingDone();
  appendOnboardingLog("Quick Setup ready.");
  renderOnboardingSerialOptions(cachedSerialPorts, fields.serialPort.value || "");
  onbSerialPort.value = fields.serialPort.value || "";
  refreshOnboardingPortState();
  await refreshOnboardingSystemCheck();
  renderStepHighlights();
}

bootstrap().catch((error) => {
  appendLog(`launcher bootstrap failed: ${error}`, "err");
  updateStatusPill("error");
});
