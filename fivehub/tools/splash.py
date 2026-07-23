"""The FIVE HUB Houdini splash screen.

Generates the launch artwork Houdini shows when the pipeline is installed
(the package points HOUDINI_SPLASH_FILE at the output): goop metaballs in
the house style, FIVE HUB in Satoshi Black, and the facts of the session —
FiveHub version, Houdini build, license type, signed-in artist.

Three ways to regenerate:

    python -m fivehub.cli splash --houdini 20.0.345 --license FX
    FIVE HUB > Pipeline Tools > "Regenerate FiveHub Splash"   (reads the
        real build + license from the running session)
    fivehub.tools.splash.render(...) from any script

Requires Pillow (pip install pillow) and the Satoshi fonts — drop them in
assets/fonts/ (free at fontshare.com; see assets/fonts/README.md). Without
Satoshi it falls back to DejaVu so the pipeline never blocks on a font.
"""

import math
import os

from . import cli_command, houdini_tool
from .. import __version__, config

WIDTH, HEIGHT = 1200, 675

INK = (11, 11, 12)
WASH = (245, 245, 247)
GOOP = (228, 228, 232)
GRAY = (110, 110, 115)

# The goop: (x, y, radius) in a 1200x675 frame, one field, merged edges.
# Centers sit far enough apart that lobes stay readable, close enough that
# liquid necks form between them.
BLOBS = [
    (905, 175, 118), (1105, 300, 96), (872, 400, 92),
    (1035, 505, 74), (1180, 130, 62), (752, 292, 52), (935, 585, 38),
]
INK_BLOBS = [(688, 478, 30), (645, 525, 17), (728, 541, 12)]
GOOP_THRESHOLD = 1.22


def _font_dirs():
    dirs = [os.environ.get("FIVEHUB_FONTS", "")]
    dirs.append(os.path.join(config.repo_root(), "assets", "fonts"))
    dirs.append(os.path.join(os.path.expanduser("~"), ".fivehub", "fonts"))
    return [d for d in dirs if d and os.path.isdir(d)]


def _find_font(*keywords):
    for directory in _font_dirs():
        for base, _dirs, files in os.walk(directory):
            for name in sorted(files):
                lowered = name.lower()
                if not lowered.endswith((".otf", ".ttf")):
                    continue
                if "italic" in lowered:
                    continue
                if all(keyword.lower() in lowered for keyword in keywords):
                    return os.path.join(base, name)
    return None


def _load_fonts(sizes):
    """{'black': font, 'medium': ..., 'regular': ...} at requested sizes,
    Satoshi first, DejaVu as the never-fail fallback."""
    from PIL import ImageFont

    fallback_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    fallback = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    paths = {
        "black": _find_font("satoshi", "black") or fallback_bold,
        "medium": _find_font("satoshi", "medium") or fallback,
        "regular": _find_font("satoshi", "regular") or fallback,
    }
    fonts = {}
    for role, size in sizes.items():
        base_role = role.split("@")[0]
        try:
            fonts[role] = ImageFont.truetype(paths[base_role], size)
        except OSError:
            fonts[role] = ImageFont.load_default()
    return fonts, paths


def _field(x, y, blobs):
    total = 0.0
    for bx, by, radius in blobs:
        dx, dy = x - bx, y - by
        d2 = dx * dx + dy * dy
        if d2 < 1.0:
            d2 = 1.0
        total += (radius * radius) / d2
    return total


def _goop_layer(width, height, blobs, threshold=1.0, edge=0.08):
    """Grayscale metaball mask with a smooth (anti-aliased) edge."""
    from PIL import Image

    scale_x = width / float(WIDTH)
    scale_y = height / float(HEIGHT)
    scaled = [(bx * scale_x, by * scale_y, r * scale_x) for bx, by, r in blobs]
    mask = bytearray(width * height)
    low, high = threshold - edge, threshold + edge
    index = 0
    for y in range(height):
        for x in range(width):
            value = _field(x, y, scaled)
            if value <= low:
                index += 1
                continue
            if value >= high:
                mask[index] = 255
            else:
                t = (value - low) / (high - low)
                mask[index] = int(255 * t * t * (3 - 2 * t))  # smoothstep
            index += 1
    return Image.frombytes("L", (width, height), bytes(mask))


def _tracked_text(draw, xy, text, font, fill, tracking=0):
    x, y = xy
    for character in text:
        draw.text((x, y), character, font=font, fill=fill)
        box = draw.textbbox((0, 0), character, font=font)
        x += (box[2] - box[0]) + tracking
    return x


def _pill(draw, x, y, text, font, filled=False, pad_x=22, height=46):
    box = draw.textbbox((0, 0), text, font=font)
    text_width = box[2] - box[0]
    width = text_width + pad_x * 2
    radius = height // 2
    if filled:
        draw.rounded_rectangle((x, y, x + width, y + height), radius, fill=INK)
        color = (255, 255, 255)
    else:
        draw.rounded_rectangle(
            (x, y, x + width, y + height), radius, outline=(0, 0, 0, 60), width=2
        )
        color = INK
    draw.text(
        (x + pad_x, y + (height - (box[3] - box[1])) / 2 - box[1]),
        text, font=font, fill=color,
    )
    return x + width


def render(out_path, houdini_version="", license_type="", user="", hub="",
           width=WIDTH, height=HEIGHT):
    """Render the splash PNG. Empty facts are simply left off."""
    from PIL import Image, ImageDraw

    fonts, font_paths = _load_fonts(
        {"black": int(height * 0.215), "medium": int(height * 0.038),
         "regular@pill": int(height * 0.030), "regular@small": int(height * 0.024)}
    )
    scale = height / float(HEIGHT)

    image = Image.new("RGB", (width, height), WASH)

    goop = Image.new("RGB", (width, height), GOOP)
    image.paste(goop, (0, 0), _goop_layer(width, height, BLOBS, GOOP_THRESHOLD))
    ink_goop = Image.new("RGB", (width, height), INK)
    image.paste(ink_goop, (0, 0), _goop_layer(width, height, INK_BLOBS))

    draw = ImageDraw.Draw(image)
    margin = int(90 * scale)

    # FIVE HUB — always Satoshi Black.
    title_y = int(150 * scale)
    draw.text((margin - int(8 * scale), title_y), "FIVE HUB",
              font=fonts["black"], fill=INK)

    _tracked_text(
        draw, (margin, int(365 * scale)), "PIPELINE FOR HOUDINI",
        fonts["medium"], GRAY, tracking=int(9 * scale),
    )

    # The facts, as pills. License type gets the solid pill.
    pill_font = fonts["regular@pill"]
    pill_y = int(520 * scale)
    x = margin
    x = _pill(draw, x, pill_y, "FIVEHUB %s" % __version__, pill_font) + int(14 * scale)
    if houdini_version:
        x = _pill(draw, x, pill_y, "HOUDINI %s" % houdini_version,
                  pill_font) + int(14 * scale)
    if license_type:
        _pill(draw, x, pill_y, license_type.upper(), pill_font, filled=True)

    footer = "validated usd publishes · versioned scenes · signed work"
    if user:
        footer = "signed in — %s · %s" % (user, footer)
    if hub:
        footer += " · %s" % hub
    draw.text((margin, int(600 * scale)), footer,
              font=fonts["regular@small"], fill=GRAY)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    image.save(out_path, "PNG")
    return {"path": out_path, "size": [width, height],
            "satoshi": "satoshi" in os.path.basename(font_paths["black"]).lower()}


def default_output():
    return os.path.join(config.repo_root(), "houdini", "splash", "fivehub_splash.png")


def _detect_houdini_version():
    hfs = os.environ.get("HFS", "")
    base = os.path.basename(hfs.rstrip("/\\"))
    return base.replace("hfs", "") if base.startswith("hfs") else ""


def _configure(parser):
    parser.add_argument("--houdini", default="", help="e.g. 20.0.345 (auto from $HFS)")
    parser.add_argument("--license", default="", help="FX / CORE / INDIE / NC / ...")
    parser.add_argument("--user", default="", help="artist name shown as signed in")
    parser.add_argument("--hub", default="", help="hub path shown in the footer")
    parser.add_argument("--out", default="", help="output PNG (default: package splash)")


@cli_command("splash", "regenerate the FIVE HUB Houdini splash screen", _configure)
def run(_root, args):
    try:
        import PIL  # noqa: F401
    except ImportError:
        raise SystemExit("the splash generator needs Pillow: pip install pillow")
    return render(
        args.out or default_output(),
        houdini_version=args.houdini or _detect_houdini_version(),
        license_type=args.license,
        user=args.user,
        hub=args.hub,
    )


@houdini_tool("Regenerate FiveHub Splash")
def regenerate_from_session():
    """Bake the *running* session's truth into the splash: real build
    number and real license category."""
    import hou

    try:
        import PIL  # noqa: F401
    except ImportError:
        hou.ui.displayMessage(
            "The splash generator needs Pillow in Houdini's python:\n"
            "hython -m pip install pillow",
            severity=hou.severityType.Error, title="FIVE HUB",
        )
        return None

    category = hou.licenseCategory()
    license_map = {
        hou.licenseCategoryType.Commercial: "FX",
        hou.licenseCategoryType.Indie: "INDIE",
        hou.licenseCategoryType.Education: "EDU",
        hou.licenseCategoryType.ApprenticeHD: "NC",
        hou.licenseCategoryType.Apprentice: "NC",
    }
    from ..user import get_user

    result = render(
        default_output(),
        houdini_version=hou.applicationVersionString(),
        license_type=license_map.get(category, str(category).split(".")[-1].upper()),
        user=get_user(),
        hub=config.ensure_hub(),
    )
    hou.ui.displayMessage(
        "Splash regenerated — it shows on the next Houdini launch.\n%s"
        % result["path"],
        title="FIVE HUB",
    )
    return result
