"""Pipeline cache nomenclature — the flagship drop-in tool.

One source of truth for where sim/geo caches live and how they are named:

    <task>/caches/<cacheName>/v###/<Entity>_<task>_<cacheName>_v###.$F4.bgeo.sc

Three faces of the same rule, all registered from this one module:

- ``cache_dir`` / ``cache_file_pattern`` — importable API for other tools
- ``python -m fivehub.cli cache-path ...`` — for shell scripts and ROPs
- FIVE HUB > Pipeline Tools > "Create Pipeline File Cache" — drops a
  filecache SOP after the selected node, pre-pointed at the right place
  (via the $FH_CACHES variable FiveHub binds on scene load/save)
"""

import os

from . import cli_command, houdini_tool
from .. import config


def cache_file_pattern(entity, task, name, version, extension=".bgeo.sc"):
    """`<Entity>_<task>_<name>_v###.$F4<ext>` — the cache file nomenclature."""
    return "%s_%s_%s_%s.$F4%s" % (
        entity, task, name, config.version_label(version), extension
    )


def cache_dir(project, kind, entity, task, name, version):
    return os.path.join(
        project.caches_dir(kind, entity, task), name, config.version_label(version)
    )


def _configure(parser):
    parser.add_argument("project")
    parser.add_argument("kind", choices=config.KINDS)
    parser.add_argument("entity")
    parser.add_argument("task")
    parser.add_argument("name", help="cache name, e.g. smoke")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--ext", default=".bgeo.sc")


@cli_command("cache-path", "pipeline cache directory + file nomenclature", _configure)
def run(root, args):
    from ..project import get_project

    project = get_project(args.project, root)
    project._task_record(args.kind, args.entity, args.task)  # validate context
    directory = cache_dir(
        project, args.kind, args.entity, args.task, args.name, args.version
    )
    return {
        "dir": directory,
        "file": os.path.join(
            directory,
            cache_file_pattern(args.entity, args.task, args.name, args.version, args.ext),
        ),
    }


@houdini_tool("Create Pipeline File Cache")
def create_file_cache():
    """A filecache SOP wired to the pipeline: caches land under $FH_CACHES
    (the current task's caches directory) with the correct nomenclature."""
    import hou
    import fivehub_houdini

    context = fivehub_houdini._current_context()
    if context is None:
        hou.ui.displayMessage(
            "Save the scene in the pipeline first (FIVE HUB > Save Scene As...) —\n"
            "the cache path comes from the scene's project/entity/task.",
            severity=hou.severityType.Error, title="FIVE HUB",
        )
        return None
    selected = hou.selectedNodes()
    if not (selected and selected[0].type().category() == hou.sopNodeTypeCategory()):
        hou.ui.displayMessage(
            "Select the SOP node to cache.", title="FIVE HUB"
        )
        return None
    source = selected[0]

    pressed, values = hou.ui.readMultiInput(
        "Cache name", ("Name",),
        initial_contents=(source.name(),),
        buttons=("Create", "Cancel"), default_choice=0, close_choice=1,
        title="FIVE HUB",
    )
    if pressed != 0:
        return None
    from ..naming import make_identifier

    cache_name = make_identifier(values[0].strip() or source.name())

    parent = source.parent()
    node = None
    for type_name in ("filecache::2.0", "filecache"):
        try:
            node = parent.createNode(type_name, "CACHE_%s" % cache_name)
            break
        except hou.OperationFailed:
            continue
    if node is None:
        hou.ui.displayMessage("No filecache SOP available in this build.",
                              severity=hou.severityType.Error, title="FIVE HUB")
        return None
    node.setFirstInput(source)

    base_name = cache_file_pattern(
        context["entity"], context["task"], cache_name, 1
    ).replace("_v001.$F4.bgeo.sc", "")
    # filecache 2.0 splits dir/name/version; 1.0 takes one file path.
    if node.parm("basedir") is not None:
        node.parm("basedir").set("$FH_CACHES/%s" % cache_name)
        if node.parm("basename") is not None:
            node.parm("basename").set(base_name)
        if node.parm("enableversion") is not None:
            node.parm("enableversion").set(1)
        if node.parm("version") is not None:
            node.parm("version").set(1)
    elif node.parm("file") is not None:
        node.parm("file").set(
            "$FH_CACHES/%s/v001/%s"
            % (cache_name, cache_file_pattern(context["entity"], context["task"],
                                              cache_name, 1))
        )
    if node.parm("trange") is not None:
        node.parm("trange").set(1)

    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    node.moveToGoodPosition()
    return node
