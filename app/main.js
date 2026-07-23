// FiveHub app — Electron main process.
//
// The app owns no pipeline logic: every data access shells out to the
// Python CLI (`python -m fivehub.cli ... --> JSON`), so the hub on disk and
// the database schema have exactly one implementation.
//
// Window model: one Library window, plus a separate window per asset and
// per validation report.

const { app, BrowserWindow, ipcMain, shell, clipboard } = require("electron");
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

const assetWindows = new Map();

function createWindow(page, query, options) {
  const win = new BrowserWindow({
    width: options.width,
    height: options.height,
    minWidth: 460,
    minHeight: 320,
    backgroundColor: "#000000",
    autoHideMenuBar: true,
    title: options.title || "FIVEHUB",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
    },
  });
  win.loadFile(path.join(__dirname, "renderer", page), { query });
  return win;
}

function openLibrary() {
  createWindow("library.html", {}, { width: 1200, height: 820, title: "FIVEHUB" });
}

function openAsset(name) {
  const existing = assetWindows.get(name);
  if (existing && !existing.isDestroyed()) {
    existing.focus();
    return;
  }
  const win = createWindow(
    "asset.html",
    { name },
    { width: 760, height: 640, title: `FIVEHUB — ${name}` },
  );
  assetWindows.set(name, win);
  win.on("closed", () => assetWindows.delete(name));
}

function openReport(params) {
  createWindow("report.html", params, {
    width: 640,
    height: 720,
    title: "FIVEHUB — VALIDATION",
  });
}

// -- ipc -----------------------------------------------------------------

ipcMain.handle("hub:root", () => runCli(["root"]));
ipcMain.handle("hub:list", () => runCli(["list"]));
ipcMain.handle("hub:projects", () => runCli(["projects"]));
ipcMain.handle("hub:show", (_event, name) => runCli(["show", name]));
ipcMain.handle("hub:log", (_event, limit) =>
  runCli(["log", "--limit", String(limit || 50)]),
);
ipcMain.handle("hub:demo", () => runCli(["demo"]));
ipcMain.handle("hub:send", (_event, name, version) => {
  const args = ["send", name];
  if (version) args.push("--version", String(version));
  return runCli(args);
});
ipcMain.handle("hub:report", (_event, params) => {
  if (params.path) return runCli(["report", "--path", params.path]);
  const args = ["report", params.name];
  if (params.version) args.push("--version", String(params.version));
  return runCli(args);
});

ipcMain.handle("win:asset", (_event, name) => openAsset(name));
ipcMain.handle("win:report", (_event, params) => openReport(params));

ipcMain.handle("os:reveal", (_event, target) => shell.showItemInFolder(target));
ipcMain.handle("os:copy", (_event, text) => clipboard.writeText(text));

// -- lifecycle -----------------------------------------------------------

app.whenReady().then(() => {
  openLibrary();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) openLibrary();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
