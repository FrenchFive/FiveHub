"""Hub location and on-disk layout.

The hub root holds every project. Each project is self-contained — it owns
its database, its image and all of its entities' files:

    <root>/
        projects/
            <Project>/
                project.json                   identity card (name, image)
                project.db                     per-project database
                image.png                      project image
                reports/                       reports of blocked publishes
                assets/<Entity>/<task>/
                    scenes/                    versioned .hip work files
                        <Entity>_<task>_v001.hip
                    publish/<format>/          published output per format
                        <Name>.usda            (usd) root interface, tracks latest
                        v001/ ...              immutable publish versions
                shots/<Entity>/<task>/         same layout as assets
        exchange/                              app <-> DCC handoff files

The root is resolved from the FIVEHUB_ROOT environment variable, falling
back to a "hub" directory next to this repository so a fresh clone works
with zero configuration.
"""

import os

ENV_ROOT = "FIVEHUB_ROOT"

PROJECTS_DIR = "projects"
EXCHANGE_DIR = "exchange"

PROJECT_FILE = "project.json"
PROJECT_DB = "project.db"
PROJECT_REPORTS_DIR = "reports"

ASSETS_DIR = "assets"
SHOTS_DIR = "shots"
SCENES_DIR = "scenes"
PUBLISH_DIR = "publish"

SELECTION_FILE = "selection.json"
REPORT_FILE = "report.json"
THUMBNAILS_DIR = "thumbnails"

KINDS = ("asset", "shot")

# Suggested task names — any valid identifier is accepted at creation time.
DEFAULT_TASKS = (
    "modeling",
    "rig",
    "lookdev",
    "fx",
    "animation",
    "environment",
    "layout",
    "lighting",
)

DEFAULT_FORMAT = "usd"
FORMATS = ("usd", "bgeo", "vdb", "obj")
FORMAT_EXTENSIONS = {
    "usd": (".usd", ".usda", ".usdc"),
    "bgeo": (".bgeo", ".bgeo.sc", ".geo"),
    "vdb": (".vdb",),
    "obj": (".obj",),
}

SCENE_EXTENSION = ".hip"


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def hub_root(override=None):
    """Resolve the hub root directory (without creating it)."""
    root = override or os.environ.get(ENV_ROOT) or os.path.join(repo_root(), "hub")
    return os.path.abspath(os.path.expanduser(root))


def ensure_hub(root=None):
    """Resolve the hub root and make sure its skeleton exists."""
    root = hub_root(root)
    for sub in (PROJECTS_DIR, EXCHANGE_DIR):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    return root


def projects_path(root):
    return os.path.join(root, PROJECTS_DIR)


def exchange_path(root):
    return os.path.join(root, EXCHANGE_DIR)


def selection_path(root):
    return os.path.join(exchange_path(root), SELECTION_FILE)


def kind_dir(kind):
    if kind not in KINDS:
        raise ValueError("unknown entity kind: %r (expected one of %s)" % (kind, KINDS))
    return ASSETS_DIR if kind == "asset" else SHOTS_DIR


def version_label(version):
    return "v%03d" % int(version)


def scene_file_name(entity, task, version):
    return "%s_%s_%s%s" % (entity, task, version_label(version), SCENE_EXTENSION)
