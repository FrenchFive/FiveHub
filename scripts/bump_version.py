#!/usr/bin/env python3
"""Automatic version bump, driven by how much code a merge changed.

Called by .github/workflows/version-bump.yml on every merge to main:

    lines changed  < 100   ->  patch   (x.y.Z+1)
    lines changed  < 500   ->  minor   (x.Y+1.0)
    lines changed >= 500   ->  major   (X+1.0.0)

Updates the two places the version lives — fivehub/__init__.py (the
source of truth for the CLI, splash and USD layers) and app/package.json —
and prints a JSON summary. Stdlib only.
"""

import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT_PATH = os.path.join(REPO, "fivehub", "__init__.py")
PACKAGE_PATH = os.path.join(REPO, "app", "package.json")

_VERSION_RE = re.compile(r'__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)"')


def classify(lines):
    """Bump level for a merge of `lines` changed lines."""
    if lines < 100:
        return "patch"
    if lines < 500:
        return "minor"
    return "major"


def bump(version, level):
    major, minor, patch = (int(part) for part in version.split("."))
    if level == "major":
        return "%d.0.0" % (major + 1)
    if level == "minor":
        return "%d.%d.0" % (major, minor + 1)
    return "%d.%d.%d" % (major, minor, patch + 1)


def read_version(init_path=INIT_PATH):
    with open(init_path, "r", encoding="utf-8") as handle:
        match = _VERSION_RE.search(handle.read())
    if not match:
        raise SystemExit("could not find __version__ in %s" % init_path)
    return "%s.%s.%s" % match.groups()


def apply(new_version, init_path=INIT_PATH, package_path=PACKAGE_PATH):
    with open(init_path, "r", encoding="utf-8") as handle:
        source = handle.read()
    source = _VERSION_RE.sub('__version__ = "%s"' % new_version, source, count=1)
    with open(init_path, "w", encoding="utf-8") as handle:
        handle.write(source)

    with open(package_path, "r", encoding="utf-8") as handle:
        package = json.load(handle)
    package["version"] = new_version
    with open(package_path, "w", encoding="utf-8") as handle:
        json.dump(package, handle, indent=2)
        handle.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lines", type=int, required=True,
                        help="total lines changed by the merge")
    parser.add_argument("--dry-run", action="store_true",
                        help="compute only, change nothing")
    args = parser.parse_args(argv)

    old = read_version()
    level = classify(args.lines)
    new = bump(old, level)
    if not args.dry_run:
        apply(new)
    json.dump(
        {"old": old, "new": new, "level": level, "lines": args.lines},
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
