"""Per-project database.

Every project owns one SQLite file (``project.db``). Built for a shared
server with several artists writing at once:

- connections are per-operation with a busy timeout and retry-on-locked,
  DELETE journal mode (safe on NFS/SMB — WAL is not),
- version numbers are **claimed atomically in the database first** (a
  pending row guarded by a UNIQUE constraint), so two artists can never
  produce the same scene or publish version and overwrite each other,
- rows are soft-deleted (``deleted_at``) — version numbers are never
  reused and history survives deletion,
- ``PRAGMA user_version`` tracks the schema; older databases are migrated
  in place on open.

All paths stored here are project-relative with forward slashes, so a hub
shared between Linux, macOS and Windows keeps working; ``project.Project``
translates to absolute paths at its boundary.
"""

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager

from .report import utc_now

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS entity (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('asset', 'shot')),
    name        TEXT NOT NULL,
    sequence    TEXT NOT NULL DEFAULT '',
    frame_start INTEGER,
    frame_end   INTEGER,
    fps         REAL,
    res_x       INTEGER,
    res_y       INTEGER,
    deleted_at  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_entity_alive
    ON entity (kind, name) WHERE deleted_at = '';

CREATE TABLE IF NOT EXISTS task (
    id          TEXT PRIMARY KEY,
    entity_id   TEXT NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    deleted_at  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_task_alive
    ON task (entity_id, name) WHERE deleted_at = '';

CREATE TABLE IF NOT EXISTS scene (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES task(id) ON DELETE CASCADE,
    name        TEXT NOT NULL DEFAULT 'main',
    version     INTEGER NOT NULL,
    file        TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    user        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'complete',
    deleted_at  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (task_id, name, version)
);

CREATE TABLE IF NOT EXISTS publish (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES task(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    format      TEXT NOT NULL,
    variant     TEXT NOT NULL DEFAULT 'default',
    version     INTEGER,
    passed      INTEGER NOT NULL DEFAULT 1,
    errors      INTEGER NOT NULL DEFAULT 0,
    warnings    INTEGER NOT NULL DEFAULT 0,
    path        TEXT NOT NULL DEFAULT '',
    report_path TEXT NOT NULL DEFAULT '',
    thumbnail   TEXT NOT NULL DEFAULT '',
    comment     TEXT NOT NULL DEFAULT '',
    user        TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'complete',
    deleted_at  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (task_id, format, version)
);

CREATE TABLE IF NOT EXISTS presence (
    user        TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    scene_version INTEGER,
    host        TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'queued',
    worker      TEXT NOT NULL DEFAULT '',
    log         TEXT NOT NULL DEFAULT '',
    user        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    started_at  TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS dependency (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES task(id) ON DELETE CASCADE,
    src_task_id TEXT NOT NULL,
    src_format  TEXT NOT NULL,
    src_name    TEXT NOT NULL,
    src_version INTEGER,
    user        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (task_id, src_task_id, src_format, src_name)
);

CREATE TABLE IF NOT EXISTS sync_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT ''
);
"""

# Tables mirrored as JSON record sidecars (the durable source of truth the
# local cache database can be rebuilt from). Presence and jobs are
# machine/site-transient and deliberately excluded.
RECORD_TABLES = {
    "entity": ("id", "kind", "name", "sequence", "frame_start", "frame_end",
               "fps", "res_x", "res_y", "deleted_at", "created_at"),
    "task": ("id", "entity_id", "name", "deleted_at", "created_at"),
    "scene": ("id", "task_id", "version", "file", "notes", "user", "status",
              "deleted_at", "created_at"),
    "publish": ("id", "task_id", "name", "format", "variant", "version",
                "passed", "errors", "warnings", "path", "report_path",
                "thumbnail", "comment", "user", "status", "deleted_at",
                "created_at"),
    "dependency": ("id", "task_id", "src_task_id", "src_format", "src_name",
                   "src_version", "user", "created_at"),
}

# Columns added since schema v1, used to migrate old databases in place.
_V2_NEW_COLUMNS = {
    "entity": (
        ("sequence", "TEXT NOT NULL DEFAULT ''"),
        ("frame_start", "INTEGER"),
        ("frame_end", "INTEGER"),
        ("fps", "REAL"),
        ("res_x", "INTEGER"),
        ("res_y", "INTEGER"),
        ("deleted_at", "TEXT NOT NULL DEFAULT ''"),
    ),
    "task": (("deleted_at", "TEXT NOT NULL DEFAULT ''"),),
    "scene": (
        ("status", "TEXT NOT NULL DEFAULT 'complete'"),
        ("deleted_at", "TEXT NOT NULL DEFAULT ''"),
    ),
    "publish": (
        ("status", "TEXT NOT NULL DEFAULT 'complete'"),
        ("deleted_at", "TEXT NOT NULL DEFAULT ''"),
    ),
}

# v3: publishes remember the scene file that produced them.
_V3_NEW_COLUMNS = {
    "publish": (("source_file", "TEXT NOT NULL DEFAULT ''"),),
}

LOCK_RETRIES = 6
LOCK_BASE_DELAY = 0.25


class ProjectDB:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._connect() as conn:
            self._migrate(conn)

    @contextmanager
    def _connect(self):
        conn = None
        for attempt in range(LOCK_RETRIES):
            try:
                conn = sqlite3.connect(self.path, timeout=15)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA busy_timeout = 15000")
                conn.execute("PRAGMA journal_mode = DELETE")
                conn.execute("PRAGMA foreign_keys = ON")
                break
            except sqlite3.OperationalError:
                if conn is not None:
                    conn.close()
                    conn = None
                if attempt == LOCK_RETRIES - 1:
                    raise
                time.sleep(LOCK_BASE_DELAY * (2 ** attempt))
        try:
            yield conn
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _migrate(self, conn):
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            conn.executescript(SCHEMA)  # new tables may still be missing
            return
        # ALTERs are applied only for tables/columns that already exist —
        # a fresh file gets everything from SCHEMA below instead.
        if version < 2:
            self._add_missing_columns(conn, _V2_NEW_COLUMNS)
        if version < 3:
            self._add_missing_columns(conn, _V3_NEW_COLUMNS)
        # v4 rebuilds the scene table: named scene streams, versioned per
        # (task, name) — a UNIQUE constraint cannot be altered in place.
        copy_scenes = False
        if version < 4:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            if "scene" in tables:
                columns = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(scene)").fetchall()
                }
                if "name" not in columns:
                    conn.execute("ALTER TABLE scene RENAME TO scene_v3")
                    copy_scenes = True
        conn.executescript(SCHEMA)
        if copy_scenes:
            conn.execute(
                "INSERT INTO scene (id, task_id, name, version, file, notes,"
                " user, status, deleted_at, created_at)"
                " SELECT id, task_id, 'main', version, file, notes, user,"
                " status, deleted_at, created_at FROM scene_v3"
            )
            conn.execute("DROP TABLE scene_v3")
        conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)

    @staticmethod
    def _add_missing_columns(conn, spec):
        existing_tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table, columns in spec.items():
            if table not in existing_tables:
                continue
            present = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(%s)" % table).fetchall()
            }
            for column, declaration in columns:
                if column not in present:
                    conn.execute(
                        "ALTER TABLE %s ADD COLUMN %s %s"
                        % (table, column, declaration)
                    )

    # -- entities --------------------------------------------------------

    def create_entity(self, kind, name, sequence="", frame_start=None,
                      frame_end=None, fps=None, res_x=None, res_y=None):
        with self._connect() as conn:
            try:
                entity_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO entity (id, kind, name, sequence, frame_start,"
                    " frame_end, fps, res_x, res_y, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (entity_id, kind, name, sequence or "", frame_start,
                     frame_end, fps, res_x, res_y, utc_now()),
                )
                return entity_id
            except sqlite3.IntegrityError:
                raise ValueError("%s %r already exists" % (kind, name))

    def update_entity(self, entity_id, **fields):
        allowed = ("sequence", "frame_start", "frame_end", "fps", "res_x", "res_y")
        updates = {key: fields[key] for key in allowed if key in fields}
        if not updates:
            return
        assignments = ", ".join("%s = ?" % key for key in updates)
        with self._connect() as conn:
            conn.execute(
                "UPDATE entity SET %s WHERE id = ?" % assignments,
                (*updates.values(), entity_id),
            )

    def get_entity(self, kind, name):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM entity WHERE kind = ? AND name = ? AND deleted_at = ''",
                (kind, name),
            ).fetchone()
            return dict(row) if row else None

    def list_entities(self, kind):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM entity WHERE kind = ? AND deleted_at = ''"
                " ORDER BY sequence, name COLLATE NOCASE",
                (kind,),
            ).fetchall()
            return [dict(row) for row in rows]

    # -- tasks -----------------------------------------------------------

    def create_task(self, entity_id, name):
        with self._connect() as conn:
            try:
                task_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO task (id, entity_id, name, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (task_id, entity_id, name, utc_now()),
                )
                return task_id
            except sqlite3.IntegrityError:
                raise ValueError("task %r already exists on this entity" % name)

    def get_task(self, entity_id, name):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM task WHERE entity_id = ? AND name = ?"
                " AND deleted_at = ''",
                (entity_id, name),
            ).fetchone()
            return dict(row) if row else None

    def list_tasks(self, entity_id):
        """Tasks of an entity with scene/publish counts for browsing."""
        query = """
            SELECT t.*,
                   (SELECT COUNT(*) FROM scene s WHERE s.task_id = t.id
                     AND s.status = 'complete' AND s.deleted_at = '') AS scene_count,
                   (SELECT COUNT(*) FROM publish p WHERE p.task_id = t.id
                     AND p.version IS NOT NULL AND p.status = 'complete'
                     AND p.deleted_at = '') AS publish_count,
                   (SELECT p.thumbnail FROM publish p WHERE p.task_id = t.id
                     AND p.version IS NOT NULL AND p.status = 'complete'
                     AND p.deleted_at = '' AND p.thumbnail != ''
                     ORDER BY p.created_at DESC, p.rowid DESC LIMIT 1) AS image,
                   (SELECT p.created_at FROM publish p WHERE p.task_id = t.id
                     AND p.version IS NOT NULL AND p.status = 'complete'
                     AND p.deleted_at = ''
                     ORDER BY p.created_at DESC, p.rowid DESC LIMIT 1)
                     AS last_publish_at
            FROM task t WHERE t.entity_id = ? AND t.deleted_at = '' ORDER BY t.name
        """
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, (entity_id,)).fetchall()]

    # -- scenes ----------------------------------------------------------

    def next_scene_version(self, task_id, name="main"):
        """Peek at the next version of one named scene stream."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(version) AS latest FROM scene"
                " WHERE task_id = ? AND name = ?",
                (task_id, name),
            ).fetchone()
            return (row["latest"] or 0) + 1

    def claim_scene_version(self, task_id, file_for_version, user="",
                            name="main"):
        """Atomically reserve the next version of a named scene stream.

        ``file_for_version`` is a callable version -> relative file path.
        The UNIQUE(task_id, name, version) constraint is the lock: whoever
        inserts first owns the number; everyone else moves to the next one.
        """
        for _ in range(50):
            version = self.next_scene_version(task_id, name)
            try:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT INTO scene (id, task_id, name, version, file,"
                        " user, status, created_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                        (str(uuid.uuid4()), task_id, name, version,
                         file_for_version(version), user, utc_now()),
                    )
                return version
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("could not claim a scene version (database contention)")

    def complete_scene(self, task_id, version, notes="", user="", name="main"):
        with self._connect() as conn:
            conn.execute(
                "UPDATE scene SET status = 'complete', notes = ?, user = ?,"
                " created_at = ? WHERE task_id = ? AND name = ? AND version = ?",
                (notes or "", user or "", utc_now(), task_id, name,
                 int(version)),
            )

    def release_scene(self, task_id, version, name="main"):
        """Drop a claim whose save never happened."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM scene WHERE task_id = ? AND name = ?"
                " AND version = ? AND status = 'pending'",
                (task_id, name, int(version)),
            )

    def list_scenes(self, task_id):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scene WHERE task_id = ? AND status = 'complete'"
                " AND deleted_at = '' ORDER BY name ASC, version DESC",
                (task_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def claimed_scene_file(self, task_id, version, name="main"):
        """File recorded at claim time, any status — the claim knows the
        real extension (.hip / .hiplc / .hipnc)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT file FROM scene WHERE task_id = ? AND name = ?"
                " AND version = ?",
                (task_id, name, int(version)),
            ).fetchone()
            return row["file"] if row else ""

    def get_scene(self, task_id, version, name="main"):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM scene WHERE task_id = ? AND name = ?"
                " AND version = ? AND status = 'complete' AND deleted_at = ''",
                (task_id, name, int(version)),
            ).fetchone()
            return dict(row) if row else None

    def latest_scene(self, task_id):
        scenes = self.list_scenes(task_id)
        return scenes[0] if scenes else None

    # -- publishes -------------------------------------------------------

    def next_publish_version(self, task_id, format_name):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(version) AS latest FROM publish"
                " WHERE task_id = ? AND format = ?",
                (task_id, format_name),
            ).fetchone()
            return (row["latest"] or 0) + 1

    def claim_publish_version(self, task_id, name, format_name, variant, user=""):
        """Atomically reserve the next publish version for a task+format."""
        for _ in range(50):
            version = self.next_publish_version(task_id, format_name)
            try:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT INTO publish (id, task_id, name, format, variant,"
                        " version, user, status, created_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                        (str(uuid.uuid4()), task_id, name, format_name, variant,
                         version, user, utc_now()),
                    )
                return version
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("could not claim a publish version (database contention)")

    def complete_publish(self, task_id, format_name, version, report,
                         path="", report_path="", thumbnail="", comment="",
                         user="", source_file=""):
        with self._connect() as conn:
            conn.execute(
                "UPDATE publish SET status = 'complete', passed = ?, errors = ?,"
                " warnings = ?, path = ?, report_path = ?, thumbnail = ?,"
                " comment = ?, user = ?, source_file = ?, created_at = ?"
                " WHERE task_id = ? AND format = ? AND version = ?",
                (
                    1 if report.passed else 0, report.error_count,
                    report.warning_count, path, report_path, thumbnail,
                    comment or "", user or "", source_file or "", utc_now(),
                    task_id, format_name, int(version),
                ),
            )

    def release_publish(self, task_id, format_name, version):
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM publish WHERE task_id = ? AND format = ?"
                " AND version = ? AND status = 'pending'",
                (task_id, format_name, int(version)),
            )

    def record_blocked_publish(self, task_id, name, format_name, variant, report,
                               report_path="", comment="", user=""):
        """A publish attempt that failed validation: no version, logged."""
        row_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO publish (id, task_id, name, format, variant, version,"
                " passed, errors, warnings, report_path, comment, user, created_at)"
                " VALUES (?, ?, ?, ?, ?, NULL, 0, ?, ?, ?, ?, ?, ?)",
                (
                    row_id, task_id, name, format_name, variant,
                    report.error_count, report.warning_count, report_path,
                    comment or "", user or "", utc_now(),
                ),
            )
        return row_id

    def list_publishes(self, task_id):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM publish WHERE task_id = ? AND status = 'complete'"
                " AND deleted_at = '' ORDER BY created_at DESC, rowid DESC",
                (task_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_publish(self, task_id, format_name, version):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM publish WHERE task_id = ? AND format = ?"
                " AND version = ? AND status = 'complete' AND deleted_at = ''",
                (task_id, format_name, version),
            ).fetchone()
            return dict(row) if row else None

    def latest_publish(self, task_id, format_name=None):
        with self._connect() as conn:
            if format_name:
                row = conn.execute(
                    "SELECT * FROM publish WHERE task_id = ? AND format = ?"
                    " AND version IS NOT NULL AND status = 'complete'"
                    " AND deleted_at = '' ORDER BY version DESC LIMIT 1",
                    (task_id, format_name),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM publish WHERE task_id = ? AND version IS NOT NULL"
                    " AND status = 'complete' AND deleted_at = ''"
                    " ORDER BY created_at DESC LIMIT 1",
                    (task_id,),
                ).fetchone()
            return dict(row) if row else None

    def known_variants(self, task_id, format_name, name):
        """Map variant -> latest live version for one publish name."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT variant, MAX(version) AS version FROM publish"
                " WHERE task_id = ? AND format = ? AND name = ?"
                " AND version IS NOT NULL AND status = 'complete'"
                " AND deleted_at = '' GROUP BY variant",
                (task_id, format_name, name),
            ).fetchall()
            return {row["variant"]: row["version"] for row in rows}

    def publish_history(self, limit=100):
        """Whole-project publish log with entity/task context, newest first."""
        query = """
            SELECT p.*, t.name AS task, e.name AS entity, e.kind AS kind
            FROM publish p
            JOIN task t ON t.id = p.task_id
            JOIN entity e ON e.id = t.entity_id
            WHERE p.status = 'complete' AND p.deleted_at = ''
            ORDER BY p.created_at DESC, p.rowid DESC LIMIT ?
        """
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, (int(limit),)).fetchall()]

    def recent_scenes(self, limit=20):
        """Whole-project scene saves with entity/task context, newest first."""
        query = """
            SELECT s.*, t.name AS task, e.name AS entity, e.kind AS kind
            FROM scene s
            JOIN task t ON t.id = s.task_id
            JOIN entity e ON e.id = t.entity_id
            WHERE s.status = 'complete' AND s.deleted_at = ''
            ORDER BY s.created_at DESC, s.rowid DESC LIMIT ?
        """
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, (int(limit),)).fetchall()]

    # -- edits & soft deletion ------------------------------------------

    def update_scene_notes(self, task_id, version, notes, name="main"):
        with self._connect() as conn:
            conn.execute(
                "UPDATE scene SET notes = ? WHERE task_id = ? AND name = ?"
                " AND version = ?",
                (notes or "", task_id, name, int(version)),
            )

    def update_publish_comment(self, task_id, format_name, version, comment):
        with self._connect() as conn:
            conn.execute(
                "UPDATE publish SET comment = ? WHERE task_id = ? AND format = ?"
                " AND version = ?",
                (comment or "", task_id, format_name, int(version)),
            )

    def delete_scene(self, task_id, version, name="main"):
        row = self.get_scene(task_id, version, name)
        if row is None:
            raise ValueError("no scene v%03d on that task" % int(version))
        with self._connect() as conn:
            conn.execute(
                "UPDATE scene SET deleted_at = ? WHERE id = ?", (utc_now(), row["id"])
            )
        return row

    def delete_publish(self, task_id, format_name, version):
        row = self.get_publish(task_id, format_name, version)
        if row is None:
            raise ValueError(
                "no %s publish v%03d on that task" % (format_name, int(version))
            )
        with self._connect() as conn:
            conn.execute(
                "UPDATE publish SET deleted_at = ? WHERE id = ?", (utc_now(), row["id"])
            )
        return row

    def delete_task(self, task_id):
        with self._connect() as conn:
            conn.execute(
                "UPDATE task SET deleted_at = ? WHERE id = ?", (utc_now(), task_id)
            )

    def delete_entity(self, entity_id):
        with self._connect() as conn:
            stamp = utc_now()
            conn.execute(
                "UPDATE entity SET deleted_at = ? WHERE id = ?", (stamp, entity_id)
            )
            conn.execute(
                "UPDATE task SET deleted_at = ? WHERE entity_id = ?"
                " AND deleted_at = ''",
                (stamp, entity_id),
            )

    # -- presence --------------------------------------------------------

    def set_presence(self, user, task_id, scene_version=None, host=""):
        if not user:
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO presence (user, task_id, scene_version, host, updated_at)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(user) DO UPDATE SET task_id = excluded.task_id,"
                " scene_version = excluded.scene_version, host = excluded.host,"
                " updated_at = excluded.updated_at",
                (user, task_id, scene_version, host, utc_now()),
            )

    def clear_presence(self, user):
        with self._connect() as conn:
            conn.execute("DELETE FROM presence WHERE user = ?", (user,))

    def list_presence(self, max_age_hours=8):
        """Fresh presence rows with entity/task context."""
        query = """
            SELECT pr.*, t.name AS task, e.name AS entity, e.kind AS kind
            FROM presence pr
            JOIN task t ON t.id = pr.task_id
            JOIN entity e ON e.id = t.entity_id
        """
        from datetime import datetime, timedelta, timezone

        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(query).fetchall()]
        return [row for row in rows if row["updated_at"] >= cutoff]

    # -- jobs ------------------------------------------------------------

    def enqueue_job(self, job_type, payload, user=""):
        job_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO job (id, type, payload, user, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (job_id, job_type, json.dumps(payload), user, utc_now()),
            )
        return job_id

    def claim_job(self, worker):
        """Atomically claim the oldest queued job (BEGIN IMMEDIATE)."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM job WHERE status = 'queued'"
                " ORDER BY created_at, rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE job SET status = 'running', worker = ?, started_at = ?"
                " WHERE id = ?",
                (worker, utc_now(), row["id"]),
            )
            job = dict(row)
        job["payload"] = json.loads(job["payload"] or "{}")
        return job

    def finish_job(self, job_id, status, log=""):
        with self._connect() as conn:
            conn.execute(
                "UPDATE job SET status = ?, log = ?, finished_at = ? WHERE id = ?",
                (status, (log or "")[-20000:], utc_now(), job_id),
            )

    def cancel_job(self, job_id):
        with self._connect() as conn:
            conn.execute(
                "UPDATE job SET status = 'cancelled', finished_at = ?"
                " WHERE id = ? AND status = 'queued'",
                (utc_now(), job_id),
            )

    def list_jobs(self, limit=50):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM job ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            jobs = [dict(row) for row in rows]
        for job in jobs:
            try:
                job["payload"] = json.loads(job["payload"] or "{}")
            except ValueError:
                job["payload"] = {}
        return jobs

    # -- dependencies ----------------------------------------------------

    def record_dependency(self, task_id, src_task_id, src_format, src_name,
                          src_version=None, user=""):
        """Remember that a task imported a publish. Re-importing updates
        the pin (src_version None = follows latest)."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO dependency (id, task_id, src_task_id, src_format,"
                " src_name, src_version, user, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(task_id, src_task_id, src_format, src_name)"
                " DO UPDATE SET src_version = excluded.src_version,"
                " user = excluded.user, created_at = excluded.created_at",
                (str(uuid.uuid4()), task_id, src_task_id, src_format, src_name,
                 src_version, user, utc_now()),
            )
            row = conn.execute(
                "SELECT id FROM dependency WHERE task_id = ? AND src_task_id = ?"
                " AND src_format = ? AND src_name = ?",
                (task_id, src_task_id, src_format, src_name),
            ).fetchone()
            return row["id"] if row else None

    def dependencies_of(self, task_id):
        """What this task uses, with source context and the latest version."""
        query = """
            SELECT d.*, t.name AS src_task, e.name AS src_entity, e.kind AS src_kind,
                   (SELECT MAX(version) FROM publish p WHERE p.task_id = d.src_task_id
                     AND p.format = d.src_format AND p.name = d.src_name
                     AND p.version IS NOT NULL AND p.status = 'complete'
                     AND p.deleted_at = '') AS latest_version
            FROM dependency d
            JOIN task t ON t.id = d.src_task_id
            JOIN entity e ON e.id = t.entity_id
            WHERE d.task_id = ?
            ORDER BY e.name, t.name
        """
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, (task_id,)).fetchall()]

    def used_by(self, task_id):
        """Which tasks import publishes of this task."""
        query = """
            SELECT d.*, t.name AS consumer_task, e.name AS consumer_entity,
                   e.kind AS consumer_kind
            FROM dependency d
            JOIN task t ON t.id = d.task_id
            JOIN entity e ON e.id = t.entity_id
            WHERE d.src_task_id = ?
            ORDER BY e.name, t.name
        """
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, (task_id,)).fetchall()]

    # -- record sync (database as a rebuildable cache) -------------------

    def get_row(self, table, row_id):
        if table not in RECORD_TABLES:
            raise ValueError("unknown record table %r" % table)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM %s WHERE id = ?" % table, (row_id,)
            ).fetchone()
            return dict(row) if row else None

    def upsert_record(self, table, row):
        """Apply one record sidecar. Returns 'inserted' | 'updated' |
        'conflict' (a *different* record already owns a unique slot, e.g.
        two artists claimed the same version offline)."""
        columns = RECORD_TABLES.get(table)
        if columns is None:
            raise ValueError("unknown record table %r" % table)
        values = tuple(row.get(column) for column in columns)
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM %s WHERE id = ?" % table, (row.get("id"),)
            ).fetchone()
            try:
                if exists:
                    assignments = ", ".join(
                        "%s = ?" % column for column in columns if column != "id"
                    )
                    conn.execute(
                        "UPDATE %s SET %s WHERE id = ?" % (table, assignments),
                        tuple(row.get(c) for c in columns if c != "id")
                        + (row.get("id"),),
                    )
                    return "updated"
                conn.execute(
                    "INSERT INTO %s (%s) VALUES (%s)"
                    % (table, ", ".join(columns), ", ".join("?" * len(columns))),
                    values,
                )
                return "inserted"
            except sqlite3.IntegrityError:
                return "conflict"

    def get_sync_state(self, key):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM sync_state WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else ""

    def set_sync_state(self, key, value):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sync_state (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )

    def latest_hdas(self):
        """The newest live version of every HDA publish in the project —
        used to auto-install a project's toolset on scene load."""
        query = """
            SELECT p.* FROM publish p
            WHERE p.format = 'hda' AND p.version IS NOT NULL
              AND p.status = 'complete' AND p.deleted_at = ''
              AND p.version = (
                  SELECT MAX(q.version) FROM publish q
                  WHERE q.task_id = p.task_id AND q.name = p.name
                    AND q.format = 'hda' AND q.version IS NOT NULL
                    AND q.status = 'complete' AND q.deleted_at = ''
              )
        """
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query).fetchall()]

    def task_context(self, task_id):
        """(kind, entity, task) names for a task id, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT e.kind AS kind, e.name AS entity, t.name AS task"
                " FROM task t JOIN entity e ON e.id = t.entity_id WHERE t.id = ?",
                (task_id,),
            ).fetchone()
            return dict(row) if row else None

    def counts(self):
        with self._connect() as conn:
            entities = conn.execute(
                "SELECT kind, COUNT(*) AS n FROM entity WHERE deleted_at = ''"
                " GROUP BY kind"
            ).fetchall()
            by_kind = {row["kind"]: row["n"] for row in entities}
            publishes = conn.execute(
                "SELECT COUNT(*) AS n FROM publish WHERE version IS NOT NULL"
                " AND status = 'complete' AND deleted_at = ''"
            ).fetchone()["n"]
            return {
                "assets": by_kind.get("asset", 0),
                "shots": by_kind.get("shot", 0),
                "publishes": publishes,
            }
