"""The publisher.

One entry point: ``publish(request)``. It validates, and only a fully passing
request (no ERROR-severity failures) is written to the hub:

    assets/<Name>/v###/           immutable version directory
        <Name>.usda               entry layer (payload, variants, thumbnail)
        <Name>.payload.usda
        <Name>.geo.usda
        <Name>.mtl.usda
        thumbnails/<Name>.png
        report.json               the validation report that let it through
    assets/<Name>/<Name>.usda     root interface, regenerated each publish so
                                  it always exposes every variant at its
                                  latest version

Failed attempts never touch the asset directory: their report lands in
``reports/`` and the attempt is recorded in the publish log.
"""

import os
import shutil
import uuid
from dataclasses import dataclass

from . import config, usdlayers, validation
from .db import Database


@dataclass
class PublishResult:
    passed: bool
    report: object
    report_path: str
    version: int = None
    version_label: str = ""
    asset_dir: str = ""
    version_dir: str = ""
    entry_layer: str = ""
    root_layer: str = ""
    thumbnail: str = ""

    def to_dict(self):
        return {
            "passed": self.passed,
            "version": self.version,
            "version_label": self.version_label,
            "asset_dir": self.asset_dir,
            "version_dir": self.version_dir,
            "entry_layer": self.entry_layer,
            "root_layer": self.root_layer,
            "thumbnail": self.thumbnail,
            "report_path": self.report_path,
            "report": self.report.to_dict(),
        }


def publish(request, hub_root=None, rule_config=None):
    root = config.ensure_hub(hub_root)
    database = Database(config.db_path(root))

    report = validation.validate(request, rule_config)

    if not report.passed:
        from .naming import make_identifier

        stamp = report.created_at.replace("-", "").replace(":", "")
        report_name = "%s_%s_%s.json" % (
            make_identifier(request.asset_name, fallback="publish"),
            stamp,
            uuid.uuid4().hex[:8],
        )
        report_path = report.save(os.path.join(config.reports_path(root), report_name))
        database.record_publish(
            request.asset_name, request.project, request.variant, report, None, report_path
        )
        return PublishResult(passed=False, report=report, report_path=report_path)

    asset = database.get_or_create_asset(request.asset_name, request.project)
    version = database.next_version(asset["id"])
    asset_dir = os.path.join(config.assets_path(root), request.asset_name)

    # Skip over directories left behind by interrupted publishes.
    while os.path.exists(os.path.join(asset_dir, config.version_label(version))):
        version += 1
    label = config.version_label(version)
    version_dir = os.path.join(asset_dir, label)
    os.makedirs(version_dir)

    thumbnail_abs = ""
    thumbnail_rel = None
    if request.thumbnail and os.path.isfile(request.thumbnail):
        ext = os.path.splitext(request.thumbnail)[1].lower() or ".png"
        thumb_dir = os.path.join(version_dir, config.THUMBNAILS_DIR)
        os.makedirs(thumb_dir, exist_ok=True)
        thumbnail_abs = os.path.join(thumb_dir, request.asset_name + ext)
        shutil.copyfile(request.thumbnail, thumbnail_abs)
        thumbnail_rel = "./%s/%s%s" % (config.THUMBNAILS_DIR, request.asset_name, ext)

    name = request.asset_name
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
    }

    # Variants seen in earlier versions stay addressable from this entry
    # layer by pointing their payloads at the version that published them.
    known = database.known_variants(asset["id"])
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

    database.record_version(
        asset["id"], version, request.variant, request.comment, entry_layer, thumbnail_abs
    )
    database.record_publish(
        request.asset_name, request.project, request.variant, report, version, report_path
    )

    # Regenerate the root interface with every variant at its latest version.
    latest = database.known_variants(asset["id"])
    root_variants = {
        variant: "./%s/%s.payload.usda" % (config.version_label(v), name)
        for variant, v in latest.items()
    }
    root_thumbnail = None
    if thumbnail_rel:
        root_thumbnail = "./%s/%s" % (label, thumbnail_rel[2:])
    root_layer = usdlayers.write_entry_layer(
        os.path.join(asset_dir, "%s.usda" % name),
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
        version=version,
        version_label=label,
        asset_dir=asset_dir,
        version_dir=version_dir,
        entry_layer=entry_layer,
        root_layer=root_layer,
        thumbnail=thumbnail_abs,
    )
