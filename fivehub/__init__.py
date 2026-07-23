"""FiveHub — USD asset publishing pipeline.

Assets are stored on disk as versioned USD component assets (entry layer with
a payload arc, split geo/mtl layers, a "geo" variantSet and a thumbnail baked
into the asset via AssetPreviewsAPI), indexed in a SQLite database.

Publishing runs a validation pass (naming, scale, unwelded geometry, missing
materials, ...) and produces a pass/fail report; errors block the publish.
"""

__version__ = "2.0.0"

from .geometry import MaterialData, MeshData, PublishRequest, SourceInfo
from .publish import PublishResult, publish
from .report import Severity, Status, ValidationReport

__all__ = [
    "MaterialData",
    "MeshData",
    "PublishRequest",
    "PublishResult",
    "Severity",
    "SourceInfo",
    "Status",
    "ValidationReport",
    "publish",
    "__version__",
]
