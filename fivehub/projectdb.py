"""Per-project database.

Every project owns one SQLite file (``project.db``) holding its entities
(assets and shots), their tasks, the versioned work scenes and the publish
history — including blocked publish attempts (``passed = 0``, no version).
Connections are opened per operation with foreign keys enabled.
"""

import os
import sqlite3
import uuid
from contextlib import contextmanager

from .report import utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS entity (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('asset', 'shot')),
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE (kind, name)
);

CREATE TABLE IF NOT EXISTS task (
    id          TEXT PRIMARY KEY,
    entity_id   TEXT NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE (entity_id, name)
);

CREATE TABLE IF NOT EXISTS scene (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES task(id) ON DELETE CASCADE,
    version     INTEGER NOT NULL,
    file        TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    user        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (task_id, version)
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
    created_at  TEXT NOT NULL,
    UNIQUE (task_id, format, version)
);
"""


class ProjectDB:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- entities --------------------------------------------------------

    def create_entity(self, kind, name):
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM entity WHERE kind = ? AND name = ?", (kind, name)
            ).fetchone()
            if existing:
                raise ValueError("%s %r already exists" % (kind, name))
            entity_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO entity (id, kind, name, created_at) VALUES (?, ?, ?, ?)",
                (entity_id, kind, name, utc_now()),
            )
            return entity_id

    def get_entity(self, kind, name):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM entity WHERE kind = ? AND name = ?", (kind, name)
            ).fetchone()
            return dict(row) if row else None

    def list_entities(self, kind):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM entity WHERE kind = ? ORDER BY name COLLATE NOCASE",
                (kind,),
            ).fetchall()
            return [dict(row) for row in rows]

    # -- tasks -----------------------------------------------------------

    def create_task(self, entity_id, name):
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM task WHERE entity_id = ? AND name = ?", (entity_id, name)
            ).fetchone()
            if existing:
                raise ValueError("task %r already exists on this entity" % name)
            task_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO task (id, entity_id, name, created_at) VALUES (?, ?, ?, ?)",
                (task_id, entity_id, name, utc_now()),
            )
            return task_id

    def get_task(self, entity_id, name):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM task WHERE entity_id = ? AND name = ?", (entity_id, name)
            ).fetchone()
            return dict(row) if row else None

    def list_tasks(self, entity_id):
        """Tasks of an entity with scene/publish counts for browsing."""
        query = """
            SELECT t.*,
                   (SELECT COUNT(*) FROM scene s WHERE s.task_id = t.id) AS scene_count,
                   (SELECT COUNT(*) FROM publish p
                     WHERE p.task_id = t.id AND p.version IS NOT NULL) AS publish_count
            FROM task t WHERE t.entity_id = ? ORDER BY t.name
        """
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, (entity_id,)).fetchall()]

    # -- scenes ----------------------------------------------------------

    def next_scene_version(self, task_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(version) AS latest FROM scene WHERE task_id = ?", (task_id,)
            ).fetchone()
            return (row["latest"] or 0) + 1

    def record_scene(self, task_id, version, file, notes="", user=""):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO scene (id, task_id, version, file, notes, user, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), task_id, int(version), file, notes, user, utc_now()),
            )

    def list_scenes(self, task_id):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scene WHERE task_id = ? ORDER BY version DESC", (task_id,)
            ).fetchall()
            return [dict(row) for row in rows]

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

    def record_publish(self, task_id, name, format_name, variant, version, report,
                       path="", report_path="", thumbnail="", comment="", user=""):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO publish (id, task_id, name, format, variant, version, passed,"
                " errors, warnings, path, report_path, thumbnail, comment, user, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), task_id, name, format_name, variant, version,
                    1 if report.passed else 0, report.error_count, report.warning_count,
                    path, report_path, thumbnail, comment, user, utc_now(),
                ),
            )

    def list_publishes(self, task_id):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM publish WHERE task_id = ?"
                " ORDER BY created_at DESC, rowid DESC",
                (task_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_publish(self, task_id, format_name, version):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM publish WHERE task_id = ? AND format = ? AND version = ?",
                (task_id, format_name, version),
            ).fetchone()
            return dict(row) if row else None

    def latest_publish(self, task_id, format_name=None):
        with self._connect() as conn:
            if format_name:
                row = conn.execute(
                    "SELECT * FROM publish WHERE task_id = ? AND format = ?"
                    " AND version IS NOT NULL ORDER BY version DESC LIMIT 1",
                    (task_id, format_name),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM publish WHERE task_id = ? AND version IS NOT NULL"
                    " ORDER BY created_at DESC LIMIT 1",
                    (task_id,),
                ).fetchone()
            return dict(row) if row else None

    def known_variants(self, task_id, format_name, name):
        """Map variant -> latest version for one publish name in a task."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT variant, MAX(version) AS version FROM publish"
                " WHERE task_id = ? AND format = ? AND name = ? AND version IS NOT NULL"
                " GROUP BY variant",
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
            ORDER BY s.created_at DESC, s.rowid DESC LIMIT ?
        """
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, (int(limit),)).fetchall()]

    def counts(self):
        with self._connect() as conn:
            entities = conn.execute(
                "SELECT kind, COUNT(*) AS n FROM entity GROUP BY kind"
            ).fetchall()
            by_kind = {row["kind"]: row["n"] for row in entities}
            publishes = conn.execute(
                "SELECT COUNT(*) AS n FROM publish WHERE version IS NOT NULL"
            ).fetchone()["n"]
            return {
                "assets": by_kind.get("asset", 0),
                "shots": by_kind.get("shot", 0),
                "publishes": publishes,
            }
