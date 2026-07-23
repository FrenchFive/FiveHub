"""DCC-neutral geometry model.

Exporters (Houdini today, anything tomorrow) translate their native geometry
into these structures. Validation and USD authoring only ever see this model,
so publish-time checks behave identically no matter where the data came from.
"""

import math
from dataclasses import dataclass, field


@dataclass
class MaterialData:
    """A material to author as a UsdPreviewSurface network."""

    name: str
    base_color: tuple = (0.18, 0.18, 0.18)
    roughness: float = 0.5
    metallic: float = 0.0
    source_path: str = ""


@dataclass
class MeshData:
    """One polygonal mesh, USD-style: flat points + faceVertexCounts/Indices."""

    name: str
    points: list = field(default_factory=list)
    face_vertex_counts: list = field(default_factory=list)
    face_vertex_indices: list = field(default_factory=list)
    # Optional per-face-vertex normals, same ordering as face_vertex_indices.
    normals: list = None
    # Optional material name per face (None entries = unassigned face).
    face_materials: list = None
    display_color: tuple = None

    @property
    def face_count(self):
        return len(self.face_vertex_counts)

    def iter_faces(self):
        """Yield (face_index, [point indices]) per face."""
        cursor = 0
        for i, count in enumerate(self.face_vertex_counts):
            yield i, self.face_vertex_indices[cursor:cursor + count]
            cursor += count

    def used_materials(self):
        """Distinct material names bound on faces, insertion-ordered."""
        if not self.face_materials:
            return []
        seen = {}
        for name in self.face_materials:
            if name:
                seen.setdefault(name, True)
        return list(seen)

    def material_face_map(self):
        """Map material name (or None) -> list of face indices."""
        faces = {}
        if not self.face_materials:
            faces[None] = list(range(self.face_count))
            return faces
        for i in range(self.face_count):
            name = self.face_materials[i] if i < len(self.face_materials) else None
            faces.setdefault(name or None, []).append(i)
        return faces

    def bounds(self):
        return bounds_of(self.points)


@dataclass
class SourceInfo:
    """Where a publish came from, for provenance in assetInfo and reports."""

    dcc: str = ""
    scene: str = ""
    nodes: list = field(default_factory=list)
    user: str = ""


@dataclass
class PublishRequest:
    """Everything the publisher needs for one publish attempt."""

    asset_name: str
    project: str = ""
    variant: str = "default"
    comment: str = ""
    meshes: list = field(default_factory=list)
    materials: dict = field(default_factory=dict)
    thumbnail: str = None
    meters_per_unit: float = 1.0
    up_axis: str = "Y"
    source: SourceInfo = field(default_factory=SourceInfo)

    def bounds(self):
        merged = None
        for mesh in self.meshes:
            merged = union_bounds(merged, mesh.bounds())
        return merged


def bounds_of(points):
    """Axis-aligned (min, max) of an iterable of 3-tuples, or None if empty."""
    lo = hi = None
    for p in points:
        if lo is None:
            lo = list(p)
            hi = list(p)
            continue
        for a in range(3):
            if p[a] < lo[a]:
                lo[a] = p[a]
            if p[a] > hi[a]:
                hi[a] = p[a]
    if lo is None:
        return None
    return tuple(lo), tuple(hi)


def union_bounds(a, b):
    if a is None:
        return b
    if b is None:
        return a
    lo = tuple(min(a[0][i], b[0][i]) for i in range(3))
    hi = tuple(max(a[1][i], b[1][i]) for i in range(3))
    return lo, hi


def bounds_size(bounds):
    if bounds is None:
        return (0.0, 0.0, 0.0)
    return tuple(bounds[1][i] - bounds[0][i] for i in range(3))


def bounds_center(bounds):
    if bounds is None:
        return (0.0, 0.0, 0.0)
    return tuple((bounds[0][i] + bounds[1][i]) * 0.5 for i in range(3))


def duplicate_point_clusters(points, tolerance=1e-5):
    """Groups of point indices that sit on the same position (unwelded points).

    Points are bucketed on their position quantized by ``tolerance``; any
    bucket holding more than one point is a cluster of coincident points.
    """
    buckets = {}
    for i, p in enumerate(points):
        key = tuple(round(c / tolerance) for c in p)
        buckets.setdefault(key, []).append(i)
    return [indices for indices in buckets.values() if len(indices) > 1]


def unused_points(mesh):
    """Point indices never referenced by any face."""
    used = set(mesh.face_vertex_indices)
    return [i for i in range(len(mesh.points)) if i not in used]


def face_area(points, indices):
    """Polygon area via Newell's method (handles non-planar faces gracefully)."""
    nx = ny = nz = 0.0
    n = len(indices)
    for i in range(n):
        x1, y1, z1 = points[indices[i]]
        x2, y2, z2 = points[indices[(i + 1) % n]]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)


def degenerate_faces(mesh, area_tolerance=1e-10):
    """Faces that are structurally broken: <3 vertices, repeated point
    indices within the face, or (near-)zero area."""
    bad = []
    for face_index, indices in mesh.iter_faces():
        if len(indices) < 3:
            bad.append((face_index, "fewer than 3 vertices"))
        elif len(set(indices)) < len(indices):
            bad.append((face_index, "repeated point index"))
        elif face_area(mesh.points, indices) <= area_tolerance:
            bad.append((face_index, "zero area"))
    return bad
