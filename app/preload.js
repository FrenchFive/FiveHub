const { contextBridge, ipcRenderer } = require("electron");
const { pathToFileURL } = require("node:url");

contextBridge.exposeInMainWorld("fivehub", {
  fileUrl: (target) => pathToFileURL(target).href,

  root: () => ipcRenderer.invoke("hub:root"),
  projects: () => ipcRenderer.invoke("hub:projects"),
  login: (name) => ipcRenderer.invoke("hub:login", name),
  whoami: () => ipcRenderer.invoke("hub:whoami"),
  activity: (project, limit) => ipcRenderer.invoke("hub:activity", project, limit),
  projectCreate: (name, image, location) =>
    ipcRenderer.invoke("hub:projectCreate", name, image, location),
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

  projectRemove: (name, deleteFiles) =>
    ipcRenderer.invoke("hub:projectRemove", name, deleteFiles),
  entityDelete: (project, kind, name) =>
    ipcRenderer.invoke("hub:entityDelete", project, kind, name),
  taskDelete: (context) => ipcRenderer.invoke("hub:taskDelete", context),
  sceneDelete: (context, version) =>
    ipcRenderer.invoke("hub:sceneDelete", context, version),
  sceneNotes: (context, version, notes) =>
    ipcRenderer.invoke("hub:sceneNotes", context, version, notes),
  publishDelete: (context, format, version) =>
    ipcRenderer.invoke("hub:publishDelete", context, format, version),
  publishComment: (context, format, version, comment) =>
    ipcRenderer.invoke("hub:publishComment", context, format, version, comment),

  openProject: (name) => ipcRenderer.invoke("win:project", name),
  openTask: (context) => ipcRenderer.invoke("win:task", context),
  openReport: (path) => ipcRenderer.invoke("win:report", path),

  reveal: (target) => ipcRenderer.invoke("os:reveal", target),
  copy: (text) => ipcRenderer.invoke("os:copy", text),
  pickImage: () => ipcRenderer.invoke("os:pickImage"),
  pickFolder: () => ipcRenderer.invoke("os:pickFolder"),
  openScene: (file) => ipcRenderer.invoke("os:openScene", file),
});
