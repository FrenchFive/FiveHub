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
        path, version = project.next_scene_path("asset", "Crate", "modeling")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write("hip")
        project.register_scene("asset", "Crate", "modeling", version, path)
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
        path, version = project.next_scene_path("asset", "Ship", "modeling")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write("hip")
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

    def test_scene_versioning(self):
        project = create_project("Epsilon", hub_root=self.hub)
        project.create_entity("shot", "SH010")
        project.create_task("shot", "SH010", "fx")

        path, version = project.next_scene_path("shot", "SH010", "fx")
        self.assertEqual(version, 1)
        self.assertTrue(path.endswith("SH010_fx_v001.hip"))

        with self.assertRaises(ValueError):
            project.register_scene("shot", "SH010", "fx", version, path)  # not written

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write("hip")
        project.register_scene("shot", "SH010", "fx", version, path, "first pass", "ana")

        path2, version2 = project.next_scene_path("shot", "SH010", "fx")
        self.assertEqual(version2, 2)
        with open(path2, "w") as handle:
            handle.write("hip")
        project.register_scene("shot", "SH010", "fx", version2, path2)

        scenes = project.scenes("shot", "SH010", "fx")
        self.assertEqual([s["version"] for s in scenes], [2, 1])
        self.assertEqual(scenes[1]["notes"], "first pass")

        context = parse_scene_path(path2, self.hub)
        self.assertEqual(
            context,
            {
                "project": "Epsilon",
                "kind": "shot",
                "entity": "SH010",
                "task": "fx",
                "file": "SH010_fx_v002.hip",
            },
        )
        self.assertIsNone(parse_scene_path("/somewhere/else.hip", self.hub))
        self.assertIsNone(parse_scene_path("", self.hub))


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
        path, version = self.project.next_scene_path("asset", "Crate", "modeling")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write("hip")
        self.project.register_scene("asset", "Crate", "modeling", version, path, notes)
        return path, version

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


class ThumbTests(unittest.TestCase):
    def test_png_magic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_placeholder_png(os.path.join(tmp, "t.png"))
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
