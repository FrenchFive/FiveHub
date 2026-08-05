"""FiveHub uninstaller / reset — run by uninstall.bat / uninstall.sh.

Removes everything the installer set up, each step best-effort so one
failure never blocks the rest:

    1. the Houdini package from every Houdini preferences folder
    2. the app shortcut (Start Menu on Windows, applications menu on Linux)
    3. app build artifacts (node_modules, dist, package-lock.json)
    4. the generated splash screen
    5. the downloaded Satoshi fonts
    6. the per-machine login (~/.fivehub)

Your work is safe by default: the hub — projects, scenes, publishes —
is NEVER touched unless you explicitly pass --purge-hub (which asks for
confirmation), and linked project folders outside the hub are never
deleted at all.

    python uninstall.py                    # remove the software, keep projects
    python uninstall.py --reinstall        # factory reset: uninstall + fresh install
    python uninstall.py --purge-hub        # also erase the hub (type ERASE to confirm)

Close the FiveHub app and Houdini first — Windows keeps files locked
while they run. Stdlib only. Flags like --no-app skip steps.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(REPO, "assets", "fonts")

RESULTS = []


def step(name, ok, detail=""):
    mark = "OK  " if ok else "SKIP"
    RESULTS.append((mark, name, detail))
    print("[%s] %s%s" % (mark, name, (" — " + detail) if detail else ""))


def _remove_file(path):
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def _remove_tree(path):
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.exists(path)


def remove_houdini_packages():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "fivehub_houdini_install", os.path.join(REPO, "houdini", "install.py")
    )
    houdini_install = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(houdini_install)

    removed = 0
    for prefs in houdini_install.candidate_pref_dirs():
        package = os.path.join(prefs, "packages", "fivehub.json")
        if os.path.isfile(package) and _remove_file(package):
            removed += 1
            step("Houdini package", True, "removed " + package)
        try:
            houdini_install.update_houdini_env(prefs, remove=True)
        except OSError:
            pass
    if not removed:
        step("Houdini package", False, "none installed")


def remove_shortcut():
    if os.name == "nt":
        shortcut = os.path.join(
            os.environ.get("APPDATA", ""), "Microsoft", "Windows",
            "Start Menu", "Programs", "FiveHub.lnk",
        )
    elif sys.platform.startswith("linux"):
        shortcut = os.path.join(
            os.path.expanduser("~"), ".local", "share", "applications",
            "fivehub.desktop",
        )
    else:
        step("App shortcut", False, "nothing was installed on macOS")
        return
    if os.path.isfile(shortcut) and _remove_file(shortcut):
        step("App shortcut", True, "removed " + shortcut)
    else:
        step("App shortcut", False, "not installed")


def remove_app_artifacts():
    removed = []
    for name in ("node_modules", "dist"):
        target = os.path.join(REPO, "app", name)
        if os.path.isdir(target):
            if _remove_tree(target):
                removed.append("app/" + name)
            else:
                step("App dependencies", False,
                     "could not delete app/%s — close FiveHub and rerun" % name)
                return
    lock = os.path.join(REPO, "app", "package-lock.json")
    if os.path.isfile(lock) and _remove_file(lock):
        removed.append("app/package-lock.json")
    step("App dependencies", bool(removed),
         ", ".join(removed) if removed else "nothing to remove")


def remove_splash():
    removed = [
        path for path in glob.glob(os.path.join(REPO, "houdini", "splash", "*.png"))
        if _remove_file(path)
    ]
    step("Generated splash", bool(removed),
         "%d file(s)" % len(removed) if removed else "nothing to remove")


def remove_fonts():
    removed = 0
    if os.path.isdir(FONTS_DIR):
        for name in os.listdir(FONTS_DIR):
            if name != "README.md" and _remove_file(os.path.join(FONTS_DIR, name)):
                removed += 1
    step("Satoshi fonts", removed > 0,
         "%d file(s)" % removed if removed else "nothing to remove")


def remove_login():
    # Mirrors fivehub.user: FIVEHUB_USER_FILE override, else ~/.fivehub.
    override = os.environ.get("FIVEHUB_USER_FILE")
    if override:
        ok = os.path.isfile(override) and _remove_file(override)
        step("Login", ok, override if ok else "no login file")
    else:
        login_dir = os.path.join(os.path.expanduser("~"), ".fivehub")
        ok = os.path.isdir(login_dir) and _remove_tree(login_dir)
        step("Login", ok, "removed " + login_dir if ok else "not logged in")
    if os.environ.get("FIVEHUB_USER"):
        print("       note: FIVEHUB_USER is set in your environment and still wins")


def purge_hub(assume_yes):
    hub = os.environ.get("FIVEHUB_ROOT") or os.path.join(REPO, "hub")
    if not os.path.isdir(hub):
        step("Hub data", False, "no hub at " + hub)
        return
    linked = {}
    try:
        with open(os.path.join(hub, "registry.json"), encoding="utf-8") as handle:
            linked = json.load(handle).get("projects", {})
    except (OSError, ValueError):
        pass
    if not assume_yes:
        print("\nThis erases the hub and EVERY project inside it:\n    %s" % hub)
        try:
            answer = input("Type ERASE to confirm: ").strip()
        except EOFError:
            answer = ""
        if answer != "ERASE":
            step("Hub data", False, "kept (not confirmed)")
            return
    ok = _remove_tree(hub)
    step("Hub data", ok, "erased " + hub if ok else "could not delete " + hub)
    for name, path in sorted(linked.items()):
        print("       kept linked project '%s' at %s" % (name, path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-houdini", action="store_true")
    parser.add_argument("--no-shortcut", action="store_true")
    parser.add_argument("--no-app", action="store_true")
    parser.add_argument("--no-splash", action="store_true")
    parser.add_argument("--no-fonts", action="store_true")
    parser.add_argument("--no-login", action="store_true")
    parser.add_argument("--purge-hub", action="store_true",
                        help="ALSO erase the hub and every project inside it")
    parser.add_argument("--reinstall", action="store_true",
                        help="run the one-shot installer after uninstalling")
    parser.add_argument("--yes", action="store_true",
                        help="skip confirmations (for scripts)")
    args = parser.parse_args(argv)

    print("FIVE HUB uninstaller — %s\n" % REPO)
    if not args.no_houdini:
        remove_houdini_packages()
    if not args.no_shortcut:
        remove_shortcut()
    if not args.no_app:
        remove_app_artifacts()
    if not args.no_splash:
        remove_splash()
    if not args.no_fonts:
        remove_fonts()
    if not args.no_login:
        remove_login()
    if args.purge_hub:
        purge_hub(args.yes)
    else:
        hub = os.environ.get("FIVEHUB_ROOT") or os.path.join(REPO, "hub")
        if os.path.isdir(hub):
            print("\nYour projects are untouched at %s" % hub)
            print("(erase them too with: python uninstall.py --purge-hub)")

    if args.reinstall:
        print("\n--- reinstalling ------------------------------------------\n")
        return subprocess.call([sys.executable, os.path.join(REPO, "install.py")])

    print("\nDone. Reinstall any time: install.bat / ./install.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
