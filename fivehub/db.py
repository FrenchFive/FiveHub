"""Hub index database.

SQLite, one file under the hub root. Replaces the old single-table schema
with assets, immutable versions and a publish log (every attempt, including
failed validations). Connections are opened per operation with foreign keys
enabled — no module-level global connection.
"""

import os
import sqlite3
import uuid
from contextlib import contextmanager

from .report import utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS asset (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    project     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS version (
    id          TEXT PRIMARY KEY,
    asset_id    TEXT NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    version     INTEGER NOT NULL,
    variant     TEXT NOT NULL DEFAULT 'default',
    comment     TEXT NOT NULL DEFAULT '',
    entry_layer TEXT NOT NULL,
    thumbnail   TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (asset_id, version)
);

CREATE TABLE IF NOT EXISTS publish_log (
    id          TEXT PRIMARY KEY,
    asset_name  TEXT NOT NULL,
    project     TEXT NOT NULL DEFAULT '',
    variant     TEXT NOT NULL DEFAULT 'default',
    passed      INTEGER NOT NULL,
    errors      INTEGER NOT NULL DEFAULT 0,
    warnings    INTEGER NOT NULL DEFAULT 0,
    version     INTEGER,
    report_path TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
"""


class Database:
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

    # -- assets ----------------------------------------------------------

    def get_or_create_asset(self, name, project=""):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM asset WHERE name = ?", (name,)).fetchone()
            if row:
                if project and not row["project"]:
                    conn.execute(
                        "UPDATE asset SET project = ? WHERE id = ?", (project, row["id"])
                    )
                return dict(row)
            asset = {
                "id": str(uuid.uuid4()),
                "name": name,
                "project": project or "",
                "created_at": utc_now(),
            }
            conn.execute(
                "INSERT INTO asset (id, name, project, created_at) VALUES (?, ?, ?, ?)",
                (asset["id"], asset["name"], asset["project"], asset["created_at"]),
            )
            return asset

    def get_asset(self, name):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM asset WHERE name = ?", (name,)).fetchone()
            return dict(row) if row else None

    def list_assets(self):
        """All assets with latest-version info, for the library view."""
        query = """
            SELECT a.id, a.name, a.project, a.created_at,
                   COUNT(v.id) AS version_count,
                   MAX(v.version) AS latest_version,
                   GROUP_CONCAT(DISTINCT v.variant) AS variants
            FROM asset a
            LEFT JOIN version v ON v.asset_id = a.id
            GROUP BY a.id
            ORDER BY a.name COLLATE NOCASE
        """
        with self._connect() as conn:
            assets = []
            for row in conn.execute(query).fetchall():
                asset = dict(row)
                asset["variants"] = sorted((asset.get("variants") or "").split(",")) if asset.get("variants") else []
                latest = conn.execute(
                    "SELECT thumbnail, entry_layer, created_at FROM version "
                    "WHERE asset_id = ? ORDER BY version DESC LIMIT 1",
                    (asset["id"],),
                ).fetchone()
                asset["thumbnail"] = latest["thumbnail"] if latest else ""
                asset["entry_layer"] = latest["entry_layer"] if latest else ""
                asset["updated_at"] = latest["created_at"] if latest else asset["created_at"]
                assets.append(asset)
            return assets

    def list_projects(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT project FROM asset WHERE project != '' ORDER BY project"
            ).fetchall()
            return [row["project"] for row in rows]

    # -- versions --------------------------------------------------------

    def next_version(self, asset_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(version) AS latest FROM version WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            return (row["latest"] or 0) + 1

    def record_version(self, asset_id, version, variant, comment, entry_layer, thumbnail):
        record = {
            "id": str(uuid.uuid4()),
            "asset_id": asset_id,
            "version": int(version),
            "variant": variant,
            "comment": comment or "",
            "entry_layer": entry_layer,
            "thumbnail": thumbnail or "",
            "created_at": utc_now(),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO version (id, asset_id, version, variant, comment, entry_layer,"
                " thumbnail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record["id"], record["asset_id"], record["version"], record["variant"],
                    record["comment"], record["entry_layer"], record["thumbnail"],
                    record["created_at"],
                ),
            )
        return record

    def list_versions(self, asset_id):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM version WHERE asset_id = ? ORDER BY version DESC", (asset_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def latest_version_for_variant(self, asset_id, variant):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM version WHERE asset_id = ? AND variant = ? "
                "ORDER BY version DESC LIMIT 1",
                (asset_id, variant),
            ).fetchone()
            return dict(row) if row else None

    def known_variants(self, asset_id):
        """Map variant name -> latest version number that published it."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT variant, MAX(version) AS version FROM version "
                "WHERE asset_id = ? GROUP BY variant",
                (asset_id,),
            ).fetchall()
            return {row["variant"]: row["version"] for row in rows}

    # -- publish log -----------------------------------------------------

    def record_publish(self, asset_name, project, variant, report, version, report_path):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO publish_log (id, asset_name, project, variant, passed, errors,"
                " warnings, version, report_path, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), asset_name, project or "", variant,
                    1 if report.passed else 0, report.error_count, report.warning_count,
                    version, report_path or "", utc_now(),
                ),
            )

    def publish_history(self, limit=50):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM publish_log ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [dict(row) for row in rows]
