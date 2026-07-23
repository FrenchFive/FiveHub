"""FiveHub core pipeline tests (stdlib unittest, no external deps).

Run with:  python -m unittest discover -s tests -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from fivehub import config, geometry, naming
from fivehub.db import Database
from fivehub.demo import cube_mesh, run_demo
from fivehub.geometry import MaterialData, MeshData, PublishRequest
from fivehub.publish import publish
from fivehub.report import Severity, Status, ValidationReport
from fivehub.thumbs import write_placeholder_png
from fivehub.validation import validate


def make_request(tmp, name="TestCrate", **overrides):
    thumbnail = os.path.join(tmp, "thumb.png")
    if not os.path.exists(thumbnail):
        write_placeholder_png(thumbnail)
    fields = {
        "asset_name": name,
        "project": "UnitTests",
        "meshes": [cube_mesh()],
        "materials": {"M_DemoWood": MaterialData("M_DemoWood")},
        "thumbnail": thumbnail,
    }
    fields.update(overrides)
    return PublishRequest(**fields)


class NamingTests(unittest.TestCase):
    def test_identifiers(self):
        self.assertTrue(naming.is_identifier("WoodenCrate"))
        self.assertTrue(naming.is_identifier("_private"))
        self.assertFalse(naming.is_identifier("9lives"))
        self.assertFalse(naming.is_identifier("my crate"))
        self.assertFalse(naming.is_identifier(""))

    def test_sanitizers(self):
        self.assertEqual(naming.make_identifier("my crate!"), "my_crate")
        self.assertEqual(naming.make_identifier("9lives"), "_9lives")
        self.assertEqual(naming.make_identifier(""), "unnamed")
        self.assertEqual(naming.make_material_name("wood.mat"), "M_wood_mat")
        self.assertEqual(naming.make_material_name("M_Steel"), "M_Steel")

    def test_asset_name_errors(self):
        self.assertEqual(naming.asset_name_errors("WoodenCrate"), [])
        self.assertTrue(naming.asset_name_errors("wooden crate"))
        self.assertTrue(naming.asset_name_errors("geo"))
        self.assertTrue(naming.asset_name_warnings("wooden_crate"))
        self.assertEqual(naming.asset_name_warnings("WoodenCrate"), [])


class GeometryTests(unittest.TestCase):
    def test_duplicate_clusters(self):
        welded = cube_mesh()
        self.assertEqual(geometry.duplicate_point_clusters(welded.points), [])
        unwelded = cube_mesh(welded=False)
        clusters = geometry.duplicate_point_clusters(unwelded.points)
        # 8 corners, each split into 3 copies (one per adjacent face).
        self.assertEqual(len(clusters), 8)
        self.assertTrue(all(len(c) == 3 for c in clusters))

    def test_unused_points(self):
        mesh = cube_mesh()
        self.assertEqual(geometry.unused_points(mesh), [])
        mesh.points.append((5.0, 5.0, 5.0))
        self.assertEqual(geometry.unused_points(mesh), [8])

    def test_degenerate_faces(self):
        mesh = cube_mesh()
        self.assertEqual(geometry.degenerate_faces(mesh), [])
        # Add a zero-area triangle (three collinear points).
        base = len(mesh.points)
        mesh.points.extend([(0, 0, 0), (1, 0, 0), (2, 0, 0)])
        mesh.face_vertex_counts.append(3)
        mesh.face_vertex_indices.extend([base, base + 1, base + 2])
        bad = geometry.degenerate_faces(mesh)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0][1], "zero area")

    def test_bounds(self):
        mesh = cube_mesh(size=2.0)
        lo, hi = mesh.bounds()
        self.assertEqual(lo, (-1.0, 0.0, -1.0))
        self.assertEqual(hi, (1.0, 2.0, 1.0))


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def rule(self, report, rule_id):
        return next(r for r in report.results if r.rule_id == rule_id)

    def test_clean_request_passes(self):
        report = validate(make_request(self.tmp.name))
        self.assertTrue(report.passed, report.to_text())
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)

    def test_unwelded_fails(self):
        request = make_request(self.tmp.name, meshes=[cube_mesh(welded=False)])
        report = validate(request)
        self.assertFalse(report.passed)
        result = self.rule(report, "geo.unwelded")
        self.assertEqual(result.status, Status.FAIL)
        self.assertEqual(result.severity, Severity.ERROR)

    def test_missing_material_fails(self):
        mesh = cube_mesh()
        mesh.face_materials = None
        report = validate(make_request(self.tmp.name, meshes=[mesh], materials={}))
        self.assertFalse(report.passed)
        self.assertEqual(self.rule(report, "mtl.missing").status, Status.FAIL)

    def test_unknown_material_fails(self):
        report = validate(make_request(self.tmp.name, materials={}))
        self.assertFalse(report.passed)
        self.assertEqual(self.rule(report, "mtl.unknown").status, Status.FAIL)

    def test_bad_name_fails_and_style_warns(self):
        report = validate(make_request(self.tmp.name, name="my crate"))
        self.assertFalse(report.passed)
        self.assertEqual(self.rule(report, "naming.asset").status, Status.FAIL)

        report = validate(make_request(self.tmp.name, name="my_crate"))
        style = self.rule(report, "naming.style")
        self.assertEqual(style.status, Status.FAIL)
        self.assertEqual(style.severity, Severity.WARNING)
        self.assertTrue(report.passed)  # warnings alone do not block

    def test_scale_warnings(self):
        report = validate(make_request(self.tmp.name, meshes=[cube_mesh(size=500.0)]))
        big = self.rule(report, "scale.size")
        self.assertEqual(big.status, Status.FAIL)
        self.assertEqual(big.severity, Severity.WARNING)
        self.assertTrue(report.passed)

    def test_missing_thumbnail_warns(self):
        report = validate(make_request(self.tmp.name, thumbnail=None))
        thumb = self.rule(report, "asset.thumbnail")
        self.assertEqual(thumb.status, Status.FAIL)
        self.assertTrue(report.passed)

    def test_severity_override(self):
        request = make_request(self.tmp.name, meshes=[cube_mesh(welded=False)])
        report = validate(request, {"geo.unwelded": {"severity": Severity.WARNING}})
        self.assertTrue(report.passed)
        self.assertEqual(self.rule(report, "geo.unwelded").severity, Severity.WARNING)

    def test_report_roundtrip(self):
        report = validate(make_request(self.tmp.name))
        path = os.path.join(self.tmp.name, "report.json")
        report.save(path)
        loaded = ValidationReport.load(path)
        self.assertEqual(loaded.to_dict(), report.to_dict())
        self.assertIn("VALIDATION PASSED", loaded.to_text())


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, *parts):
        with open(os.path.join(*parts), "r", encoding="utf-8") as handle:
            return handle.read()

    def test_publish_creates_component_structure(self):
        result = publish(make_request(self.tmp.name), hub_root=self.hub)
        self.assertTrue(result.passed, result.report.to_text())
        self.assertEqual(result.version, 1)

        version_dir = result.version_dir
        for filename in (
            "TestCrate.usda",
            "TestCrate.payload.usda",
            "TestCrate.geo.usda",
            "TestCrate.mtl.usda",
            "report.json",
            os.path.join("thumbnails", "TestCrate.png"),
        ):
            self.assertTrue(
                os.path.isfile(os.path.join(version_dir, filename)), filename
            )

        entry = self.read(version_dir, "TestCrate.usda")
        self.assertIn('defaultPrim = "TestCrate"', entry)
        self.assertIn('kind = "component"', entry)
        self.assertIn('variantSet "geo"', entry)
        self.assertIn("payload = @./TestCrate.payload.usda@</TestCrate>", entry)
        self.assertIn("AssetPreviewsAPI", entry)
        self.assertIn(
            "previews:thumbnails:default:defaultImage = @./thumbnails/TestCrate.png@",
            entry,
        )
        self.assertIn("extentsHint", entry)

        payload = self.read(version_dir, "TestCrate.payload.usda")
        self.assertIn("@./TestCrate.mtl.usda@</TestCrate>", payload)
        self.assertIn("@./TestCrate.geo.usda@</TestCrate>", payload)

        geo = self.read(version_dir, "TestCrate.geo.usda")
        self.assertIn('def Mesh "crate"', geo)
        self.assertIn("faceVertexCounts", geo)

        mtl = self.read(version_dir, "TestCrate.mtl.usda")
        self.assertIn('def Material "M_DemoWood"', mtl)
        self.assertIn("UsdPreviewSurface", mtl)
        self.assertIn("rel material:binding = </TestCrate/mtl/M_DemoWood>", mtl)

        database = Database(config.db_path(self.hub))
        assets = database.list_assets()
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["name"], "TestCrate")
        self.assertEqual(assets[0]["latest_version"], 1)

    def test_failed_publish_writes_nothing_to_assets(self):
        request = make_request(self.tmp.name, meshes=[cube_mesh(welded=False)])
        result = publish(request, hub_root=self.hub)
        self.assertFalse(result.passed)
        self.assertIsNone(result.version)
        self.assertFalse(
            os.path.exists(os.path.join(config.assets_path(self.hub), "TestCrate"))
        )
        self.assertTrue(os.path.isfile(result.report_path))
        self.assertTrue(result.report_path.startswith(config.reports_path(self.hub)))

        history = Database(config.db_path(self.hub)).publish_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["passed"], 0)
        self.assertIsNone(history[0]["version"])

    def test_variant_publish_composes_across_versions(self):
        publish(make_request(self.tmp.name), hub_root=self.hub)
        result = publish(
            make_request(self.tmp.name, variant="damaged", comment="dents"),
            hub_root=self.hub,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.version, 2)

        # v002's entry exposes its own variant locally and v001's by relative path.
        entry = self.read(result.version_dir, "TestCrate.usda")
        self.assertIn('"damaged" (', entry)
        self.assertIn("payload = @./TestCrate.payload.usda@</TestCrate>", entry)
        self.assertIn("payload = @../v001/TestCrate.payload.usda@</TestCrate>", entry)
        self.assertIn('string geo = "default"', entry)

        # The root interface points every variant at its latest version.
        root_layer = self.read(result.asset_dir, "TestCrate.usda")
        self.assertIn("payload = @./v001/TestCrate.payload.usda@</TestCrate>", root_layer)
        self.assertIn("payload = @./v002/TestCrate.payload.usda@</TestCrate>", root_layer)

    def test_multi_material_mesh_gets_subsets(self):
        mesh = cube_mesh()
        mesh.face_materials = ["M_A", "M_A", "M_A", "M_B", "M_B", "M_B"]
        request = make_request(
            self.tmp.name,
            meshes=[mesh],
            materials={"M_A": MaterialData("M_A"), "M_B": MaterialData("M_B")},
        )
        result = publish(request, hub_root=self.hub)
        self.assertTrue(result.passed, result.report.to_text())
        geo = self.read(result.version_dir, "TestCrate.geo.usda")
        self.assertIn('def GeomSubset "M_A"', geo)
        self.assertIn('familyName = "materialBind"', geo)
        mtl = self.read(result.version_dir, "TestCrate.mtl.usda")
        self.assertIn('over "M_A"', mtl)
        self.assertIn("rel material:binding = </TestCrate/mtl/M_B>", mtl)

    def test_demo_end_to_end(self):
        results = run_demo(self.hub)
        self.assertEqual([r.passed for r in results], [True, True, False])
        database = Database(config.db_path(self.hub))
        self.assertEqual(len(database.publish_history()), 3)
        asset = database.get_asset("DemoCrate")
        self.assertEqual(
            database.known_variants(asset["id"]), {"default": 1, "dark": 2}
        )


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        completed = subprocess.run(
            [sys.executable, "-m", "fivehub.cli", "--hub", self.hub, *args],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_cli_contract(self):
        info = self.cli("root")
        self.assertEqual(info["root"], os.path.abspath(self.hub))

        self.cli("demo")

        listing = self.cli("list")
        self.assertEqual([a["name"] for a in listing["assets"]], ["DemoCrate"])
        self.assertTrue(os.path.isfile(listing["assets"][0]["thumbnail"]))

        detail = self.cli("show", "DemoCrate")
        self.assertEqual(len(detail["asset"]["versions"]), 2)
        self.assertEqual(detail["asset"]["variants"], {"default": 1, "dark": 2})

        report = self.cli("report", "DemoCrate", "--version", "1")
        self.assertTrue(report["report"]["passed"])

        log = self.cli("log")
        self.assertEqual(len(log["log"]), 3)
        self.assertEqual(log["log"][0]["passed"], 0)  # newest = the broken one

        sent = self.cli("send", "DemoCrate")
        self.assertTrue(os.path.isfile(sent["path"]))
        self.assertTrue(sent["selection"]["layer"].endswith("DemoCrate.usda"))

        projects = self.cli("projects")
        self.assertEqual(projects["projects"], ["Demo"])


class ThumbTests(unittest.TestCase):
    def test_png_magic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_placeholder_png(os.path.join(tmp, "t.png"))
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
