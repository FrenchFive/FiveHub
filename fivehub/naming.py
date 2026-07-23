"""Naming rules and sanitizers.

Asset names are the public face of the pipeline: they become prim paths,
file names and reference targets, so they must be valid USD identifiers.
The studio style on top of that is UpperCamelCase for assets and an ``M_``
prefix for materials.
"""

import re

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ASSET_STYLE_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
MATERIAL_PREFIX = "M_"

RESERVED_NAMES = {"geo", "mtl", "default", "none", "class"}


def is_identifier(name):
    return bool(name) and bool(IDENTIFIER_RE.match(name))


def is_asset_style(name):
    return bool(name) and bool(ASSET_STYLE_RE.match(name))


def make_identifier(text, fallback="unnamed"):
    """Force arbitrary text into a valid USD identifier."""
    text = re.sub(r"[^A-Za-z0-9_]", "_", str(text or ""))
    text = re.sub(r"_+", "_", text).strip("_") or fallback
    if text[0].isdigit():
        text = "_" + text
    return text


def make_material_name(text):
    name = make_identifier(text, fallback="material")
    if not name.startswith(MATERIAL_PREFIX):
        name = MATERIAL_PREFIX + name
    return name


def asset_name_errors(name):
    """All hard errors that make a name unusable as an asset name."""
    errors = []
    if not name:
        errors.append("asset name is empty")
        return errors
    if not is_identifier(name):
        errors.append(
            "%r is not a valid USD identifier (letters, digits and underscores, "
            "must not start with a digit)" % name
        )
    if name.lower() in RESERVED_NAMES:
        errors.append("%r is a reserved name" % name)
    return errors


def asset_name_warnings(name):
    warnings = []
    if name and is_identifier(name) and not is_asset_style(name):
        warnings.append(
            "%r does not follow the UpperCamelCase asset style (e.g. WoodenCrate)" % name
        )
    return warnings
