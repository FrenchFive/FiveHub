"""FiveHub Houdini integration.

Shelf-facing entry points:

    publish()   extract selected geometry, capture a thumbnail, run the
                validated USD publish and show the pass/fail report
    import_asset()  reference a published asset (picks up the selection the
                    hub app staged, or falls back to a file chooser)
    launch_hub()    start the standalone FiveHub Electron app
    reload_fivehub()  developer helper

Geometry is translated to the DCC-neutral fivehub model here; everything
downstream (validation, USD authoring, database) is Houdini-free.
"""

import getpass
import os
import subprocess
import sys

import hou

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (_REPO, os.path.join(_REPO, "houdini")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fivehub import config, naming
from fivehub.geometry import MaterialData, MeshData, PublishRequest, SourceInfo
from fivehub.publish import publish as core_publish


# -- geometry extraction -------------------------------------------------


def _sop_geometry(node):
    """Resolve a selected node (OBJ geo or SOP) to its cooked geometry."""
    category = node.type().category()
    if category == hou.objNodeTypeCategory():
        if node.type().name() != "geo":
            raise ValueError("node %s is not a geo object" % node.path())
        sop = node.displayNode()
        if sop is None:
            raise ValueError("geo object %s has no display SOP" % node.path())
        return sop.geometry()
    if category == hou.sopNodeTypeCategory():
        return node.geometry()
    raise ValueError("unsupported node type: %s" % node.path())


def _object_material(node):
    """Object-level material assignment, used when prims carry none."""
    for parm_name in ("shop_materialpath", "materialpath"):
        parm = node.parm(parm_name)
        if parm:
            path = parm.evalAsString().strip()
            if path:
                return path
    return ""


def _extract_mesh(node, material_paths):
    """Build a MeshData from a node, collecting material paths per face.

    Faces are re-wound to USD's right-handed orientation (Houdini polygons
    are wound the opposite way), and vertex normals follow the same order.
    """
    geo = _sop_geometry(node)
    if geo is None:
        raise ValueError("no geometry on %s" % node.path())

    raw_points = geo.pointFloatAttribValues("P")
    points = [
        (raw_points[i], raw_points[i + 1], raw_points[i + 2])
        for i in range(0, len(raw_points), 3)
    ]

    normal_attrib = geo.findVertexAttrib("N") or geo.findPointAttrib("N")

    counts = []
    indices = []
    normals = [] if normal_attrib else None
    face_materials = []
    skipped = 0

    material_attrib = geo.findPrimAttrib("shop_materialpath")
    default_material = _object_material(node)

    for prim in geo.prims():
        if prim.type() != hou.primType.Polygon or not prim.isClosed():
            skipped += 1
            continue
        vertices = list(prim.vertices())
        vertices.reverse()
        counts.append(len(vertices))
        for vertex in vertices:
            indices.append(vertex.point().number())
            if normals is None:
                continue
            if normal_attrib.type() == hou.attribType.Vertex:
                normals.append(tuple(vertex.attribValue(normal_attrib)))
            else:
                normals.append(tuple(vertex.point().attribValue(normal_attrib)))

        path = ""
        if material_attrib is not None:
            path = prim.attribValue(material_attrib).strip()
        if not path:
            path = default_material
        if path:
            material_paths.setdefault(path, None)
        face_materials.append(path or None)

    mesh_name = naming.make_identifier(node.name())
    mesh = MeshData(
        name=mesh_name,
        points=points,
        face_vertex_counts=counts,
        face_vertex_indices=indices,
        normals=normals,
        face_materials=face_materials,
    )
    return mesh, skipped


def _material_from_path(path, used_names):
    """Turn a Houdini material node path into MaterialData, sampling
    principled shader parameters when the node is reachable."""
    base_name = naming.make_material_name(path.rstrip("/").split("/")[-1])
    name = base_name
    suffix = 1
    while name in used_names:
        suffix += 1
        name = "%s_%d" % (base_name, suffix)
    used_names.add(name)

    material = MaterialData(name=name, source_path=path)
    node = hou.node(path)
    if node is None:
        return material

    def _parm(name_x, default):
        parm = node.parm(name_x)
        try:
            return parm.eval() if parm else default
        except hou.OperationFailed:
            return default

    tuple_parm = node.parmTuple("basecolor")
    if tuple_parm:
        try:
            material.base_color = tuple(tuple_parm.eval())
        except hou.OperationFailed:
            pass
    material.roughness = float(_parm("rough", material.roughness))
    material.metallic = float(_parm("metallic", material.metallic))
    return material


def _build_request(nodes, name, project, variant, comment):
    material_paths = {}
    meshes = []
    skipped_total = 0
    used_mesh_names = set()

    for node in nodes:
        mesh, skipped = _extract_mesh(node, material_paths)
        skipped_total += skipped
        base = mesh.name
        counter = 1
        while mesh.name in used_mesh_names:
            counter += 1
            mesh.name = "%s_%d" % (base, counter)
        used_mesh_names.add(mesh.name)
        meshes.append(mesh)

    # Path -> MaterialData, then rewrite per-face paths to material names.
    used_names = set()
    materials_by_path = {
        path: _material_from_path(path, used_names) for path in material_paths
    }
    materials = {m.name: m for m in materials_by_path.values()}
    for mesh in meshes:
        if mesh.face_materials:
            mesh.face_materials = [
                materials_by_path[p].name if p and p in materials_by_path else None
                for p in mesh.face_materials
            ]

    request = PublishRequest(
        asset_name=name,
        project=project,
        variant=variant or "default",
        comment=comment,
        meshes=meshes,
        materials=materials,
        source=SourceInfo(
            dcc="houdini %s" % hou.applicationVersionString(),
            scene=hou.hipFile.path(),
            nodes=[node.path() for node in nodes],
            user=getpass.getuser(),
        ),
    )
    return request, skipped_total


# -- thumbnail capture ---------------------------------------------------


def _capture_thumbnail(nodes, path):
    """Frame the selection in the viewport and grab a 512px capture,
    restoring every display flag and viewport setting afterwards."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if viewer is None:
        return None

    obj_nodes = {n if n.type().category() == hou.objNodeTypeCategory() else n.parent()
                 for n in nodes}
    others = [n for n in hou.node("/obj").children() if n not in obj_nodes]
    flag_states = [(n, n.isDisplayFlagSet()) for n in others]

    viewport = viewer.curViewport()
    settings = viewport.settings()
    display_set = settings.displaySet(hou.displaySetType.SceneObject)
    previous_shading = display_set.shadedMode()
    previous_lighting = settings.lighting()

    try:
        for node in others:
            node.setDisplayFlag(False)
        viewport.home()
        viewport.frameSelected()
        display_set.setShadingModeLocked(False)
        display_set.setShadedMode(hou.glShadingType.Smooth)
        settings.setLighting(hou.viewportLighting.Headlight)

        frame = int(hou.frame())
        camera_path = "%s.%s.world.%s" % (
            hou.ui.curDesktop().name(),
            viewer.name(),
            viewport.name(),
        )
        hou.hscript(
            "viewwrite -r 512 512 -f %d %d %s '%s'" % (frame, frame, camera_path, path)
        )
    finally:
        for node, state in flag_states:
            node.setDisplayFlag(state)
        display_set.setShadedMode(previous_shading)
        settings.setLighting(previous_lighting)

    return path if os.path.isfile(path) else None


# -- shelf entry points --------------------------------------------------


def publish():
    nodes = hou.selectedNodes()
    if not nodes:
        hou.ui.displayMessage(
            "Select the geo objects (or SOPs) to publish.", title="FiveHub"
        )
        return None

    default_name = naming.make_identifier(nodes[0].name(), fallback="Asset")
    default_name = default_name[0].upper() + default_name[1:]

    pressed, values = hou.ui.readMultiInput(
        "Publish selection as a USD component asset",
        ("Asset Name", "Project", "Variant", "Comment"),
        initial_contents=(default_name, "", "default", ""),
        buttons=("Publish", "Cancel"),
        default_choice=0,
        close_choice=1,
        title="FiveHub Publish",
    )
    if pressed != 0:
        return None
    name, project, variant, comment = (value.strip() for value in values)

    try:
        request, skipped = _build_request(nodes, name, project, variant, comment)
    except ValueError as error:
        hou.ui.displayMessage(str(error), severity=hou.severityType.Error, title="FiveHub")
        return None

    root = config.ensure_hub()
    thumbnail = os.path.join(
        config.exchange_path(root), "capture_%s.png" % naming.make_identifier(name)
    )
    request.thumbnail = _capture_thumbnail(nodes, thumbnail)

    result = core_publish(request, hub_root=root)

    summary = result.report.to_text()
    if skipped:
        summary += "\n\nNote: %d non-polygon primitive(s) were skipped." % skipped
    if result.passed:
        message = "PUBLISHED %s %s\n\n%s" % (name, result.version_label, summary)
        severity = hou.severityType.Message
    else:
        message = "PUBLISH BLOCKED — validation failed\n\n%s" % summary
        severity = hou.severityType.Error
    hou.ui.displayMessage(message, severity=severity, title="FiveHub Publish Report")

    if request.thumbnail and os.path.isfile(thumbnail):
        os.remove(thumbnail)
    return result


def _read_selection():
    import json

    path = config.selection_path(config.ensure_hub())
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            selection = json.load(handle)
    except (ValueError, OSError):
        return None
    layer = selection.get("layer", "")
    return selection if layer and os.path.isfile(layer) else None


def import_asset():
    """Reference a published asset into the scene: Solaris /stage when
    available, SOP-level USD import otherwise."""
    selection = _read_selection()
    if selection:
        layer = selection["layer"]
    else:
        layer = hou.ui.selectFile(
            start_directory=config.assets_path(config.ensure_hub()),
            title="FiveHub — pick a published asset layer",
            pattern="*.usd *.usda *.usdc",
            chooser_mode=hou.fileChooserMode.Read,
        )
        layer = hou.text.expandString(layer) if layer else ""
    if not layer:
        return None

    node_name = naming.make_identifier(os.path.splitext(os.path.basename(layer))[0])

    stage = hou.node("/stage")
    if stage is not None:
        for type_name in ("reference::2.0", "reference"):
            try:
                ref = stage.createNode(type_name, node_name)
            except hou.OperationFailed:
                continue
            ref.parm("filepath1").set(layer)
            ref.moveToGoodPosition()
            try:
                ref.setDisplayFlag(True)
            except hou.OperationFailed:
                pass
            return ref

    obj = hou.node("/obj").createNode("geo", node_name)
    importer = obj.createNode("usdimport", "import")
    importer.parm("filepath1").set(layer)
    obj.moveToGoodPosition()
    return obj


def launch_hub():
    """Start the FiveHub Electron app as a detached process."""
    app_dir = os.path.join(_REPO, "app")
    binary = os.path.join(app_dir, "node_modules", ".bin",
                          "electron.cmd" if os.name == "nt" else "electron")
    if not os.path.isfile(binary):
        hou.ui.displayMessage(
            "The FiveHub app is not installed yet.\n\n"
            "Run this once in a terminal:\n    cd %s\n    npm install" % app_dir,
            severity=hou.severityType.Warning,
            title="FiveHub",
        )
        return

    env = dict(os.environ)
    env[config.ENV_ROOT] = config.ensure_hub()
    kwargs = {"cwd": app_dir, "env": env}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([binary, app_dir], **kwargs)


def reload_fivehub():
    import importlib

    import fivehub
    import fivehub.cli
    import fivehub.config
    import fivehub.db
    import fivehub.demo
    import fivehub.geometry
    import fivehub.naming
    import fivehub.publish
    import fivehub.report
    import fivehub.thumbs
    import fivehub.usdlayers
    import fivehub.validation

    for module in (
        fivehub.config, fivehub.naming, fivehub.geometry, fivehub.report,
        fivehub.validation, fivehub.db, fivehub.usdlayers, fivehub.thumbs,
        fivehub.publish, fivehub.demo, fivehub.cli, fivehub,
    ):
        importlib.reload(module)
    importlib.reload(sys.modules[__name__])
