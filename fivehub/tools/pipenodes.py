"""FIVE HUB pipeline nodes — Pipeline Tools face of PUBLISH / LOADER.

The implementations live in houdini/fivehub_houdini.py (they need hou);
this module lists them in FIVE HUB > Pipeline Tools next to the other
drop-in tools, so they are discoverable from both places.
"""

from . import houdini_tool


@houdini_tool("Create Publish Node")
def create_publish_node():
    """PUBLISH null that owns name/format/variant — republish is the
    button on the node, never a mystery selection."""
    import fivehub_houdini

    return fivehub_houdini.create_publish_node()


@houdini_tool("Update Selected Loaders")
def update_selected_loaders():
    """Run UPDATE TO LATEST on every selected FIVEHUB LOADER node."""
    import hou

    import fivehub_houdini

    updated = []
    for node in hou.selectedNodes():
        if node.parm("fh_update") is not None:
            fivehub_houdini.update_loader(node)
            updated.append(node.name())
    if not updated:
        hou.ui.displayMessage(
            "Select FIVEHUB LOADER node(s) first.", title="FIVE HUB"
        )
    return updated
