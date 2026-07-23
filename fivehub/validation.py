"""Publish-time validation rules.

The default rule set gates every publish: naming, units and scale, geometry
health (unwelded points, unused points, degenerate faces) and material
coverage. Severities and tolerances can be overridden per publish via a
``{rule_id: {param: value}}`` config mapping.
"""

import math
import os

from . import geometry, naming
from .report import Rule, Severity, run_rules


class AssetNameRule(Rule):
    rule_id = "naming.asset"
    label = "Asset name is a valid USD identifier"
    severity = Severity.ERROR

    def check(self, request):
        return naming.asset_name_errors(request.asset_name)


class AssetStyleRule(Rule):
    rule_id = "naming.style"
    label = "Asset name follows UpperCamelCase style"
    severity = Severity.WARNING

    def check(self, request):
        return naming.asset_name_warnings(request.asset_name)


class VariantNameRule(Rule):
    rule_id = "naming.variant"
    label = "Variant name is a valid USD identifier"
    severity = Severity.ERROR

    def check(self, request):
        if not naming.is_identifier(request.variant):
            return ["variant %r is not a valid USD identifier" % request.variant]
        return []


class MeshNameRule(Rule):
    rule_id = "naming.meshes"
    label = "Mesh names are valid and unique"
    severity = Severity.ERROR

    def check(self, request):
        issues = []
        seen = set()
        for mesh in request.meshes:
            if not naming.is_identifier(mesh.name):
                issues.append("mesh name %r is not a valid USD identifier" % mesh.name)
            if mesh.name in seen:
                issues.append("duplicate mesh name %r" % mesh.name)
            seen.add(mesh.name)
        return issues


class MaterialNameRule(Rule):
    rule_id = "naming.materials"
    label = "Material names are valid identifiers"
    severity = Severity.ERROR

    def check(self, request):
        issues = []
        for key, material in request.materials.items():
            if not naming.is_identifier(material.name):
                issues.append("material name %r is not a valid USD identifier" % material.name)
            if material.name != key:
                issues.append(
                    "material registered as %r but named %r" % (key, material.name)
                )
        return issues


class EmptyGeoRule(Rule):
    rule_id = "geo.empty"
    label = "Asset contains polygonal geometry"
    severity = Severity.ERROR

    def check(self, request):
        if not request.meshes:
            return ["no meshes in publish"]
        issues = []
        for mesh in request.meshes:
            if not mesh.points:
                issues.append("mesh %r has no points" % mesh.name)
            elif not mesh.face_vertex_counts:
                issues.append("mesh %r has no faces" % mesh.name)
        return issues


class UnitsRule(Rule):
    rule_id = "scale.units"
    label = "Stage units and up axis are declared sanely"
    severity = Severity.ERROR

    def check(self, request):
        issues = []
        if not request.meters_per_unit or request.meters_per_unit <= 0:
            issues.append("metersPerUnit must be > 0 (got %r)" % request.meters_per_unit)
        if request.up_axis not in ("Y", "Z"):
            issues.append("upAxis must be Y or Z (got %r)" % request.up_axis)
        return issues


class ScaleRule(Rule):
    rule_id = "scale.size"
    label = "Asset size is within plausible world scale"
    severity = Severity.WARNING
    min_size = 0.001   # meters — smaller than a grain of rice is suspicious
    max_size = 100.0   # meters — larger than a building is suspicious

    def applies(self, request):
        return bool(request.meshes) and request.bounds() is not None

    def check(self, request):
        size = geometry.bounds_size(request.bounds())
        mpu = request.meters_per_unit or 1.0
        meters = [c * mpu for c in size]
        largest = max(meters)
        issues = []
        if largest > self.max_size:
            issues.append(
                "asset is %.2f m across — larger than %.0f m, check scene scale"
                % (largest, self.max_size)
            )
        if 0 < largest < self.min_size:
            issues.append(
                "asset is %.5f m across — smaller than %.3f m, check scene scale"
                % (largest, self.min_size)
            )
        return issues


class DegenerateBoundsRule(Rule):
    rule_id = "scale.bounds"
    label = "Bounding box is not degenerate"
    severity = Severity.ERROR

    def applies(self, request):
        return bool(request.meshes)

    def check(self, request):
        bounds = request.bounds()
        if bounds is None:
            return ["no points to compute bounds from"]
        size = geometry.bounds_size(bounds)
        if max(size) <= 0.0:
            return ["bounding box has zero size — all points coincide"]
        return []


class OriginRule(Rule):
    rule_id = "scale.origin"
    label = "Asset sits near the world origin"
    severity = Severity.WARNING

    def applies(self, request):
        return bool(request.meshes) and request.bounds() is not None

    def check(self, request):
        bounds = request.bounds()
        center = geometry.bounds_center(bounds)
        size = geometry.bounds_size(bounds)
        diagonal = math.sqrt(sum(c * c for c in size))
        distance = math.sqrt(sum(c * c for c in center))
        if distance > max(diagonal, 1.0):
            return [
                "asset center is %.2f units from the origin — publish assets at origin"
                % distance
            ]
        return []


class UnweldedRule(Rule):
    rule_id = "geo.unwelded"
    label = "No unwelded (coincident) points"
    severity = Severity.ERROR
    tolerance = 1e-5
    # Number of coincident-point clusters tolerated before failing.
    allowed_clusters = 0

    def applies(self, request):
        return bool(request.meshes)

    def check(self, request):
        issues = []
        for mesh in request.meshes:
            clusters = geometry.duplicate_point_clusters(mesh.points, self.tolerance)
            if len(clusters) > self.allowed_clusters:
                doubled = sum(len(c) for c in clusters)
                issues.append(
                    "mesh %r has %d cluster(s) of coincident points (%d points) — "
                    "fuse/weld before publishing" % (mesh.name, len(clusters), doubled)
                )
        return issues


class UnusedPointsRule(Rule):
    rule_id = "geo.unused"
    label = "No points detached from faces"
    severity = Severity.WARNING

    def applies(self, request):
        return bool(request.meshes)

    def check(self, request):
        issues = []
        for mesh in request.meshes:
            stray = geometry.unused_points(mesh)
            if stray:
                issues.append(
                    "mesh %r has %d point(s) not used by any face" % (mesh.name, len(stray))
                )
        return issues


class DegenerateFacesRule(Rule):
    rule_id = "geo.degenerate"
    label = "No degenerate faces"
    severity = Severity.ERROR
    area_tolerance = 1e-10

    def applies(self, request):
        return bool(request.meshes)

    def check(self, request):
        issues = []
        for mesh in request.meshes:
            bad = geometry.degenerate_faces(mesh, self.area_tolerance)
            if bad:
                sample = ", ".join(
                    "face %d (%s)" % (index, why) for index, why in bad[:5]
                )
                more = " and %d more" % (len(bad) - 5) if len(bad) > 5 else ""
                issues.append(
                    "mesh %r has %d degenerate face(s): %s%s"
                    % (mesh.name, len(bad), sample, more)
                )
        return issues


class MissingMaterialRule(Rule):
    rule_id = "mtl.missing"
    label = "Every face has a material assigned"
    severity = Severity.ERROR

    def applies(self, request):
        return bool(request.meshes)

    def check(self, request):
        issues = []
        for mesh in request.meshes:
            unassigned = mesh.material_face_map().get(None, [])
            if unassigned:
                issues.append(
                    "mesh %r has %d face(s) with no material assigned"
                    % (mesh.name, len(unassigned))
                )
        return issues


class UnknownMaterialRule(Rule):
    rule_id = "mtl.unknown"
    label = "All bound materials are published with the asset"
    severity = Severity.ERROR

    def applies(self, request):
        return bool(request.meshes)

    def check(self, request):
        issues = []
        for mesh in request.meshes:
            for name in mesh.used_materials():
                if name not in request.materials:
                    issues.append(
                        "mesh %r binds material %r which is not part of the publish"
                        % (mesh.name, name)
                    )
        return issues


class ThumbnailRule(Rule):
    rule_id = "asset.thumbnail"
    label = "Thumbnail is captured for the asset"
    severity = Severity.WARNING

    def check(self, request):
        if not request.thumbnail:
            return ["no thumbnail was provided with the publish"]
        if not os.path.isfile(request.thumbnail) or os.path.getsize(request.thumbnail) == 0:
            return ["thumbnail file %r is missing or empty" % request.thumbnail]
        return []


DEFAULT_RULES = (
    AssetNameRule,
    AssetStyleRule,
    VariantNameRule,
    MeshNameRule,
    MaterialNameRule,
    EmptyGeoRule,
    UnitsRule,
    DegenerateBoundsRule,
    ScaleRule,
    OriginRule,
    UnweldedRule,
    UnusedPointsRule,
    DegenerateFacesRule,
    MissingMaterialRule,
    UnknownMaterialRule,
    ThumbnailRule,
)


def build_rules(config=None):
    """Instantiate the default rule set, applying per-rule config overrides."""
    config = config or {}
    rules = []
    for rule_class in DEFAULT_RULES:
        params = dict(config.get(rule_class.rule_id, {}))
        rules.append(rule_class(**params))
    return rules


def validate(request, config=None):
    """Run the full default rule set against a publish request."""
    return run_rules(build_rules(config), request)
