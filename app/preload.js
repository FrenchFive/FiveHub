const { contextBridge, ipcRenderer } = require("electron");
const { pathToFileURL } = require("node:url");

contextBridge.exposeInMainWorld("fivehub", {
  fileUrl: (target) => pathToFileURL(target).href,

  root: () => ipcRenderer.invoke("hub:root"),
  projects: () => ipcRenderer.invoke("hub:projects"),
  projectCreate: (name, image) => ipcRenderer.invoke("hub:projectCreate", name, image),
  entityCreate: (project, kind, name) =>
    ipcRenderer.invoke("hub:entityCreate", project, kind, name),
  taskCreate: (project, kind, entity, name) =>
    ipcRenderer.invoke("hub:taskCreate", project, kind, entity, name),
  browse: (name) => ipcRenderer.invoke("hub:browse", name),
  taskInfo: (context) => ipcRenderer.invoke("hub:taskInfo", context),
  report: (path) => ipcRenderer.invoke("hub:report", path),
  log: (project, limit) => ipcRenderer.invoke("hub:log", project, limit),
  send: (context, format, version) =>
    ipcRenderer.invoke("hub:send", context, format, version),
  demo: () => ipcRenderer.invoke("hub:demo"),

  openProject: (name) => ipcRenderer.invoke("win:project", name),
  openTask: (context) => ipcRenderer.invoke("win:task", context),
  openReport: (path) => ipcRenderer.invoke("win:report", path),

  reveal: (target) => ipcRenderer.invoke("os:reveal", target),
  copy: (text) => ipcRenderer.invoke("os:copy", text),
  pickImage: () => ipcRenderer.invoke("os:pickImage"),
});
