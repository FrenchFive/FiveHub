const { contextBridge, ipcRenderer } = require("electron");
const { pathToFileURL } = require("node:url");

contextBridge.exposeInMainWorld("fivehub", {
  fileUrl: (target) => pathToFileURL(target).href,
  root: () => ipcRenderer.invoke("hub:root"),
  list: () => ipcRenderer.invoke("hub:list"),
  projects: () => ipcRenderer.invoke("hub:projects"),
  show: (name) => ipcRenderer.invoke("hub:show", name),
  log: (limit) => ipcRenderer.invoke("hub:log", limit),
  demo: () => ipcRenderer.invoke("hub:demo"),
  send: (name, version) => ipcRenderer.invoke("hub:send", name, version),
  report: (params) => ipcRenderer.invoke("hub:report", params),
  openAsset: (name) => ipcRenderer.invoke("win:asset", name),
  openReport: (params) => ipcRenderer.invoke("win:report", params),
  reveal: (target) => ipcRenderer.invoke("os:reveal", target),
  copy: (text) => ipcRenderer.invoke("os:copy", text),
});
