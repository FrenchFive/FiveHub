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
# Registry of projects living outside the default projects/ directory
# (shared drives, synced folders, repositories — the user picks a location).
REGISTRY_FILE = "registry.json"

PROJECT_FILE = "project.json"
PROJECT_DB = "project.db"
PROJECT_REPORTS_DIR = "reports"

ASSETS_DIR = "assets"
SHOTS_DIR = "shots"
SCENES_DIR = "scenes"
PUBLISH_DIR = "publish"
CACHES_DIR = "caches"
RENDER_DIR = "render"
REFS_DIR = "refs"
TRASH_DIR = ".trash"

SELECTION_FILE = "selection.json"
REPORT_FILE = "report.json"
THUMBNAILS_DIR = "thumbnails"

# Per-record JSON sidecars: the durable, git-mergeable source of truth the
# local project.db cache is rebuilt from.
RECORDS_DIR = os.path.join(".fivehub", "records")

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

# Tasks whose deliverable IS the look. Only these block a publish on
# missing material assignments — a modeling publish legitimately ships
# before lookdev has happened.
LOOKDEV_TASKS = ("lookdev", "shading", "surfacing", "texturing", "look")

DEFAULT_FORMAT = "usd"
FORMATS = ("usd", "bgeo", "vdb", "obj", "hda")
FORMAT_EXTENSIONS = {
    "usd": (".usd", ".usda", ".usdc", ".usdz"),
    "bgeo": (".bgeo", ".bgeo.sc", ".geo"),
    "vdb": (".vdb",),
    "obj": (".obj",),
    "hda": (".hda", ".otl", ".hdanc", ".hdalc"),
    "abc": (".abc",),
    "fbx": (".fbx",),
    "tex": (".png", ".jpg", ".jpeg", ".exr", ".hdr", ".tif", ".tiff", ".tx", ".rat"),
    "render": (".exr", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".mp4"),
}

# Extension -> format used when ingesting external files.
INGEST_FORMATS = {}
for _format, _extensions in FORMAT_EXTENSIONS.items():
    if _format == "render":
        continue
    for _ext in _extensions:
        INGEST_FORMATS.setdefault(_ext, _format)

SCENE_EXTENSION = ".hip"
# What a Houdini license actually writes: commercial .hip, Indie .hiplc,
# Apprentice/Education .hipnc — all three are pipeline scenes.
SCENE_EXTENSIONS = (".hip", ".hiplc", ".hipnc")


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


def user_exchange_path(root, user=None):
    """Per-user exchange directory, so artists never overwrite each other's
    staged selections or capture files on a shared hub."""
    if user is None:
        from .user import get_user

        user = get_user()
    from .naming import make_identifier

    path = os.path.join(exchange_path(root), make_identifier(user, fallback="user"))
    os.makedirs(path, exist_ok=True)
    return path


def selection_path(root, user=None):
    return os.path.join(user_exchange_path(root, user), SELECTION_FILE)


def kind_dir(kind):
    if kind not in KINDS:
        raise ValueError("unknown entity kind: %r (expected one of %s)" % (kind, KINDS))
    return ASSETS_DIR if kind == "asset" else SHOTS_DIR


def version_label(version):
    return "v%03d" % int(version)


def scene_file_name(entity, task, version, extension=None):
    return "%s_%s_%s%s" % (
        entity, task, version_label(version), extension or SCENE_EXTENSION,
    )
