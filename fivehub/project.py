"""Projects: creation, browsing, scene versioning and path logic.

A Project wraps one directory under ``<hub>/projects`` and its database.
All name rules are enforced here at creation time, so everything that ever
reaches disk or the database is a valid USD identifier.
"""

import json
import os
import shutil

from . import config, naming
from .projectdb import ProjectDB
from .report import utc_now


class Project:
    def __init__(self, root):
        self.root = root
        self.name = os.path.basename(root)
        self._db = None

    # -- infrastructure --------------------------------------------------

    @property
    def db(self):
        if self._db is None:
            self._db = ProjectDB(os.path.join(self.root, config.PROJECT_DB))
        return self._db

    @property
    def meta_path(self):
        return os.path.join(self.root, config.PROJECT_FILE)

    def meta(self):
        try:
            with open(self.meta_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {"name": self.name, "image": "", "created_at": ""}

    def image_path(self):
        image = self.meta().get("image", "")
        return os.path.join(self.root, image) if image else ""

    def reports_dir(self):
        return os.path.join(self.root, config.PROJECT_REPORTS_DIR)

    # -- paths -----------------------------------------------------------

    def entity_dir(self, kind, entity):
        return os.path.join(self.root, config.kind_dir(kind), entity)

    def task_dir(self, kind, entity, task):
        return os.path.join(self.entity_dir(kind, entity), task)

    def scenes_dir(self, kind, entity, task):
        return os.path.join(self.task_dir(kind, entity, task), config.SCENES_DIR)

    def publish_dir(self, kind, entity, task, format_name):
        return os.path.join(
            self.task_dir(kind, entity, task), config.PUBLISH_DIR, format_name
        )

    def scene_path(self, kind, entity, task, version):
        return os.path.join(
            self.scenes_dir(kind, entity, task),
            config.scene_file_name(entity, task, version),
        )

    # -- entities & tasks ------------------------------------------------

    def create_entity(self, kind, name):
        errors = naming.asset_name_errors(name)
        if errors:
            raise ValueError("; ".join(errors))
        self.db.create_entity(kind, name)
        os.makedirs(self.entity_dir(kind, name), exist_ok=True)
        return name

    def create_task(self, kind, entity, task):
        task = str(task or "").strip().lower()
        if not naming.is_identifier(task):
            raise ValueError(
                "task %r is not a valid identifier (letters, digits, underscores)" % task
            )
        record = self.db.get_entity(kind, entity)
        if record is None:
            raise ValueError("unknown %s %r" % (kind, entity))
        self.db.create_task(record["id"], task)
        os.makedirs(self.scenes_dir(kind, entity, task), exist_ok=True)
        os.makedirs(os.path.join(self.task_dir(kind, entity, task), config.PUBLISH_DIR),
                    exist_ok=True)
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

    # -- scenes ----------------------------------------------------------

    def next_scene_version(self, kind, entity, task):
        return self.db.next_scene_version(self._task_record(kind, entity, task)["id"])

    def next_scene_path(self, kind, entity, task):
        version = self.next_scene_version(kind, entity, task)
        return self.scene_path(kind, entity, task, version), version

    def register_scene(self, kind, entity, task, version, file, notes="", user=""):
        if not os.path.isfile(file):
            raise ValueError("scene file was not written: %s" % file)
        task_record = self._task_record(kind, entity, task)
        self.db.record_scene(task_record["id"], version, file, notes, user)

    def scenes(self, kind, entity, task):
        return self.db.list_scenes(self._task_record(kind, entity, task)["id"])

    # -- publishes -------------------------------------------------------

    def publishes(self, kind, entity, task):
        return self.db.list_publishes(self._task_record(kind, entity, task)["id"])

    def browse(self):
        """Full project tree for the app: entities with their tasks."""
        tree = {"name": self.name, **self.meta(), "image_path": self.image_path()}
        for kind in config.KINDS:
            entries = []
            for entity in self.entities(kind):
                entries.append(
                    {
                        "name": entity["name"],
                        "created_at": entity["created_at"],
                        "tasks": self.db.list_tasks(entity["id"]),
                    }
                )
            tree[config.kind_dir(kind)] = entries
        tree["counts"] = self.db.counts()
        return tree


# -- hub-level operations ------------------------------------------------


def create_project(name, image=None, hub_root=None):
    """Create a project directory, identity card, image and database."""
    errors = naming.asset_name_errors(name)
    if errors:
        raise ValueError("; ".join(errors))
    root = config.ensure_hub(hub_root)
    project_root = os.path.join(config.projects_path(root), name)
    if os.path.exists(project_root):
        raise ValueError("project %r already exists" % name)
    os.makedirs(project_root)
    for sub in (config.ASSETS_DIR, config.SHOTS_DIR, config.PROJECT_REPORTS_DIR):
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

    with open(os.path.join(project_root, config.PROJECT_FILE), "w", encoding="utf-8") as f:
        json.dump({"name": name, "image": image_name, "created_at": utc_now()}, f, indent=2)

    project = Project(project_root)
    project.db  # create the database file up front
    return project


def get_project(name, hub_root=None):
    root = config.ensure_hub(hub_root)
    project_root = os.path.join(config.projects_path(root), name)
    if not os.path.isfile(os.path.join(project_root, config.PROJECT_FILE)):
        raise ValueError("unknown project %r" % name)
    return Project(project_root)


def list_projects(hub_root=None):
    root = config.ensure_hub(hub_root)
    projects = []
    projects_dir = config.projects_path(root)
    for entry in sorted(os.listdir(projects_dir)):
        candidate = os.path.join(projects_dir, entry)
        if not os.path.isfile(os.path.join(candidate, config.PROJECT_FILE)):
            continue
        project = Project(candidate)
        info = {"name": project.name, **project.meta()}
        info["path"] = candidate
        info["image_path"] = project.image_path()
        info["counts"] = project.db.counts()
        projects.append(info)
    return projects


def parse_scene_path(path, hub_root=None):
    """Recover the pipeline context from a scene file path.

    Returns ``{project, kind, entity, task, file}`` when the path lives at
    ``projects/<P>/(assets|shots)/<E>/<task>/scenes/<file>``, else None.
    """
    if not path:
        return None
    root = config.hub_root(hub_root)
    try:
        relative = os.path.relpath(os.path.abspath(path), config.projects_path(root))
    except ValueError:  # different drive on Windows
        return None
    parts = relative.replace(os.sep, "/").split("/")
    if len(parts) != 6 or parts[0] == ".." or parts[4] != config.SCENES_DIR:
        return None
    project, kind_folder, entity, task = parts[0], parts[1], parts[2], parts[3]
    kind = {config.ASSETS_DIR: "asset", config.SHOTS_DIR: "shot"}.get(kind_folder)
    if kind is None:
        return None
    return {
        "project": project,
        "kind": kind,
        "entity": entity,
        "task": task,
        "file": parts[5],
    }
