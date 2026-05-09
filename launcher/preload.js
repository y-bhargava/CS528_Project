const { contextBridge, ipcRenderer } = require("electron");

function onChannel(channel, callback) {
  const wrapped = (_event, payload) => {
    callback(payload);
  };
  ipcRenderer.on(channel, wrapped);
  return () => {
    ipcRenderer.removeListener(channel, wrapped);
  };
}

contextBridge.exposeInMainWorld("launcher", {
  getRuntime: () => ipcRenderer.invoke("launcher:get-runtime"),
  getConfig: () => ipcRenderer.invoke("launcher:get-config"),
  saveConfig: (config) => ipcRenderer.invoke("launcher:save-config", config),
  previewCommand: (config) => ipcRenderer.invoke("launcher:preview-command", config),
  pickReplayFile: () => ipcRenderer.invoke("launcher:pick-file"),

  startRun: (config) => ipcRenderer.invoke("launcher:start", config),
  stopRun: () => ipcRenderer.invoke("launcher:stop"),

  getPermissions: () => ipcRenderer.invoke("launcher:get-permissions"),
  requestCameraPermission: () => ipcRenderer.invoke("launcher:request-camera"),
  promptAccessibilityPermission: () => ipcRenderer.invoke("launcher:prompt-accessibility"),
  openPermissionSettings: (kind) =>
    ipcRenderer.invoke("launcher:open-permission-settings", kind),
  flashEsp: (serialPort) => ipcRenderer.invoke("launcher:flash-esp", serialPort),
  stopFlashEsp: () => ipcRenderer.invoke("launcher:stop-flash-esp"),
  startVerifyEspStream: (serialPort) => ipcRenderer.invoke("launcher:start-verify-esp-stream", serialPort),
  stopVerifyEspStream: () => ipcRenderer.invoke("launcher:stop-verify-esp-stream"),

  onRunLog: (callback) => onChannel("run:log", callback),
  onRunStatus: (callback) => onChannel("run:status", callback),
  onVerifyLog: (callback) => onChannel("onboarding:verify-log", callback),
  onVerifyStatus: (callback) => onChannel("onboarding:verify-status", callback),
});
