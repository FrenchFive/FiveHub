"""Hub location and on-disk layout.

The hub root holds everything FiveHub writes:

    <root>/
        assets/<AssetName>/            one directory per asset
            <AssetName>.usda           root interface layer (always latest)
            v001/ v002/ ...            immutable published versions
        db/fivehub.db                  index database
        reports/                       reports for failed publish attempts
        exchange/                      app <-> DCC handoff files (selection, thumbs)

The root is resolved from the FIVEHUB_ROOT environment variable, falling back
to a "hub" directory next to this repository so a fresh clone works with zero
configuration.
"""

import os

ENV_ROOT = "FIVEHUB_ROOT"

ASSETS_DIR = "assets"
DB_FILE = os.path.join("db", "fivehub.db")
REPORTS_DIR = "reports"
EXCHANGE_DIR = "exchange"

SELECTION_FILE = "selection.json"
REPORT_FILE = "report.json"
THUMBNAILS_DIR = "thumbnails"


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def hub_root(override=None):
    """Resolve the hub root directory (without creating it)."""
    root = override or os.environ.get(ENV_ROOT) or os.path.join(repo_root(), "hub")
    return os.path.abspath(os.path.expanduser(root))


def ensure_hub(root=None):
    """Resolve the hub root and make sure its skeleton exists."""
    root = hub_root(root)
    for sub in (ASSETS_DIR, os.path.dirname(DB_FILE), REPORTS_DIR, EXCHANGE_DIR):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    return root


def assets_path(root):
    return os.path.join(root, ASSETS_DIR)


def db_path(root):
    return os.path.join(root, DB_FILE)


def reports_path(root):
    return os.path.join(root, REPORTS_DIR)


def exchange_path(root):
    return os.path.join(root, EXCHANGE_DIR)


def selection_path(root):
    return os.path.join(exchange_path(root), SELECTION_FILE)


def version_label(version):
    return "v%03d" % int(version)
