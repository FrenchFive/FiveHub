"""Install FiveHub into Houdini.

Writes a Houdini *package* file (the modern replacement for houdini.env
editing) into the chosen preferences directory:

    <prefs>/packages/fivehub.json

The package exports $FIVEHUB, extends PYTHONPATH with the pipeline modules
and adds ``$FIVEHUB/houdini`` to HOUDINI_PATH — which brings in both the
FIVE HUB main menu (MainMenuCommon.xml) and the shelf (toolbar/). Removing
the single JSON file uninstalls cleanly.

Usage:
    python houdini/install.py             interactive
    python houdini/install.py --prefs ~/houdini20.5   non-interactive
"""

import argparse
import glob
import json
import os
import platform
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def candidate_pref_dirs():
    """Existing houdini preference directories on this machine."""
    home = os.path.expanduser("~")
    system = platform.system()
    if system == "Windows":
        pattern = os.path.join(home, "Documents", "houdini*")
    elif system == "Darwin":
        pattern = os.path.join(home, "Library", "Preferences", "houdini", "*")
    else:
        pattern = os.path.join(home, "houdini*")
    return sorted(path for path in glob.glob(pattern) if os.path.isdir(path))


def package_payload():
    return {
        "hpath": "$FIVEHUB/houdini",
        "env": [
            {"FIVEHUB": REPO.replace("\\", "/")},
            {
                "PYTHONPATH": {
                    "value": ["$FIVEHUB", "$FIVEHUB/houdini"],
                    "method": "prepend",
                }
            },
            # The FIVE HUB launch artwork (regenerate: fivehub.cli splash).
            # Absolute on purpose: the splash file is read so early in the
            # launch that $FIVEHUB may not expand yet — the message applies
            # but the art silently falls back to Houdini's stock image.
            {"HOUDINI_SPLASH_FILE":
                REPO.replace("\\", "/") + "/houdini/splash/fivehub_splash.png"},
            {"HOUDINI_SPLASH_MESSAGE": "FIVE HUB pipeline — validated USD publishes"},
        ],
    }


def install(prefs_dir):
    packages_dir = os.path.join(prefs_dir, "packages")
    os.makedirs(packages_dir, exist_ok=True)
    target = os.path.join(packages_dir, "fivehub.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(package_payload(), handle, indent=4)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefs", help="Houdini preferences directory (e.g. ~/houdini20.5)")
    parser.add_argument("--auto", action="store_true",
                        help="no prompts: install into every Houdini prefs dir found")
    args = parser.parse_args(argv)

    if args.auto:
        candidates = candidate_pref_dirs()
        if not candidates:
            print("No Houdini preferences directory found — launch Houdini once, "
                  "then rerun, or use --prefs <path>.")
            return 1
        for prefs in candidates:
            print("Installed package: %s" % install(prefs))
        print("FIVEHUB -> %s" % REPO)
        return 0

    if args.prefs:
        prefs = os.path.expanduser(args.prefs)
    else:
        candidates = candidate_pref_dirs()
        if not candidates:
            print("No Houdini preferences directory found.")
            prefs = os.path.expanduser(
                input("Enter your Houdini prefs path (e.g. ~/houdini20.5): ").strip()
            )
        else:
            print("Houdini preference directories found:")
            for index, path in enumerate(candidates):
                print("  [%d] %s" % (index, path))
            choice = input(
                "Install into which one? [%d] " % (len(candidates) - 1)
            ).strip()
            index = int(choice) if choice else len(candidates) - 1
            prefs = candidates[index]

    if not os.path.isdir(prefs):
        print("Not a directory: %s" % prefs)
        return 1

    target = install(prefs)
    print("Installed package: %s" % target)
    print("FIVEHUB -> %s" % REPO)
    print("Launch Houdini — the FIVE HUB menu appears in the main menu bar.")
    print("For everything else in one step (app, fonts, splash), run the")
    print("installer at the repo root: install.bat (Windows) / ./install.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
