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
import os
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-houdini", action="store_true")
    parser.add_argument("--no-pip", action="store_true")
    parser.add_argument("--no-fonts", action="store_true")
    parser.add_argument("--no-splash", action="store_true")
    parser.add_argument("--no-app", action="store_true")
    args = parser.parse_args(argv)

    print("FIVE HUB installer — %s\n" % REPO)
    if not args.no_houdini:
        install_houdini_package()
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
