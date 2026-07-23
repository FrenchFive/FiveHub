// FiveHub app — Electron main process.
//
// The app owns no pipeline logic: every data access shells out to the
// Python CLI (`python -m fivehub.cli ... --> JSON`), so the hub on disk and
// the database schemas have exactly one implementation.
//
// Window model: one Projects window, plus a separate window per project,
// per task and per validation report.

const { app, BrowserWindow, ipcMain, shell, clipboard, dialog } = require("electron");
const { spawn, spawnSync } = require("node:child_process");
const path = require("node:path");

const REPO_ROOT = path.resolve(__dirname, "..");

let pythonBinary = null;

function resolvePython() {
  if (pythonBinary) return pythonBinary;
  const candidates = [
    process.env.FIVEHUB_PYTHON,
    "python3",
    "python",
    "py",
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      const probe = spawnSync(candidate, ["--version"], { timeout: 5000 });
      if (probe.status === 0) {
        pythonBinary = candidate;
        return candidate;
      }
    } catch {
      // keep looking
    }
  }
  throw new Error(
    "No Python interpreter found. Set FIVEHUB_PYTHON to your python binary.",
  );
}

function runCli(args) {
  return new Promise((resolve, reject) => {
    let python;
    try {
      python = resolvePython();
    } catch (error) {
      reject(error);
      return;
    }
    const child = spawn(python, ["-m", "fivehub.cli", ...args], {
      cwd: REPO_ROOT,
      env: process.env,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || `fivehub.cli exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error("fivehub.cli returned invalid JSON"));
      }
    });
  });
}

// -- windows -------------------------------------------------------------

const namedWindows = new Map();

function createWindow(page, query, options) {
  const win = new BrowserWindow({
    width: options.width,
    height: options.height,
    minWidth: 480,
    minHeight: 340,
    backgroundColor: "#f5f5f7",
    autoHideMenuBar: true,
    title: options.title || "FIVEHUB",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
    },
  });
  win.loadFile(path.join(__dirname, "renderer", page), { query });
  return win;
}

function openKeyed(key, factory) {
  const existing = namedWindows.get(key);
  if (existing && !existing.isDestroyed()) {
    existing.focus();
    return;
  }
  const win = factory();
  namedWindows.set(key, win);
  win.on("closed", () => namedWindows.delete(key));
}

function openProjects() {
  openKeyed("projects", () =>
    createWindow("projects.html", {}, { width: 1200, height: 820, title: "FIVEHUB" }),
  );
}

function openProject(name) {
  openKeyed(`project:${name}`, () =>
    createWindow(
      "project.html",
      { name },
      { width: 1080, height: 760, title: `FIVEHUB — ${name}` },
    ),
  );
}

function openTask(context) {
  const key = `task:${context.project}/${context.kind}/${context.entity}/${context.task}`;
  openKeyed(key, () =>
    createWindow("task.html", context, {
      width: 900,
      height: 700,
      title: `FIVEHUB — ${context.entity} / ${context.task}`,
    }),
  );
}

function openReport(reportPath) {
  createWindow(
    "report.html",
    { path: reportPath },
    { width: 640, height: 720, title: "FIVEHUB — VALIDATION" },
  );
}

// -- ipc -----------------------------------------------------------------

ipcMain.handle("hub:root", () => runCli(["root"]));
ipcMain.handle("hub:projects", () => runCli(["projects"]));
ipcMain.handle("hub:login", (_event, name) => runCli(["login", name]));
ipcMain.handle("hub:whoami", () => runCli(["whoami"]));
ipcMain.handle("hub:activity", (_event, project, limit) =>
  runCli(["activity", project, "--limit", String(limit || 20)]),
);
ipcMain.handle("hub:projectCreate", (_event, name, image, location) => {
  const args = ["project-create", name];
  if (image) args.push("--image", image);
  if (location) args.push("--location", location);
  return runCli(args);
});
ipcMain.handle("hub:entityCreate", (_event, project, kind, name) =>
  runCli(["entity-create", project, kind, name]),
);
ipcMain.handle("hub:taskCreate", (_event, project, kind, entity, name) =>
  runCli(["task-create", project, kind, entity, name]),
);
ipcMain.handle("hub:browse", (_event, name) => runCli(["browse", name]));
ipcMain.handle("hub:taskInfo", (_event, context) =>
  runCli(["task-info", context.project, context.kind, context.entity, context.task]),
);
ipcMain.handle("hub:report", (_event, reportPath) =>
  runCli(["report", "--path", reportPath]),
);
ipcMain.handle("hub:log", (_event, project, limit) =>
  runCli(["log", project, "--limit", String(limit || 100)]),
);
ipcMain.handle("hub:send", (_event, context, format, version) => {
  const args = ["send", context.project, context.kind, context.entity, context.task];
  if (format) args.push("--format", format);
  if (version) args.push("--version", String(version));
  return runCli(args);
});
ipcMain.handle("hub:demo", () => runCli(["demo"]));

ipcMain.handle("hub:projectRemove", (_event, name, deleteFiles) =>
  runCli(["project-remove", name, ...(deleteFiles ? ["--delete-files"] : [])]),
);
ipcMain.handle("hub:entityDelete", (_event, project, kind, name) =>
  runCli(["entity-delete", project, kind, name]),
);
ipcMain.handle("hub:taskDelete", (_event, context) =>
  runCli(["task-delete", context.project, context.kind, context.entity, context.task]),
);
ipcMain.handle("hub:sceneDelete", (_event, context, version) =>
  runCli([
    "scene-delete", context.project, context.kind, context.entity, context.task,
    String(version),
  ]),
);
ipcMain.handle("hub:sceneNotes", (_event, context, version, notes) =>
  runCli([
    "scene-notes", context.project, context.kind, context.entity, context.task,
    String(version), "--notes", notes || "",
  ]),
);
ipcMain.handle("hub:publishDelete", (_event, context, format, version) =>
  runCli([
    "publish-delete", context.project, context.kind, context.entity, context.task,
    format, String(version),
  ]),
);
ipcMain.handle("hub:publishComment", (_event, context, format, version, comment) =>
  runCli([
    "publish-comment", context.project, context.kind, context.entity, context.task,
    format, String(version), "--comment", comment || "",
  ]),
);

ipcMain.handle("win:project", (_event, name) => openProject(name));
ipcMain.handle("win:task", (_event, context) => openTask(context));
ipcMain.handle("win:report", (_event, reportPath) => openReport(reportPath));

ipcMain.handle("os:reveal", (_event, target) => shell.showItemInFolder(target));
ipcMain.handle("os:copy", (_event, text) => clipboard.writeText(text));
ipcMain.handle("os:pickImage", async (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  const picked = await dialog.showOpenDialog(win, {
    title: "Project image",
    properties: ["openFile"],
    filters: [{ name: "Images", extensions: ["png", "jpg", "jpeg", "webp"] }],
  });
  return picked.canceled ? null : picked.filePaths[0];
});
ipcMain.handle("os:pickFolder", async (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  const picked = await dialog.showOpenDialog(win, {
    title: "Project location",
    properties: ["openDirectory", "createDirectory"],
  });
  return picked.canceled ? null : picked.filePaths[0];
});

// -- houdini launcher ----------------------------------------------------

let houdiniBinary; // undefined = not probed yet, null = not found

function resolveHoudini() {
  if (houdiniBinary !== undefined) return houdiniBinary;
  if (process.env.FIVEHUB_HOUDINI) {
    houdiniBinary = process.env.FIVEHUB_HOUDINI;
    return houdiniBinary;
  }
  const probe = process.platform === "win32" ? "where" : "which";
  for (const candidate of ["houdinifx", "houdini", "houdinicore", "hindie"]) {
    try {
      const result = spawnSync(probe, [candidate], { timeout: 4000 });
      if (result.status === 0) {
        houdiniBinary = candidate;
        return candidate;
      }
    } catch {
      // keep looking
    }
  }
  houdiniBinary = null;
  return null;
}

ipcMain.handle("os:openScene", async (_event, sceneFile) => {
  const binary = resolveHoudini();
  if (binary) {
    const child = spawn(binary, [sceneFile], {
      detached: true,
      stdio: "ignore",
      env: process.env,
    });
    child.unref();
    return { via: "houdini", binary };
  }
  // No binary on PATH — fall back to the OS association for .hip files.
  const error = await shell.openPath(sceneFile);
  if (error) {
    throw new Error(
      "Houdini not found. Set FIVEHUB_HOUDINI to your houdini binary. (" + error + ")",
    );
  }
  return { via: "os" };
});

// -- lifecycle -----------------------------------------------------------

app.whenReady().then(() => {
  openProjects();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) openProjects();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
