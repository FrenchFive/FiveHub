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
const fs = require("node:fs");
const os = require("node:os");
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
//
// ONE main window: the projects, project and task pages navigate in place
// (location.href) so browsing never spawns windows. Only validation
// reports pop a separate small window — documents you read side by side.

let mainWindow = null;

function createWindow(page, query, options) {
  const win = new BrowserWindow({
    width: options.width,
    height: options.height,
    minWidth: 480,
    minHeight: 340,
    backgroundColor: "#f5f5f7",
    autoHideMenuBar: true,
    title: options.title || "FIVEHUB",
    icon: path.join(REPO_ROOT, "assets", "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
    },
  });
  win.loadFile(path.join(__dirname, "renderer", page), { query });
  return win;
}

function openMain() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.focus();
    return;
  }
  mainWindow = createWindow("projects.html", {}, {
    width: 1200,
    height: 820,
    title: "FIVEHUB",
  });
  mainWindow.on("closed", () => (mainWindow = null));
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
ipcMain.handle("hub:entityUpdate", (_event, project, kind, name, fields) => {
  const args = ["entity-update", project, kind, name];
  const flags = {
    sequence: "--sequence",
    frame_start: "--frame-start",
    frame_end: "--frame-end",
    fps: "--fps",
    res_x: "--res-x",
    res_y: "--res-y",
  };
  for (const [key, flag] of Object.entries(flags)) {
    if (fields[key] !== undefined && fields[key] !== null && fields[key] !== "") {
      args.push(flag, String(fields[key]));
    }
  }
  return runCli(args);
});
ipcMain.handle("hub:ingest", (_event, context, files, name, comment) => {
  const args = [
    "ingest", context.project, context.kind, context.entity, context.task, ...files,
  ];
  if (name) args.push("--name", name);
  if (comment) args.push("--comment", comment);
  return runCli(args);
});
ipcMain.handle("hub:refs", (_event, project) => runCli(["refs", project]));
ipcMain.handle("hub:refsAdd", (_event, project, files) =>
  runCli(["refs", project, "--add", ...files]),
);
ipcMain.handle("hub:refsDelete", (_event, project, name) =>
  runCli(["refs", project, "--delete", name]),
);
ipcMain.handle("hub:jobs", (_event, project, limit) =>
  runCli(["jobs", project, "--limit", String(limit || 30)]),
);
ipcMain.handle("hub:jobCancel", (_event, project, jobId) =>
  runCli(["jobs", project, "--cancel", jobId]),
);
ipcMain.handle("hub:gitStatus", (_event, project) => runCli(["git-status", project]));
ipcMain.handle("hub:gitSetup", (_event, project) => runCli(["git-setup", project]));
ipcMain.handle("hub:gitSync", (_event, project) => runCli(["git-sync", project]));

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

// The installer records the detected binary here; the app re-records it
// whenever it rediscovers Houdini (or the user picks it once).
const MACHINE_FILE = path.join(os.homedir(), ".fivehub", "machine.json");

function storedHoudini() {
  try {
    const stored = JSON.parse(fs.readFileSync(MACHINE_FILE, "utf8")).houdini;
    if (stored && fs.existsSync(stored)) return stored;
  } catch {
    // no machine file yet
  }
  return null;
}

function rememberHoudini(binary) {
  try {
    let data = {};
    try {
      data = JSON.parse(fs.readFileSync(MACHINE_FILE, "utf8"));
    } catch {
      // first write
    }
    data.houdini = binary;
    fs.mkdirSync(path.dirname(MACHINE_FILE), { recursive: true });
    fs.writeFileSync(MACHINE_FILE, JSON.stringify(data, null, 2));
  } catch {
    // read-only home — rediscover next launch
  }
}

let houdiniBinary; // undefined = not probed yet, null = not found

function resolveHoudini() {
  if (houdiniBinary !== undefined) return houdiniBinary;
  if (process.env.FIVEHUB_HOUDINI) {
    houdiniBinary = process.env.FIVEHUB_HOUDINI;
    return houdiniBinary;
  }
  const stored = storedHoudini();
  if (stored) {
    houdiniBinary = stored;
    return stored;
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
  houdiniBinary = findHoudiniInstall();
  if (houdiniBinary) rememberHoudini(houdiniBinary);
  return houdiniBinary;
}

// Houdini is almost never on PATH (especially on Windows) — walk the
// standard install locations and pick the newest version found.
const HOUDINI_NAMES = ["houdinifx", "houdini", "houdinicore", "hindie"];

function byVersionDesc(a, b) {
  const ka = (a.match(/\d+/g) || []).map(Number);
  const kb = (b.match(/\d+/g) || []).map(Number);
  for (let i = 0; i < Math.max(ka.length, kb.length); i += 1) {
    const diff = (kb[i] || 0) - (ka[i] || 0);
    if (diff) return diff;
  }
  return 0;
}

function firstBinary(binDir, extension) {
  for (const name of HOUDINI_NAMES) {
    const candidate = path.join(binDir, name + extension);
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function findHoudiniInstall() {
  try {
    if (process.env.HFS) {
      const fromHfs = firstBinary(
        path.join(process.env.HFS, "bin"),
        process.platform === "win32" ? ".exe" : "",
      );
      if (fromHfs) return fromHfs;
    }
    if (process.platform === "win32") {
      const base = path.join(
        process.env.ProgramFiles || "C:\\Program Files",
        "Side Effects Software",
      );
      for (const dir of fs.readdirSync(base)
        .filter((name) => name.startsWith("Houdini"))
        .sort(byVersionDesc)) {
        const found = firstBinary(path.join(base, dir, "bin"), ".exe");
        if (found) return found;
      }
    } else if (process.platform === "darwin") {
      const base = "/Applications/Houdini";
      for (const dir of fs.readdirSync(base)
        .filter((name) => name.startsWith("Houdini"))
        .sort(byVersionDesc)) {
        const found = firstBinary(
          path.join(base, dir,
            "Frameworks/Houdini.framework/Versions/Current/Resources/bin"),
          "",
        );
        if (found) return found;
      }
    } else {
      for (const dir of fs.readdirSync("/opt")
        .filter((name) => name.startsWith("hfs"))
        .sort(byVersionDesc)) {
        const found = firstBinary(path.join("/opt", dir, "bin"), "");
        if (found) return found;
      }
    }
  } catch {
    // no standard install location on this machine
  }
  return null;
}

ipcMain.handle("os:pickFiles", async (event, title) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  const picked = await dialog.showOpenDialog(win, {
    title: title || "Pick files",
    properties: ["openFile", "multiSelections"],
  });
  return picked.canceled ? [] : picked.filePaths;
});

// Launch Houdini on a task with no scene yet: JOB + FH_* ride along so the
// FIVE HUB Save Scene As dialog opens prefilled and creates the first
// version in the right place.
ipcMain.handle("os:launchHoudini", async (event, context, projectRoot) => {
  let binary = resolveHoudini();
  if (!binary) {
    // Last resort: point at houdini once — remembered in machine.json.
    const win = BrowserWindow.fromWebContents(event.sender);
    const picked = await dialog.showOpenDialog(win, {
      title: "Locate your Houdini executable (e.g. houdinifx)",
      properties: ["openFile"],
      filters:
        process.platform === "win32"
          ? [{ name: "Houdini", extensions: ["exe"] }]
          : [],
    });
    if (!picked.canceled && picked.filePaths.length) {
      binary = picked.filePaths[0];
      houdiniBinary = binary;
      rememberHoudini(binary);
    }
  }
  if (!binary) {
    throw new Error(
      "Houdini not found. Set FIVEHUB_HOUDINI to your houdini binary.",
    );
  }
  const env = { ...process.env };
  if (projectRoot) env.JOB = projectRoot;
  if (context) {
    env.FH_PROJECT = context.project || "";
    env.FH_KIND = context.kind || "";
    env.FH_ENTITY = context.entity || "";
    env.FH_TASK = context.task || "";
  }
  const child = spawn(binary, [], { detached: true, stdio: "ignore", env });
  child.unref();
  return { binary };
});

ipcMain.handle("os:openScene", async (_event, sceneFile, projectRoot) => {
  const binary = resolveHoudini();
  if (binary) {
    // $JOB rides along so relative paths resolve inside Houdini.
    const env = { ...process.env };
    if (projectRoot) env.JOB = projectRoot;
    const child = spawn(binary, [sceneFile], {
      detached: true,
      stdio: "ignore",
      env,
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

// -- self-update ---------------------------------------------------------
//
// Nothing updates behind the user's back: windows open immediately, the
// renderer runs the version check in the background and offers a small
// dismissible popup when a newer version exists. Accepting pulls and
// relaunches; dismissing keeps the popup away until the next app boot —
// the flag lives here so it covers every window for this process's life.
// FIVEHUB_NO_AUTOUPDATE=1 mutes the popup (the header button still works).

let updateOfferDismissed = Boolean(process.env.FIVEHUB_NO_AUTOUPDATE);

ipcMain.handle("hub:updateCheck", async () => {
  const result = await runCli(["update", "--check"]);
  result.dismissed = updateOfferDismissed;
  return result;
});
ipcMain.handle("hub:updateDismiss", () => {
  updateOfferDismissed = true;
});
ipcMain.handle("hub:updateRun", async () => {
  const result = await runCli(["update"]);
  if (result.update && result.update.updated) {
    // Relaunch so every window runs the freshly pulled code.
    app.relaunch();
    app.exit(0);
  }
  return result;
});

// -- lifecycle -----------------------------------------------------------

// One instance only: opening the hub again (from Houdini, the Start Menu,
// anywhere) focuses the running window instead of racing a second Chromium
// profile — that race is what spams GPU-cache "Access is denied" errors.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    openMain();
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    openMain();
    // The splash is machine-generated; if an update or cleanup removed it,
    // quietly re-render so the next Houdini launch is branded again.
    runCli(["splash", "--if-missing"]).catch(() => {});
    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) openMain();
    });
  });
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
