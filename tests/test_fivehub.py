"""FiveHub core pipeline tests (stdlib unittest, no external deps).

Run with:  python -m unittest discover -s tests -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from fivehub import config, geometry, naming, user
from fivehub.demo import cube_mesh, run_demo
from fivehub.geometry import MaterialData, PublishRequest
from fivehub.project import create_project, get_project, list_projects, parse_scene_path
from fivehub.publish import FilePublishRequest, publish_files, publish_usd
from fivehub.report import Severity, Status, ValidationReport
from fivehub.thumbs import write_placeholder_png
from fivehub.validation import validate, validate_files


def usd_request(tmp, name="TestCrate", **overrides):
    thumbnail = os.path.join(tmp, "thumb.png")
    if not os.path.exists(thumbnail):
        write_placeholder_png(thumbnail)
    fields = {
        "asset_name": name,
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
        report = validate(usd_request(self.tmp.name))
        self.assertTrue(report.passed, report.to_text())
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)

    def test_unwelded_fails(self):
        report = validate(usd_request(self.tmp.name, meshes=[cube_mesh(welded=False)]))
        self.assertFalse(report.passed)
        result = self.rule(report, "geo.unwelded")
        self.assertEqual(result.status, Status.FAIL)
        self.assertEqual(result.severity, Severity.ERROR)

    def test_missing_material_fails(self):
        mesh = cube_mesh()
        mesh.face_materials = None
        report = validate(usd_request(self.tmp.name, meshes=[mesh], materials={}))
        self.assertFalse(report.passed)
        self.assertEqual(self.rule(report, "mtl.missing").status, Status.FAIL)

    def test_unknown_material_fails(self):
        report = validate(usd_request(self.tmp.name, materials={}))
        self.assertFalse(report.passed)
        self.assertEqual(self.rule(report, "mtl.unknown").status, Status.FAIL)

    def test_bad_name_fails_and_style_warns(self):
        report = validate(usd_request(self.tmp.name, name="my crate"))
        self.assertFalse(report.passed)
        self.assertEqual(self.rule(report, "naming.asset").status, Status.FAIL)

        report = validate(usd_request(self.tmp.name, name="my_crate"))
        style = self.rule(report, "naming.style")
        self.assertEqual(style.status, Status.FAIL)
        self.assertEqual(style.severity, Severity.WARNING)
        self.assertTrue(report.passed)  # warnings alone do not block

    def test_scale_warnings(self):
        report = validate(usd_request(self.tmp.name, meshes=[cube_mesh(size=500.0)]))
        big = self.rule(report, "scale.size")
        self.assertEqual(big.status, Status.FAIL)
        self.assertEqual(big.severity, Severity.WARNING)
        self.assertTrue(report.passed)

    def test_severity_override(self):
        request = usd_request(self.tmp.name, meshes=[cube_mesh(welded=False)])
        report = validate(request, {"geo.unwelded": {"severity": Severity.WARNING}})
        self.assertTrue(report.passed)
        self.assertEqual(self.rule(report, "geo.unwelded").severity, Severity.WARNING)

    def test_file_rules(self):
        cache = os.path.join(self.tmp.name, "cache.vdb")
        with open(cache, "wb") as handle:
            handle.write(b"data")
        request = FilePublishRequest(asset_name="Smoke", format="vdb", files=[cache])
        report = validate_files(request)
        self.assertTrue(report.passed, report.to_text())

        # Missing file blocks; wrong extension only warns.
        request = FilePublishRequest(
            asset_name="Smoke", format="vdb", files=[cache + ".missing"]
        )
        self.assertFalse(validate_files(request).passed)

        wrong = os.path.join(self.tmp.name, "cache.obj")
        with open(wrong, "wb") as handle:
            handle.write(b"data")
        request = FilePublishRequest(asset_name="Smoke", format="vdb", files=[wrong])
        report = validate_files(request)
        self.assertTrue(report.passed)
        self.assertEqual(self.rule(report, "files.format").status, Status.FAIL)

    def test_report_roundtrip(self):
        report = validate(usd_request(self.tmp.name))
        path = os.path.join(self.tmp.name, "report.json")
        report.save(path)
        loaded = ValidationReport.load(path)
        self.assertEqual(loaded.to_dict(), report.to_dict())
        self.assertIn("VALIDATION PASSED", loaded.to_text())


class UserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = {
            key: os.environ.get(key) for key in (user.ENV_USER, user.ENV_USER_FILE)
        }
        os.environ.pop(user.ENV_USER, None)
        os.environ[user.ENV_USER_FILE] = os.path.join(self.tmp.name, "user.json")

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_login_roundtrip(self):
        self.assertFalse(user.logged_in())
        self.assertTrue(user.get_user())  # OS fallback still gives a name
        user.set_user("  Chan  ")
        self.assertTrue(user.logged_in())
        self.assertEqual(user.get_user(), "Chan")
        with self.assertRaises(ValueError):
            user.set_user("   ")

    def test_env_wins(self):
        user.set_user("Chan")
        os.environ[user.ENV_USER] = "Override"
        self.assertEqual(user.get_user(), "Override")

    def test_publish_is_signed_with_login(self):
        user.set_user("Signer")
        hub = os.path.join(self.tmp.name, "hub")
        project = create_project("Signed", hub_root=hub)
        project.create_entity("asset", "Crate")
        project.create_task("asset", "Crate", "modeling")
        result = publish_usd(
            project, "asset", "Crate", "modeling", usd_request(self.tmp.name, name="Crate")
        )
        self.assertTrue(result.passed)
        self.assertEqual(
            project.publishes("asset", "Crate", "modeling")[0]["user"], "Signer"
        )
        # The signature travels with the report itself (who + when).
        self.assertEqual(result.report.user, "Signer")
        self.assertIn("by Signer", result.report.to_text())
        self.assertEqual(
            ValidationReport.load(result.report_path).user, "Signer"
        )

        # Scene saves are signed the same way when no user is given.
        project.register_scene("asset", "Crate", "modeling")
        self.assertEqual(project.scenes("asset", "Crate", "modeling")[0]["user"], "Signer")


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_project_layout(self):
        project = create_project("Alpha", hub_root=self.hub)
        for expected in (
            config.PROJECT_FILE,
            config.PROJECT_DB,
            "image.png",
        ):
            self.assertTrue(os.path.isfile(os.path.join(project.root, expected)), expected)
        for directory in (config.ASSETS_DIR, config.SHOTS_DIR, config.PROJECT_REPORTS_DIR):
            self.assertTrue(os.path.isdir(os.path.join(project.root, directory)))
        self.assertEqual(project.meta()["name"], "Alpha")

        listed = list_projects(self.hub)
        self.assertEqual([p["name"] for p in listed], ["Alpha"])
        self.assertTrue(os.path.isfile(listed[0]["image_path"]))

    def test_create_project_with_image(self):
        image = os.path.join(self.tmp.name, "poster.png")
        write_placeholder_png(image)
        project = create_project("Beta", image=image, hub_root=self.hub)
        self.assertTrue(project.image_path().endswith("image.png"))
        self.assertTrue(os.path.isfile(project.image_path()))

    def test_project_name_rules(self):
        with self.assertRaises(ValueError):
            create_project("bad name", hub_root=self.hub)
        create_project("Gamma", hub_root=self.hub)
        with self.assertRaises(ValueError):
            create_project("Gamma", hub_root=self.hub)

    def test_external_location_and_registry(self):
        shared = os.path.join(self.tmp.name, "shared_drive")
        os.makedirs(shared)
        project = create_project("Orbital", hub_root=self.hub, location=shared)
        self.assertEqual(project.root, os.path.join(shared, "Orbital"))
        self.assertTrue(os.path.isfile(os.path.join(self.hub, config.REGISTRY_FILE)))

        # Resolvable and listed alongside hub-local projects.
        self.assertEqual(get_project("Orbital", self.hub).root, project.root)
        create_project("Local", hub_root=self.hub)
        listed = {p["name"]: p for p in list_projects(self.hub)}
        self.assertEqual(set(listed), {"Local", "Orbital"})
        self.assertTrue(listed["Orbital"]["external"])
        self.assertFalse(listed["Local"]["external"])

        # Same-name collisions and bad locations are rejected.
        with self.assertRaises(ValueError):
            create_project("Orbital", hub_root=self.hub)
        with self.assertRaises(ValueError):
            create_project("Elsewhere", hub_root=self.hub, location="/does/not/exist")

        # Scene context parses from the external root too.
        project.create_entity("asset", "Ship")
        project.create_task("asset", "Ship", "modeling")
        path, _version = project.register_scene("asset", "Ship", "modeling")
        context = parse_scene_path(path, self.hub)
        self.assertEqual(context["project"], "Orbital")
        self.assertEqual(context["entity"], "Ship")

    def test_entities_and_tasks(self):
        project = create_project("Delta", hub_root=self.hub)
        project.create_entity("asset", "Crate")
        project.create_task("asset", "Crate", "Modeling")  # lowered on creation
        self.assertEqual([t["name"] for t in project.tasks("asset", "Crate")], ["modeling"])
        self.assertTrue(os.path.isdir(project.scenes_dir("asset", "Crate", "modeling")))

        with self.assertRaises(ValueError):
            project.create_entity("asset", "Crate")  # duplicate
        with self.assertRaises(ValueError):
            project.create_entity("asset", "bad name")
        with self.assertRaises(ValueError):
            project.create_task("asset", "Nope", "modeling")  # unknown entity
        with self.assertRaises(ValueError):
            project.create_task("asset", "Crate", "bad task")

    def test_scene_versioning_with_claims(self):
        project = create_project("Epsilon", hub_root=self.hub)
        project.create_entity("shot", "SH010")
        project.create_task("shot", "SH010", "fx")

        # Claim -> the version is reserved before any file exists; a second
        # claim can never get the same number (the multi-user guarantee).
        path, version = project.claim_scene("shot", "SH010", "fx", "ana")
        self.assertEqual(version, 1)
        self.assertTrue(path.endswith("SH010_fx_v001.hip"))
        path2, version2 = project.claim_scene("shot", "SH010", "fx", "five")
        self.assertEqual(version2, 2)

        # Pending claims are invisible until completed.
        self.assertEqual(project.scenes("shot", "SH010", "fx"), [])

        with self.assertRaises(ValueError):
            project.complete_scene("shot", "SH010", "fx", version)  # not written

        with open(path, "w") as handle:
            handle.write("hip")
        project.complete_scene("shot", "SH010", "fx", version, "first pass", "ana")
        project.release_scene("shot", "SH010", "fx", version2)  # save cancelled

        scenes = project.scenes("shot", "SH010", "fx")
        self.assertEqual([s["version"] for s in scenes], [1])
        self.assertEqual(scenes[0]["notes"], "first pass")
        # The released number is reused by the next claim.
        _, version3 = project.claim_scene("shot", "SH010", "fx")
        self.assertEqual(version3, 2)
        project.release_scene("shot", "SH010", "fx", version3)

        context = parse_scene_path(path, self.hub)
        self.assertEqual(
            context,
            {
                "project": "Epsilon",
                "kind": "shot",
                "entity": "SH010",
                "task": "fx",
                "file": "SH010_fx_v001.hip",
            },
        )
        self.assertIsNone(parse_scene_path("/somewhere/else.hip", self.hub))
        self.assertIsNone(parse_scene_path("", self.hub))

    def test_paths_stored_relative(self):
        import sqlite3

        project = create_project("Rel", hub_root=self.hub)
        project.create_entity("asset", "Crate")
        project.create_task("asset", "Crate", "modeling")
        path, _version = project.register_scene("asset", "Crate", "modeling", "n")
        self.assertTrue(os.path.isabs(path))

        with sqlite3.connect(os.path.join(project.root, config.PROJECT_DB)) as conn:
            stored = conn.execute("SELECT file FROM scene").fetchone()[0]
        self.assertFalse(os.path.isabs(stored))
        self.assertNotIn("\\", stored)
        # And the boundary translates back to absolute.
        self.assertEqual(project.scenes("asset", "Crate", "modeling")[0]["file"], path)

    def test_shot_metadata_defaults_and_update(self):
        project = create_project("Meta", hub_root=self.hub)
        project.create_entity("shot", "SH020", sequence="SEQ010")
        shot = project.db.get_entity("shot", "SH020")
        self.assertEqual(shot["sequence"], "SEQ010")
        self.assertEqual(shot["frame_start"], 1001)  # project defaults applied
        self.assertEqual(shot["fps"], 24.0)
        self.assertEqual(shot["res_x"], 1920)

        project.update_entity("shot", "SH020", frame_start=1001, frame_end=1250)
        self.assertEqual(project.db.get_entity("shot", "SH020")["frame_end"], 1250)

        # Assets carry no forced frame data.
        project.create_entity("asset", "Crate")
        self.assertIsNone(project.db.get_entity("asset", "Crate")["frame_start"])


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")
        self.project = create_project("Pub", hub_root=self.hub)
        self.project.create_entity("asset", "TestCrate")
        self.project.create_task("asset", "TestCrate", "modeling")

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, *parts):
        with open(os.path.join(*parts), "r", encoding="utf-8") as handle:
            return handle.read()

    def test_publish_usd_component_structure(self):
        result = publish_usd(
            self.project, "asset", "TestCrate", "modeling", usd_request(self.tmp.name)
        )
        self.assertTrue(result.passed, result.report.to_text())
        self.assertEqual(result.version, 1)
        self.assertIn(
            os.path.join("assets", "TestCrate", "modeling", "publish", "usd", "v001"),
            result.publish_dir,
        )

        for filename in (
            "TestCrate.usda",
            "TestCrate.payload.usda",
            "TestCrate.geo.usda",
            "TestCrate.mtl.usda",
            "report.json",
            os.path.join("thumbnails", "TestCrate.png"),
        ):
            self.assertTrue(
                os.path.isfile(os.path.join(result.publish_dir, filename)), filename
            )

        entry = self.read(result.publish_dir, "TestCrate.usda")
        self.assertIn('kind = "component"', entry)
        self.assertIn('variantSet "geo"', entry)
        self.assertIn("payload = @./TestCrate.payload.usda@</TestCrate>", entry)
        self.assertIn(
            "previews:thumbnails:default:defaultImage = @./thumbnails/TestCrate.png@",
            entry,
        )
        self.assertIn("extentsHint", entry)
        self.assertIn("Pub / asset TestCrate / modeling", entry)

        mtl = self.read(result.publish_dir, "TestCrate.mtl.usda")
        self.assertIn("UsdPreviewSurface", mtl)
        self.assertIn("rel material:binding = </TestCrate/mtl/M_DemoWood>", mtl)

        publishes = self.project.publishes("asset", "TestCrate", "modeling")
        self.assertEqual(len(publishes), 1)
        self.assertEqual(publishes[0]["format"], "usd")
        self.assertEqual(publishes[0]["version"], 1)
        self.assertEqual(publishes[0]["passed"], 1)

    def test_variant_publish_composes_across_versions(self):
        publish_usd(
            self.project, "asset", "TestCrate", "modeling", usd_request(self.tmp.name)
        )
        result = publish_usd(
            self.project, "asset", "TestCrate", "modeling",
            usd_request(self.tmp.name, variant="damaged"),
        )
        self.assertEqual(result.version, 2)

        entry = self.read(result.publish_dir, "TestCrate.usda")
        self.assertIn('"damaged" (', entry)
        self.assertIn("payload = @./TestCrate.payload.usda@</TestCrate>", entry)
        self.assertIn("payload = @../v001/TestCrate.payload.usda@</TestCrate>", entry)
        self.assertIn('string geo = "default"', entry)

        root_layer = self.read(result.root_layer)
        self.assertIn("payload = @./v001/TestCrate.payload.usda@</TestCrate>", root_layer)
        self.assertIn("payload = @./v002/TestCrate.payload.usda@</TestCrate>", root_layer)

    def test_blocked_publish_writes_nothing_to_task(self):
        result = publish_usd(
            self.project, "asset", "TestCrate", "modeling",
            usd_request(self.tmp.name, meshes=[cube_mesh(welded=False)]),
        )
        self.assertFalse(result.passed)
        self.assertIsNone(result.version)
        self.assertFalse(
            os.path.exists(
                self.project.publish_dir("asset", "TestCrate", "modeling", "usd")
            )
        )
        self.assertTrue(result.report_path.startswith(self.project.reports_dir()))

        publishes = self.project.publishes("asset", "TestCrate", "modeling")
        self.assertEqual(len(publishes), 1)
        self.assertEqual(publishes[0]["passed"], 0)
        self.assertIsNone(publishes[0]["version"])

    def test_publish_files(self):
        cache = os.path.join(self.tmp.name, "smoke.vdb")
        with open(cache, "wb") as handle:
            handle.write(b"volume data")
        result = publish_files(
            self.project, "asset", "TestCrate", "modeling",
            FilePublishRequest(asset_name="TestCrate", format="vdb", files=[cache]),
        )
        self.assertTrue(result.passed, result.report.to_text())
        self.assertEqual(result.version, 1)
        self.assertTrue(os.path.isfile(os.path.join(result.publish_dir, "smoke.vdb")))
        self.assertTrue(os.path.isfile(os.path.join(result.publish_dir, "report.json")))

        # USD and vdb version counters are independent.
        usd = publish_usd(
            self.project, "asset", "TestCrate", "modeling", usd_request(self.tmp.name)
        )
        self.assertEqual(usd.version, 1)

    def test_publish_files_blocked_on_missing_file(self):
        result = publish_files(
            self.project, "asset", "TestCrate", "modeling",
            FilePublishRequest(asset_name="TestCrate", format="vdb", files=["/nope.vdb"]),
        )
        self.assertFalse(result.passed)
        self.assertIsNone(result.version)


class EditDeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")
        self.project = create_project("Ops", hub_root=self.hub)
        self.project.create_entity("asset", "Crate")
        self.project.create_task("asset", "Crate", "modeling")

    def tearDown(self):
        self.tmp.cleanup()

    def _scene(self, notes=""):
        return self.project.register_scene("asset", "Crate", "modeling", notes)

    def test_scene_edit_and_delete(self):
        path, version = self._scene("first")
        self.project.set_scene_notes("asset", "Crate", "modeling", version, "better notes")
        self.assertEqual(
            self.project.scenes("asset", "Crate", "modeling")[0]["notes"], "better notes"
        )
        self.project.delete_scene("asset", "Crate", "modeling", version)
        self.assertFalse(os.path.exists(path))
        self.assertEqual(self.project.scenes("asset", "Crate", "modeling"), [])
        with self.assertRaises(ValueError):
            self.project.delete_scene("asset", "Crate", "modeling", version)
        # Soft: the file went to the trash, not into the void, and the
        # version number is never reused.
        self.assertTrue(os.listdir(self.project.trash_dir()))
        _, next_version = self._scene("after delete")
        self.assertEqual(next_version, version + 1)

    def test_publish_delete_rebuilds_usd_root(self):
        publish_usd(self.project, "asset", "Crate", "modeling",
                    usd_request(self.tmp.name, name="Crate"))
        publish_usd(self.project, "asset", "Crate", "modeling",
                    usd_request(self.tmp.name, name="Crate", variant="damaged"))
        publish_root = self.project.publish_dir("asset", "Crate", "modeling", "usd")
        root_layer = os.path.join(publish_root, "Crate.usda")

        self.project.set_publish_comment("asset", "Crate", "modeling", "usd", 2, "edited")
        publishes = self.project.publishes("asset", "Crate", "modeling")
        self.assertEqual(publishes[0]["comment"], "edited")

        self.project.delete_publish("asset", "Crate", "modeling", "usd", 2)
        self.assertFalse(os.path.exists(os.path.join(publish_root, "v002")))
        with open(root_layer) as handle:
            content = handle.read()
        self.assertIn("@./v001/Crate.payload.usda@", content)
        self.assertNotIn("v002", content)

        self.project.delete_publish("asset", "Crate", "modeling", "usd", 1)
        self.assertFalse(os.path.exists(root_layer))

    def test_task_and_entity_delete(self):
        self._scene()
        task_dir = self.project.task_dir("asset", "Crate", "modeling")
        self.project.delete_task("asset", "Crate", "modeling")
        self.assertFalse(os.path.exists(task_dir))
        self.assertEqual(self.project.tasks("asset", "Crate"), [])

        entity_dir = self.project.entity_dir("asset", "Crate")
        self.project.delete_entity("asset", "Crate")
        self.assertFalse(os.path.exists(entity_dir))
        self.assertIsNone(self.project.db.get_entity("asset", "Crate"))

    def test_remove_project(self):
        from fivehub.project import remove_project

        shared = os.path.join(self.tmp.name, "shared")
        os.makedirs(shared)
        external = create_project("Linked", hub_root=self.hub, location=shared)
        result = remove_project("Linked", self.hub)
        self.assertTrue(result["external"])
        self.assertFalse(result["deleted_files"])
        self.assertTrue(os.path.isdir(external.root))  # files kept
        self.assertNotIn("Linked", [p["name"] for p in list_projects(self.hub)])

        local_root = self.project.root
        result = remove_project("Ops", self.hub)
        self.assertTrue(result["deleted_files"])  # local removal deletes files
        self.assertFalse(os.path.exists(local_root))
        with self.assertRaises(ValueError):
            remove_project("Ops", self.hub)


class IngestRefsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")
        self.project = create_project("Ing", hub_root=self.hub)
        self.project.create_entity("asset", "Kit")
        self.project.create_task("asset", "Kit", "modeling")

    def tearDown(self):
        self.tmp.cleanup()

    def _file(self, name, content=b"data"):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def test_ingest_external_files(self):
        from fivehub.ingest import infer_format, ingest_files

        self.assertEqual(infer_format("model.FBX"), "fbx")
        self.assertEqual(infer_format("cache.bgeo.sc"), "bgeo")
        self.assertEqual(infer_format("map.exr"), "tex")
        self.assertIsNone(infer_format("weird.xyz"))

        fbx = self._file("vendor.fbx")
        result = ingest_files(
            self.project, "asset", "Kit", "modeling", [fbx], comment="from vendor"
        )
        self.assertTrue(result.passed, result.report.to_text())
        self.assertEqual(result.format, "fbx")
        self.assertEqual(result.version, 1)
        self.assertTrue(os.path.isfile(os.path.join(result.publish_dir, "vendor.fbx")))
        row = self.project.publishes("asset", "Kit", "modeling")[0]
        self.assertEqual(row["format"], "fbx")

        with self.assertRaises(ValueError):
            ingest_files(
                self.project, "asset", "Kit", "modeling",
                [self._file("a.fbx"), self._file("b.abc")],  # mixed
            )
        with self.assertRaises(ValueError):
            ingest_files(self.project, "asset", "Kit", "modeling",
                         [self._file("weird.xyz")])

    def test_refs_gallery(self):
        from fivehub.ingest import add_refs, delete_ref, list_refs

        board = self._file("board.png")
        brief = self._file("brief.pdf")
        add_refs(self.project, [board, brief])
        add_refs(self.project, [board])  # same name -> suffixed, not clobbered
        refs = list_refs(self.project)
        names = sorted(ref["name"] for ref in refs)
        self.assertEqual(names, ["board.png", "board_2.png", "brief.pdf"])
        self.assertTrue(next(r for r in refs if r["name"] == "board.png")["is_image"])

        delete_ref(self.project, "board_2.png")
        self.assertEqual(len(list_refs(self.project)), 2)
        with self.assertRaises(ValueError):
            delete_ref(self.project, "nope.png")


class TextureUvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")
        self.project = create_project("Look", hub_root=self.hub)
        self.project.create_entity("asset", "Crate")
        self.project.create_task("asset", "Crate", "lookdev")

    def tearDown(self):
        self.tmp.cleanup()

    def test_uvs_and_textures_published(self):
        mesh = cube_mesh()
        mesh.uvs = [(0.0, 0.0)] * len(mesh.face_vertex_indices)
        diffuse = write_placeholder_png(os.path.join(self.tmp.name, "wood_diff.png"))
        rough = write_placeholder_png(os.path.join(self.tmp.name, "wood_rough.png"))
        material = MaterialData(
            "M_DemoWood", textures={"diffuse": diffuse, "roughness": rough}
        )
        request = usd_request(
            self.tmp.name, name="Crate", meshes=[mesh],
            materials={"M_DemoWood": material},
        )
        result = publish_usd(self.project, "asset", "Crate", "lookdev", request)
        self.assertTrue(result.passed, result.report.to_text())

        with open(os.path.join(result.publish_dir, "Crate.geo.usda")) as handle:
            geo = handle.read()
        self.assertIn("texCoord2f[] primvars:st", geo)
        self.assertIn('interpolation = "faceVarying"', geo)

        with open(os.path.join(result.publish_dir, "Crate.mtl.usda")) as handle:
            mtl = handle.read()
        self.assertIn('info:id = "UsdUVTexture"', mtl)
        self.assertIn('info:id = "UsdPrimvarReader_float2"', mtl)
        self.assertIn("inputs:file = @./textures/wood_diff.png@", mtl)
        self.assertIn("inputs:diffuseColor.connect", mtl)
        self.assertIn("inputs:roughness.connect", mtl)
        self.assertTrue(
            os.path.isfile(os.path.join(result.publish_dir, "textures", "wood_diff.png"))
        )

    def test_missing_texture_blocks(self):
        material = MaterialData("M_DemoWood", textures={"diffuse": "/missing/tex.png"})
        request = usd_request(
            self.tmp.name, name="Crate", materials={"M_DemoWood": material}
        )
        result = publish_usd(self.project, "asset", "Crate", "lookdev", request)
        self.assertFalse(result.passed)
        failed = [r.rule_id for r in result.report.results
                  if r.status == Status.FAIL and r.severity == Severity.ERROR]
        self.assertIn("mtl.textures", failed)


class AnimationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")
        self.project = create_project("Anim", hub_root=self.hub)
        self.project.create_entity("shot", "SH010")
        self.project.create_task("shot", "SH010", "animation")

    def tearDown(self):
        self.tmp.cleanup()

    def test_time_sampled_usd(self):
        mesh = cube_mesh(name="crate")
        mesh.point_samples = {
            1001.0: list(mesh.points),
            1002.0: [(x, y + 0.1, z) for x, y, z in mesh.points],
        }
        request = usd_request(
            self.tmp.name, name="SH010", meshes=[mesh],
            frame_start=1001, frame_end=1002, fps=24.0,
        )
        result = publish_usd(self.project, "shot", "SH010", "animation", request)
        self.assertTrue(result.passed, result.report.to_text())
        with open(os.path.join(result.publish_dir, "SH010.geo.usda")) as handle:
            geo = handle.read()
        self.assertIn("startTimeCode = 1001", geo)
        self.assertIn("endTimeCode = 1002", geo)
        self.assertIn("points.timeSamples", geo)
        self.assertIn("1002:", geo)

    def test_changing_topology_blocks(self):
        mesh = cube_mesh(name="crate")
        mesh.point_samples = {1001.0: list(mesh.points), 1002.0: mesh.points[:-1]}
        request = usd_request(self.tmp.name, name="SH010", meshes=[mesh])
        result = publish_usd(self.project, "shot", "SH010", "animation", request)
        self.assertFalse(result.passed)
        failed = [r.rule_id for r in result.report.results if r.status == Status.FAIL]
        self.assertIn("anim.topology", failed)


class JobsRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")
        self.project = create_project("Rend", hub_root=self.hub)
        self.project.create_entity("shot", "SH010", frame_start=1001, frame_end=1002)
        self.project.create_task("shot", "SH010", "lighting")
        self._env = {
            key: os.environ.pop(key, None)
            for key in ("FIVEHUB_HYTHON", "FIVEHUB_HOUDINI")
        }

    def tearDown(self):
        for key, value in self._env.items():
            if value is not None:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_submit_claim_and_worker_without_hython(self):
        from fivehub.render import submit_render
        from fivehub.worker import run_once

        with self.assertRaises(ValueError):
            submit_render(self.project, "shot", "SH010", "lighting", 1, "/out/karma1")

        self.project.register_scene("shot", "SH010", "lighting", "for render")
        submitted = submit_render(
            self.project, "shot", "SH010", "lighting", 1, "/out/karma1"
        )
        self.assertEqual(submitted["frame_start"], 1001)  # shot metadata drives it
        self.assertEqual(submitted["frame_end"], 1002)

        jobs = self.project.db.list_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["status"], "queued")

        # A worker without hython fails the job cleanly and says why.
        executed = run_once(self.hub, "Rend", log=lambda *_a: None)
        self.assertEqual(executed, 1)
        job = self.project.db.list_jobs()[0]
        self.assertEqual(job["status"], "failed")
        self.assertIn("hython not found", job["log"])
        # The failed render released its claim — no publish row remains.
        self.assertEqual(self.project.publishes("shot", "SH010", "lighting"), [])

    def test_cancel_queued_job(self):
        job_id = self.project.db.enqueue_job("render", {"x": 1}, user="ana")
        self.project.db.cancel_job(job_id)
        self.assertEqual(self.project.db.list_jobs()[0]["status"], "cancelled")
        claimed = self.project.db.claim_job("worker-1")
        self.assertIsNone(claimed)  # cancelled jobs are never claimed


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")
        self.project = create_project("Asm", hub_root=self.hub)
        self.project.create_entity("asset", "Crate")
        self.project.create_task("asset", "Crate", "modeling")
        self.project.create_entity("shot", "SH010")
        self.project.create_task("shot", "SH010", "layout")

    def tearDown(self):
        self.tmp.cleanup()

    def test_assembly_from_tracked_dependencies(self):
        from fivehub.assembly import publish_assembly

        with self.assertRaises(ValueError):
            publish_assembly(self.project, "SH010", "layout")

        publish_usd(self.project, "asset", "Crate", "modeling",
                    usd_request(self.tmp.name, name="Crate"))
        consumer = self.project._task_record("shot", "SH010", "layout")
        producer = self.project._task_record("asset", "Crate", "modeling")
        self.project.db.record_dependency(
            consumer["id"], producer["id"], "usd", "Crate", None, "ana"
        )

        result = publish_assembly(self.project, "SH010", "layout", comment="first")
        self.assertEqual(result["references"], 1)
        with open(result["layer"]) as handle:
            layer = handle.read()
        self.assertIn('kind = "assembly"', layer)
        self.assertIn("Crate.usda@", layer)  # references the root interface

        # It registers as a usd publish on the layout task.
        rows = self.project.publishes("shot", "SH010", "layout")
        self.assertEqual(rows[0]["name"], "SH010_assembly")

        # Dependency queries see both directions, with latest-version info.
        uses = self.project.db.dependencies_of(consumer["id"])
        self.assertEqual(uses[0]["latest_version"], 1)
        self.assertEqual(
            self.project.db.used_by(producer["id"])[0]["consumer_entity"], "SH010"
        )


class PresenceTrashBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")
        self.project = create_project("Ops2", hub_root=self.hub)
        self.project.create_entity("asset", "Crate")
        self.project.create_task("asset", "Crate", "modeling")

    def tearDown(self):
        self.tmp.cleanup()

    def test_presence(self):
        self.project.touch_presence("asset", "Crate", "modeling", "ana", 3, "ws-01")
        rows = self.project.task_presence("asset", "Crate", "modeling")
        self.assertEqual(rows[0]["user"], "ana")
        self.assertEqual(rows[0]["scene_version"], 3)
        self.project.db.clear_presence("ana")
        self.assertEqual(self.project.task_presence("asset", "Crate", "modeling"), [])

    def test_trash_empty(self):
        path, version = self.project.register_scene("asset", "Crate", "modeling")
        self.project.delete_scene("asset", "Crate", "modeling", version)
        self.assertTrue(os.listdir(self.project.trash_dir()))
        purged = self.project.empty_trash()
        self.assertTrue(purged)
        self.assertFalse(os.listdir(self.project.trash_dir()))

    def test_backup_via_cli(self):
        env = dict(os.environ)
        env[user.ENV_USER_FILE] = os.path.join(self.tmp.name, "user.json")
        completed = subprocess.run(
            [sys.executable, "-m", "fivehub.cli", "--hub", self.hub, "backup"],
            cwd=REPO, capture_output=True, text=True, env=env,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(
            any(path.endswith("Ops2.db") for path in payload["files"])
        )
        for path in payload["files"]:
            self.assertTrue(os.path.isfile(path))


class RecordsGitTests(unittest.TestCase):
    """The three deployment modes: the DB is a cache of record sidecars."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")
        self.project = create_project("Sync", hub_root=self.hub)
        self.project.create_entity("asset", "Crate", )
        self.project.create_task("asset", "Crate", "modeling")

    def tearDown(self):
        self.tmp.cleanup()

    def test_sidecars_written_and_db_rebuilds(self):
        from fivehub.project import Project

        self.project.register_scene("asset", "Crate", "modeling", "v1 notes", "ana")
        publish_usd(self.project, "asset", "Crate", "modeling",
                    usd_request(self.tmp.name, name="Crate"))

        records = self.project.records_dir()
        for table in ("entity", "task", "scene", "publish"):
            self.assertTrue(os.listdir(os.path.join(records, table)), table)

        # Kill the database — a fresh Project rebuilds it from the records
        # (this is exactly what a git clone without project.db looks like).
        os.remove(os.path.join(self.project.root, config.PROJECT_DB))
        rebuilt = Project(self.project.root)
        scenes = rebuilt.scenes("asset", "Crate", "modeling")
        self.assertEqual(scenes[0]["notes"], "v1 notes")
        self.assertTrue(os.path.isabs(scenes[0]["file"]))
        publishes = rebuilt.publishes("asset", "Crate", "modeling")
        self.assertEqual(publishes[0]["format"], "usd")
        self.assertEqual(publishes[0]["version"], 1)

    def test_deletion_propagates_through_records(self):
        from fivehub.project import Project

        _path, version = self.project.register_scene("asset", "Crate", "modeling")
        self.project.delete_scene("asset", "Crate", "modeling", version)
        os.remove(os.path.join(self.project.root, config.PROJECT_DB))
        rebuilt = Project(self.project.root)
        self.assertEqual(rebuilt.scenes("asset", "Crate", "modeling"), [])

    def test_pulled_records_appear_without_rebuild(self):
        # Simulate a teammate's pulled sidecar: write a foreign scene record
        # directly, then access through a new Project instance.
        from fivehub.project import Project

        task_id = self.project._task_record("asset", "Crate", "modeling")["id"]
        foreign = {
            "table": "scene",
            "row": {
                "id": "aaaaaaaa-0000-0000-0000-000000000001",
                "task_id": task_id, "version": 7,
                "file": "assets/Crate/modeling/scenes/Crate_modeling_v007.hip",
                "notes": "from teammate", "user": "remote", "status": "complete",
                "deleted_at": "", "created_at": "2026-07-23T10:00:00Z",
            },
        }
        table_dir = os.path.join(self.project.records_dir(), "scene")
        os.makedirs(table_dir, exist_ok=True)
        with open(os.path.join(table_dir, "%s.json" % foreign["row"]["id"]), "w") as f:
            json.dump(foreign, f)

        fresh = Project(self.project.root)
        scenes = fresh.scenes("asset", "Crate", "modeling")
        self.assertIn(7, [s["version"] for s in scenes])
        # The next claim respects the pulled version.
        _path, version = fresh.claim_scene("asset", "Crate", "modeling")
        self.assertEqual(version, 8)
        fresh.release_scene("asset", "Crate", "modeling", version)

    def test_offline_version_collision_is_reported(self):
        from fivehub.project import Project

        _path, version = self.project.register_scene("asset", "Crate", "modeling")
        task_id = self.project._task_record("asset", "Crate", "modeling")["id"]
        clash = {
            "table": "scene",
            "row": {
                "id": "bbbbbbbb-0000-0000-0000-000000000002",
                "task_id": task_id, "version": version,  # same slot, other id
                "file": "assets/Crate/modeling/scenes/other.hip",
                "notes": "", "user": "remote", "status": "complete",
                "deleted_at": "", "created_at": "2026-07-23T10:00:00Z",
            },
        }
        table_dir = os.path.join(self.project.records_dir(), "scene")
        with open(os.path.join(table_dir, "%s.json" % clash["row"]["id"]), "w") as f:
            json.dump(clash, f)
        result = Project(self.project.root).sync_from_records()
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertIn("version slot", result["conflicts"][0]["reason"])

    def test_gitignore_written_at_creation(self):
        gitignore = os.path.join(self.project.root, ".gitignore")
        self.assertTrue(os.path.isfile(gitignore))
        with open(gitignore) as handle:
            content = handle.read()
        self.assertIn("project.db", content)
        self.assertIn("caches/", content)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_git_setup_autocommit_and_status(self):
        from fivehub import gitsync

        env_backup = {k: os.environ.get(k) for k in
                      ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                       "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")}
        os.environ.update({
            "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.t",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.t",
        })
        try:
            self.assertFalse(gitsync.is_git_project(self.project.root))
            setup = gitsync.setup(self.project.root, user="Ana")
            self.assertTrue(setup["initialized"])
            self.assertTrue(gitsync.is_git_project(self.project.root))

            status = gitsync.status(self.project.root)
            self.assertTrue(status["git"])
            self.assertEqual(status["dirty"], 0)

            # A publish auto-commits (project.db itself is gitignored).
            publish_usd(self.project, "asset", "Crate", "modeling",
                        usd_request(self.tmp.name, name="Crate"))
            self.assertEqual(gitsync.status(self.project.root)["dirty"], 0)
            ok, log = gitsync._run(self.project.root, "log", "--oneline")
            self.assertTrue(ok)
            self.assertIn("publish usd v001", log)

            # sync without a remote degrades to commit-only.
            result = gitsync.sync(self.project.root, user="Ana")
            self.assertTrue(result["ok"])
            self.assertEqual(result["steps"][1]["detail"], "no remote configured")
        finally:
            for key, value in env_backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class ToolsRegistryTests(unittest.TestCase):
    """Drop-in tools: one module plugs into CLI, validation and the worker."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")
        self.project = create_project("Tools", hub_root=self.hub)
        self.project.create_entity("shot", "SH010")
        self.project.create_task("shot", "SH010", "fx")

    def tearDown(self):
        self.tmp.cleanup()

    def test_registry_discovers_bundled_tools(self):
        from fivehub import tools

        registry = tools.load_tools()
        names = [entry["name"] for entry in registry["cli"]]
        self.assertIn("cache-path", names)
        self.assertIn("splash", names)
        labels = [entry["label"] for entry in registry["houdini"]]
        self.assertIn("Create Pipeline File Cache", labels)
        self.assertIn("Regenerate FiveHub Splash", labels)
        self.assertIs(tools.load_tools(), registry)  # loads once

    def test_splash_renders(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow not installed")
        from fivehub.tools.splash import render

        out = os.path.join(self.tmp.name, "splash.png")
        result = render(out, houdini_version="20.0.345", license_type="FX",
                        user="ana", width=300, height=169)
        self.assertEqual(result["size"], [300, 169])
        with open(out, "rb") as handle:
            self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")

    def test_cache_path_nomenclature_via_cli(self):
        env = dict(os.environ)
        env[user.ENV_USER_FILE] = os.path.join(self.tmp.name, "user.json")
        completed = subprocess.run(
            [sys.executable, "-m", "fivehub.cli", "--hub", self.hub,
             "cache-path", "Tools", "shot", "SH010", "fx", "smoke", "--version", "2"],
            cwd=REPO, capture_output=True, text=True, env=env,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(
            payload["dir"].endswith(os.path.join("fx", "caches", "smoke", "v002"))
        )
        self.assertTrue(payload["file"].endswith("SH010_fx_smoke_v002.$F4.bgeo.sc"))

    def test_dropin_validation_rule_joins_the_chain(self):
        from fivehub import tools
        from fivehub.report import Rule

        class NoTinyMeshRule(Rule):
            rule_id = "tools.test_rule"
            label = "Drop-in rule ran"
            severity = Severity.WARNING

            def check(self, request):
                return []

        tools.load_tools()
        tools.validation_rule(NoTinyMeshRule)
        try:
            report = validate(usd_request(self.tmp.name))
            self.assertIn("tools.test_rule", [r.rule_id for r in report.results])
        finally:
            tools.REGISTRY["rules"].remove(NoTinyMeshRule)

    def test_dropin_job_handler_runs_on_worker(self):
        from fivehub import tools
        from fivehub.worker import run_once

        tools.load_tools()

        @tools.job_handler("echo")
        def _echo(project, job):
            return "done", "echo says %s" % job["payload"].get("word", "")

        try:
            self.project.db.enqueue_job("echo", {"word": "hello"}, user="ana")
            executed = run_once(self.hub, "Tools", log=lambda *_a: None)
            self.assertEqual(executed, 1)
            job = self.project.db.list_jobs()[0]
            self.assertEqual(job["status"], "done")
            self.assertIn("echo says hello", job["log"])
        finally:
            tools.REGISTRY["jobs"].pop("echo", None)


class DemoTests(unittest.TestCase):
    def test_demo_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub = os.path.join(tmp, "hub")
            results = run_demo(hub)
            self.assertEqual([r["passed"] for r in results], [True, True, False, True])

            project = get_project("DemoProject", hub)
            self.assertEqual(
                project.db.counts(), {"assets": 2, "shots": 1, "publishes": 3}
            )
            history = project.db.publish_history()
            self.assertEqual(len(history), 4)
            # Running the demo twice keeps working (idempotent structure).
            run_demo(hub)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = os.path.join(self.tmp.name, "hub")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, expect_failure=False):
        env = dict(os.environ)
        env[user.ENV_USER_FILE] = os.path.join(self.tmp.name, "user.json")
        env.pop(user.ENV_USER, None)
        completed = subprocess.run(
            [sys.executable, "-m", "fivehub.cli", "--hub", self.hub, *args],
            cwd=REPO,
            capture_output=True,
            text=True,
            env=env,
        )
        if expect_failure:
            self.assertNotEqual(completed.returncode, 0)
            return completed.stderr
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_cli_contract(self):
        info = self.cli("root")
        self.assertEqual(info["root"], os.path.abspath(self.hub))
        self.assertEqual(info["default_format"], "usd")
        self.assertIn("modeling", info["default_tasks"])
        self.assertEqual(info["user"], "")  # nobody logged in yet

        self.assertEqual(self.cli("whoami")["user"], "")
        self.assertEqual(self.cli("login", "Chan")["user"], "Chan")
        self.assertEqual(self.cli("whoami")["user"], "Chan")
        self.assertEqual(self.cli("root")["user"], "Chan")

        image = os.path.join(self.tmp.name, "poster.png")
        write_placeholder_png(image)
        created = self.cli("project-create", "Mars", "--image", image)
        self.assertTrue(os.path.isfile(created["project"]["image_path"]))
        self.cli("project-create", "Mars", expect_failure=True)

        shared = os.path.join(self.tmp.name, "shared")
        os.makedirs(shared)
        external = self.cli("project-create", "Orbital", "--location", shared)
        self.assertTrue(external["project"]["root"].startswith(shared))

        self.cli("entity-create", "Mars", "asset", "Rover")
        self.cli("task-create", "Mars", "asset", "Rover", "modeling")
        self.cli("entity-create", "Mars", "asset", "bad name", expect_failure=True)

        tree = self.cli("browse", "Mars")["project"]
        self.assertEqual(tree["assets"][0]["name"], "Rover")
        self.assertEqual(tree["assets"][0]["tasks"][0]["name"], "modeling")

        self.cli("demo")
        projects = self.cli("projects")["projects"]
        self.assertEqual(
            [p["name"] for p in projects], ["DemoProject", "Mars", "Orbital"]
        )

        info = self.cli("task-info", "DemoProject", "asset", "DemoCrate", "modeling")
        self.assertEqual(len(info["publishes"]), 2)
        report_path = info["publishes"][0]["report_path"]
        report = self.cli("report", "--path", report_path)
        self.assertTrue(report["report"]["passed"])
        self.assertEqual(report["report"]["user"], "demo")  # signed publish

        log = self.cli("log", "DemoProject")["log"]
        self.assertEqual(len(log), 4)
        self.assertEqual(log[0]["format"], "vdb")

        activity = self.cli("activity", "DemoProject")
        self.assertEqual(len(activity["publishes"]), 4)
        self.assertEqual(activity["scenes"], [])
        self.cli("activity", "Nowhere", expect_failure=True)

        sent = self.cli("send", "DemoProject", "asset", "DemoCrate", "modeling")
        self.assertTrue(sent["selection"]["path"].endswith("DemoCrate.usda"))
        self.assertTrue(os.path.isfile(sent["path"]))

        sent = self.cli(
            "send", "DemoProject", "shot", "SH010", "fx", "--format", "vdb"
        )
        self.assertTrue(os.path.isdir(sent["selection"]["path"]))
        self.cli(
            "send", "DemoProject", "shot", "SH010", "layout", expect_failure=True
        )


class VersionBumpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bump_version", os.path.join(REPO, "scripts", "bump_version.py")
        )
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_thresholds(self):
        self.assertEqual(self.mod.classify(0), "patch")
        self.assertEqual(self.mod.classify(99), "patch")
        self.assertEqual(self.mod.classify(100), "minor")
        self.assertEqual(self.mod.classify(499), "minor")
        self.assertEqual(self.mod.classify(500), "major")
        self.assertEqual(self.mod.classify(12000), "major")

    def test_bump_math(self):
        self.assertEqual(self.mod.bump("3.0.0", "patch"), "3.0.1")
        self.assertEqual(self.mod.bump("3.0.9", "patch"), "3.0.10")
        self.assertEqual(self.mod.bump("3.2.7", "minor"), "3.3.0")
        self.assertEqual(self.mod.bump("3.2.7", "major"), "4.0.0")

    def test_apply_rewrites_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_path = os.path.join(tmp, "__init__.py")
            with open(init_path, "w") as handle:
                handle.write('"""doc"""\n\n__version__ = "3.0.0"\n\nX = 1\n')
            package_path = os.path.join(tmp, "package.json")
            with open(package_path, "w") as handle:
                json.dump({"name": "fivehub-app", "version": "3.0.0"}, handle)

            self.mod.apply("3.1.0", init_path, package_path)

            with open(init_path) as handle:
                content = handle.read()
            self.assertIn('__version__ = "3.1.0"', content)
            self.assertIn("X = 1", content)  # rest of the file untouched
            with open(package_path) as handle:
                self.assertEqual(json.load(handle)["version"], "3.1.0")

    def test_real_files_are_parseable(self):
        # The script must find the live version and agree with the package.
        version = self.mod.read_version()
        with open(os.path.join(REPO, "app", "package.json")) as handle:
            self.assertEqual(json.load(handle)["version"], version)


class HoudiniDetectTests(unittest.TestCase):
    def test_find_houdini_walks_installs_newest_first(self):
        import importlib.util
        from unittest import mock

        spec = importlib.util.spec_from_file_location(
            "fivehub_installer", os.path.join(REPO, "install.py"))
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)

        with tempfile.TemporaryDirectory() as tmp:
            newest = os.path.join(tmp, "hfs20.5.487", "bin")
            older = os.path.join(tmp, "hfs19.5.605", "bin")
            os.makedirs(newest)
            os.makedirs(older)
            with open(os.path.join(older, "houdinifx"), "w") as handle:
                handle.write("")
            with open(os.path.join(newest, "houdini"), "w") as handle:
                handle.write("")
            with mock.patch.dict(os.environ):
                os.environ.pop("HFS", None)
                found = installer.find_houdini(base=tmp)
            # The newest version wins even when it only carries a lesser
            # binary than an older install.
            self.assertEqual(found, os.path.join(newest, "houdini"))


class UninstallerTests(unittest.TestCase):
    def test_uninstall_removes_installed_pieces(self):
        # Install into a sandbox HOME, then uninstall: the Houdini package,
        # shortcut, login and (only with --purge-hub --yes) the hub itself
        # disappear. Repo-level steps are skipped so the checkout is safe.
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home")
            prefs = os.path.join(home, "houdini20.5")
            os.makedirs(prefs)
            hub = os.path.join(tmp, "hub")
            os.makedirs(hub)
            with open(os.path.join(hub, "registry.json"), "w") as handle:
                json.dump({"projects": {"ext": os.path.join(tmp, "elsewhere")}},
                          handle)
            login = os.path.join(home, ".fivehub")
            os.makedirs(login)
            with open(os.path.join(login, "user.json"), "w") as handle:
                json.dump({"name": "FIVE"}, handle)
            apps = os.path.join(home, ".local", "share", "applications")
            os.makedirs(apps)
            desktop = os.path.join(apps, "fivehub.desktop")
            with open(desktop, "w") as handle:
                handle.write("[Desktop Entry]\n")

            env = dict(os.environ, HOME=home, FIVEHUB_ROOT=hub)
            env.pop("FIVEHUB_USER_FILE", None)
            subprocess.run(
                [sys.executable, "install.py", "--no-pip", "--no-fonts",
                 "--no-splash", "--no-app", "--no-shortcut"],
                cwd=REPO, capture_output=True, text=True, env=env,
                timeout=120, check=True,
            )
            package = os.path.join(prefs, "packages", "fivehub.json")
            self.assertTrue(os.path.isfile(package))

            completed = subprocess.run(
                [sys.executable, "uninstall.py", "--no-app", "--no-fonts",
                 "--no-splash", "--purge-hub", "--yes"],
                cwd=REPO, capture_output=True, text=True, env=env, timeout=120,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(os.path.exists(package))
            self.assertFalse(os.path.exists(desktop))
            self.assertFalse(os.path.exists(login))
            self.assertFalse(os.path.exists(hub))
            self.assertIn("kept linked project", completed.stdout)

    def test_purge_needs_explicit_confirmation(self):
        # Without --yes and without a terminal, the hub must survive.
        with tempfile.TemporaryDirectory() as tmp:
            hub = os.path.join(tmp, "hub")
            os.makedirs(hub)
            env = dict(os.environ, HOME=os.path.join(tmp, "home"),
                       FIVEHUB_ROOT=hub)
            completed = subprocess.run(
                [sys.executable, "uninstall.py", "--no-houdini",
                 "--no-shortcut", "--no-app", "--no-fonts", "--no-splash",
                 "--no-login", "--purge-hub"],
                cwd=REPO, capture_output=True, text=True, env=env,
                timeout=120, stdin=subprocess.DEVNULL,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(os.path.isdir(hub))
            self.assertIn("kept (not confirmed)", completed.stdout)


class UpdaterTests(unittest.TestCase):
    def test_version_parse_and_compare(self):
        from fivehub import updater

        self.assertEqual(updater.parse_version("3.10.2"), (3, 10, 2))
        self.assertGreater(updater.parse_version("3.10.0"),
                           updater.parse_version("3.9.9"))
        self.assertEqual(updater.parse_version("junk"), (0, 0, 0))

    def test_newest_tag_from_ls_remote(self):
        from fivehub import updater

        output = "\n".join([
            "aaa\trefs/tags/v3.0.1",
            "bbb\trefs/tags/v3.10.0",
            "ccc\trefs/tags/v3.2.0",
            "ddd\trefs/tags/v3.10.0^{}",   # peeled tags are ignored
            "eee\trefs/tags/not-a-version",
        ])
        self.assertEqual(updater.newest_tag(output), "3.10.0")
        self.assertEqual(updater.newest_tag(""), "")

    def test_non_git_checkout_reports_cleanly(self):
        from fivehub import updater

        with tempfile.TemporaryDirectory() as tmp:
            check = updater.check(tmp)
            self.assertIn("not a git checkout", check["error"])
            outcome = updater.update(tmp)
            self.assertFalse(outcome["updated"])
            self.assertIn("not a git checkout", outcome["error"])

    def test_update_never_blocks_on_regenerated_files(self):
        # Machine-generated files (the splash) sit modified in clones from
        # before they were gitignored; update() must discard them and pull
        # — including the very pull that stops tracking them.
        from fivehub import updater

        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

        def git(cwd, *args):
            subprocess.run(["git", *args], cwd=cwd, check=True,
                           capture_output=True, text=True, env=env)

        with tempfile.TemporaryDirectory() as tmp:
            origin = os.path.join(tmp, "origin")
            splash = os.path.join("houdini", "splash", "fivehub_splash.png")
            os.makedirs(os.path.join(origin, "houdini", "splash"))
            with open(os.path.join(origin, splash), "w") as handle:
                handle.write("committed pixels")
            git(origin, "init")
            git(origin, "add", ".")
            git(origin, "commit", "-m", "track the splash")

            clone = os.path.join(tmp, "clone")
            git(tmp, "clone", "origin", "clone")
            with open(os.path.join(clone, splash), "w") as handle:
                handle.write("regenerated on this machine")

            git(origin, "rm", "--cached", "houdini/splash/fivehub_splash.png")
            with open(os.path.join(origin, ".gitignore"), "w") as handle:
                handle.write("houdini/splash/*.png\n")
            git(origin, "add", ".gitignore")
            git(origin, "commit", "-m", "stop tracking the splash")

            outcome = updater.update(clone)
            self.assertEqual(outcome["error"], "")
            self.assertTrue(outcome["updated"])


class InstallerTests(unittest.TestCase):
    def test_one_shot_installer_offline(self):
        # Network/npm/pip steps skipped: the installer must still succeed
        # and write the Houdini package for every prefs dir it finds.
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home")
            os.makedirs(os.path.join(home, "houdini20.5"))
            os.makedirs(os.path.join(home, "houdini21.0"))
            env = dict(os.environ, HOME=home)
            completed = subprocess.run(
                [sys.executable, "install.py", "--no-pip", "--no-fonts",
                 "--no-splash", "--no-app"],
                cwd=REPO, capture_output=True, text=True, env=env, timeout=120,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            for version in ("houdini20.5", "houdini21.0"):
                package = os.path.join(home, version, "packages", "fivehub.json")
                self.assertTrue(os.path.isfile(package), package)
            self.assertIn("FIVE HUB menu", completed.stdout)

    def test_houdini_installer_auto_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home")
            os.makedirs(os.path.join(home, "houdini20.5"))
            env = dict(os.environ, HOME=home)
            completed = subprocess.run(
                [sys.executable, os.path.join("houdini", "install.py"), "--auto"],
                cwd=REPO, capture_output=True, text=True, env=env, timeout=60,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(
                os.path.isfile(
                    os.path.join(home, "houdini20.5", "packages", "fivehub.json")
                )
            )


class ThumbTests(unittest.TestCase):
    def test_png_magic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_placeholder_png(os.path.join(tmp, "t.png"))
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
