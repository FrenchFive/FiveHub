"""USD component-asset authoring.

Writes the standard component layer stack as ASCII usda (no pxr dependency,
so the same code runs inside any DCC or standalone):

    <Asset>.usda           entry layer — kind=component, assetInfo, extentsHint,
                           thumbnail baked in via AssetPreviewsAPI, and a "geo"
                           variantSet whose variants carry the payload arcs
    <Asset>.payload.usda   composes the mtl + geo layers (mtl stronger)
    <Asset>.geo.usda       geometry: Scope "geo" with Mesh prims + GeomSubsets
    <Asset>.mtl.usda       materials: Scope "mtl" with UsdPreviewSurface
                           networks and bindings over the geo hierarchy

Consumers reference the entry layer only; the payload keeps heavy geometry
out of the composition until it is actually needed.
"""

import os

from . import __version__

GENERATOR = "FiveHub %s" % __version__
INDENT = "    "


def _num(value):
    """Compact float/int formatting for usda."""
    if isinstance(value, int):
        return str(value)
    text = "%.8g" % float(value)
    return "0" if text in ("-0", "-0.0") else text


def _vec3(value):
    return "(%s, %s, %s)" % tuple(_num(c) for c in value)


def _vec3_array(values):
    return "[%s]" % ", ".join(_vec3(v) for v in values)


def _vec2(value):
    return "(%s, %s)" % (_num(value[0]), _num(value[1]))


def _vec2_array(values):
    return "[%s]" % ", ".join(_vec2(v) for v in values)


def _int_array(values):
    return "[%s]" % ", ".join(str(int(v)) for v in values)


def _string(value):
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return '"%s"' % escaped


def _posix(path):
    return path.replace(os.sep, "/")


def _layer_header(default_prim, meters_per_unit=None, up_axis=None, custom=None,
                  time_range=None, fps=None):
    lines = ["#usda 1.0", "("]
    lines.append('%sdefaultPrim = "%s"' % (INDENT, default_prim))
    if meters_per_unit is not None:
        lines.append("%smetersPerUnit = %s" % (INDENT, _num(meters_per_unit)))
    if up_axis is not None:
        lines.append('%supAxis = "%s"' % (INDENT, up_axis))
    if time_range is not None:
        lines.append("%sstartTimeCode = %s" % (INDENT, _num(time_range[0])))
        lines.append("%sendTimeCode = %s" % (INDENT, _num(time_range[1])))
        if fps:
            lines.append("%stimeCodesPerSecond = %s" % (INDENT, _num(fps)))
            lines.append("%sframesPerSecond = %s" % (INDENT, _num(fps)))
    lines.append("%scustomLayerData = {" % INDENT)
    lines.append('%sstring generator = %s' % (INDENT * 2, _string(GENERATOR)))
    for key, value in (custom or {}).items():
        lines.append("%sstring %s = %s" % (INDENT * 2, key, _string(value)))
    lines.append("%s}" % INDENT)
    lines.append(")")
    lines.append("")
    return lines


def _time_range(request):
    """(start, end) when any mesh carries animation samples, else None."""
    frames = set()
    for mesh in getattr(request, "meshes", []) or []:
        if mesh.point_samples:
            frames.update(mesh.point_samples)
    if not frames:
        return None
    return (min(frames), max(frames))


def _write(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


# -- geometry layer ------------------------------------------------------


def write_geo_layer(path, request):
    asset = request.asset_name
    lines = _layer_header(
        asset, request.meters_per_unit, request.up_axis,
        time_range=_time_range(request), fps=getattr(request, "fps", None),
    )
    lines.append('def Xform "%s" (' % asset)
    lines.append('%skind = "component"' % INDENT)
    lines.append(")")
    lines.append("{")
    lines.append('%sdef Scope "geo"' % INDENT)
    lines.append("%s{" % INDENT)
    for mesh in request.meshes:
        lines.extend(_mesh_block(mesh, depth=2))
    lines.append("%s}" % INDENT)
    lines.append("}")
    return _write(path, lines)


def _mesh_block(mesh, depth):
    pad = INDENT * depth
    inner = INDENT * (depth + 1)
    lines = []
    lines.append('%sdef Mesh "%s"' % (pad, mesh.name))
    lines.append("%s{" % pad)
    bounds = mesh.bounds()
    if bounds:
        lines.append("%sfloat3[] extent = %s" % (inner, _vec3_array(bounds)))
    lines.append("%sint[] faceVertexCounts = %s" % (inner, _int_array(mesh.face_vertex_counts)))
    lines.append("%sint[] faceVertexIndices = %s" % (inner, _int_array(mesh.face_vertex_indices)))
    if mesh.normals:
        lines.append(
            '%snormal3f[] normals = %s (\n%sinterpolation = "faceVarying"\n%s)'
            % (inner, _vec3_array(mesh.normals), inner + INDENT, inner)
        )
    if mesh.point_samples:
        # Animated geometry: default = first sample, plus timeSamples.
        frames = sorted(mesh.point_samples)
        lines.append(
            "%spoint3f[] points = %s"
            % (inner, _vec3_array(mesh.point_samples[frames[0]]))
        )
        lines.append("%spoint3f[] points.timeSamples = {" % inner)
        for frame in frames:
            lines.append(
                "%s%s: %s,"
                % (inner + INDENT, _num(frame), _vec3_array(mesh.point_samples[frame]))
            )
        lines.append("%s}" % inner)
    else:
        lines.append("%spoint3f[] points = %s" % (inner, _vec3_array(mesh.points)))
    if mesh.uvs:
        lines.append(
            '%stexCoord2f[] primvars:st = %s (\n%sinterpolation = "faceVarying"\n%s)'
            % (inner, _vec2_array(mesh.uvs), inner + INDENT, inner)
        )
    if mesh.display_color:
        lines.append(
            '%scolor3f[] primvars:displayColor = [%s]' % (inner, _vec3(mesh.display_color))
        )
    lines.append('%suniform token orientation = "rightHanded"' % inner)
    lines.append('%suniform token subdivisionScheme = "none"' % inner)

    # Faces split across several materials become materialBind GeomSubsets;
    # the bindings themselves live in the mtl layer.
    material_faces = mesh.material_face_map()
    named = [name for name in material_faces if name]
    if len(named) > 1 or (named and None in material_faces):
        for name in named:
            lines.append("")
            lines.append('%sdef GeomSubset "%s"' % (inner, name))
            lines.append("%s{" % inner)
            lines.append('%suniform token elementType = "face"' % (inner + INDENT))
            lines.append('%suniform token familyName = "materialBind"' % (inner + INDENT))
            lines.append(
                "%sint[] indices = %s" % (inner + INDENT, _int_array(material_faces[name]))
            )
            lines.append("%s}" % inner)
    lines.append("%s}" % pad)
    return lines


# -- material layer ------------------------------------------------------


def write_mtl_layer(path, request):
    asset = request.asset_name
    lines = _layer_header(asset)
    lines.append('def Xform "%s"' % asset)
    lines.append("{")
    lines.append('%sdef Scope "mtl"' % INDENT)
    lines.append("%s{" % INDENT)
    for material in request.materials.values():
        lines.extend(_material_block(asset, material, depth=2))
    lines.append("%s}" % INDENT)

    bindings = _binding_blocks(asset, request)
    if bindings:
        lines.append("")
        lines.extend(bindings)
    lines.append("}")
    return _write(path, lines)


# channel -> (UsdPreviewSurface input, declaration, UsdUVTexture output)
_TEXTURE_CHANNELS = {
    "diffuse": ("diffuseColor", "color3f", "rgb"),
    "roughness": ("roughness", "float", "r"),
    "metallic": ("metallic", "float", "r"),
    "normal": ("normal", "normal3f", "rgb"),
}


def _material_block(asset, material, depth):
    pad = INDENT * depth
    inner = INDENT * (depth + 1)
    shader = INDENT * (depth + 2)
    mtl_path = "/%s/mtl/%s" % (asset, material.name)
    textures = {
        channel: file_path
        for channel, file_path in (getattr(material, "textures", None) or {}).items()
        if channel in _TEXTURE_CHANNELS and file_path
    }

    lines = []
    lines.append('%sdef Material "%s"' % (pad, material.name))
    lines.append("%s{" % pad)
    lines.append(
        "%stoken outputs:surface.connect = <%s/Surface.outputs:surface>" % (inner, mtl_path)
    )
    lines.append("")
    lines.append('%sdef Shader "Surface"' % inner)
    lines.append("%s{" % inner)
    lines.append('%suniform token info:id = "UsdPreviewSurface"' % shader)
    if "diffuse" in textures:
        lines.append(
            "%scolor3f inputs:diffuseColor.connect = <%s/diffuseTexture.outputs:rgb>"
            % (shader, mtl_path)
        )
    else:
        lines.append(
            "%scolor3f inputs:diffuseColor = %s" % (shader, _vec3(material.base_color))
        )
    if "metallic" in textures:
        lines.append(
            "%sfloat inputs:metallic.connect = <%s/metallicTexture.outputs:r>"
            % (shader, mtl_path)
        )
    else:
        lines.append("%sfloat inputs:metallic = %s" % (shader, _num(material.metallic)))
    if "roughness" in textures:
        lines.append(
            "%sfloat inputs:roughness.connect = <%s/roughnessTexture.outputs:r>"
            % (shader, mtl_path)
        )
    else:
        lines.append("%sfloat inputs:roughness = %s" % (shader, _num(material.roughness)))
    if "normal" in textures:
        lines.append(
            "%snormal3f inputs:normal.connect = <%s/normalTexture.outputs:rgb>"
            % (shader, mtl_path)
        )
    lines.append("%stoken outputs:surface" % shader)
    lines.append("%s}" % inner)

    if textures:
        lines.append("")
        lines.append('%sdef Shader "stReader"' % inner)
        lines.append("%s{" % inner)
        lines.append('%suniform token info:id = "UsdPrimvarReader_float2"' % shader)
        lines.append('%sstring inputs:varname = "st"' % shader)
        lines.append("%sfloat2 outputs:result" % shader)
        lines.append("%s}" % inner)
        for channel, file_path in sorted(textures.items()):
            _input, _decl, output = _TEXTURE_CHANNELS[channel]
            lines.append("")
            lines.append('%sdef Shader "%sTexture"' % (inner, channel))
            lines.append("%s{" % inner)
            lines.append('%suniform token info:id = "UsdUVTexture"' % shader)
            lines.append("%sasset inputs:file = @%s@" % (shader, _posix(file_path)))
            lines.append(
                "%sfloat2 inputs:st.connect = <%s/stReader.outputs:result>"
                % (shader, mtl_path)
            )
            lines.append('%stoken inputs:wrapS = "repeat"' % shader)
            lines.append('%stoken inputs:wrapT = "repeat"' % shader)
            if channel == "normal":
                lines.append('%stoken inputs:sourceColorSpace = "raw"' % shader)
                lines.append("%sfloat4 inputs:scale = (2, 2, 2, 1)" % shader)
                lines.append("%sfloat4 inputs:bias = (-1, -1, -1, 0)" % shader)
            elif channel != "diffuse":
                lines.append('%stoken inputs:sourceColorSpace = "raw"' % shader)
            if output == "rgb":
                lines.append("%sfloat3 outputs:rgb" % shader)
            else:
                lines.append("%sfloat outputs:r" % shader)
            lines.append("%s}" % inner)
    lines.append("%s}" % pad)
    return lines


def _binding_blocks(asset, request):
    """`over` hierarchy binding materials onto meshes (or their subsets)."""
    lines = []
    mesh_blocks = []
    for mesh in request.meshes:
        material_faces = mesh.material_face_map()
        named = [name for name in material_faces if name]
        if not named:
            continue
        block = []
        whole_mesh = len(named) == 1 and None not in material_faces
        if whole_mesh:
            block.append('%sover "%s" (' % (INDENT * 2, mesh.name))
            block.append('%sprepend apiSchemas = ["MaterialBindingAPI"]' % (INDENT * 3))
            block.append("%s)" % (INDENT * 2))
            block.append("%s{" % (INDENT * 2))
            block.append(
                "%srel material:binding = </%s/mtl/%s>" % (INDENT * 3, asset, named[0])
            )
            block.append("%s}" % (INDENT * 2))
        else:
            block.append('%sover "%s"' % (INDENT * 2, mesh.name))
            block.append("%s{" % (INDENT * 2))
            for name in named:
                block.append('%sover "%s" (' % (INDENT * 3, name))
                block.append('%sprepend apiSchemas = ["MaterialBindingAPI"]' % (INDENT * 4))
                block.append("%s)" % (INDENT * 3))
                block.append("%s{" % (INDENT * 3))
                block.append(
                    "%srel material:binding = </%s/mtl/%s>" % (INDENT * 4, asset, name)
                )
                block.append("%s}" % (INDENT * 3))
            block.append("%s}" % (INDENT * 2))
        mesh_blocks.append(block)
    if not mesh_blocks:
        return []
    lines.append('%sover "geo"' % INDENT)
    lines.append("%s{" % INDENT)
    for i, block in enumerate(mesh_blocks):
        if i:
            lines.append("")
        lines.extend(block)
    lines.append("%s}" % INDENT)
    return lines


# -- payload layer -------------------------------------------------------


def write_assembly_layer(path, name, references, custom=None):
    """A shot assembly: one Xform referencing published assets.

    ``references`` is a list of (child_name, relative_layer_path) — each
    becomes ``def "child" (references = @layer@)`` under the root prim, so
    the assembly stays live: it follows whatever those layers resolve to.
    """
    lines = _layer_header(name, 1.0, "Y", custom)
    lines.append('def Xform "%s" (' % name)
    lines.append('%skind = "assembly"' % INDENT)
    lines.append(")")
    lines.append("{")
    for child_name, layer in references:
        lines.append('%sdef "%s" (' % (INDENT, child_name))
        lines.append("%sprepend references = @%s@" % (INDENT * 2, _posix(layer)))
        lines.append("%s)" % INDENT)
        lines.append("%s{" % INDENT)
        lines.append("%s}" % INDENT)
    lines.append("}")
    return _write(path, lines)


def write_payload_layer(path, request, geo_layer, mtl_layer):
    """Compose mtl over geo. The mtl reference is listed first so its overs
    win over the geometry layer's opinions."""
    asset = request.asset_name
    lines = _layer_header(
        asset, request.meters_per_unit, request.up_axis,
        time_range=_time_range(request), fps=getattr(request, "fps", None),
    )
    lines.append('def Xform "%s" (' % asset)
    lines.append("%sprepend references = [" % INDENT)
    lines.append("%s@%s@</%s>," % (INDENT * 2, _posix(mtl_layer), asset))
    lines.append("%s@%s@</%s>" % (INDENT * 2, _posix(geo_layer), asset))
    lines.append("%s]" % INDENT)
    lines.append(")")
    lines.append("{")
    lines.append("}")
    return _write(path, lines)


# -- entry layer ---------------------------------------------------------


def write_entry_layer(
    path,
    request,
    variants,
    selected_variant,
    version_label,
    thumbnail=None,
    extents=None,
    custom=None,
):
    """The asset interface. ``variants`` maps variant name -> relative payload
    layer path; each variant carries its payload arc so unloading the payload
    strips all geometry while the interface (bounds, thumbnail) survives."""
    asset = request.asset_name
    lines = _layer_header(asset, request.meters_per_unit, request.up_axis, custom)

    api_schemas = ['"GeomModelAPI"']
    if thumbnail:
        api_schemas.append('"AssetPreviewsAPI"')

    lines.append('def Xform "%s" (' % asset)
    lines.append("%sassetInfo = {" % INDENT)
    lines.append("%sasset identifier = @./%s.usda@" % (INDENT * 2, asset))
    lines.append("%sstring name = %s" % (INDENT * 2, _string(asset)))
    lines.append("%sstring version = %s" % (INDENT * 2, _string(version_label)))
    lines.append("%s}" % INDENT)
    lines.append('%skind = "component"' % INDENT)
    lines.append("%sprepend apiSchemas = [%s]" % (INDENT, ", ".join(api_schemas)))
    lines.append('%svariants = {' % INDENT)
    lines.append('%sstring geo = "%s"' % (INDENT * 2, selected_variant))
    lines.append("%s}" % INDENT)
    lines.append('%sprepend variantSets = "geo"' % INDENT)
    lines.append(")")
    lines.append("{")
    if extents:
        lines.append("%sfloat3[] extentsHint = %s" % (INDENT, _vec3_array(extents)))
    if thumbnail:
        lines.append(
            "%suniform asset previews:thumbnails:default:defaultImage = @%s@"
            % (INDENT, _posix(thumbnail))
        )
    lines.append("")
    lines.append('%svariantSet "geo" = {' % INDENT)
    for name in sorted(variants):
        lines.append('%s"%s" (' % (INDENT * 2, name))
        lines.append("%spayload = @%s@</%s>" % (INDENT * 3, _posix(variants[name]), asset))
        lines.append("%s) {" % (INDENT * 2))
        lines.append("%s}" % (INDENT * 2))
    lines.append("%s}" % INDENT)
    lines.append("}")
    return _write(path, lines)
