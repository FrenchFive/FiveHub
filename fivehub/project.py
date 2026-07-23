"""Projects: creation, browsing, scene versioning and path logic.

A Project wraps one directory (in the hub or at a registered external
location) and its database. Multi-user rules live here:

- the database stores project-relative paths; this class translates to
  absolute paths at its boundary, so mixed-OS mounts keep working,
- scene and publish versions are claimed atomically in the database
  before any file is written — no two artists can collide on a version,
- deletion is soft: rows keep their history and files move to the
  project's ``.trash`` instead of disappearing.
"""

import json
import os
import shutil
import time
from types import SimpleNamespace

from . import config, naming
from .projectdb import ProjectDB
from .report import utc_now

DEFAULT_SETTINGS = {
    "fps": 24.0,
    "res_x": 1920,
    "res_y": 1080,
    "frame_start": 1001,
    "frame_end": 1100,
    # Git-tracked projects: commit publishes/saves automatically (push stays
    # manual via Sync).
    "git_autocommit": True,
}

# FK-safe application order for record sidecars.
_RECORD_ORDER = ("entity", "task", "scene", "publish", "dependency")


class Project:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.name = os.path.basename(self.root)
        self._db = None

    # -- infrastructure --------------------------------------------------

    @property
    def db(self):
        if self._db is None:
            self._db = ProjectDB(os.path.join(self.root, config.PROJECT_DB))
            # The database is a local cache of the record sidecars — after a
            # git pull (or with a fresh/deleted db) it catches itself up.
            try:
                self._maybe_sync()
            except Exception:
                pass  # a broken sidecar must not block the pipeline
        return self._db

    # -- record sidecars (git-mergeable source of truth) -----------------

    def records_dir(self):
        return os.path.join(self.root, config.RECORDS_DIR)

    def _records_signature(self):
        base = self.records_dir()
        count = 0
        latest = 0
        if os.path.isdir(base):
            for table in os.listdir(base):
                table_dir = os.path.join(base, table)
                if not os.path.isdir(table_dir):
                    continue
                with os.scandir(table_dir) as entries:
                    for entry in entries:
                        if entry.name.endswith(".json"):
                            count += 1
                            mtime = entry.stat().st_mtime_ns
                            if mtime > latest:
                                latest = mtime
        return "%d:%d" % (count, latest)

    def _record(self, table, row_id):
        """Mirror one database row as a JSON sidecar (atomic write)."""
        if not row_id:
            return
        row = self._db.get_row(table, row_id)
        if row is None:
            return
        table_dir = os.path.join(self.records_dir(), table)
        os.makedirs(table_dir, exist_ok=True)
        target = os.path.join(table_dir, "%s.json" % row_id)
        temp = target + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump({"table": table, "row": row}, handle, indent=2, sort_keys=True)
        os.replace(temp, target)
        self._db.set_sync_state("records_sig", self._records_signature())

    def _maybe_sync(self):
        signature = self._records_signature()
        if signature == self._db.get_sync_state("records_sig"):
            return None
        return self.sync_from_records(signature=signature)

    def sync_from_records(self, signature=None):
        """Apply every record sidecar to the local database (rebuild)."""
        self.db  # ensure the database exists (property also self-syncs once)
        base = self.records_dir()
        result = {"applied": 0, "conflicts": []}
        for table in _RECORD_ORDER:
            table_dir = os.path.join(base, table)
            if not os.path.isdir(table_dir):
                continue
            for entry in sorted(os.listdir(table_dir)):
                if not entry.endswith(".json"):
                    continue
                path = os.path.join(table_dir, entry)
                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        row = json.load(handle).get("row", {})
                except (OSError, ValueError):
                    result["conflicts"].append({"record": path, "reason": "unreadable"})
                    continue
                outcome = self._db.upsert_record(table, row)
                if outcome == "conflict":
                    result["conflicts"].append({
                        "record": path,
                        "reason": "a different record owns this version slot "
                                  "(simultaneous offline claims) — rename one "
                                  "and rebuild",
                    })
                else:
                    result["applied"] += 1
        self._db.set_sync_state(
            "records_sig", signature or self._records_signature()
        )
        return result

    def _autocommit(self, message):
        """Best-effort git commit of pipeline events on git-tracked projects."""
        from . import gitsync

        if not self.settings().get("git_autocommit", True):
            return
        gitsync.autocommit(self.root, "[fivehub] %s" % message)

    @property
    def meta_path(self):
        return os.path.join(self.root, config.PROJECT_FILE)

    def meta(self):
        try:
            with open(self.meta_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {"name": self.name, "image": "", "created_at": ""}

    def settings(self):
        merged = dict(DEFAULT_SETTINGS)
        merged.update(self.meta().get("settings", {}))
        return merged

    def image_path(self):
        image = self.meta().get("image", "")
        return os.path.join(self.root, image) if image else ""

    def reports_dir(self):
        return os.path.join(self.root, config.PROJECT_REPORTS_DIR)

    def refs_dir(self):
        return os.path.join(self.root, config.REFS_DIR)

    def trash_dir(self):
        return os.path.join(self.root, config.TRASH_DIR)

    # -- path translation (database <-> disk) ---------------------------

    def rel(self, path):
        """Project-relative posix path for storage."""
        if not path:
            return ""
        return os.path.relpath(os.path.abspath(path), self.root).replace(os.sep, "/")

    def absolute(self, stored):
        """Stored project-relative path back to an absolute one."""
        if not stored:
            return ""
        if os.path.isabs(stored):
            return stored  # pre-migration rows
        return os.path.normpath(os.path.join(self.root, stored))

    def _abs_row(self, row, keys=("file", "path", "report_path", "thumbnail")):
        for key in keys:
            if key in row and row[key]:
                row[key] = self.absolute(row[key])
        return row

    # -- paths -----------------------------------------------------------

    def entity_dir(self, kind, entity):
        return os.path.join(self.root, config.kind_dir(kind), entity)

    def task_dir(self, kind, entity, task):
        return os.path.join(self.entity_dir(kind, entity), task)

    def scenes_dir(self, kind, entity, task):
        return os.path.join(self.task_dir(kind, entity, task), config.SCENES_DIR)

    def caches_dir(self, kind, entity, task):
        return os.path.join(self.task_dir(kind, entity, task), config.CACHES_DIR)

    def render_dir(self, kind, entity, task):
        return os.path.join(self.task_dir(kind, entity, task), config.RENDER_DIR)

    def publish_dir(self, kind, entity, task, format_name):
        return os.path.join(
            self.task_dir(kind, entity, task), config.PUBLISH_DIR, format_name
        )

    def scene_path(self, kind, entity, task, version, extension=None):
        return os.path.join(
            self.scenes_dir(kind, entity, task),
            config.scene_file_name(entity, task, version, extension),
        )

    # -- entities & tasks ------------------------------------------------

    def create_entity(self, kind, name, sequence="", frame_start=None,
                      frame_end=None, fps=None, res_x=None, res_y=None):
        errors = naming.asset_name_errors(name)
        if errors:
            raise ValueError("; ".join(errors))
        if kind == "shot":
            # Shots always carry usable frame/format metadata.
            defaults = self.settings()
            frame_start = defaults["frame_start"] if frame_start is None else frame_start
            frame_end = defaults["frame_end"] if frame_end is None else frame_end
            fps = defaults["fps"] if fps is None else fps
            res_x = defaults["res_x"] if res_x is None else res_x
            res_y = defaults["res_y"] if res_y is None else res_y
        entity_id = self.db.create_entity(
            kind, name, sequence=sequence, frame_start=frame_start,
            frame_end=frame_end, fps=fps, res_x=res_x, res_y=res_y,
        )
        os.makedirs(self.entity_dir(kind, name), exist_ok=True)
        self._record("entity", entity_id)
        self._autocommit("add %s %s" % (kind, name))
        return name

    def update_entity(self, kind, name, **fields):
        record = self.db.get_entity(kind, name)
        if record is None:
            raise ValueError("unknown %s %r" % (kind, name))
        self.db.update_entity(record["id"], **fields)
        self._record("entity", record["id"])

    def create_task(self, kind, entity, task):
        task = str(task or "").strip().lower()
        if not naming.is_identifier(task):
            raise ValueError(
                "task %r is not a valid identifier (letters, digits, underscores)" % task
            )
        record = self.db.get_entity(kind, entity)
        if record is None:
            raise ValueError("unknown %s %r" % (kind, entity))
        task_id = self.db.create_task(record["id"], task)
        for directory in (
            self.scenes_dir(kind, entity, task),
            self.caches_dir(kind, entity, task),
            os.path.join(self.task_dir(kind, entity, task), config.PUBLISH_DIR),
        ):
            os.makedirs(directory, exist_ok=True)
        self._record("task", task_id)
        self._autocommit("add task %s/%s" % (entity, task))
        return task

    def _task_record(self, kind, entity, task):
        record = self.db.get_entity(kind, entity)
        if record is None:
            raise ValueError("unknown %s %r" % (kind, entity))
        task_record = self.db.get_task(record["id"], task)
        if task_record is None:
            raise ValueError("unknown task %r on %s %r" % (task, kind, entity))
        return task_record

    def entities(self, kind):
        return self.db.list_entities(kind)

    def tasks(self, kind, entity):
        record = self.db.get_entity(kind, entity)
        return self.db.list_tasks(record["id"]) if record else []

    # -- scenes (claim -> write -> complete) -----------------------------

    def next_scene_version(self, kind, entity, task):
        """Peek only — the real number is fixed by claim_scene."""
        return self.db.next_scene_version(self._task_record(kind, entity, task)["id"])

    def claim_scene(self, kind, entity, task, user="", extension=None):
        """Reserve the next scene version; returns (absolute path, version).

        The claim guarantees no other artist gets the same version — write
        the file at the returned path, then call complete_scene (or
        release_scene if the save failed). ``extension`` follows the DCC's
        license (.hip / .hiplc / .hipnc) so the claimed path is the file
        Houdini will actually write."""
        task_record = self._task_record(kind, entity, task)
        version = self.db.claim_scene_version(
            task_record["id"],
            lambda v: self.rel(self.scene_path(kind, entity, task, v, extension)),
            user=user,
        )
        path = self.scene_path(kind, entity, task, version, extension)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path, version

    def complete_scene(self, kind, entity, task, version, notes="", user=""):
        task_id = self._task_record(kind, entity, task)["id"]
        # The claim recorded the real file (extension included) — check that.
        claimed = self.db.claimed_scene_file(task_id, version)
        path = (
            self.absolute(claimed)
            if claimed
            else self.scene_path(kind, entity, task, version)
        )
        if not os.path.isfile(path):
            raise ValueError("scene file was not written: %s" % path)
        if not user:
            from .user import get_user

            user = get_user()
        task_record = self._task_record(kind, entity, task)
        self.db.complete_scene(task_record["id"], version, notes, user)
        row = self.db.get_scene(task_record["id"], version)
        if row:
            self._record("scene", row["id"])
        self._autocommit(
            "scene v%03d %s/%s — %s" % (int(version), entity, task, user)
        )
        return path

    def release_scene(self, kind, entity, task, version):
        task_record = self._task_record(kind, entity, task)
        self.db.release_scene(task_record["id"], version)

    def register_scene(self, kind, entity, task, notes="", user="", writer=None):
        """Convenience for tests/scripts: claim, write via ``writer(path)``
        (default: empty file), complete. Returns (path, version)."""
        path, version = self.claim_scene(kind, entity, task, user)
        try:
            if writer is not None:
                writer(path)
            elif not os.path.isfile(path):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("")
            self.complete_scene(kind, entity, task, version, notes, user)
        except Exception:
            self.release_scene(kind, entity, task, version)
            raise
        return path, version

    def scenes(self, kind, entity, task):
        rows = self.db.list_scenes(self._task_record(kind, entity, task)["id"])
        return [self._abs_row(row) for row in rows]

    def get_scene(self, kind, entity, task, version):
        row = self.db.get_scene(self._task_record(kind, entity, task)["id"], version)
        return self._abs_row(row) if row else None

    # -- publishes -------------------------------------------------------

    def claim_publish(self, kind, entity, task, name, format_name, variant, user=""):
        task_record = self._task_record(kind, entity, task)
        return self.db.claim_publish_version(
            task_record["id"], name, format_name, variant, user
        )

    def complete_publish(self, kind, entity, task, format_name, version, report,
                         path="", report_path="", thumbnail="", comment="", user=""):
        task_record = self._task_record(kind, entity, task)
        self.db.complete_publish(
            task_record["id"], format_name, version, report,
            path=self.rel(path), report_path=self.rel(report_path),
            thumbnail=self.rel(thumbnail), comment=comment, user=user,
        )
        row = self.db.get_publish(task_record["id"], format_name, version)
        if row:
            self._record("publish", row["id"])
        self._autocommit(
            "publish %s v%03d %s/%s — %s"
            % (format_name, int(version), entity, task, user)
        )

    def release_publish(self, kind, entity, task, format_name, version):
        task_record = self._task_record(kind, entity, task)
        self.db.release_publish(task_record["id"], format_name, version)

    def record_blocked_publish(self, kind, entity, task, name, format_name,
                               variant, report, report_path="", comment="", user=""):
        task_record = self._task_record(kind, entity, task)
        row_id = self.db.record_blocked_publish(
            task_record["id"], name, format_name, variant, report,
            report_path=self.rel(report_path), comment=comment, user=user,
        )
        self._record("publish", row_id)

    def record_dependency(self, kind, entity, task, src_kind, src_entity,
                          src_task, src_format, src_name, src_version=None, user=""):
        consumer = self._task_record(kind, entity, task)
        producer = self._task_record(src_kind, src_entity, src_task)
        row_id = self.db.record_dependency(
            consumer["id"], producer["id"], src_format, src_name,
            src_version=src_version, user=user,
        )
        self._record("dependency", row_id)
        return row_id

    def publishes(self, kind, entity, task):
        rows = self.db.list_publishes(self._task_record(kind, entity, task)["id"])
        return [self._abs_row(row) for row in rows]

    def get_publish(self, kind, entity, task, format_name, version):
        row = self.db.get_publish(
            self._task_record(kind, entity, task)["id"], format_name, version
        )
        return self._abs_row(row) if row else None

    def latest_publish(self, kind, entity, task, format_name=None):
        row = self.db.latest_publish(
            self._task_record(kind, entity, task)["id"], format_name
        )
        return self._abs_row(row) if row else None

    def publish_history(self, limit=100):
        return [self._abs_row(row) for row in self.db.publish_history(limit)]

    def recent_scenes(self, limit=20):
        return [self._abs_row(row) for row in self.db.recent_scenes(limit)]

    def browse(self):
        """Full project tree for the app: entities with their tasks."""
        from . import gitsync

        tree = {"name": self.name, **self.meta(), "image_path": self.image_path(),
                "root": self.root, "settings": self.settings(),
                "git_status": gitsync.status(self.root)}
        presence = {row["task_id"]: row for row in self.db.list_presence()}
        for kind in config.KINDS:
            entries = []
            for entity in self.entities(kind):
                tasks = self.db.list_tasks(entity["id"])
                for task in tasks:
                    active = presence.get(task["id"])
                    task["active_user"] = active["user"] if active else ""
                entries.append({**entity, "tasks": tasks})
            tree[config.kind_dir(kind)] = entries
        tree["counts"] = self.db.counts()
        return tree

    # -- edits & deletions (soft: rows keep history, files go to trash) --

    def _inside_root(self, path):
        target = os.path.abspath(path)
        try:
            return os.path.commonpath([self.root, target]) == self.root
        except ValueError:
            return False

    def _trash(self, path, label):
        """Move a file or tree into the project trash (never delete)."""
        if not path or not self._inside_root(path) or not os.path.exists(path):
            return ""
        stamp = utc_now().replace(":", "").replace("-", "")
        target_dir = os.path.join(
            self.trash_dir(), "%s_%s" % (stamp, naming.make_identifier(label))
        )
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, os.path.basename(path))
        shutil.move(path, target)
        return target

    def empty_trash(self, older_than_days=0):
        """Purge trash entries older than N days (0 = everything)."""
        trash = self.trash_dir()
        if not os.path.isdir(trash):
            return []
        removed = []
        cutoff = time.time() - older_than_days * 86400
        for entry in sorted(os.listdir(trash)):
            path = os.path.join(trash, entry)
            if os.path.getmtime(path) <= cutoff:
                shutil.rmtree(path, ignore_errors=True)
                removed.append(entry)
        return removed

    def set_scene_notes(self, kind, entity, task, version, notes):
        task_record = self._task_record(kind, entity, task)
        self.db.update_scene_notes(task_record["id"], version, notes)
        row = self.db.get_scene(task_record["id"], version)
        if row:
            self._record("scene", row["id"])

    def set_publish_comment(self, kind, entity, task, format_name, version, comment):
        task_record = self._task_record(kind, entity, task)
        self.db.update_publish_comment(task_record["id"], format_name, version, comment)
        row = self.db.get_publish(task_record["id"], format_name, version)
        if row:
            self._record("publish", row["id"])

    def delete_scene(self, kind, entity, task, version):
        task_record = self._task_record(kind, entity, task)
        row = self.db.delete_scene(task_record["id"], version)
        self._record("scene", row["id"])
        row = self._abs_row(dict(row))
        self._trash(row.get("file", ""), "%s_%s_scene_v%03d" % (entity, task, version))
        self._autocommit("remove scene v%03d %s/%s" % (int(version), entity, task))
        return row

    def delete_publish(self, kind, entity, task, format_name, version):
        task_record = self._task_record(kind, entity, task)
        row = self.db.delete_publish(task_record["id"], format_name, version)
        self._record("publish", row["id"])
        row = self._abs_row(dict(row))
        path = row.get("path", "")
        # usd rows point at the entry layer; file rows at the version dir.
        version_dir = os.path.dirname(path) if os.path.isfile(path) else path
        self._trash(
            version_dir, "%s_%s_%s_v%03d" % (entity, task, format_name, version)
        )
        if format_name == "usd":
            self._rebuild_usd_root(task_record["id"], kind, entity, task, row["name"])
        self._autocommit(
            "remove publish %s v%03d %s/%s" % (format_name, int(version), entity, task)
        )
        return row

    def _rebuild_usd_root(self, task_id, kind, entity, task, name):
        """Re-point the root interface after a version disappears; drop it
        entirely when no versions of this publish name remain."""
        from . import usdlayers

        publish_root = self.publish_dir(kind, entity, task, "usd")
        root_layer = os.path.join(publish_root, "%s.usda" % name)
        variants = self.db.known_variants(task_id, "usd", name)
        if not variants:
            self._trash(root_layer, "%s_root_layer" % name)
            return
        latest_version = max(variants.values())
        latest_row = self.db.get_publish(task_id, "usd", latest_version)
        thumbnail = None
        if latest_row and latest_row.get("thumbnail"):
            thumbnail_abs = self.absolute(latest_row["thumbnail"])
            if os.path.isfile(thumbnail_abs):
                thumbnail = "./" + os.path.relpath(
                    thumbnail_abs, publish_root
                ).replace(os.sep, "/")
        usdlayers.write_entry_layer(
            root_layer,
            SimpleNamespace(asset_name=name, meters_per_unit=1.0, up_axis="Y"),
            variants={
                variant: "./%s/%s.payload.usda" % (config.version_label(v), name)
                for variant, v in variants.items()
            },
            selected_variant="default" if "default" in variants else sorted(variants)[0],
            version_label=config.version_label(latest_version),
            thumbnail=thumbnail,
            extents=None,
        )

    def delete_task(self, kind, entity, task):
        task_record = self._task_record(kind, entity, task)
        self.db.delete_task(task_record["id"])
        self._record("task", task_record["id"])
        self._trash(self.task_dir(kind, entity, task), "%s_%s" % (entity, task))
        self._autocommit("remove task %s/%s" % (entity, task))

    def delete_entity(self, kind, name):
        record = self.db.get_entity(kind, name)
        if record is None:
            raise ValueError("unknown %s %r" % (kind, name))
        tasks = self.db.list_tasks(record["id"])
        self.db.delete_entity(record["id"])
        self._record("entity", record["id"])
        for task_row in tasks:
            self._record("task", task_row["id"])
        self._trash(self.entity_dir(kind, name), name)
        self._autocommit("remove %s %s" % (kind, name))

    # -- presence --------------------------------------------------------

    def touch_presence(self, kind, entity, task, user, scene_version=None, host=""):
        try:
            task_record = self._task_record(kind, entity, task)
        except ValueError:
            return
        self.db.set_presence(user, task_record["id"], scene_version, host)

    def task_presence(self, kind, entity, task):
        task_record = self._task_record(kind, entity, task)
        return [
            row for row in self.db.list_presence() if row["task_id"] == task_record["id"]
        ]


# -- hub-level operations ------------------------------------------------


def _registry_path(root):
    return os.path.join(root, config.REGISTRY_FILE)


def _read_registry(root):
    """Map of project name -> root directory for externally-located projects."""
    try:
        with open(_registry_path(root), "r", encoding="utf-8") as handle:
            entries = json.load(handle).get("projects", {})
            return {str(k): str(v) for k, v in entries.items()}
    except (OSError, ValueError):
        return {}


def _write_registry_locked(root, mutate):
    """Atomically update the registry under a lock file (shared server)."""
    lock = _registry_path(root) + ".lock"
    acquired = False
    for _ in range(60):
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(handle)
            acquired = True
            break
        except FileExistsError:
            # Steal locks abandoned by crashed processes.
            try:
                if time.time() - os.path.getmtime(lock) > 30:
                    os.remove(lock)
                    continue
            except OSError:
                pass
            time.sleep(0.1)
    if not acquired:
        raise RuntimeError("could not lock the project registry (%s)" % lock)
    try:
        registry = _read_registry(root)
        mutate(registry)
        temp = _registry_path(root) + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump({"projects": registry}, handle, indent=2)
        os.replace(temp, _registry_path(root))
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def _project_roots(root):
    """Every known project as name -> root: default directory + registry."""
    roots = {}
    projects_dir = config.projects_path(root)
    if os.path.isdir(projects_dir):
        for entry in sorted(os.listdir(projects_dir)):
            candidate = os.path.join(projects_dir, entry)
            if os.path.isfile(os.path.join(candidate, config.PROJECT_FILE)):
                roots[entry] = candidate
    for name, candidate in _read_registry(root).items():
        if os.path.isfile(os.path.join(candidate, config.PROJECT_FILE)):
            roots[name] = candidate
    return roots


def create_project(name, image=None, hub_root=None, location=None, settings=None):
    """Create a project — in the hub by default, or at a chosen location
    (shared drive, synced repository folder, anywhere) which is then
    recorded in the hub registry."""
    errors = naming.asset_name_errors(name)
    if errors:
        raise ValueError("; ".join(errors))
    root = config.ensure_hub(hub_root)
    if name in _project_roots(root):
        raise ValueError("project %r already exists" % name)
    if location:
        base = os.path.abspath(os.path.expanduser(str(location)))
        if not os.path.isdir(base):
            raise ValueError("project location does not exist: %s" % base)
        project_root = os.path.join(base, name)
    else:
        project_root = os.path.join(config.projects_path(root), name)
    if os.path.exists(project_root):
        raise ValueError("project directory already exists: %s" % project_root)
    os.makedirs(project_root)
    for sub in (config.ASSETS_DIR, config.SHOTS_DIR, config.PROJECT_REPORTS_DIR,
                config.REFS_DIR):
        os.makedirs(os.path.join(project_root, sub), exist_ok=True)

    image_name = ""
    if image:
        if not os.path.isfile(image):
            raise ValueError("project image not found: %s" % image)
        extension = os.path.splitext(image)[1].lower() or ".png"
        image_name = "image" + extension
        shutil.copyfile(image, os.path.join(project_root, image_name))
    else:
        from .thumbs import write_placeholder_png

        image_name = "image.png"
        write_placeholder_png(os.path.join(project_root, image_name), size=128, cell=16)

    project_settings = dict(DEFAULT_SETTINGS)
    project_settings.update(settings or {})
    with open(os.path.join(project_root, config.PROJECT_FILE), "w", encoding="utf-8") as f:
        json.dump(
            {"name": name, "image": image_name, "created_at": utc_now(),
             "settings": project_settings},
            f, indent=2,
        )

    # Ready for git from day one (harmless when the project never uses it).
    from . import gitsync

    with open(os.path.join(project_root, ".gitignore"), "w", encoding="utf-8") as f:
        f.write(gitsync.GITIGNORE)

    if location:
        _write_registry_locked(root, lambda reg: reg.__setitem__(name, project_root))

    project = Project(project_root)
    project.db  # create the database file up front
    return project


def get_project(name, hub_root=None):
    root = config.ensure_hub(hub_root)
    project_root = _project_roots(root).get(name)
    if project_root is None:
        raise ValueError("unknown project %r" % name)
    return Project(project_root)


def list_projects(hub_root=None):
    from . import gitsync

    root = config.ensure_hub(hub_root)
    default_dir = config.projects_path(root)
    projects = []
    for name, project_root in sorted(_project_roots(root).items()):
        project = Project(project_root)
        info = {"name": name, **project.meta()}
        info["path"] = project_root
        info["external"] = os.path.dirname(project_root) != default_dir
        info["git"] = gitsync.is_git_project(project_root)
        info["image_path"] = project.image_path()
        info["counts"] = project.db.counts()
        projects.append(info)
    return projects


def remove_project(name, hub_root=None, delete_files=False):
    """Remove a project from the hub.

    External (linked) projects are unregistered and their files kept unless
    ``delete_files`` is set. Hub-local projects live inside the scanned
    directory, so removing them always deletes their files.
    """
    root = config.ensure_hub(hub_root)
    roots = _project_roots(root)
    project_root = roots.get(name)
    if project_root is None:
        raise ValueError("unknown project %r" % name)
    external = name in _read_registry(root)
    if external:
        _write_registry_locked(root, lambda reg: reg.pop(name, None))
    deleted = False
    if delete_files or not external:
        shutil.rmtree(project_root, ignore_errors=True)
        deleted = True
    return {"removed": name, "external": external, "deleted_files": deleted,
            "path": project_root}


def parse_scene_path(path, hub_root=None):
    """Recover the pipeline context from a scene file path.

    Works for projects in the hub and at registered external locations:
    the path must live at ``<project>/(assets|shots)/<E>/<task>/scenes/<f>``
    under a known project root. Returns ``{project, kind, entity, task,
    file}`` or None.
    """
    if not path:
        return None
    root = config.hub_root(hub_root)
    target = os.path.abspath(path)
    for name, project_root in _project_roots(root).items():
        try:
            relative = os.path.relpath(target, project_root)
        except ValueError:  # different drive on Windows
            continue
        parts = relative.replace(os.sep, "/").split("/")
        if len(parts) != 5 or parts[0] == ".." or parts[3] != config.SCENES_DIR:
            continue
        kind = {config.ASSETS_DIR: "asset", config.SHOTS_DIR: "shot"}.get(parts[0])
        if kind is None:
            continue
        return {
            "project": name,
            "kind": kind,
            "entity": parts[1],
            "task": parts[2],
            "file": parts[4],
        }
    return None
