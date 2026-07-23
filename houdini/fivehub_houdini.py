"""FiveHub Houdini integration — the FIVE HUB menu's engine.

Entry points (wired to the main menu and the shelf):

    save_scene_as()   save the current scene into a project/entity/task,
                      versioned with notes
    increment_save()  next version of the current pipeline scene
    load_scene()      open a versioned scene from an asset or shot
    publish()         validated publish of the selection (USD component by
                      default, or vdb/bgeo/obj file drops)
    load_asset()      import a publish into the scene
    import_staged()   import whatever the hub app staged (SEND TO HOUDINI)
    launch_hub()      start the standalone Electron app
    reload_fivehub()  developer helper

Geometry is translated to the DCC-neutral fivehub model here; everything
downstream (validation, USD authoring, database) is Houdini-free.
"""

import getpass
import json
import os
import shutil
import subprocess
import sys
import uuid

import hou

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (_REPO, os.path.join(_REPO, "houdini")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fivehub import config, naming
from fivehub.geometry import MaterialData, MeshData, PublishRequest, SourceInfo
from fivehub.project import get_project, parse_scene_path
from fivehub.publish import FilePublishRequest, publish_files, publish_usd

FILE_EXPORT_EXTENSION = {"bgeo": ".bgeo.sc", "vdb": ".vdb", "obj": ".obj"}


def _message(text, severity=hou.severityType.Message):
    hou.ui.displayMessage(text, severity=severity, title="FIVE HUB")


def _error(text):
    _message(text, hou.severityType.Error)


def _source_info(nodes=()):
    return SourceInfo(
        dcc="houdini %s" % hou.applicationVersionString(),
        scene=hou.hipFile.path(),
        nodes=[node.path() for node in nodes],
        user=getpass.getuser(),
    )


def _current_context():
    return parse_scene_path(hou.hipFile.path())


def _ensure_context(context):
    """Resolve a dialog context to a Project, creating the entity and task
    on demand (projects themselves are created in the hub app)."""
    try:
        project = get_project(context["project"])
    except ValueError:
        raise ValueError(
            "Project %r does not exist.\nCreate projects in the hub app first."
            % context["project"]
        )
    kind, entity, task = context["kind"], context["entity"], context["task"]
    if project.db.get_entity(kind, entity) is None:
        project.create_entity(kind, entity)
    entity_id = project.db.get_entity(kind, entity)["id"]
    if project.db.get_task(entity_id, task) is None:
        project.create_task(kind, entity, task)
    return project


# -- scenes --------------------------------------------------------------


def save_scene_as():
    from fivehub_windows import SaveSceneDialog, exec_dialog

    dialog = SaveSceneDialog(prefill=_current_context())
    if not dialog.context_widget.has_projects():
        _error("No projects in the hub yet.\nCreate one in the hub app first.")
        return None
    if not exec_dialog(dialog):
        return None
    context, notes = dialog.values()
    if not (context["project"] and context["entity"] and context["task"]):
        _error("Project, asset/shot and task are all required.")
        return None
    return _save_into(context, notes)


def increment_save():
    context = _current_context()
    if context is None:
        return save_scene_as()
    pressed, values = hou.ui.readMultiInput(
        "Increment %s / %s / %s" % (context["project"], context["entity"], context["task"]),
        ("Notes",),
        buttons=("Save", "Cancel"),
        default_choice=0,
        close_choice=1,
        title="FIVE HUB",
    )
    if pressed != 0:
        return None
    return _save_into(context, values[0].strip())


def _save_into(context, notes):
    try:
        project = _ensure_context(context)
        path, version = project.next_scene_path(
            context["kind"], context["entity"], context["task"]
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        hou.hipFile.save(path)
        project.register_scene(
            context["kind"], context["entity"], context["task"],
            version, path, notes, getpass.getuser(),
        )
    except (ValueError, hou.OperationFailed) as error:
        _error(str(error))
        return None
    _message(
        "SAVED %s\n%s / %s %s / %s"
        % (
            config.version_label(version),
            context["project"], context["kind"], context["entity"], context["task"],
        )
    )
    return path


def load_scene():
    from fivehub_windows import LoadSceneDialog, exec_dialog

    dialog = LoadSceneDialog(prefill=_current_context())
    if not exec_dialog(dialog):
        return None
    scene_file = dialog.selected_file()
    if not scene_file:
        return None
    if not os.path.isfile(scene_file):
        _error("Scene file is missing on disk:\n%s" % scene_file)
        return None
    try:
        hou.hipFile.load(scene_file, suppress_save_prompt=False)
    except hou.OperationInterrupted:
        return None
    except (hou.OperationFailed, hou.LoadWarning) as error:
        _message(str(error), hou.severityType.Warning)
    return scene_file


# -- geometry extraction (USD publishes) ---------------------------------


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

    mesh = MeshData(
        name=naming.make_identifier(node.name()),
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

    def _parm(parm_name, default):
        parm = node.parm(parm_name)
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


def _build_usd_request(nodes, name, variant, comment):
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
        variant=variant,
        comment=comment,
        meshes=meshes,
        materials=materials,
        source=_source_info(nodes),
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


# -- publish -------------------------------------------------------------


def publish():
    from fivehub_windows import PublishDialog, exec_dialog, show_report

    nodes = hou.selectedNodes()
    if not nodes:
        _message("Select the geo objects (or SOPs) to publish.")
        return None

    prefill = _current_context()
    dialog = PublishDialog(prefill=prefill)
    if not dialog.context_widget.has_projects():
        _error("No projects in the hub yet.\nCreate one in the hub app first.")
        return None
    if prefill is None:
        # No pipeline scene context — suggest a name from the selection.
        suggested = naming.make_identifier(nodes[0].name(), fallback="Asset")
        dialog.name_edit.setText(suggested[0].upper() + suggested[1:])
    if not exec_dialog(dialog):
        return None

    values = dialog.values()
    context = values["context"]
    if not (context["project"] and context["entity"] and context["task"]):
        _error("Project, asset/shot and task are all required.")
        return None

    try:
        project = _ensure_context(context)
    except ValueError as error:
        _error(str(error))
        return None

    root = config.ensure_hub()
    thumbnail = os.path.join(
        config.exchange_path(root),
        "capture_%s.png" % naming.make_identifier(values["name"] or "publish"),
    )
    thumbnail = _capture_thumbnail(nodes, thumbnail)

    scratch = None
    try:
        if values["format"] == "usd":
            try:
                request, skipped = _build_usd_request(
                    nodes, values["name"], values["variant"], values["comment"]
                )
            except ValueError as error:
                _error(str(error))
                return None
            request.thumbnail = thumbnail
            result = publish_usd(
                project, context["kind"], context["entity"], context["task"], request
            )
            extra = "Skipped %d non-polygon primitive(s)." % skipped if skipped else ""
        else:
            scratch = os.path.join(
                config.exchange_path(root), "export_%s" % uuid.uuid4().hex[:8]
            )
            os.makedirs(scratch, exist_ok=True)
            files, failures = _export_node_files(nodes, values["format"], scratch)
            if failures and not files:
                _error("Nothing could be exported:\n%s" % "\n".join(failures))
                return None
            request = FilePublishRequest(
                asset_name=values["name"],
                format=values["format"],
                files=files,
                variant=values["variant"],
                comment=values["comment"],
                thumbnail=thumbnail,
                source=_source_info(nodes),
            )
            result = publish_files(
                project, context["kind"], context["entity"], context["task"], request
            )
            extra = "\n".join(failures)

        header = (
            "PUBLISHED %s %s" % (values["format"].upper(), result.version_label)
            if result.passed
            else "PUBLISH BLOCKED"
        )
        show_report(result.report, extra="%s\n%s" % (header, extra) if extra else header)
        return result
    finally:
        if thumbnail and os.path.isfile(thumbnail):
            os.remove(thumbnail)
        if scratch and os.path.isdir(scratch):
            shutil.rmtree(scratch, ignore_errors=True)


def _export_node_files(nodes, format_name, scratch):
    """Write each node's geometry to a file of the requested format."""
    extension = FILE_EXPORT_EXTENSION[format_name]
    files, failures = [], []
    used = set()
    for node in nodes:
        name = naming.make_identifier(node.name())
        while name in used:
            name += "_1"
        used.add(name)
        target = os.path.join(scratch, name + extension)
        try:
            geometry = _sop_geometry(node)
            if geometry is None:
                raise ValueError("no geometry")
            geometry.saveToFile(target)
            files.append(target)
        except (ValueError, hou.OperationFailed, hou.Error) as error:
            failures.append("%s: %s" % (node.path(), error))
    return files, failures


# -- import --------------------------------------------------------------


def load_asset():
    from fivehub_windows import LoadAssetDialog, exec_dialog

    dialog = LoadAssetDialog(prefill=_current_context())
    if not exec_dialog(dialog):
        return None
    row = dialog.selected_publish()
    if not row:
        return None
    return _import_publish(row["format"], row["path"], row["name"])


def import_staged():
    """Import whatever the hub app staged via SEND TO HOUDINI."""
    selection_file = config.selection_path(config.ensure_hub())
    if not os.path.isfile(selection_file):
        return load_asset()
    try:
        with open(selection_file, "r", encoding="utf-8") as handle:
            selection = json.load(handle)
    except (ValueError, OSError):
        return load_asset()
    path = selection.get("path", "")
    if not path or not os.path.exists(path):
        _error("The staged publish is missing on disk:\n%s" % path)
        return None
    return _import_publish(
        selection.get("format", config.DEFAULT_FORMAT),
        path,
        selection.get("name", "asset"),
    )


def _import_publish(format_name, path, name):
    node_name = naming.make_identifier(name)
    if format_name == "usd":
        return _import_usd(path, node_name)

    # File formats: one geo object, one File SOP per published file.
    if os.path.isdir(path):
        files = sorted(
            os.path.join(path, entry)
            for entry in os.listdir(path)
            if os.path.isfile(os.path.join(path, entry))
            and not entry.endswith(".json")
        )
    else:
        files = [path]
    if not files:
        _error("No files found in publish:\n%s" % path)
        return None
    container = hou.node("/obj").createNode("geo", node_name)
    for file_path in files:
        file_sop = container.createNode(
            "file", naming.make_identifier(os.path.basename(file_path).split(".")[0])
        )
        file_sop.parm("file").set(file_path)
    container.moveToGoodPosition()
    container.layoutChildren()
    return container


def _import_usd(layer, node_name):
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

    container = hou.node("/obj").createNode("geo", node_name)
    importer = container.createNode("usdimport", "import")
    importer.parm("filepath1").set(layer)
    container.moveToGoodPosition()
    return container


# -- app -----------------------------------------------------------------


def launch_hub():
    """Start the FiveHub Electron app as a detached process."""
    app_dir = os.path.join(_REPO, "app")
    binary = os.path.join(app_dir, "node_modules", ".bin",
                          "electron.cmd" if os.name == "nt" else "electron")
    if not os.path.isfile(binary):
        _message(
            "The FiveHub app is not installed yet.\n\n"
            "Run this once in a terminal:\n    cd %s\n    npm install" % app_dir,
            hou.severityType.Warning,
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
    import fivehub.demo
    import fivehub.geometry
    import fivehub.naming
    import fivehub.project
    import fivehub.projectdb
    import fivehub.publish
    import fivehub.report
    import fivehub.thumbs
    import fivehub.usdlayers
    import fivehub.validation
    import fivehub_windows

    for module in (
        fivehub.config, fivehub.naming, fivehub.geometry, fivehub.report,
        fivehub.validation, fivehub.projectdb, fivehub.project, fivehub.usdlayers,
        fivehub.thumbs, fivehub.publish, fivehub.demo, fivehub.cli, fivehub,
        fivehub_windows,
    ):
        importlib.reload(module)
    importlib.reload(sys.modules[__name__])
