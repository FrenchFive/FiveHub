"""JSON command-line interface.

Every command prints a single JSON document on stdout — this is the contract
the FiveHub app builds on (it spawns ``python -m fivehub.cli ...`` instead of
linking a native SQLite driver), and it doubles as a scripting surface.
"""

import argparse
import json
import os
import sys

from . import __version__, config
from .project import create_project, get_project, list_projects, remove_project
from .report import ValidationReport, utc_now
from .user import get_user, logged_in, set_user


def cmd_root(root, _args):
    return {
        "root": root,
        "projects": config.projects_path(root),
        "version": __version__,
        "kinds": list(config.KINDS),
        "formats": list(config.FORMATS),
        "default_format": config.DEFAULT_FORMAT,
        "default_tasks": list(config.DEFAULT_TASKS),
        "user": get_user() if logged_in() else "",
    }


def cmd_login(_root, args):
    return {"user": set_user(args.name)}


def cmd_whoami(_root, _args):
    return {"user": get_user() if logged_in() else "", "fallback": get_user()}


def cmd_projects(root, _args):
    return {"projects": list_projects(root)}


def cmd_project_create(root, args):
    project = create_project(
        args.name,
        image=args.image or None,
        hub_root=root,
        location=args.location or None,
    )
    return {"project": {"name": project.name, **project.meta(),
                        "root": project.root,
                        "image_path": project.image_path()}}


def _entity_fields(args):
    fields = {}
    for key in ("sequence", "frame_start", "frame_end", "fps", "res_x", "res_y"):
        value = getattr(args, key, None)
        if value not in (None, ""):
            fields[key] = value
    return fields


def cmd_entity_create(root, args):
    project = get_project(args.project, root)
    project.create_entity(args.kind, args.name, **_entity_fields(args))
    return {"created": {"project": args.project, "kind": args.kind, "name": args.name}}


def cmd_entity_update(root, args):
    project = get_project(args.project, root)
    fields = _entity_fields(args)
    project.update_entity(args.kind, args.name, **fields)
    return {"updated": {"kind": args.kind, "name": args.name, **fields}}


def cmd_task_create(root, args):
    project = get_project(args.project, root)
    task = project.create_task(args.kind, args.entity, args.name)
    return {
        "created": {
            "project": args.project,
            "kind": args.kind,
            "entity": args.entity,
            "task": task,
        }
    }


def cmd_browse(root, args):
    return {"project": get_project(args.project, root).browse()}


def cmd_task_info(root, args):
    project = get_project(args.project, root)
    task_record = project._task_record(args.kind, args.entity, args.task)
    dependencies = project.db.dependencies_of(task_record["id"])
    for dep in dependencies:
        dep["outdated"] = bool(
            dep["src_version"]
            and dep["latest_version"]
            and dep["latest_version"] > dep["src_version"]
        )
    return {
        "context": {
            "project": args.project,
            "kind": args.kind,
            "entity": args.entity,
            "task": args.task,
        },
        "root": project.root,
        "entity": project.db.get_entity(args.kind, args.entity),
        "scenes": project.scenes(args.kind, args.entity, args.task),
        "publishes": project.publishes(args.kind, args.entity, args.task),
        "presence": project.task_presence(args.kind, args.entity, args.task),
        "uses": dependencies,
        "used_by": project.db.used_by(task_record["id"]),
    }


def cmd_report(root, args):
    return {"report": ValidationReport.load(args.path).to_dict(), "path": args.path}


def cmd_log(root, args):
    project = get_project(args.project, root)
    return {"log": project.db.publish_history(limit=args.limit)}


def cmd_activity(root, args):
    """Project-scoped recent activity: publishes and scene saves."""
    project = get_project(args.project, root)
    return {
        "project": args.project,
        "publishes": project.db.publish_history(limit=args.limit),
        "scenes": project.db.recent_scenes(limit=args.limit),
    }


def cmd_send(root, args):
    """Stage a publish for pickup by the Houdini import tool."""
    project = get_project(args.project, root)
    format_name = args.format or config.DEFAULT_FORMAT

    if args.version:
        row = project.get_publish(
            args.kind, args.entity, args.task, format_name, args.version
        )
        if row is None:
            raise SystemExit(
                "no %s publish v%03d on that task" % (format_name, args.version)
            )
        path = row["path"]
        name = row["name"]
    else:
        row = project.latest_publish(args.kind, args.entity, args.task, format_name)
        if row is None:
            raise SystemExit("no %s publish on that task yet" % format_name)
        name = row["name"]
        if format_name == "usd":
            # Root interface tracks the latest version of every variant.
            path = os.path.join(
                project.publish_dir(args.kind, args.entity, args.task, "usd"),
                "%s.usda" % name,
            )
        else:
            path = row["path"]

    selection = {
        "project": args.project,
        "kind": args.kind,
        "entity": args.entity,
        "task": args.task,
        "format": format_name,
        "version": args.version or None,
        "name": name,
        "path": path,
        "written_at": utc_now(),
    }
    selection_file = config.selection_path(root)
    os.makedirs(os.path.dirname(selection_file), exist_ok=True)
    with open(selection_file, "w", encoding="utf-8") as handle:
        json.dump(selection, handle, indent=2)
    return {"selection": selection, "path": selection_file}


def cmd_demo(root, _args):
    from .demo import run_demo

    return {"results": run_demo(root)}


def cmd_project_remove(root, args):
    return {"result": remove_project(args.name, root, delete_files=args.delete_files)}


def cmd_entity_delete(root, args):
    get_project(args.project, root).delete_entity(args.kind, args.name)
    return {"deleted": {"project": args.project, "kind": args.kind, "name": args.name}}


def cmd_task_delete(root, args):
    get_project(args.project, root).delete_task(args.kind, args.entity, args.task)
    return {"deleted": {"project": args.project, "entity": args.entity, "task": args.task}}


def cmd_scene_delete(root, args):
    row = get_project(args.project, root).delete_scene(
        args.kind, args.entity, args.task, args.version
    )
    return {"deleted": row}


def cmd_scene_notes(root, args):
    get_project(args.project, root).set_scene_notes(
        args.kind, args.entity, args.task, args.version, args.notes
    )
    return {"updated": {"version": args.version, "notes": args.notes}}


def cmd_publish_delete(root, args):
    row = get_project(args.project, root).delete_publish(
        args.kind, args.entity, args.task, args.format, args.version
    )
    return {"deleted": row}


def cmd_publish_comment(root, args):
    get_project(args.project, root).set_publish_comment(
        args.kind, args.entity, args.task, args.format, args.version, args.comment
    )
    return {"updated": {"version": args.version, "comment": args.comment}}


def cmd_ingest(root, args):
    from .ingest import ingest_files

    result = ingest_files(
        get_project(args.project, root), args.kind, args.entity, args.task,
        args.files, name=args.name or None, comment=args.comment,
    )
    return {"result": result.to_dict()}


def cmd_refs(root, args):
    from .ingest import add_refs, delete_ref, list_refs

    project = get_project(args.project, root)
    if args.add:
        return {"added": add_refs(project, args.add)}
    if args.delete:
        delete_ref(project, args.delete)
        return {"deleted": args.delete}
    return {"refs": list_refs(project)}


def cmd_trash(root, args):
    project = get_project(args.project, root)
    if args.empty:
        return {"purged": project.empty_trash(args.days)}
    trash = project.trash_dir()
    entries = sorted(os.listdir(trash)) if os.path.isdir(trash) else []
    return {"trash": entries}


def cmd_jobs(root, args):
    project = get_project(args.project, root)
    if args.cancel:
        project.db.cancel_job(args.cancel)
        return {"cancelled": args.cancel}
    return {"jobs": project.db.list_jobs(limit=args.limit)}


def cmd_render(root, args):
    from .render import submit_render

    result = submit_render(
        get_project(args.project, root), args.kind, args.entity, args.task,
        args.scene_version, args.rop,
        frame_start=args.start, frame_end=args.end, step=args.step,
    )
    return {"submitted": result}


def cmd_worker(root, args):
    from .worker import run_forever, run_once

    if args.once:
        executed = run_once(root, args.project or None)
        return {"executed": executed}
    run_forever(root, args.project or None, poll_seconds=args.poll)
    return {"stopped": True}


def cmd_assemble(root, args):
    from .assembly import publish_assembly

    result = publish_assembly(
        get_project(args.project, root), args.entity, args.task,
        kind=args.kind, comment=args.comment,
    )
    return {"assembly": result}


def cmd_rebuild(root, args):
    """Rebuild the project database cache from its record sidecars."""
    project = get_project(args.project, root)
    return {"rebuild": project.sync_from_records()}


def cmd_git_status(root, args):
    from . import gitsync

    return {"status": gitsync.status(get_project(args.project, root).root)}


def cmd_git_setup(root, args):
    from . import gitsync

    project = get_project(args.project, root)
    return {"setup": gitsync.setup(project.root, user=get_user())}


def cmd_git_sync(root, args):
    from . import gitsync

    project = get_project(args.project, root)
    result = gitsync.sync(project.root, message=args.message, user=get_user())
    # A pull may have brought teammates' record sidecars — apply them.
    result["rebuild"] = project.sync_from_records()
    return {"sync": result}


def cmd_backup(root, args):
    """Consistent SQLite backups of every project DB + the registry."""
    import sqlite3

    stamp = utc_now().replace(":", "").replace("-", "")
    target_dir = os.path.join(root, "backups", stamp)
    os.makedirs(target_dir, exist_ok=True)
    saved = []
    for info in list_projects(root):
        source = os.path.join(info["path"], config.PROJECT_DB)
        if not os.path.isfile(source):
            continue
        target = os.path.join(target_dir, "%s.db" % info["name"])
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
        saved.append(target)
    registry = os.path.join(root, config.REGISTRY_FILE)
    if os.path.isfile(registry):
        import shutil

        shutil.copyfile(registry, os.path.join(target_dir, config.REGISTRY_FILE))
        saved.append(os.path.join(target_dir, config.REGISTRY_FILE))
    return {"backup_dir": target_dir, "files": saved}


def build_parser():
    parser = argparse.ArgumentParser(prog="fivehub", description=__doc__)
    parser.add_argument("--hub", help="hub root override (defaults to $FIVEHUB_ROOT)")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("root", help="resolved hub paths and constants").set_defaults(
        func=cmd_root
    )
    commands.add_parser("projects", help="all projects with counts").set_defaults(
        func=cmd_projects
    )

    login = commands.add_parser("login", help="set the name that signs your publishes")
    login.add_argument("name")
    login.set_defaults(func=cmd_login)

    commands.add_parser("whoami", help="current signing identity").set_defaults(
        func=cmd_whoami
    )

    create = commands.add_parser("project-create", help="create a project")
    create.add_argument("name")
    create.add_argument("--image", default="", help="image file for the project")
    create.add_argument(
        "--location",
        default="",
        help="directory the project should live in (shared drive, repo, ...);"
        " defaults to the hub's projects directory",
    )
    create.set_defaults(func=cmd_project_create)

    def _entity_flags(parser_):
        parser_.add_argument("--sequence", default="")
        parser_.add_argument("--frame-start", dest="frame_start", type=int, default=None)
        parser_.add_argument("--frame-end", dest="frame_end", type=int, default=None)
        parser_.add_argument("--fps", type=float, default=None)
        parser_.add_argument("--res-x", dest="res_x", type=int, default=None)
        parser_.add_argument("--res-y", dest="res_y", type=int, default=None)

    entity = commands.add_parser("entity-create", help="create an asset or shot")
    entity.add_argument("project")
    entity.add_argument("kind", choices=config.KINDS)
    entity.add_argument("name")
    _entity_flags(entity)
    entity.set_defaults(func=cmd_entity_create)

    entity_update = commands.add_parser(
        "entity-update", help="edit shot metadata (sequence, range, fps, res)"
    )
    entity_update.add_argument("project")
    entity_update.add_argument("kind", choices=config.KINDS)
    entity_update.add_argument("name")
    _entity_flags(entity_update)
    entity_update.set_defaults(func=cmd_entity_update)

    task = commands.add_parser("task-create", help="create a task on an entity")
    task.add_argument("project")
    task.add_argument("kind", choices=config.KINDS)
    task.add_argument("entity")
    task.add_argument("name")
    task.set_defaults(func=cmd_task_create)

    browse = commands.add_parser("browse", help="full project tree")
    browse.add_argument("project")
    browse.set_defaults(func=cmd_browse)

    info = commands.add_parser("task-info", help="scenes and publishes of a task")
    info.add_argument("project")
    info.add_argument("kind", choices=config.KINDS)
    info.add_argument("entity")
    info.add_argument("task")
    info.set_defaults(func=cmd_task_info)

    report = commands.add_parser("report", help="load a validation report JSON")
    report.add_argument("--path", required=True)
    report.set_defaults(func=cmd_report)

    log = commands.add_parser("log", help="project publish history, newest first")
    log.add_argument("project")
    log.add_argument("--limit", type=int, default=100)
    log.set_defaults(func=cmd_log)

    activity = commands.add_parser(
        "activity", help="project-scoped recent publishes and scene saves"
    )
    activity.add_argument("project")
    activity.add_argument("--limit", type=int, default=20)
    activity.set_defaults(func=cmd_activity)

    send = commands.add_parser("send", help="stage a publish for the Houdini import tool")
    send.add_argument("project")
    send.add_argument("kind", choices=config.KINDS)
    send.add_argument("entity")
    send.add_argument("task")
    send.add_argument("--format", default="", choices=("",) + config.FORMATS)
    send.add_argument("--version", type=int, default=0)
    send.set_defaults(func=cmd_send)

    commands.add_parser(
        "demo", help="seed a demo project (incl. a failing publish)"
    ).set_defaults(func=cmd_demo)

    remove = commands.add_parser(
        "project-remove", help="unlink an external project / delete a local one"
    )
    remove.add_argument("name")
    remove.add_argument("--delete-files", action="store_true")
    remove.set_defaults(func=cmd_project_remove)

    entity_delete = commands.add_parser("entity-delete", help="delete an asset or shot")
    entity_delete.add_argument("project")
    entity_delete.add_argument("kind", choices=config.KINDS)
    entity_delete.add_argument("name")
    entity_delete.set_defaults(func=cmd_entity_delete)

    task_delete = commands.add_parser("task-delete", help="delete a task")
    task_delete.add_argument("project")
    task_delete.add_argument("kind", choices=config.KINDS)
    task_delete.add_argument("entity")
    task_delete.add_argument("task")
    task_delete.set_defaults(func=cmd_task_delete)

    scene_delete = commands.add_parser("scene-delete", help="delete a scene version")
    scene_delete.add_argument("project")
    scene_delete.add_argument("kind", choices=config.KINDS)
    scene_delete.add_argument("entity")
    scene_delete.add_argument("task")
    scene_delete.add_argument("version", type=int)
    scene_delete.set_defaults(func=cmd_scene_delete)

    scene_notes = commands.add_parser("scene-notes", help="edit a scene version's notes")
    scene_notes.add_argument("project")
    scene_notes.add_argument("kind", choices=config.KINDS)
    scene_notes.add_argument("entity")
    scene_notes.add_argument("task")
    scene_notes.add_argument("version", type=int)
    scene_notes.add_argument("--notes", default="")
    scene_notes.set_defaults(func=cmd_scene_notes)

    publish_delete = commands.add_parser(
        "publish-delete", help="delete a publish version"
    )
    publish_delete.add_argument("project")
    publish_delete.add_argument("kind", choices=config.KINDS)
    publish_delete.add_argument("entity")
    publish_delete.add_argument("task")
    publish_delete.add_argument("format", choices=config.FORMATS)
    publish_delete.add_argument("version", type=int)
    publish_delete.set_defaults(func=cmd_publish_delete)

    publish_comment = commands.add_parser(
        "publish-comment", help="edit a publish version's comment"
    )
    publish_comment.add_argument("project")
    publish_comment.add_argument("kind", choices=config.KINDS)
    publish_comment.add_argument("entity")
    publish_comment.add_argument("task")
    publish_comment.add_argument("format", choices=config.FORMATS)
    publish_comment.add_argument("version", type=int)
    publish_comment.add_argument("--comment", default="")
    publish_comment.set_defaults(func=cmd_publish_comment)

    ingest = commands.add_parser(
        "ingest", help="publish external files (fbx/abc/usd/textures/...) into a task"
    )
    ingest.add_argument("project")
    ingest.add_argument("kind", choices=config.KINDS)
    ingest.add_argument("entity")
    ingest.add_argument("task")
    ingest.add_argument("files", nargs="+")
    ingest.add_argument("--name", default="")
    ingest.add_argument("--comment", default="")
    ingest.set_defaults(func=cmd_ingest)

    refs = commands.add_parser("refs", help="project reference material gallery")
    refs.add_argument("project")
    refs.add_argument("--add", nargs="+", default=None, help="copy files into refs/")
    refs.add_argument("--delete", default="", help="move a ref to the trash")
    refs.set_defaults(func=cmd_refs)

    trash = commands.add_parser("trash", help="list or purge the project trash")
    trash.add_argument("project")
    trash.add_argument("--empty", action="store_true")
    trash.add_argument("--days", type=int, default=0)
    trash.set_defaults(func=cmd_trash)

    jobs = commands.add_parser("jobs", help="list or cancel project jobs")
    jobs.add_argument("project")
    jobs.add_argument("--limit", type=int, default=50)
    jobs.add_argument("--cancel", default="", help="job id to cancel (if still queued)")
    jobs.set_defaults(func=cmd_jobs)

    render = commands.add_parser("render", help="queue a render of a saved scene")
    render.add_argument("project")
    render.add_argument("kind", choices=config.KINDS)
    render.add_argument("entity")
    render.add_argument("task")
    render.add_argument("scene_version", type=int)
    render.add_argument("rop", help="ROP node path, e.g. /out/mantra1")
    render.add_argument("--start", type=int, default=None)
    render.add_argument("--end", type=int, default=None)
    render.add_argument("--step", type=int, default=1)
    render.set_defaults(func=cmd_render)

    worker = commands.add_parser("worker", help="run the job worker (renders, encodes)")
    worker.add_argument("--project", default="")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--poll", type=int, default=5)
    worker.set_defaults(func=cmd_worker)

    assemble = commands.add_parser(
        "assemble", help="publish a shot assembly from tracked USD dependencies"
    )
    assemble.add_argument("project")
    assemble.add_argument("entity")
    assemble.add_argument("task")
    assemble.add_argument("--kind", choices=config.KINDS, default="shot")
    assemble.add_argument("--comment", default="")
    assemble.set_defaults(func=cmd_assemble)

    rebuild = commands.add_parser(
        "rebuild", help="rebuild a project's database from its record files"
    )
    rebuild.add_argument("project")
    rebuild.set_defaults(func=cmd_rebuild)

    git_status = commands.add_parser("git-status", help="repository state of a project")
    git_status.add_argument("project")
    git_status.set_defaults(func=cmd_git_status)

    git_setup = commands.add_parser(
        "git-setup", help="make a project git-ready (.gitignore, init, first commit)"
    )
    git_setup.add_argument("project")
    git_setup.set_defaults(func=cmd_git_setup)

    git_sync = commands.add_parser(
        "git-sync", help="commit, pull --rebase, push, and apply pulled records"
    )
    git_sync.add_argument("project")
    git_sync.add_argument("--message", default="")
    git_sync.set_defaults(func=cmd_git_sync)

    commands.add_parser(
        "backup", help="back up every project database and the registry"
    ).set_defaults(func=cmd_backup)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = config.ensure_hub(args.hub)
    try:
        result = args.func(root, args)
    except ValueError as error:
        raise SystemExit(str(error))
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
