"""FiveHub one-shot installer — run by install.bat / install.sh.

Does everything a workstation needs, each step best-effort so one failure
(no internet, no npm) never blocks the rest:

    1. Houdini package into every Houdini preferences folder found
    2. Pillow (splash generator) via pip
    3. Satoshi fonts from Fontshare into assets/fonts/
    4. Generate the FIVE HUB splash screen
    5. App dependencies (npm install)

Stdlib only. Flags like --no-app / --no-fonts skip steps (used by CI).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

REPO = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(REPO, "assets", "fonts")
FONTSHARE_URL = "https://api.fontshare.com/v2/fonts/download/satoshi"
FONT_FILES = (
    "Satoshi-Variable.woff2", "Satoshi-Variable.ttf",
    "Satoshi-Black.otf", "Satoshi-Medium.otf", "Satoshi-Regular.otf",
)

RESULTS = []


def step(name, ok, detail=""):
    mark = "OK  " if ok else "SKIP"
    RESULTS.append((mark, name, detail))
    print("[%s] %s%s" % (mark, name, (" — " + detail) if detail else ""))


def run(command, timeout=900, cwd=None):
    completed = subprocess.run(
        command, cwd=cwd or REPO, capture_output=True, text=True, timeout=timeout
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output.strip()


HOUDINI_BINARIES = ("houdinifx", "houdini", "houdinicore", "hindie")


def _find_houdini_registry():
    """Windows registry — SideFX records every install location here, so
    this finds Houdini wherever it was installed (any drive, any folder)."""
    try:
        import winreg
    except ImportError:
        return ""
    found = []
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(root, r"SOFTWARE\Side Effects Software")
        except OSError:
            continue
        with key:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(key, index)
                except OSError:
                    break
                index += 1
                if not name.startswith("Houdini"):
                    continue
                path = ""
                try:
                    with winreg.OpenKey(key, name) as version_key:
                        for value_name in ("InstallPath", ""):
                            try:
                                path = str(
                                    winreg.QueryValueEx(version_key, value_name)[0]
                                )
                                break
                            except OSError:
                                continue
                except OSError:
                    continue
                if path:
                    found.append((name, path))

    def version_of(item):
        return [int(number) for number in re.findall(r"\d+", item[0])]

    for _, path in sorted(found, key=version_of, reverse=True):
        for name in HOUDINI_BINARIES:
            candidate = os.path.join(path, "bin", name + ".exe")
            if os.path.isfile(candidate):
                return candidate
    return ""


def _ask_houdini():
    """Interactive last resort: the user pastes the executable or its
    install folder. Non-interactive runs (CI) skip via EOF."""
    extension = ".exe" if os.name == "nt" else ""
    try:
        answer = input(
            "\nWhere is Houdini installed? Paste the path to the executable\n"
            "(e.g. C:\\...\\Houdini 20.5.487\\bin\\houdinifx.exe) or to the\n"
            "install folder. Press Enter to skip: "
        ).strip().strip('"')
    except (EOFError, OSError):
        return ""
    if not answer:
        return ""
    path = os.path.expanduser(answer)
    if os.path.isfile(path):
        return path
    for sub in ("bin", ""):
        for name in HOUDINI_BINARIES:
            candidate = os.path.join(path, sub, name + extension)
            if os.path.isfile(candidate):
                return candidate
    print("  no houdini executable found at %r" % answer)
    return ""


def find_houdini(base=None):
    """Newest Houdini binary from $HFS or the standard install locations."""
    if os.name == "nt":
        from_registry = _find_houdini_registry()
        if from_registry:
            return from_registry
        default_base = os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            "Side Effects Software",
        )
        prefix, bin_sub, extension = "Houdini", "bin", ".exe"
    elif sys.platform == "darwin":
        default_base = "/Applications/Houdini"
        prefix = "Houdini"
        bin_sub = "Frameworks/Houdini.framework/Versions/Current/Resources/bin"
        extension = ""
    else:
        default_base, prefix, bin_sub, extension = "/opt", "hfs", "bin", ""
    hfs = os.environ.get("HFS", "")
    if hfs:
        for name in HOUDINI_BINARIES:
            candidate = os.path.join(hfs, "bin", name + extension)
            if os.path.isfile(candidate):
                return candidate
    try:
        directories = [
            entry for entry in os.listdir(base or default_base)
            if entry.startswith(prefix)
        ]
    except OSError:
        return ""

    def version_key(text):
        return [int(number) for number in re.findall(r"\d+", text)]

    for directory in sorted(directories, key=version_key, reverse=True):
        for name in HOUDINI_BINARIES:
            candidate = os.path.join(
                base or default_base, directory, bin_sub, name + extension
            )
            if os.path.isfile(candidate):
                return candidate
    return ""


def detect_houdini():
    """Record the Houdini binary in ~/.fivehub/machine.json for the app's
    open/launch buttons — set once at install, self-repaired by the app."""
    binary = find_houdini()
    if not binary:
        binary = _ask_houdini()  # ask the human before giving up
    if not binary:
        step("Houdini binary", False,
             "not found — the app will ask you to locate houdini once")
        return
    target = os.path.join(os.path.expanduser("~"), ".fivehub", "machine.json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    data = {}
    try:
        with open(target, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        pass
    data["houdini"] = binary
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    step("Houdini binary", True, binary)


def install_houdini_package():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "fivehub_houdini_install", os.path.join(REPO, "houdini", "install.py")
    )
    houdini_install = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(houdini_install)

    candidates = houdini_install.candidate_pref_dirs()
    if not candidates:
        step("Houdini package", False,
             "no Houdini preferences folder found — run 'python houdini/install.py"
             " --prefs <path>' after launching Houdini once")
        return
    for prefs in candidates:
        target = houdini_install.install(prefs)
        step("Houdini package", True, target)


def install_pillow():
    try:
        import PIL  # noqa: F401

        step("Pillow (splash generator)", True, "already installed")
        return True
    except ImportError:
        pass
    ok, output = run([sys.executable, "-m", "pip", "install", "--user", "pillow"],
                     timeout=300)
    if not ok:  # some pythons refuse --user in venvs
        ok, output = run([sys.executable, "-m", "pip", "install", "pillow"],
                         timeout=300)
    step("Pillow (splash generator)", ok, "" if ok else output.splitlines()[-1] if output else "pip failed")
    return ok


def have_satoshi():
    return os.path.isdir(FONTS_DIR) and any(
        name.lower().startswith("satoshi") for name in os.listdir(FONTS_DIR)
    )


def install_fonts():
    if have_satoshi():
        step("Satoshi fonts", True, "already in assets/fonts")
        return
    os.makedirs(FONTS_DIR, exist_ok=True)
    archive = os.path.join(FONTS_DIR, "_satoshi.zip")
    try:
        # You are downloading Satoshi from Fontshare yourself here — the
        # files never ship inside this repository (license terms).
        with urllib.request.urlopen(FONTSHARE_URL, timeout=90) as response:
            with open(archive, "wb") as handle:
                shutil.copyfileobj(response, handle)
        extracted = 0
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.namelist():
                base = os.path.basename(member)
                if base in FONT_FILES:
                    with bundle.open(member) as source, open(
                        os.path.join(FONTS_DIR, base), "wb"
                    ) as target:
                        shutil.copyfileobj(source, target)
                    extracted += 1
        step("Satoshi fonts", extracted > 0,
             "%d file(s) into assets/fonts" % extracted if extracted
             else "archive had no expected files")
    except Exception as error:  # offline is fine — system fonts take over
        step("Satoshi fonts", False,
             "download failed (%s) — see assets/fonts/README.md" % error)
    finally:
        if os.path.isfile(archive):
            os.remove(archive)


def generate_splash():
    ok, output = run([sys.executable, "-m", "fivehub.cli", "splash"], timeout=300)
    step("Splash screen", ok,
         "houdini/splash/fivehub_splash.png" if ok
         else (output.splitlines()[-1] if output else "generator failed"))


def install_app():
    npm = shutil.which("npm")
    if not npm:
        step("App dependencies (npm install)", False,
             "npm not found — install Node.js, then run npm install in app/")
        return
    ok, output = run([npm, "install"], cwd=os.path.join(REPO, "app"), timeout=1200)
    step("App dependencies (npm install)", ok,
         "" if ok else (output.splitlines()[-1] if output else "npm failed"))


def install_shortcut():
    """Make FIVE HUB findable: Start Menu (Windows) / app menu (Linux)."""
    app_dir = os.path.join(REPO, "app")
    electron = os.path.join(app_dir, "node_modules", "electron", "dist",
                            "electron.exe" if os.name == "nt" else "electron")
    if not os.path.isfile(electron):
        step("App shortcut", False,
             "app not installed yet — rerun this installer after npm install")
        return

    if os.name == "nt":
        shortcut = os.path.join(
            os.environ.get("APPDATA", ""), "Microsoft", "Windows",
            "Start Menu", "Programs", "FiveHub.lnk",
        )
        icon = os.path.join(REPO, "assets", "fivehub.ico")
        script = (
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
            "$s.TargetPath = '%s';"
            "$s.Arguments = '\"%s\"';"
            "$s.WorkingDirectory = '%s';"
            "$s.IconLocation = '%s';"
            "$s.Description = 'FIVE HUB — pipeline for Houdini';"
            "$s.Save()"
        ) % (shortcut, electron, app_dir, app_dir, icon)
        ok, output = run(["powershell", "-NoProfile", "-Command", script],
                         timeout=60)
        step("App shortcut (Start Menu)", ok,
             shortcut if ok else output.splitlines()[-1] if output else "failed")
    elif sys.platform.startswith("linux"):
        applications = os.path.join(
            os.path.expanduser("~"), ".local", "share", "applications"
        )
        os.makedirs(applications, exist_ok=True)
        desktop = os.path.join(applications, "fivehub.desktop")
        with open(desktop, "w", encoding="utf-8") as handle:
            handle.write(
                "[Desktop Entry]\nType=Application\nName=FiveHub\n"
                "Comment=FIVE HUB — pipeline for Houdini\n"
                "Exec=\"%s\" \"%s\"\nIcon=%s\nTerminal=false\n"
                "Categories=Graphics;\n"
                % (electron, app_dir, os.path.join(REPO, "assets", "icon.png"))
            )
        step("App shortcut (applications menu)", True, desktop)
    else:
        step("App shortcut", False,
             "macOS: use 'npm run dist' in app/ for a real .app, or the HUB "
             "button in Houdini")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-houdini", action="store_true")
    parser.add_argument("--no-pip", action="store_true")
    parser.add_argument("--no-fonts", action="store_true")
    parser.add_argument("--no-splash", action="store_true")
    parser.add_argument("--no-app", action="store_true")
    parser.add_argument("--no-shortcut", action="store_true")
    args = parser.parse_args(argv)

    print("FIVE HUB installer — %s\n" % REPO)
    if not args.no_houdini:
        install_houdini_package()
        detect_houdini()
    pillow = True
    if not args.no_pip:
        pillow = install_pillow()
    if not args.no_fonts:
        install_fonts()
    if not args.no_splash:
        if pillow:
            generate_splash()
        else:
            step("Splash screen", False, "needs Pillow")
    if not args.no_app:
        install_app()
    if not args.no_shortcut:
        install_shortcut()

    print("\nDone. Launch Houdini — the FIVE HUB menu is in the main menu bar.")
    print("The HUB button opens the app; first launch asks your name (that's the login).")
    skipped = [name for mark, name, _ in RESULTS if mark == "SKIP"]
    if skipped:
        print("Skipped (everything still works, just without these):")
        for name in skipped:
            print("  - %s" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
