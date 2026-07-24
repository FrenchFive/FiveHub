"""FiveHub — a USD-first publishing pipeline for Houdini.

Projects own their own database, image and files. Inside a project, assets
and shots carry tasks (modeling, rig, lookdev, fx, ...); each task versions
its work scenes and its publishes. USD publishes are full component assets
(payload arc, geo/mtl layer split, "geo" variantSet, thumbnail baked in via
AssetPreviewsAPI); other formats (vdb, bgeo, obj) are validated file drops.

Publishing runs a validation pass (naming, scale, unwelded geometry, missing
materials, ...) and produces a pass/fail report; errors block the publish.
"""

__version__ = "7.1.0"

from .geometry import MaterialData, MeshData, PublishRequest, SourceInfo
from .project import (
    Project,
    create_project,
    get_project,
    list_projects,
    parse_scene_path,
)
from .publish import FilePublishRequest, PublishResult, publish_files, publish_usd
from .report import Severity, Status, ValidationReport

__all__ = [
    "FilePublishRequest",
    "MaterialData",
    "MeshData",
    "Project",
    "PublishRequest",
    "PublishResult",
    "Severity",
    "SourceInfo",
    "Status",
    "ValidationReport",
    "create_project",
    "get_project",
    "list_projects",
    "parse_scene_path",
    "publish_files",
    "publish_usd",
    "__version__",
]
