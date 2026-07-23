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
from .project import create_project, get_project, list_projects
from .report import ValidationReport, utc_now


def cmd_root(root, _args):
    return {
        "root": root,
        "projects": config.projects_path(root),
        "version": __version__,
        "kinds": list(config.KINDS),
        "formats": list(config.FORMATS),
        "default_format": config.DEFAULT_FORMAT,
        "default_tasks": list(config.DEFAULT_TASKS),
    }


def cmd_projects(root, _args):
    return {"projects": list_projects(root)}


def cmd_project_create(root, args):
    project = create_project(args.name, image=args.image or None, hub_root=root)
    return {"project": {"name": project.name, **project.meta(),
                        "image_path": project.image_path()}}


def cmd_entity_create(root, args):
    project = get_project(args.project, root)
    project.create_entity(args.kind, args.name)
    return {"created": {"project": args.project, "kind": args.kind, "name": args.name}}


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
    scenes = project.scenes(args.kind, args.entity, args.task)
    publishes = project.publishes(args.kind, args.entity, args.task)
    return {
        "context": {
            "project": args.project,
            "kind": args.kind,
            "entity": args.entity,
            "task": args.task,
        },
        "scenes": scenes,
        "publishes": publishes,
    }


def cmd_report(root, args):
    return {"report": ValidationReport.load(args.path).to_dict(), "path": args.path}


def cmd_log(root, args):
    project = get_project(args.project, root)
    return {"log": project.db.publish_history(limit=args.limit)}


def cmd_send(root, args):
    """Stage a publish for pickup by the Houdini import tool."""
    project = get_project(args.project, root)
    task_record = project._task_record(args.kind, args.entity, args.task)
    format_name = args.format or config.DEFAULT_FORMAT

    if args.version:
        row = project.db.get_publish(task_record["id"], format_name, args.version)
        if row is None:
            raise SystemExit(
                "no %s publish v%03d on that task" % (format_name, args.version)
            )
        path = row["path"]
        name = row["name"]
    else:
        row = project.db.latest_publish(task_record["id"], format_name)
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

    create = commands.add_parser("project-create", help="create a project")
    create.add_argument("name")
    create.add_argument("--image", default="", help="image file for the project")
    create.set_defaults(func=cmd_project_create)

    entity = commands.add_parser("entity-create", help="create an asset or shot")
    entity.add_argument("project")
    entity.add_argument("kind", choices=config.KINDS)
    entity.add_argument("name")
    entity.set_defaults(func=cmd_entity_create)

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
