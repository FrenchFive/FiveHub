"""FiveHub drop-in tools.

This package is where the pipeline grows. Any ``.py`` module placed here is
discovered automatically and can plug into every FiveHub surface by using
the decorators below — no core file needs editing:

    from fivehub.tools import cli_command, houdini_tool, job_handler, validation_rule

    @cli_command("my-thing", "what it does", configure=_add_args)
    def run(root, args): ...            # becomes `python -m fivehub.cli my-thing`

    @houdini_tool("My Thing...")
    def my_thing(): ...                 # appears in FIVE HUB > Pipeline Tools

    @job_handler("mytype")
    def handle(project, job): ...       # executed by the fivehub worker

    @validation_rule
    class MyRule(Rule): ...             # joins the USD publish rule chain

``cachepath.py`` in this package is a working example of all of it.
Pipeline HDAs don't need Python at all — drop ``.hda`` files into
``houdini/otls/`` and Houdini loads them on launch.
"""

import importlib
import pkgutil
import sys

REGISTRY = {"cli": [], "rules": [], "jobs": {}, "houdini": []}
_loaded = False


def cli_command(name, help_text="", configure=None):
    """Register a CLI subcommand: ``run(root, args) -> dict`` (printed as
    JSON). ``configure(parser)`` adds arguments."""

    def decorator(func):
        REGISTRY["cli"].append(
            {"name": name, "help": help_text, "configure": configure, "run": func}
        )
        return func

    return decorator


def validation_rule(rule_class):
    """Add a Rule subclass to the USD publish validation chain."""
    REGISTRY["rules"].append(rule_class)
    return rule_class


def job_handler(job_type):
    """Register a worker job handler: ``handle(project, job) -> (status, log)``."""

    def decorator(func):
        REGISTRY["jobs"][job_type] = func
        return func

    return decorator


def houdini_tool(label):
    """Register an in-Houdini tool, listed under FIVE HUB > Pipeline Tools.
    The callable runs inside the Houdini session (import ``hou`` inside it)."""

    def decorator(func):
        REGISTRY["houdini"].append({"label": label, "run": func})
        return func

    return decorator


def load_tools():
    """Import every module in this package once; a broken tool is reported
    on stderr and skipped — it never takes the pipeline down."""
    global _loaded
    if _loaded:
        return REGISTRY
    _loaded = True
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_"):
            continue
        try:
            importlib.import_module("%s.%s" % (__name__, module_info.name))
        except Exception as error:  # noqa: BLE001 — isolation is the point
            print(
                "fivehub tool %r failed to load: %r" % (module_info.name, error),
                file=sys.stderr,
            )
    return REGISTRY
