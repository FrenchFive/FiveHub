"""The publisher.

Publishes always happen in a pipeline context — project / entity (asset or
shot) / task — and are gated by validation: no ERROR-severity failure ever
reaches disk. Two flavours:

``publish_usd``     full USD component asset (entry layer with payload arc,
                    geo/mtl split, "geo" variantSet, thumbnail baked in via
                    AssetPreviewsAPI) written under
                    ``.../<task>/publish/usd/v###/`` with a root interface
                    layer per publish name that always tracks the latest
                    version of every variant.

``publish_files``   any other format (vdb, bgeo, obj, ...): validated file
                    drop into ``.../<task>/publish/<format>/v###/``.

Blocked attempts write their report to the project's ``reports/`` directory
and are recorded in the project database with no version.
"""

import os
import shutil
import uuid
from dataclasses import dataclass, field

from . import config, usdlayers, validation
from .geometry import SourceInfo
from .naming import make_identifier
from .user import get_user


@dataclass
class FilePublishRequest:
    """A non-USD publish: files produced by the DCC, dropped as a version."""

    asset_name: str
    format: str
    files: list = field(default_factory=list)
    variant: str = "default"
    comment: str = ""
    thumbnail: str = None
    project: str = ""
    source: SourceInfo = field(default_factory=SourceInfo)


@dataclass
class PublishResult:
    passed: bool
    report: object
    report_path: str
    format: str = "usd"
    version: int = None
    version_label: str = ""
    publish_dir: str = ""
    entry_layer: str = ""
    root_layer: str = ""
    files: list = field(default_factory=list)
    thumbnail: str = ""

    def to_dict(self):
        return {
            "passed": self.passed,
            "format": self.format,
            "version": self.version,
            "version_label": self.version_label,
            "publish_dir": self.publish_dir,
            "entry_layer": self.entry_layer,
            "root_layer": self.root_layer,
            "files": list(self.files),
            "thumbnail": self.thumbnail,
            "report_path": self.report_path,
            "report": self.report.to_dict(),
        }


def _blocked(project, task_id, request, report, format_name):
    stamp = report.created_at.replace("-", "").replace(":", "")
    report_name = "%s_%s_%s.json" % (
        make_identifier(request.asset_name, fallback="publish"),
        stamp,
        uuid.uuid4().hex[:8],
    )
    report_path = report.save(os.path.join(project.reports_dir(), report_name))
    project.db.record_publish(
        task_id,
        request.asset_name,
        format_name,
        request.variant,
        None,
        report,
        report_path=report_path,
        comment=request.comment,
        user=request.source.user,
    )
    return PublishResult(
        passed=False, report=report, report_path=report_path, format=format_name
    )


def _allocate_version(project, task_id, publish_root, format_name):
    version = project.db.next_publish_version(task_id, format_name)
    # Skip over directories left behind by interrupted publishes.
    while os.path.exists(os.path.join(publish_root, config.version_label(version))):
        version += 1
    return version


def _copy_thumbnail(request, version_dir):
    """Copy the capture into the version dir; returns (abs, entry-relative)."""
    if not (request.thumbnail and os.path.isfile(request.thumbnail)):
        return "", None
    extension = os.path.splitext(request.thumbnail)[1].lower() or ".png"
    thumb_dir = os.path.join(version_dir, config.THUMBNAILS_DIR)
    os.makedirs(thumb_dir, exist_ok=True)
    absolute = os.path.join(thumb_dir, request.asset_name + extension)
    shutil.copyfile(request.thumbnail, absolute)
    relative = "./%s/%s%s" % (config.THUMBNAILS_DIR, request.asset_name, extension)
    return absolute, relative


def publish_usd(project, kind, entity, task, request, rule_config=None):
    """Validated USD component publish into a project task."""
    if not request.asset_name:
        request.asset_name = entity
    request.project = project.name
    if not request.source.user:
        request.source.user = get_user()  # every publish is signed
    task_record = project._task_record(kind, entity, task)
    task_id = task_record["id"]

    report = validation.validate(request, rule_config)
    if not report.passed:
        return _blocked(project, task_id, request, report, "usd")

    name = request.asset_name
    publish_root = project.publish_dir(kind, entity, task, "usd")
    version = _allocate_version(project, task_id, publish_root, "usd")
    label = config.version_label(version)
    version_dir = os.path.join(publish_root, label)
    os.makedirs(version_dir)

    thumbnail_abs, thumbnail_rel = _copy_thumbnail(request, version_dir)

    geo_layer = usdlayers.write_geo_layer(
        os.path.join(version_dir, "%s.geo.usda" % name), request
    )
    usdlayers.write_mtl_layer(os.path.join(version_dir, "%s.mtl.usda" % name), request)
    usdlayers.write_payload_layer(
        os.path.join(version_dir, "%s.payload.usda" % name),
        request,
        geo_layer="./%s.geo.usda" % name,
        mtl_layer="./%s.mtl.usda" % name,
    )

    bounds = request.bounds()
    provenance = {
        "comment": request.comment or "",
        "sourceDcc": request.source.dcc or "",
        "sourceScene": request.source.scene or "",
        "context": "%s / %s %s / %s" % (project.name, kind, entity, task),
    }

    # Variants published in earlier versions stay addressable from this
    # entry layer by pointing their payloads at the version that owns them.
    known = project.db.known_variants(task_id, "usd", name)
    variants = {
        variant: "../%s/%s.payload.usda" % (config.version_label(v), name)
        for variant, v in known.items()
    }
    variants[request.variant] = "./%s.payload.usda" % name
    selected = "default" if "default" in variants else request.variant

    entry_layer = usdlayers.write_entry_layer(
        os.path.join(version_dir, "%s.usda" % name),
        request,
        variants=variants,
        selected_variant=selected,
        version_label=label,
        thumbnail=thumbnail_rel,
        extents=bounds,
        custom=provenance,
    )
    report_path = report.save(os.path.join(version_dir, config.REPORT_FILE))

    project.db.record_publish(
        task_id,
        name,
        "usd",
        request.variant,
        version,
        report,
        path=entry_layer,
        report_path=report_path,
        thumbnail=thumbnail_abs,
        comment=request.comment,
        user=request.source.user,
    )

    # Root interface: every variant of this publish name at its latest.
    latest = project.db.known_variants(task_id, "usd", name)
    root_variants = {
        variant: "./%s/%s.payload.usda" % (config.version_label(v), name)
        for variant, v in latest.items()
    }
    root_thumbnail = "./%s/%s" % (label, thumbnail_rel[2:]) if thumbnail_rel else None
    root_layer = usdlayers.write_entry_layer(
        os.path.join(publish_root, "%s.usda" % name),
        request,
        variants=root_variants,
        selected_variant="default" if "default" in root_variants else request.variant,
        version_label=label,
        thumbnail=root_thumbnail,
        extents=bounds,
        custom=provenance,
    )

    return PublishResult(
        passed=True,
        report=report,
        report_path=report_path,
        format="usd",
        version=version,
        version_label=label,
        publish_dir=version_dir,
        entry_layer=entry_layer,
        root_layer=root_layer,
        files=[entry_layer],
        thumbnail=thumbnail_abs,
    )


def publish_files(project, kind, entity, task, request, rule_config=None):
    """Validated file publish (vdb / bgeo / obj / ...) into a project task."""
    if not request.asset_name:
        request.asset_name = entity
    request.project = project.name
    if not request.source.user:
        request.source.user = get_user()  # every publish is signed
    task_record = project._task_record(kind, entity, task)
    task_id = task_record["id"]

    report = validation.validate_files(request, rule_config)
    if not report.passed:
        return _blocked(project, task_id, request, report, request.format)

    publish_root = project.publish_dir(kind, entity, task, request.format)
    version = _allocate_version(project, task_id, publish_root, request.format)
    label = config.version_label(version)
    version_dir = os.path.join(publish_root, label)
    os.makedirs(version_dir)

    published = []
    for source_file in request.files:
        target = os.path.join(version_dir, os.path.basename(source_file))
        shutil.copyfile(source_file, target)
        published.append(target)

    thumbnail_abs, _ = _copy_thumbnail(request, version_dir)
    report_path = report.save(os.path.join(version_dir, config.REPORT_FILE))

    project.db.record_publish(
        task_id,
        request.asset_name,
        request.format,
        request.variant,
        version,
        report,
        path=version_dir,
        report_path=report_path,
        thumbnail=thumbnail_abs,
        comment=request.comment,
        user=request.source.user,
    )

    return PublishResult(
        passed=True,
        report=report,
        report_path=report_path,
        format=request.format,
        version=version,
        version_label=label,
        publish_dir=version_dir,
        files=published,
        thumbnail=thumbnail_abs,
    )
