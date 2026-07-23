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
  entityUpdate: (project, kind, name, fields) =>
    ipcRenderer.invoke("hub:entityUpdate", project, kind, name, fields),
  ingest: (context, files, name, comment) =>
    ipcRenderer.invoke("hub:ingest", context, files, name, comment),
  refs: (project) => ipcRenderer.invoke("hub:refs", project),
  refsAdd: (project, files) => ipcRenderer.invoke("hub:refsAdd", project, files),
  refsDelete: (project, name) => ipcRenderer.invoke("hub:refsDelete", project, name),
  jobs: (project, limit) => ipcRenderer.invoke("hub:jobs", project, limit),
  jobCancel: (project, jobId) => ipcRenderer.invoke("hub:jobCancel", project, jobId),
  gitStatus: (project) => ipcRenderer.invoke("hub:gitStatus", project),
  gitSetup: (project) => ipcRenderer.invoke("hub:gitSetup", project),
  gitSync: (project) => ipcRenderer.invoke("hub:gitSync", project),
  updateCheck: () => ipcRenderer.invoke("hub:updateCheck"),
  updateDismiss: () => ipcRenderer.invoke("hub:updateDismiss"),
  updateRun: () => ipcRenderer.invoke("hub:updateRun"),

  openProject: (name) => ipcRenderer.invoke("win:project", name),
  openTask: (context) => ipcRenderer.invoke("win:task", context),
  openReport: (path) => ipcRenderer.invoke("win:report", path),

  reveal: (target) => ipcRenderer.invoke("os:reveal", target),
  copy: (text) => ipcRenderer.invoke("os:copy", text),
  pickImage: () => ipcRenderer.invoke("os:pickImage"),
  pickFolder: () => ipcRenderer.invoke("os:pickFolder"),
  pickFiles: (title) => ipcRenderer.invoke("os:pickFiles", title),
  openScene: (file, projectRoot) =>
    ipcRenderer.invoke("os:openScene", file, projectRoot),
});
