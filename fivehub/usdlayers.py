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


def _int_array(values):
    return "[%s]" % ", ".join(str(int(v)) for v in values)


def _string(value):
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return '"%s"' % escaped


def _posix(path):
    return path.replace(os.sep, "/")


def _layer_header(default_prim, meters_per_unit=None, up_axis=None, custom=None):
    lines = ["#usda 1.0", "("]
    lines.append('%sdefaultPrim = "%s"' % (INDENT, default_prim))
    if meters_per_unit is not None:
        lines.append("%smetersPerUnit = %s" % (INDENT, _num(meters_per_unit)))
    if up_axis is not None:
        lines.append('%supAxis = "%s"' % (INDENT, up_axis))
    lines.append("%scustomLayerData = {" % INDENT)
    lines.append('%sstring generator = %s' % (INDENT * 2, _string(GENERATOR)))
    for key, value in (custom or {}).items():
        lines.append("%sstring %s = %s" % (INDENT * 2, key, _string(value)))
    lines.append("%s}" % INDENT)
    lines.append(")")
    lines.append("")
    return lines


def _write(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


# -- geometry layer ------------------------------------------------------


def write_geo_layer(path, request):
    asset = request.asset_name
    lines = _layer_header(asset, request.meters_per_unit, request.up_axis)
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
    lines.append("%spoint3f[] points = %s" % (inner, _vec3_array(mesh.points)))
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


def _material_block(asset, material, depth):
    pad = INDENT * depth
    inner = INDENT * (depth + 1)
    shader = INDENT * (depth + 2)
    mtl_path = "/%s/mtl/%s" % (asset, material.name)
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
    lines.append("%scolor3f inputs:diffuseColor = %s" % (shader, _vec3(material.base_color)))
    lines.append("%sfloat inputs:metallic = %s" % (shader, _num(material.metallic)))
    lines.append("%sfloat inputs:roughness = %s" % (shader, _num(material.roughness)))
    lines.append("%stoken outputs:surface" % shader)
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


def write_payload_layer(path, request, geo_layer, mtl_layer):
    """Compose mtl over geo. The mtl reference is listed first so its overs
    win over the geometry layer's opinions."""
    asset = request.asset_name
    lines = _layer_header(asset, request.meters_per_unit, request.up_axis)
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
