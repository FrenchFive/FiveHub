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

import json
import os
import re
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
from fivehub.user import get_user

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
        user=get_user(),
    )


def _current_context():
    return parse_scene_path(hou.hipFile.path())


def _bind_context_env(project, context):
    """$JOB + FiveHub vars point at the project so artists build relative
    paths ($JOB/...) instead of baking server-absolute ones into hips."""
    hou.putenv("JOB", project.root.replace("\\", "/"))
    hou.putenv("FH_PROJECT", context["project"])
    hou.putenv("FH_KIND", context["kind"])
    hou.putenv("FH_ENTITY", context["entity"])
    hou.putenv("FH_TASK", context["task"])
    hou.putenv(
        "FH_CACHES",
        project.caches_dir(
            context["kind"], context["entity"], context["task"]
        ).replace("\\", "/"),
    )


def _apply_shot_settings(project, context):
    """Push the shot's frame range and fps onto the session."""
    meta = project.db.get_entity(context["kind"], context["entity"]) or {}
    fps = meta.get("fps")
    if fps:
        try:
            hou.setFps(fps)
        except hou.OperationFailed:
            pass
    start, end = meta.get("frame_start"), meta.get("frame_end")
    if start and end:
        hou.playbar.setFrameRange(start, end)
        hou.playbar.setPlaybackRange(start, end)


def _entity_frame_range(project, context):
    meta = project.db.get_entity(context["kind"], context["entity"]) or {}
    settings = project.settings()
    start = meta.get("frame_start") or settings["frame_start"]
    end = meta.get("frame_end") or settings["frame_end"]
    return int(start), int(end)


def _after_context_change(project, context, scene_version=None):
    _bind_context_env(project, context)
    if context["kind"] == "shot":
        _apply_shot_settings(project, context)
    project.touch_presence(
        context["kind"], context["entity"], context["task"], get_user(),
        scene_version=scene_version, host=os.environ.get("HOSTNAME", ""),
    )


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
    """Claim the version in the database first (multi-user safe), then save
    the hip at the claimed path, then complete — never overwrite a peer."""
    try:
        project = _ensure_context(context)
        path, version = project.claim_scene(
            context["kind"], context["entity"], context["task"], get_user()
        )
    except (ValueError, RuntimeError) as error:
        _error(str(error))
        return None
    try:
        hou.hipFile.save(path)
        project.complete_scene(
            context["kind"], context["entity"], context["task"],
            version, notes, get_user(),
        )
    except (ValueError, hou.OperationFailed) as error:
        project.release_scene(
            context["kind"], context["entity"], context["task"], version
        )
        _error(str(error))
        return None
    _after_context_change(project, context, scene_version=version)
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
    context = parse_scene_path(scene_file)
    if context:
        try:
            project = get_project(context["project"])
            match = None
            for scene in project.scenes(
                context["kind"], context["entity"], context["task"]
            ):
                if scene["file"] == os.path.abspath(scene_file):
                    match = scene["version"]
                    break
            _after_context_change(project, context, scene_version=match)
        except ValueError:
            pass
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
    uv_attrib = geo.findVertexAttrib("uv") or geo.findPointAttrib("uv")

    counts = []
    indices = []
    normals = [] if normal_attrib else None
    uvs = [] if uv_attrib else None
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
            if normals is not None:
                if normal_attrib.type() == hou.attribType.Vertex:
                    normals.append(tuple(vertex.attribValue(normal_attrib)))
                else:
                    normals.append(tuple(vertex.point().attribValue(normal_attrib)))
            if uvs is not None:
                if uv_attrib.type() == hou.attribType.Vertex:
                    value = vertex.attribValue(uv_attrib)
                else:
                    value = vertex.point().attribValue(uv_attrib)
                uvs.append((value[0], value[1]))  # Houdini uv is 3-float

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
        uvs=uvs,
        face_materials=face_materials,
    )
    return mesh, skipped


def _sample_animation(nodes, meshes, frame_start, frame_end, step=1):
    """Per-frame point positions for each mesh (topology must hold)."""
    original_frame = hou.frame()
    try:
        for mesh in meshes:
            mesh.point_samples = {}
        frame = frame_start
        while frame <= frame_end:
            hou.setFrame(frame)
            for node, mesh in zip(nodes, meshes):
                geo = _sop_geometry(node)
                raw = geo.pointFloatAttribValues("P")
                mesh.point_samples[float(frame)] = [
                    (raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)
                ]
            frame += step
    finally:
        hou.setFrame(original_frame)


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

    # Principled shader textures -> UsdUVTexture channels.
    def _texture(toggle, parm_name):
        if toggle and not _parm(toggle, 0):
            return ""
        value = str(_parm(parm_name, "")).strip()
        return value if value and os.path.isfile(hou.text.expandString(value)) else ""

    textures = {
        "diffuse": _texture("basecolor_useTexture", "basecolor_texture"),
        "roughness": _texture("rough_useTexture", "rough_texture"),
        "metallic": _texture("metallic_useTexture", "metallic_texture"),
        "normal": _texture("baseBumpAndNormal_enable", "baseNormal_texture"),
    }
    material.textures = {
        channel: hou.text.expandString(path)
        for channel, path in textures.items()
        if path
    }
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

    # Publishing is only available from a scene saved in the pipeline —
    # the context is derived from the scene, never chosen at publish time.
    context = _current_context()
    if context is None:
        _error(
            "This scene is not saved in the pipeline, so there is nothing "
            "to publish into.\n\nUse FIVE HUB > Save Scene As... to save it "
            "under a project / asset-or-shot / task first."
        )
        return None

    try:
        project = get_project(context["project"])
        project._task_record(context["kind"], context["entity"], context["task"])
    except ValueError as error:
        _error(str(error))
        return None

    dialog = PublishDialog(context=context)
    dialog.set_frame_range(*_entity_frame_range(project, context))
    if not exec_dialog(dialog):
        return None
    values = dialog.values()
    if not values["name"]:
        _error("A publish name is required.")
        return None

    root = config.ensure_hub()
    thumbnail = os.path.join(
        config.user_exchange_path(root),
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
                if values.get("animated"):
                    _sample_animation(
                        nodes, request.meshes,
                        values["frame_start"], values["frame_end"],
                    )
                    request.frame_start = values["frame_start"]
                    request.frame_end = values["frame_end"]
                    request.fps = hou.fps()
            except ValueError as error:
                _error(str(error))
                return None
            request.thumbnail = thumbnail
            result = publish_usd(
                project, context["kind"], context["entity"], context["task"], request
            )
            extra = "Skipped %d non-polygon primitive(s)." % skipped if skipped else ""
        elif values["format"] == "hda":
            files, failures = _collect_hda_files(nodes)
            if not files:
                _error(
                    "No HDA definitions in the selection.\n%s" % "\n".join(failures)
                )
                return None
            request = FilePublishRequest(
                asset_name=values["name"],
                format="hda",
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
        else:
            scratch = os.path.join(
                config.user_exchange_path(root), "export_%s" % uuid.uuid4().hex[:8]
            )
            os.makedirs(scratch, exist_ok=True)
            if values.get("animated"):
                files, failures = _export_node_sequences(
                    nodes, values["format"], scratch,
                    values["frame_start"], values["frame_end"],
                )
            else:
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


def _export_node_sequences(nodes, format_name, scratch, frame_start, frame_end):
    """Write each node's geometry per frame — vdb/bgeo cache sequences."""
    extension = FILE_EXPORT_EXTENSION[format_name]
    files, failures = [], []
    original_frame = hou.frame()
    used = set()
    try:
        for node in nodes:
            name = naming.make_identifier(node.name())
            while name in used:
                name += "_1"
            used.add(name)
            for frame in range(int(frame_start), int(frame_end) + 1):
                hou.setFrame(frame)
                target = os.path.join(scratch, "%s.%04d%s" % (name, frame, extension))
                try:
                    geometry = _sop_geometry(node)
                    if geometry is None:
                        raise ValueError("no geometry")
                    geometry.saveToFile(target)
                    files.append(target)
                except (ValueError, hou.OperationFailed, hou.Error) as error:
                    failures.append("%s f%d: %s" % (node.path(), frame, error))
                    break
    finally:
        hou.setFrame(original_frame)
    return files, failures


def _collect_hda_files(nodes):
    """The .hda library files behind the selected nodes' definitions."""
    files, failures = [], []
    seen = set()
    for node in nodes:
        definition = node.type().definition()
        if definition is None:
            failures.append("%s has no HDA definition" % node.path())
            continue
        library = definition.libraryFilePath()
        if not library or library == "Embedded" or not os.path.isfile(library):
            failures.append("%s: definition is embedded — save it to a file first"
                            % node.path())
            continue
        if library not in seen:
            seen.add(library)
            files.append(library)
    return files, failures


# -- import --------------------------------------------------------------


def load_asset():
    from fivehub_windows import LoadAssetDialog, exec_dialog

    context = _current_context()
    dialog = LoadAssetDialog(prefill=context)
    if not exec_dialog(dialog):
        return None
    row = dialog.selected_publish()
    if not row:
        return None
    source = dialog.context_widget.context()
    # Picking a row in the browser pins the exact version.
    _track_dependency(context, source, row["format"], row["name"], row["version"])
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
    _track_dependency(
        _current_context(),
        {
            "project": selection.get("project", ""),
            "kind": selection.get("kind", "asset"),
            "entity": selection.get("entity", ""),
            "task": selection.get("task", ""),
        },
        selection.get("format", config.DEFAULT_FORMAT),
        selection.get("name", "asset"),
        selection.get("version"),  # None = follows latest via the root layer
    )
    return _import_publish(
        selection.get("format", config.DEFAULT_FORMAT),
        path,
        selection.get("name", "asset"),
    )


def _track_dependency(context, source, format_name, name, version):
    """Remember that the current scene's task uses a publish (same project)."""
    if not context or not source.get("entity"):
        return
    if source.get("project") and source["project"] != context["project"]:
        return
    try:
        project = get_project(context["project"])
        consumer = project._task_record(
            context["kind"], context["entity"], context["task"]
        )
        producer = project._task_record(
            source["kind"], source["entity"], source["task"]
        )
    except ValueError:
        return
    project.db.record_dependency(
        consumer["id"], producer["id"], format_name, name,
        src_version=version or None, user=get_user(),
    )


def _import_publish(format_name, path, name):
    node_name = naming.make_identifier(name)

    if format_name == "usd":
        # Ingested USD rows point at the version dir — find the layer.
        if os.path.isdir(path):
            layers = sorted(
                entry for entry in os.listdir(path)
                if entry.lower().endswith((".usd", ".usda", ".usdc", ".usdz"))
            )
            if layers:
                path = os.path.join(path, layers[0])
        return _import_usd(path, node_name)

    if format_name == "hda":
        installed = []
        files = [path] if os.path.isfile(path) else [
            os.path.join(path, entry) for entry in sorted(os.listdir(path))
            if entry.lower().endswith((".hda", ".otl", ".hdanc", ".hdalc"))
        ]
        for library in files:
            hou.hda.installFile(library)
            installed.append(os.path.basename(library))
        _message("Installed HDA librarie(s):\n%s" % "\n".join(installed or ["none"]))
        return installed

    # File formats: one geo object; frame sequences collapse to one File
    # SOP with $F4, single files get one File SOP each.
    if os.path.isdir(path):
        files = sorted(
            os.path.join(path, entry)
            for entry in os.listdir(path)
            if os.path.isfile(os.path.join(path, entry))
            and not entry.endswith(".json")
            and os.path.basename(os.path.dirname(os.path.join(path, entry)))
            != config.THUMBNAILS_DIR
        )
    else:
        files = [path]
    files = [f for f in files if config.THUMBNAILS_DIR not in f.split(os.sep)]
    if not files:
        _error("No files found in publish:\n%s" % path)
        return None

    container = hou.node("/obj").createNode("geo", node_name)
    for label, parm_value in _group_sequences(files):
        file_sop = container.createNode("file", naming.make_identifier(label))
        file_sop.parm("file").set(parm_value)
    container.moveToGoodPosition()
    container.layoutChildren()
    return container


def _group_sequences(files):
    """[(label, file-parm value)] — frame sequences become $F4 patterns."""
    groups = {}
    for path in files:
        base = os.path.basename(path)
        match = re.match(r"^(.*?)\.(\d+)(\.[A-Za-z0-9.]+)$", base)
        if match:
            key = (match.group(1), len(match.group(2)), match.group(3))
            groups.setdefault(key, []).append(path)
        else:
            groups.setdefault(base, []).append(path)
    result = []
    for key, members in groups.items():
        if isinstance(key, tuple) and len(members) > 1:
            prefix, padding, extension = key
            pattern = os.path.join(
                os.path.dirname(members[0]),
                "%s.$F%d%s" % (prefix, padding, extension),
            )
            result.append((prefix, pattern))
        else:
            for member in members:
                result.append((os.path.basename(member).split(".")[0], member))
    return result


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


# -- render & assembly ---------------------------------------------------


def submit_render():
    """Queue a render of the current pipeline scene on the FiveHub worker."""
    from fivehub.render import submit_render as core_submit
    from fivehub_windows import RenderDialog, exec_dialog

    context = _current_context()
    if context is None:
        _error(
            "This scene is not saved in the pipeline.\n\n"
            "Use FIVE HUB > Save Scene As... first — renders run from a "
            "saved scene version."
        )
        return None
    match = re.search(r"_v(\d+)\.hip", context["file"])
    if not match:
        _error("Could not read the scene version from %r." % context["file"])
        return None
    scene_version = int(match.group(1))

    rops = [node.path() for node in hou.node("/out").children()]
    stage = hou.node("/stage")
    if stage is not None:
        rops += [
            node.path() for node in stage.allSubChildren()
            if node.type().name().startswith("usdrender")
        ]
    if not rops:
        _error("No ROP nodes found (looked in /out and /stage).")
        return None

    try:
        project = get_project(context["project"])
    except ValueError as error:
        _error(str(error))
        return None
    start, end = _entity_frame_range(project, context)

    dialog = RenderDialog(context, rops, start, end, scene_version)
    if not exec_dialog(dialog):
        return None
    values = dialog.values()
    try:
        result = core_submit(
            project, context["kind"], context["entity"], context["task"],
            scene_version, values["rop"],
            frame_start=values["frame_start"], frame_end=values["frame_end"],
            step=values["step"], user=get_user(),
        )
    except ValueError as error:
        _error(str(error))
        return None
    _message(
        "RENDER QUEUED\n%s  f%d-%d\n\nA FiveHub worker will pick it up\n"
        "(python -m fivehub.cli worker on the server)."
        % (values["rop"], result["frame_start"], result["frame_end"])
    )
    return result


def publish_shot_assembly():
    """Publish this task's tracked USD imports as one assembly layer."""
    from fivehub.assembly import publish_assembly

    context = _current_context()
    if context is None:
        _error(
            "This scene is not saved in the pipeline.\n\n"
            "Assemblies are built from the imports tracked on a saved "
            "project scene."
        )
        return None
    pressed, values = hou.ui.readMultiInput(
        "Publish assembly of %s / %s" % (context["entity"], context["task"]),
        ("Comment",),
        buttons=("Publish", "Cancel"),
        default_choice=0,
        close_choice=1,
        title="FIVE HUB",
    )
    if pressed != 0:
        return None
    try:
        project = get_project(context["project"])
        result = publish_assembly(
            project, context["entity"], context["task"],
            kind=context["kind"], comment=values[0].strip(), user=get_user(),
        )
    except ValueError as error:
        _error(str(error))
        return None
    _message(
        "ASSEMBLY PUBLISHED %s\n%d reference(s)\n%s"
        % (result["version_label"], result["references"], result["layer"])
    )
    return result


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
