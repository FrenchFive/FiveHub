"""JSON command-line interface.

Every command prints a single JSON document on stdout — this is the contract
the Electron app builds on (it spawns ``python -m fivehub.cli ...`` instead of
linking a native SQLite driver), and it doubles as a scripting surface for
pipeline tooling.
"""

import argparse
import json
import os
import sys

from . import __version__, config
from .db import Database
from .report import ValidationReport, utc_now


def _database(root):
    return Database(config.db_path(root))


def cmd_root(root, _args):
    return {
        "root": root,
        "assets": config.assets_path(root),
        "database": config.db_path(root),
        "version": __version__,
    }


def cmd_list(root, _args):
    return {"assets": _database(root).list_assets()}


def cmd_projects(root, _args):
    return {"projects": _database(root).list_projects()}


def cmd_show(root, args):
    database = _database(root)
    asset = database.get_asset(args.name)
    if not asset:
        raise SystemExit("unknown asset: %s" % args.name)
    versions = database.list_versions(asset["id"])
    for version in versions:
        report_path = os.path.join(os.path.dirname(version["entry_layer"]), config.REPORT_FILE)
        version["report_path"] = report_path if os.path.isfile(report_path) else ""
    asset["versions"] = versions
    asset["variants"] = database.known_variants(asset["id"])
    asset["root_layer"] = os.path.join(
        config.assets_path(root), asset["name"], "%s.usda" % asset["name"]
    )
    return {"asset": asset}


def cmd_report(root, args):
    if args.path:
        return {"report": ValidationReport.load(args.path).to_dict(), "path": args.path}
    database = _database(root)
    asset = database.get_asset(args.name)
    if not asset:
        raise SystemExit("unknown asset: %s" % args.name)
    versions = database.list_versions(asset["id"])
    if args.version:
        versions = [v for v in versions if v["version"] == args.version]
    if not versions:
        raise SystemExit("no such version for asset %s" % args.name)
    path = os.path.join(os.path.dirname(versions[0]["entry_layer"]), config.REPORT_FILE)
    return {"report": ValidationReport.load(path).to_dict(), "path": path}


def cmd_log(root, args):
    return {"log": _database(root).publish_history(limit=args.limit)}


def cmd_send(root, args):
    """Stage an asset for pickup by the DCC import tool (exchange file)."""
    database = _database(root)
    asset = database.get_asset(args.name)
    if not asset:
        raise SystemExit("unknown asset: %s" % args.name)
    if args.version:
        version = next(
            (v for v in database.list_versions(asset["id"]) if v["version"] == args.version),
            None,
        )
        if version is None:
            raise SystemExit("no such version for asset %s" % args.name)
        layer = version["entry_layer"]
    else:
        # Root layer tracks the latest publish of every variant.
        layer = os.path.join(config.assets_path(root), asset["name"], "%s.usda" % asset["name"])
    selection = {
        "asset": asset["name"],
        "version": args.version or None,
        "layer": layer,
        "written_at": utc_now(),
    }
    path = config.selection_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(selection, handle, indent=2)
    return {"selection": selection, "path": path}


def cmd_demo(root, _args):
    from .demo import run_demo

    results = run_demo(root)
    return {"results": [result.to_dict() for result in results]}


def build_parser():
    parser = argparse.ArgumentParser(prog="fivehub", description=__doc__)
    parser.add_argument("--hub", help="hub root override (defaults to $FIVEHUB_ROOT)")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("root", help="resolved hub paths").set_defaults(func=cmd_root)
    commands.add_parser("list", help="all assets with latest version info").set_defaults(func=cmd_list)
    commands.add_parser("projects", help="distinct project names").set_defaults(func=cmd_projects)

    show = commands.add_parser("show", help="asset detail with versions")
    show.add_argument("name")
    show.set_defaults(func=cmd_show)

    report = commands.add_parser("report", help="validation report for a version")
    report.add_argument("name", nargs="?", default="")
    report.add_argument("--version", type=int, default=0)
    report.add_argument("--path", default="", help="load a report JSON directly")
    report.set_defaults(func=cmd_report)

    log = commands.add_parser("log", help="publish history, newest first")
    log.add_argument("--limit", type=int, default=50)
    log.set_defaults(func=cmd_log)

    send = commands.add_parser("send", help="stage an asset for the DCC import tool")
    send.add_argument("name")
    send.add_argument("--version", type=int, default=0)
    send.set_defaults(func=cmd_send)

    commands.add_parser("demo", help="publish demo assets (incl. a failing one)").set_defaults(
        func=cmd_demo
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = config.ensure_hub(args.hub)
    result = args.func(root, args)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
