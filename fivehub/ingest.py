"""Bringing external material into the pipeline.

``ingest_files`` turns files from anywhere (vendor FBX/Alembic, purchased
USD kits, textures, caches) into a proper validated publish version of a
task — same versioning, same signing, same report as a Houdini publish.

``add_refs`` / ``list_refs`` / ``delete_ref`` manage the project's
reference-material gallery (boards, briefs, style frames) under
``<project>/refs`` — plain files, no database.
"""

import os
import shutil

from . import config
from .geometry import SourceInfo
from .publish import FilePublishRequest, publish_files
from .user import get_user

# Longest extensions first so ".bgeo.sc" wins over ".sc"-style suffixes.
_EXTENSIONS = sorted(config.INGEST_FORMATS, key=len, reverse=True)


def infer_format(path):
    lowered = path.lower()
    for extension in _EXTENSIONS:
        if lowered.endswith(extension):
            return config.INGEST_FORMATS[extension]
    return None


def ingest_files(project, kind, entity, task, files, name=None, variant="default",
                 comment="", thumbnail=None, user=""):
    """Publish external files into a task. All files of one ingest must map
    to a single format — mixed drops are rejected with a clear message."""
    resolved = [os.path.abspath(os.path.expanduser(f)) for f in files]
    formats = {}
    for path in resolved:
        formats.setdefault(infer_format(path) or "?", []).append(path)
    if "?" in formats:
        unknown = ", ".join(os.path.basename(p) for p in formats["?"])
        raise ValueError(
            "cannot ingest %s — unknown format. Known: %s"
            % (unknown, ", ".join(sorted(set(config.INGEST_FORMATS.values()))))
        )
    if len(formats) != 1:
        raise ValueError(
            "mixed formats in one ingest (%s) — ingest each format separately"
            % ", ".join(sorted(formats))
        )
    format_name = next(iter(formats))
    request = FilePublishRequest(
        asset_name=name or entity,
        format=format_name,
        files=resolved,
        variant=variant,
        comment=comment or "ingested",
        thumbnail=thumbnail,
        source=SourceInfo(dcc="ingest", user=user or get_user()),
    )
    return publish_files(project, kind, entity, task, request)


# -- reference material --------------------------------------------------


def add_refs(project, files):
    refs_dir = project.refs_dir()
    os.makedirs(refs_dir, exist_ok=True)
    copied = []
    for source in files:
        source = os.path.abspath(os.path.expanduser(source))
        if not os.path.isfile(source):
            raise ValueError("reference file not found: %s" % source)
        base = os.path.basename(source)
        target = os.path.join(refs_dir, base)
        counter = 1
        while os.path.exists(target):
            counter += 1
            stem, extension = os.path.splitext(base)
            target = os.path.join(refs_dir, "%s_%d%s" % (stem, counter, extension))
        shutil.copyfile(source, target)
        copied.append(target)
    return copied


_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff")


def list_refs(project):
    refs_dir = project.refs_dir()
    if not os.path.isdir(refs_dir):
        return []
    entries = []
    for entry in os.listdir(refs_dir):
        path = os.path.join(refs_dir, entry)
        if not os.path.isfile(path):
            continue
        entries.append(
            {
                "name": entry,
                "path": path,
                "size": os.path.getsize(path),
                "modified": os.path.getmtime(path),
                "is_image": entry.lower().endswith(_IMAGE_EXTENSIONS),
            }
        )
    entries.sort(key=lambda item: item["modified"], reverse=True)
    for entry in entries:
        entry["modified"] = ""  # timestamps travel via mtime sort only
    return entries


def delete_ref(project, name):
    path = os.path.join(project.refs_dir(), os.path.basename(name))
    if not os.path.isfile(path):
        raise ValueError("unknown reference %r" % name)
    project._trash(path, "ref_%s" % name)
